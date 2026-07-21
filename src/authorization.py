# SPDX-License-Identifier: AGPL-3.0-or-later
"""Signed, target-exact authorization receipts for Canvas mutations.

Execution-plan approval and Canvas mutation authority are deliberately
different capabilities.  A receipt is tamper-evident, short-lived, bound to a
Codex session, and contains no wildcard action or target.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import os
import secrets
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

from .run_state import atomic_write_json


ROOT = Path(__file__).resolve().parent.parent
RECEIPT_VERSION = 1
MUTATION_ACTIONS = frozenset(
    {
        "assignment.submit_text",
        "assignment.submit_url",
        "assignment.upload_init",
        "assignment.upload_blob",
        "assignment.submit_files",
        "quiz.start",
        "quiz.retake",
        "quiz.answer",
        "quiz.event",
        "quiz.complete",
    }
)


class AuthorizationDenied(PermissionError):
    """The requested Canvas mutation is outside a valid signed receipt."""


def canonical_canvas_origin(value: str) -> str:
    raw = (value or "").strip()
    if "://" not in raw:
        raw = "https://" + raw
    parsed = urlparse(raw)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise AuthorizationDenied("Canvas origin must be an http(s) origin")
    if parsed.username or parsed.password:
        raise AuthorizationDenied("Canvas origin must not contain credentials")
    host = parsed.hostname.lower()
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    default_port = 443 if parsed.scheme.lower() == "https" else 80
    port = parsed.port
    authority = host if port in (None, default_port) else f"{host}:{port}"
    return f"{parsed.scheme.lower()}://{authority}"


def _is_exact_loopback(origin: str) -> bool:
    host = (urlparse(origin).hostname or "").lower()
    return host in {"localhost", "127.0.0.1", "::1"}


def mutation_authorization_enforced(environ: Mapping[str, str] | None = None) -> bool:
    env = os.environ if environ is None else environ
    return bool(env.get("CODEX_THREAD_ID")) or env.get("CANVAS_ENFORCE_MUTATION_AUTH", "").lower() in {
        "1", "true", "yes", "on"
    }


def current_authorization_session(environ: Mapping[str, str] | None = None) -> str | None:
    env = os.environ if environ is None else environ
    return env.get("CODEX_THREAD_ID") or env.get("CODEX_SESSION_ID")


def _default_key_path() -> Path:
    configured = os.environ.get("CANVAS_AUTHORIZATION_KEY_PATH")
    return Path(configured) if configured else ROOT / "_private" / "authorization-signing.key"


def _default_usage_path() -> Path:
    configured = os.environ.get("CANVAS_AUTHORIZATION_USAGE_PATH")
    if configured:
        return Path(configured)
    return _default_key_path().with_name("authorization-usage.json")


@contextmanager
def _usage_lock(path: Path):
    """Serialize local receipt-usage updates with a short exclusive lock."""

    lock_path = path.with_name(path.name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor: int | None = None
    deadline = time.monotonic() + 5.0
    while descriptor is None:
        try:
            descriptor = os.open(
                lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY
            )
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise AuthorizationDenied("authorization usage ledger is busy")
            time.sleep(0.02)
    try:
        os.write(descriptor, str(os.getpid()).encode("ascii"))
        yield
    finally:
        os.close(descriptor)
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass


def _load_usage(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AuthorizationDenied("authorization usage ledger is unreadable") from exc
    if not isinstance(data, dict):
        raise AuthorizationDenied("authorization usage ledger must be a JSON object")
    return data


def track_authorization_usage(
    receipt: Mapping[str, Any],
    *,
    action: str,
    record: bool,
    usage_path: Path | str | None = None,
) -> dict[str, Any]:
    """Check replay state and optionally record one exact mutation attempt.

    Upload and quiz workflows legitimately make several writes under one
    receipt.  The ledger therefore tracks every action and consumes the whole
    receipt at the terminal assignment submit or final quiz completion.  A
    receipt containing ``quiz.retake`` allows two completion calls; otherwise
    the first completion is terminal.
    """

    path = Path(usage_path) if usage_path is not None else _default_usage_path()
    receipt_id = receipt.get("receipt_id")
    if not isinstance(receipt_id, str) or not receipt_id:
        raise AuthorizationDenied("authorization receipt has no receipt_id")
    with _usage_lock(path):
        usage = _load_usage(path)
        raw_entry = usage.get(receipt_id) or {}
        if not isinstance(raw_entry, Mapping):
            raise AuthorizationDenied("authorization usage entry is invalid")
        entry = dict(raw_entry)
        if entry.get("terminal_at"):
            raise AuthorizationDenied("authorization receipt has already been consumed")
        counts = entry.get("action_counts") or {}
        if not isinstance(counts, Mapping):
            raise AuthorizationDenied("authorization action counters are invalid")
        counts = {str(key): int(value) for key, value in counts.items()}
        if action == "quiz.start" and counts.get(action, 0) >= 1:
            raise AuthorizationDenied("quiz.start authorization was already used")
        if action == "quiz.retake" and counts.get(action, 0) >= 1:
            raise AuthorizationDenied("quiz.retake authorization was already used")
        allows_retake = "quiz.retake" in (receipt.get("actions") or [])
        completion_limit = 2 if allows_retake else 1
        if action == "quiz.complete" and counts.get(action, 0) >= completion_limit:
            raise AuthorizationDenied("quiz.complete authorization was already consumed")

        if record:
            now = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
            counts[action] = counts.get(action, 0) + 1
            entry.update(
                {
                    "receipt_id": receipt_id,
                    "canvas_origin": receipt.get("canvas_origin"),
                    "course_id": receipt.get("course_id"),
                    "target_type": receipt.get("target_type"),
                    "target_id": receipt.get("target_id"),
                    "first_used_at": entry.get("first_used_at") or now,
                    "last_used_at": now,
                    "action_counts": counts,
                }
            )
            terminal = action in {
                "assignment.submit_text",
                "assignment.submit_url",
                "assignment.submit_files",
            } or (
                action == "quiz.complete"
                and (
                    not allows_retake
                    or counts.get("quiz.retake", 0) >= 1
                    or counts[action] >= completion_limit
                )
            )
            if terminal:
                entry["terminal_at"] = now
                entry["terminal_action"] = action
            usage[receipt_id] = entry
            atomic_write_json(path, usage)
        return entry


def authorization_usage_status(
    receipt_or_id: Mapping[str, Any] | str,
    *,
    usage_path: Path | str | None = None,
) -> dict[str, Any] | None:
    path = Path(usage_path) if usage_path is not None else _default_usage_path()
    receipt_id = (
        str(receipt_or_id.get("receipt_id"))
        if isinstance(receipt_or_id, Mapping)
        else str(receipt_or_id)
    )
    with _usage_lock(path):
        entry = _load_usage(path).get(receipt_id)
    return dict(entry) if isinstance(entry, Mapping) else None


def finalize_authorization_usage(
    receipt: Mapping[str, Any],
    *,
    reason: str,
    usage_path: Path | str | None = None,
) -> dict[str, Any]:
    """Consume a multi-attempt quiz receipt after its final chosen attempt.

    A receipt that includes ``quiz.retake`` cannot be consumed automatically
    by the first ``quiz.complete`` call because the caller may legitimately
    start a second attempt.  Once the caller has read the score and chosen to
    keep the completed attempt, it must close the receipt explicitly.  The
    close is accepted only for the exact receipt already recorded by a real
    ``quiz.complete`` mutation.
    """

    path = Path(usage_path) if usage_path is not None else _default_usage_path()
    receipt_id = receipt.get("receipt_id")
    if not isinstance(receipt_id, str) or not receipt_id:
        raise AuthorizationDenied("authorization receipt has no receipt_id")
    if receipt.get("target_type") != "quiz":
        raise AuthorizationDenied("only a quiz receipt supports explicit finalization")
    if not isinstance(reason, str) or not reason.strip():
        raise AuthorizationDenied("authorization finalization requires a reason")

    with _usage_lock(path):
        usage = _load_usage(path)
        raw_entry = usage.get(receipt_id)
        if not isinstance(raw_entry, Mapping):
            raise AuthorizationDenied("authorization receipt has no recorded mutation usage")
        entry = dict(raw_entry)
        for field in ("canvas_origin", "course_id", "target_type", "target_id"):
            if str(entry.get(field)) != str(receipt.get(field)):
                raise AuthorizationDenied(
                    f"authorization usage entry does not match receipt {field}"
                )
        counts = entry.get("action_counts")
        if not isinstance(counts, Mapping) or int(counts.get("quiz.complete", 0)) < 1:
            raise AuthorizationDenied(
                "quiz authorization cannot be finalized before quiz.complete is recorded"
            )
        if entry.get("terminal_at"):
            return entry
        now = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
        entry["terminal_at"] = now
        entry["terminal_action"] = "quiz.complete"
        entry["finalization_reason"] = reason.strip()[:240]
        usage[receipt_id] = entry
        atomic_write_json(path, usage)
        return entry


def load_signing_key(
    key_path: Path | str | None = None,
    *,
    create: bool = False,
) -> bytes:
    path = Path(key_path) if key_path is not None else _default_key_path()
    if path.exists():
        try:
            value = bytes.fromhex(path.read_text(encoding="ascii").strip())
        except (OSError, ValueError) as exc:
            raise AuthorizationDenied("authorization signing key is unreadable") from exc
        if len(value) < 32:
            raise AuthorizationDenied("authorization signing key is too short")
        return value
    if not create:
        raise AuthorizationDenied("authorization signing key is missing")
    path.parent.mkdir(parents=True, exist_ok=True)
    value = secrets.token_bytes(32)
    try:
        with path.open("x", encoding="ascii", newline="\n") as handle:
            handle.write(value.hex() + "\n")
    except FileExistsError:
        return load_signing_key(path, create=False)
    return value


def _key_bytes(signing_key: bytes | str | None, key_path: Path | str | None, *, create: bool) -> bytes:
    if signing_key is not None:
        value = signing_key.encode("utf-8") if isinstance(signing_key, str) else signing_key
        if len(value) < 32:
            raise AuthorizationDenied("injected signing key must contain at least 32 bytes")
        return value
    return load_signing_key(key_path, create=create)


def _iso(value: dt.datetime | str) -> str:
    if isinstance(value, str):
        parsed = _parse_time(value)
    elif isinstance(value, dt.datetime):
        parsed = value
    else:
        raise AuthorizationDenied("receipt timestamp must be ISO text or datetime")
    if parsed.tzinfo is None:
        raise AuthorizationDenied("receipt timestamp must include a timezone")
    return parsed.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_time(value: Any) -> dt.datetime:
    if not isinstance(value, str) or not value.strip():
        raise AuthorizationDenied("receipt timestamp is missing")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AuthorizationDenied("receipt timestamp is invalid") from exc
    if parsed.tzinfo is None:
        raise AuthorizationDenied("receipt timestamp must include a timezone")
    return parsed.astimezone(dt.timezone.utc)


def _canonical_payload(receipt: Mapping[str, Any]) -> bytes:
    unsigned = {key: value for key, value in receipt.items() if key != "signature"}
    return json.dumps(
        unsigned,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _signature(receipt: Mapping[str, Any], key: bytes) -> str:
    return hmac.new(key, _canonical_payload(receipt), hashlib.sha256).hexdigest()


def _authority_reference(value: str | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(value, str):
        if not value.strip():
            raise AuthorizationDenied("authority_reference must identify verified user authority")
        payload: Any = value.strip()
        label = value.strip()[:120]
    elif isinstance(value, Mapping) and value:
        payload = dict(value)
        label = str(payload.get("delegation_id") or payload.get("approval_id") or "structured-authority")[:120]
    else:
        raise AuthorizationDenied("authority_reference must identify verified user authority")
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    return {"label": label, "sha256": digest}


def create_authorization_receipt(
    *,
    canvas_origin: str,
    course_id: str | int,
    target_type: str,
    target_id: str | int,
    actions: Sequence[str],
    session_id: str,
    expires_at: dt.datetime | str,
    authority_reference: str | Mapping[str, Any],
    synthetic_qa: bool = False,
    issued_at: dt.datetime | str | None = None,
    output_path: Path | str | None = None,
    signing_key: bytes | str | None = None,
    key_path: Path | str | None = None,
) -> dict[str, Any]:
    """Create a signed receipt after the caller proves user/delegated authority.

    The caller owns validation of ``authority_reference`` (for example a
    durable cron delegation).  This function enforces the receipt's mechanical
    scope; it does not turn prose, a plan approval, or an environment toggle
    into authority.
    """

    origin = canonical_canvas_origin(canvas_origin)
    if target_type not in {"assignment", "quiz", "automation_template"}:
        raise AuthorizationDenied("target_type must be assignment, quiz, or automation_template")
    if not str(course_id).strip() or not str(target_id).strip():
        raise AuthorizationDenied("course_id and target_id are required")
    if not isinstance(session_id, str) or not session_id.strip():
        raise AuthorizationDenied("session_id is required")
    exact_actions = sorted(set(actions))
    if not exact_actions or any(action not in MUTATION_ACTIONS for action in exact_actions):
        raise AuthorizationDenied("receipt actions must be known exact mutation actions")
    prefix = f"{target_type}."
    if target_type in {"assignment", "quiz"} and any(
        not action.startswith(prefix) for action in exact_actions
    ):
        raise AuthorizationDenied("receipt actions must match target_type")
    if target_type == "automation_template" and any(
        not action.startswith(("assignment.", "quiz.")) for action in exact_actions
    ):
        raise AuthorizationDenied("automation template may delegate only exact assignment/quiz actions")
    if synthetic_qa and target_type == "automation_template":
        raise AuthorizationDenied("synthetic-QA receipts cannot create durable automation authority")
    if synthetic_qa and not _is_exact_loopback(origin):
        raise AuthorizationDenied("synthetic-QA receipts are restricted to an exact loopback origin")

    now = dt.datetime.now(dt.timezone.utc) if issued_at is None else _parse_time(_iso(issued_at))
    expiry = _parse_time(_iso(expires_at))
    if expiry <= now:
        raise AuthorizationDenied("authorization receipt must expire in the future")

    receipt: dict[str, Any] = {
        "version": RECEIPT_VERSION,
        "receipt_id": str(uuid.uuid4()),
        "issued_at": _iso(now),
        "expires_at": _iso(expiry),
        "canvas_origin": origin,
        "course_id": str(course_id),
        "target_type": target_type,
        "target_id": str(target_id),
        "actions": exact_actions,
        "session_id": session_id.strip(),
        "synthetic_qa": bool(synthetic_qa),
        "authority_reference": _authority_reference(authority_reference),
        "nonce": secrets.token_hex(16),
    }
    key = _key_bytes(signing_key, key_path, create=True)
    receipt["signature"] = _signature(receipt, key)
    if output_path is not None:
        write_authorization_receipt(output_path, receipt)
    return receipt


def create_delegated_authorization_receipt(
    parent_receipt_or_path: Mapping[str, Any] | Path | str,
    *,
    target_type: str,
    target_id: str | int,
    actions: Sequence[str],
    session_id: str,
    expires_at: dt.datetime | str,
    output_path: Path | str | None = None,
    signing_key: bytes | str | None = None,
    key_path: Path | str | None = None,
) -> dict[str, Any]:
    """Mint one short child receipt mechanically bounded by durable authority."""

    parent = _coerce_receipt(parent_receipt_or_path)
    if parent.get("target_type") != "automation_template":
        raise AuthorizationDenied("delegated receipt requires automation_template authority")
    exact_actions = sorted(set(actions))
    if not exact_actions:
        raise AuthorizationDenied("delegated receipt requires exact actions")
    for action in exact_actions:
        validate_authorization_receipt(
            parent,
            canvas_origin=str(parent.get("canvas_origin") or ""),
            course_id=str(parent.get("course_id") or ""),
            target_type="automation_template",
            target_id=str(parent.get("target_id") or ""),
            action=action,
            session_id=None,
            signing_key=signing_key,
            key_path=key_path,
        )
    child_expiry = _parse_time(_iso(expires_at))
    if child_expiry > _parse_time(parent.get("expires_at")):
        raise AuthorizationDenied("delegated receipt cannot outlive its parent")
    expected_prefix = f"{target_type}."
    if target_type not in {"assignment", "quiz"} or any(
        not action.startswith(expected_prefix) for action in exact_actions
    ):
        raise AuthorizationDenied("delegated actions must match the concrete target type")
    return create_authorization_receipt(
        canvas_origin=str(parent["canvas_origin"]),
        course_id=str(parent["course_id"]),
        target_type=target_type,
        target_id=target_id,
        actions=exact_actions,
        session_id=session_id,
        expires_at=child_expiry,
        authority_reference={
            "delegation_id": parent["receipt_id"],
            "automation_template": parent["target_id"],
        },
        output_path=output_path,
        signing_key=signing_key,
        key_path=key_path,
    )


def write_authorization_receipt(path: Path | str, receipt: Mapping[str, Any]) -> Path:
    return atomic_write_json(path, dict(receipt))


def load_authorization_receipt(path: Path | str) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AuthorizationDenied("authorization receipt cannot be loaded") from exc
    if not isinstance(data, dict):
        raise AuthorizationDenied("authorization receipt must be a JSON object")
    return data


def _coerce_receipt(receipt_or_path: Mapping[str, Any] | Path | str) -> dict[str, Any]:
    if isinstance(receipt_or_path, Mapping):
        return dict(receipt_or_path)
    return load_authorization_receipt(receipt_or_path)


def validate_authorization_receipt(
    receipt_or_path: Mapping[str, Any] | Path | str,
    *,
    canvas_origin: str,
    course_id: str | int,
    target_type: str,
    target_id: str | int,
    action: str,
    session_id: str | None = None,
    now: dt.datetime | None = None,
    signing_key: bytes | str | None = None,
    key_path: Path | str | None = None,
) -> dict[str, Any]:
    receipt = _coerce_receipt(receipt_or_path)
    if receipt.get("version") != RECEIPT_VERSION:
        raise AuthorizationDenied("authorization receipt version is unsupported")
    key = _key_bytes(signing_key, key_path, create=False)
    supplied_signature = receipt.get("signature")
    if not isinstance(supplied_signature, str) or not hmac.compare_digest(
        supplied_signature, _signature(receipt, key)
    ):
        raise AuthorizationDenied("authorization receipt signature is invalid")

    expected_origin = canonical_canvas_origin(canvas_origin)
    if receipt.get("canvas_origin") != expected_origin:
        raise AuthorizationDenied("authorization receipt Canvas origin does not match")
    if str(receipt.get("course_id")) != str(course_id):
        raise AuthorizationDenied("authorization receipt course does not match")
    if receipt.get("target_type") != target_type or str(receipt.get("target_id")) != str(target_id):
        raise AuthorizationDenied("authorization receipt target does not match")
    actions = receipt.get("actions")
    if not isinstance(actions, list) or action not in actions:
        raise AuthorizationDenied("authorization receipt does not allow this exact action")
    if session_id is not None and receipt.get("session_id") != session_id:
        raise AuthorizationDenied("authorization receipt session does not match")

    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=dt.timezone.utc)
    if current.astimezone(dt.timezone.utc) >= _parse_time(receipt.get("expires_at")):
        raise AuthorizationDenied("authorization receipt has expired")
    issued = _parse_time(receipt.get("issued_at"))
    if issued > current.astimezone(dt.timezone.utc) + dt.timedelta(minutes=2):
        raise AuthorizationDenied("authorization receipt was issued in the future")
    if receipt.get("synthetic_qa"):
        if not _is_exact_loopback(expected_origin) or receipt.get("canvas_origin") != expected_origin:
            raise AuthorizationDenied("synthetic-QA authorization is not valid for this origin")
    return receipt


def require_mutation_authorization(
    receipt_or_path: Mapping[str, Any] | Path | str | None,
    *,
    canvas_origin: str,
    course_id: str | int,
    target_type: str,
    target_id: str | int,
    action: str,
    session_id: str | None = None,
    track_usage: bool = False,
) -> dict[str, Any] | None:
    """Enforce automatically in Codex, and validate any supplied receipt."""

    enforced = mutation_authorization_enforced()
    if receipt_or_path is None:
        if enforced:
            raise AuthorizationDenied("Canvas mutation requires a signed authorization receipt")
        return None
    exact_session = session_id
    if enforced and exact_session is None:
        exact_session = current_authorization_session()
        if not exact_session:
            raise AuthorizationDenied("Codex mutation enforcement requires a session identifier")
    receipt = validate_authorization_receipt(
        receipt_or_path,
        canvas_origin=canvas_origin,
        course_id=course_id,
        target_type=target_type,
        target_id=target_id,
        action=action,
        session_id=exact_session,
    )
    track_authorization_usage(receipt, action=action, record=track_usage)
    return receipt
