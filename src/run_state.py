# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared Canvas Pilot run-state contracts.

This module is the single runtime authority for ``plan.json``, per-assignment
``result.json`` files, and ``runs/_processed.json``.  Skills, framework code,
and Codex hooks should call these helpers instead of carrying local status
enums or ad-hoc JSON writes.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping, MutableMapping


CANONICAL_STATUSES = frozenset({"draft_ready", "submitted", "skipped", "error"})
VALID_STATUSES = CANONICAL_STATUSES  # compatibility name for hook callers
PLAN_DECISIONS = frozenset({"approve", "defer"})
_ID_COMPONENT = re.compile(r"[^A-Za-z0-9_.-]+")
_CANONICAL_SKILL = re.compile(r"^canvas-[a-z0-9][a-z0-9-]*$")
_PLACEHOLDER = re.compile(
    r"UNFILLED_SKELETON|\[(?:answer\s+needed|placeholder|todo|insert[^\]]*)\]",
    re.IGNORECASE,
)
_TEXT_DRAFT_SUFFIXES = frozenset(
    {".txt", ".md", ".py", ".json", ".html", ".htm", ".csv", ".tex", ".java", ".js", ".ts", ".rs", ".go", ".c", ".cpp"}
)


class RunStateError(ValueError):
    """A run-state document violates the shared contract."""


def _number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _nonempty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _resolved_path(value: str, root: Path | None) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute() and root is not None:
        candidate = root / candidate
    return candidate


def _stable_id_component(value: str | int) -> str:
    text = _ID_COMPONENT.sub("-", str(value).strip()).strip("-.")
    if not text:
        raise RunStateError("course_id and assignment_id must contain a stable identifier")
    return text[:96]


def stable_work_dir(
    run_dir: Path | str,
    course_id: str | int,
    assignment_id: str | int,
) -> Path:
    """Return the single ID-based work directory used by skills and guards."""

    return Path(run_dir) / (
        f"course-{_stable_id_component(course_id)}__"
        f"assignment-{_stable_id_component(assignment_id)}"
    )


def _parse_aware_time(value: Any, field: str) -> dt.datetime:
    if not _nonempty_text(value):
        raise RunStateError(f"plan requires timezone-aware {field}")
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise RunStateError(f"plan {field} is not valid ISO time") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RunStateError(f"plan {field} must include a timezone")
    return parsed.astimezone(dt.timezone.utc)


def _substantive_draft_path(value: str, root: Path | None) -> Path:
    path = _resolved_path(value, root)
    if not path.exists():
        raise RunStateError(f"draft_path does not exist: {value}")
    candidates: list[Path]
    if path.is_file():
        candidates = [path]
    elif path.is_dir():
        candidates = [candidate for candidate in path.rglob("*") if candidate.is_file()]
    else:
        raise RunStateError(f"draft_path is not a regular file or directory: {value}")
    if not candidates or not any(candidate.stat().st_size > 0 for candidate in candidates):
        raise RunStateError("draft_path must contain a non-empty substantive artifact")
    for candidate in candidates:
        if candidate.stat().st_size <= 0 or candidate.suffix.lower() not in _TEXT_DRAFT_SUFFIXES:
            continue
        try:
            text = candidate.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeError):
            continue
        match = _PLACEHOLDER.search(text)
        if match:
            raise RunStateError(
                f"draft_path contains unresolved placeholder/sentinel {match.group(0)!r}"
            )
    return path


def validate_verification_log(path: Path | str) -> Path:
    verification = Path(path)
    if not verification.is_file() or verification.stat().st_size <= 0:
        raise RunStateError("draft_ready/submitted draft requires a non-empty verification.log")
    try:
        lines = verification.read_text(encoding="utf-8", errors="strict").splitlines()
    except (OSError, UnicodeError) as exc:
        raise RunStateError("verification.log is unreadable") from exc
    normalized = [line.strip() for line in lines if line.strip()]
    failures = [line for line in normalized if re.match(r"^FAIL(?:\s*\||\b)", line, re.IGNORECASE)]
    passes = [line for line in normalized if re.match(r"^PASS(?:\s*\||\b)", line, re.IGNORECASE)]
    if failures:
        raise RunStateError(f"verification.log contains FAIL evidence: {failures[0]}")
    if not passes:
        raise RunStateError("verification.log has no PASS evidence")
    return verification


def _verification_path(
    result: Mapping[str, Any],
    *,
    root: Path | None,
    work_dir: Path | None,
    draft_path: Path | None,
) -> Path:
    metadata = result.get("metadata")
    raw = result.get("verification_log_path")
    if raw is None and isinstance(metadata, Mapping):
        raw = metadata.get("verification_log_path")
    if _nonempty_text(raw):
        return _resolved_path(str(raw), root)
    if work_dir is not None:
        return work_dir / "verification.log"
    if draft_path is not None:
        parent = draft_path.parent
        return (parent.parent if parent.name == "draft" else parent) / "verification.log"
    raise RunStateError("verified result requires verification_log_path evidence")


_QUIZ_NUMERIC_FIELDS = ("kept_score", "points_possible")
_QUIZ_INTEGER_FIELDS = ("attempts_used", "allowed_attempts")
_QUIZ_SCORING_POLICIES = frozenset({"keep_highest", "keep_latest", "keep_average"})
_DIAGNOSTIC_NUMERIC_FIELDS = frozenset(
    {
        "started_at_pt_hour",
        "total_answer_time_seconds",
        "total_time_limit_seconds",
        "time_utilization",
        "per_question_cv",
        "revisits",
        "events_posted",
        "blur_events_count",
        "flagged_questions_count",
        "outlier_count",
        "strategic_miss_count",
    }
)
_DIAGNOSTIC_BOOL_FIELDS = frozenset(
    {
        "answer_sequence_linear",
        "views_paired_with_answers",
        "strategic_miss_enabled",
    }
)


def validate_quiz_submission_result(data: Mapping[str, Any]) -> None:
    """Validate the extra evidence claimed by a submitted Classic Quiz.

    ``bool`` is deliberately rejected for every numeric field.  Python treats
    booleans as integers, which previously let ``true`` satisfy score/attempt
    checks.  A submitted quiz also has to carry the diagnostics it claims;
    omitting the block is not equivalent to proving paced interaction.
    """

    for field in _QUIZ_NUMERIC_FIELDS:
        if not _number(data.get(field)):
            raise RunStateError(f"quiz submitted result requires numeric {field!r} (bool is invalid)")
    for field in _QUIZ_INTEGER_FIELDS:
        if not _integer(data.get(field)):
            raise RunStateError(f"quiz submitted result requires integer {field!r} (bool is invalid)")

    if data.get("scoring_policy") not in _QUIZ_SCORING_POLICIES:
        raise RunStateError(
            "quiz submitted result requires scoring_policy in "
            "keep_highest/keep_latest/keep_average"
        )

    passes = data.get("agent_passes_count")
    consent = data.get("degraded_method_user_consent")
    has_arbitration = _integer(passes) and passes >= 4
    has_override = isinstance(consent, str) and len(consent.strip()) >= 10
    if not has_arbitration and not has_override:
        raise RunStateError(
            "quiz submitted result requires agent_passes_count >= 4 or "
            "degraded_method_user_consent with at least 10 non-space characters"
        )

    diagnostics = data.get("human_ness_diagnostics")
    if not isinstance(diagnostics, Mapping):
        raise RunStateError("quiz submitted result requires human_ness_diagnostics object")
    if diagnostics.get("views_paired_with_answers") is not True:
        raise RunStateError(
            "quiz human_ness_diagnostics.views_paired_with_answers must be true"
        )
    for field in _DIAGNOSTIC_NUMERIC_FIELDS.intersection(diagnostics):
        if not _number(diagnostics[field]):
            raise RunStateError(
                f"quiz human_ness_diagnostics.{field} must be numeric (bool is invalid)"
            )
    for field in _DIAGNOSTIC_BOOL_FIELDS.intersection(diagnostics):
        if not isinstance(diagnostics[field], bool):
            raise RunStateError(f"quiz human_ness_diagnostics.{field} must be boolean")


def validate_result(
    data: Any,
    *,
    root: Path | None = None,
    work_dir: Path | None = None,
) -> dict[str, Any]:
    """Return a shallow copy of a valid result document or raise.

    Canvas may report a graded workflow state, but ``graded`` is metadata, not
    a fifth run status.  Likewise, a submission found before our write is
    represented as ``status=submitted`` plus ``reason_code=already_submitted``.
    """

    if not isinstance(data, Mapping):
        raise RunStateError("result.json must be a JSON object")
    result = dict(data)
    status = result.get("status")
    if status not in CANONICAL_STATUSES:
        raise RunStateError(
            f"status={status!r} is not one of {sorted(CANONICAL_STATUSES)}; "
            "graded belongs in metadata and an existing submit uses "
            "status='submitted', reason_code='already_submitted'"
        )

    resolved_draft: Path | None = None
    if status == "draft_ready":
        draft_path = result.get("draft_path")
        if not _nonempty_text(draft_path):
            raise RunStateError("draft_ready requires draft_path")
        resolved_draft = _substantive_draft_path(str(draft_path), root)
        validate_verification_log(
            _verification_path(
                result, root=root, work_dir=work_dir, draft_path=resolved_draft
            )
        )
    elif status == "submitted":
        has_draft = _nonempty_text(result.get("draft_path"))
        has_timestamp = _nonempty_text(result.get("submitted_at"))
        if not (has_draft or has_timestamp):
            raise RunStateError("submitted requires draft_path or submitted_at")
        if result.get("reason_code") == "already_submitted" and not has_timestamp:
            raise RunStateError("already_submitted reason requires submitted_at read from Canvas")
        if has_draft:
            resolved_draft = _substantive_draft_path(str(result["draft_path"]), root)

    metadata = result.get("metadata")
    if metadata is not None and not isinstance(metadata, Mapping):
        raise RunStateError("metadata must be a JSON object when present")
    if isinstance(metadata, Mapping) and metadata.get("canvas_workflow_state") == "graded":
        if status != "submitted":
            raise RunStateError("graded Canvas workflow metadata requires canonical status='submitted'")

    if status == "submitted":
        workflow_state = metadata.get("canvas_workflow_state") if isinstance(metadata, Mapping) else None
        readback_verified = metadata.get("readback_verified") if isinstance(metadata, Mapping) else None
        if workflow_state not in {"submitted", "graded"} or readback_verified is not True:
            raise RunStateError(
                "submitted requires Canvas read-back metadata with workflow_state and readback_verified=true"
            )
        if result.get("reason_code") == "already_submitted":
            if result.get("authorization_receipt_id") or result.get("authorization_consumed"):
                raise RunStateError("already_submitted is read-only and must not claim receipt consumption")
        else:
            if not _nonempty_text(result.get("authorization_receipt_id")):
                raise RunStateError("new submitted result requires authorization_receipt_id")
            if result.get("authorization_consumed") is not True:
                raise RunStateError("new submitted result requires authorization_consumed=true")
            if not has_timestamp:
                raise RunStateError("new submitted result requires submitted_at read back from Canvas")
        if resolved_draft is not None:
            validate_verification_log(
                _verification_path(
                    result, root=root, work_dir=work_dir, draft_path=resolved_draft
                )
            )

    if result.get("kind") == "quiz" and status == "submitted":
        validate_quiz_submission_result(result)
    return result


def validate_result_json(
    content: str,
    *,
    root: Path | None = None,
    work_dir: Path | None = None,
) -> tuple[bool, str]:
    """Tuple-returning adapter used by hooks."""

    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        return False, f"result.json is not valid JSON: {exc}"
    try:
        validate_result(data, root=root, work_dir=work_dir)
    except RunStateError as exc:
        return False, str(exc)
    return True, ""


def validate_plan(
    data: Any,
    *,
    require_timestamps: bool = True,
    require_current: bool = False,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    if not isinstance(data, Mapping):
        raise RunStateError("plan.json must be a JSON object")
    plan = dict(data)
    if require_timestamps:
        generated_at = _parse_aware_time(plan.get("generated_at"), "generated_at")
        expires_at = _parse_aware_time(plan.get("expires_at"), "expires_at")
        if expires_at <= generated_at:
            raise RunStateError("plan expires_at must be after generated_at")
        current = now or dt.datetime.now(dt.timezone.utc)
        if current.tzinfo is None or current.utcoffset() is None:
            raise RunStateError("plan validation clock must include a timezone")
        if require_current and current.astimezone(dt.timezone.utc) >= expires_at:
            raise RunStateError("plan has expired; run canvas-scan again")
    items = plan.get("items")
    if not isinstance(items, list):
        raise RunStateError("plan.json items must be a list")
    seen: set[int] = set()
    normalized: list[dict[str, Any]] = []
    for position, raw in enumerate(items, start=1):
        if not isinstance(raw, Mapping):
            raise RunStateError(f"plan item {position} must be an object")
        item = dict(raw)
        index = item.get("index")
        if not _integer(index) or index <= 0:
            raise RunStateError(f"plan item {position} requires a positive integer index")
        if index in seen:
            raise RunStateError(f"plan item index {index} is duplicated")
        seen.add(index)
        decision = item.get("user_decision")
        if decision is not None and decision not in PLAN_DECISIONS and not (
            isinstance(decision, str) and decision.startswith("swap:canvas-")
        ):
            raise RunStateError(f"plan item {index} has invalid user_decision={decision!r}")
        normalized.append(item)
    expected_indices = list(range(1, len(normalized) + 1))
    observed_indices = [int(item["index"]) for item in normalized]
    if observed_indices != expected_indices:
        raise RunStateError(
            "plan indices must be contiguous, ordered, and 1-based; "
            f"expected {expected_indices}, got {observed_indices}"
        )
    plan["items"] = normalized
    return plan


def validate_plan_assignments(
    plan_data: Any,
    assignments_data: Any,
    *,
    run_dir: Path | str | None = None,
    require_current: bool = False,
    now: dt.datetime | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Validate the approval plan against its immutable assignment snapshot."""

    plan = validate_plan(plan_data, require_current=require_current, now=now)
    assignments = validate_assignments(assignments_data)
    snapshot_by_key = {
        (str(item["course_id"]), str(item["assignment_id"])): item
        for item in assignments
    }
    plan_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for item in plan["items"]:
        if item.get("course_id") in (None, "") or item.get("assignment_id") in (None, ""):
            raise RunStateError("every plan item requires course_id and assignment_id")
        key = (str(item["course_id"]), str(item["assignment_id"]))
        if key in plan_by_key:
            raise RunStateError(f"plan duplicates course/assignment {key}")
        plan_by_key[key] = item

    if set(plan_by_key) != set(snapshot_by_key):
        missing = sorted(set(snapshot_by_key) - set(plan_by_key))
        extra = sorted(set(plan_by_key) - set(snapshot_by_key))
        raise RunStateError(
            f"plan and assignments snapshot identities differ; missing={missing}, extra={extra}"
        )

    for key, plan_item in plan_by_key.items():
        snapshot_item = snapshot_by_key[key]
        proposed = plan_item.get("proposed_skill") or plan_item.get("skill")
        snapshot_skill = snapshot_item.get("skill") or snapshot_item.get("proposed_skill")
        if not _nonempty_text(proposed) or not _CANONICAL_SKILL.fullmatch(str(proposed)):
            raise RunStateError(f"plan item {plan_item['index']} requires a canonical canvas-* skill")
        if str(proposed) != str(snapshot_skill):
            raise RunStateError(
                f"plan item {plan_item['index']} skill does not match assignments snapshot"
            )
        if run_dir is not None and snapshot_item.get("work_dir"):
            expected_name = stable_work_dir(run_dir, *key).name
            if Path(str(snapshot_item["work_dir"])).name != expected_name:
                raise RunStateError(
                    f"assignment {key} work_dir must be the stable ID directory {expected_name}"
                )
    return plan, assignments


def plan_digest(plan_data: Any) -> str:
    """Return a deterministic digest of the complete validated approval plan."""

    plan = validate_plan(plan_data)
    encoded = json.dumps(
        plan, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_execute_marker(
    marker_data: Any,
    plan_data: Any,
    *,
    expected_session_id: str | None = None,
) -> dict[str, Any]:
    """Validate marker ownership and bind it to the current complete plan."""

    if not isinstance(marker_data, Mapping):
        raise RunStateError(".scan_in_progress must contain a JSON object")
    marker = dict(marker_data)
    if not _nonempty_text(marker.get("session_id")):
        raise RunStateError("execute marker requires session_id")
    if marker.get("owner_kind") != "codex":
        raise RunStateError("execute marker owner_kind must be 'codex'")
    _parse_aware_time(marker.get("created_at"), "marker created_at")
    digest = marker.get("plan_digest")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise RunStateError("execute marker requires a SHA-256 plan_digest")
    expected_digest = plan_digest(plan_data)
    if digest != expected_digest:
        raise RunStateError("execute marker plan_digest does not match plan.json")
    if expected_session_id is not None and marker["session_id"] != expected_session_id:
        raise RunStateError("execute marker belongs to a different Codex session")
    return marker


_RESULT_PREPARATION_FIELDS = (
    "results_prepared_at",
    "results_archive_count",
    "prepared_approved_result_keys",
)


def validate_execute_result_preparation(
    marker_data: Any,
    plan_data: Any,
) -> list[str]:
    """Validate the exact approved-result slots prepared for this execute.

    Preparation archives every approved item's old ``result.json`` before the
    marker is stamped.  Once stamped, any result that reappears in that exact
    slot belongs to the current execute.  Encoding the complete key set avoids
    relying on filesystem timestamp precision and makes same-session resume
    idempotent.
    """

    marker = validate_execute_marker(marker_data, plan_data)
    plan = validate_plan(plan_data)
    expected_keys: list[str] = []
    for item in plan["items"]:
        if item.get("user_decision") == "defer":
            continue
        if item.get("course_id") in (None, "") or item.get("assignment_id") in (None, ""):
            raise RunStateError("approved plan item requires course_id and assignment_id")
        expected_keys.append(
            stable_work_dir(Path("."), item["course_id"], item["assignment_id"]).name
        )
    present = [field in marker for field in _RESULT_PREPARATION_FIELDS]
    if not all(present):
        raise RunStateError(
            "execute marker is missing complete result-preparation evidence"
        )

    prepared_at = _parse_aware_time(
        marker.get("results_prepared_at"), "marker results_prepared_at"
    )
    created_at = _parse_aware_time(marker.get("created_at"), "marker created_at")
    if prepared_at < created_at:
        raise RunStateError("execute result preparation predates marker creation")
    archive_count = marker.get("results_archive_count")
    if not _integer(archive_count) or archive_count < 0:
        raise RunStateError("execute marker requires a non-negative results_archive_count")
    prepared_keys = marker.get("prepared_approved_result_keys")
    if not isinstance(prepared_keys, list) or not all(
        _nonempty_text(value) for value in prepared_keys
    ):
        raise RunStateError(
            "execute marker prepared_approved_result_keys must be a string list"
        )
    if prepared_keys != expected_keys:
        raise RunStateError(
            "execute marker prepared approved-result keys do not exactly match plan.json"
        )
    if archive_count > len(expected_keys):
        raise RunStateError("execute marker archive count exceeds approved result slots")
    return list(prepared_keys)


def validate_assignments(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, list):
        raise RunStateError("assignments.json must be a list")
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for position, raw in enumerate(data, start=1):
        if not isinstance(raw, Mapping):
            raise RunStateError(f"assignment snapshot item {position} must be an object")
        item = dict(raw)
        if item.get("course_id") in (None, "") or item.get("assignment_id") in (None, ""):
            raise RunStateError(f"assignment snapshot item {position} requires course_id and assignment_id")
        key = (str(item["course_id"]), str(item["assignment_id"]))
        if key in seen:
            raise RunStateError(f"assignment snapshot duplicates course/assignment {key}")
        seen.add(key)
        normalized.append(item)
    return normalized


def validate_ledger(data: Any) -> dict[str, Any]:
    if not isinstance(data, Mapping):
        raise RunStateError("runs/_processed.json must be a JSON object")
    ledger = dict(data)
    for key, raw in ledger.items():
        if not isinstance(key, str) or not isinstance(raw, Mapping):
            raise RunStateError("ledger entries must map string keys to JSON objects")
        status = raw.get("status")
        if status is not None and status not in CANONICAL_STATUSES:
            raise RunStateError(f"ledger entry {key!r} has non-canonical status={status!r}")
    return ledger


def load_json(path: Path | str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def atomic_write_json(path: Path | str, data: Any) -> Path:
    """Write JSON in the destination directory and atomically replace it."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    try:
        with tmp.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
    return target


def prepare_approved_results(
    run_dir: Path | str,
    *,
    expected_session_id: str,
) -> dict[str, Any]:
    """Archive approved items' old results and bind new results to this run.

    The operation is recoverable and idempotent.  If a crash happens after a
    result is moved but before the marker update, a retry observes the
    deterministic history path and completes preparation.  Once the marker is
    prepared, later retries never archive a result produced by this execute.
    """

    if not _nonempty_text(expected_session_id):
        raise RunStateError("result preparation requires the current Codex session id")
    directory = Path(run_dir)
    plan_path = directory / "plan.json"
    assignments_path = directory / "assignments.json"
    marker_path = directory / ".scan_in_progress"
    if not plan_path.is_file() or not assignments_path.is_file():
        raise RunStateError("result preparation requires plan.json and assignments.json")
    if not marker_path.is_file():
        raise RunStateError("result preparation requires an active .scan_in_progress marker")

    plan, assignments = validate_plan_assignments(
        load_json(plan_path), load_json(assignments_path), run_dir=directory
    )
    undecided = [
        item["index"] for item in plan["items"] if item.get("user_decision") is None
    ]
    if undecided:
        raise RunStateError(
            f"result preparation requires a complete decision set; undecided={undecided}"
        )
    marker = validate_execute_marker(
        load_json(marker_path), plan, expected_session_id=expected_session_id
    )
    already_prepared = any(
        field in marker for field in _RESULT_PREPARATION_FIELDS
    )
    if already_prepared:
        prepared_keys = validate_execute_result_preparation(marker, plan)
        return {
            "prepared": True,
            "idempotent": True,
            "archived": int(marker["results_archive_count"]),
            "prepared_approved_result_keys": prepared_keys,
            "marker": marker_path.as_posix(),
        }

    items_by_key = {
        (str(item["course_id"]), str(item["assignment_id"])): item
        for item in assignments
    }
    approved = [
        item for item in plan["items"] if item.get("user_decision") != "defer"
    ]
    prepared_keys = [
        stable_work_dir(directory, item["course_id"], item["assignment_id"]).name
        for item in approved
    ]
    digest = marker["plan_digest"]
    archive_paths: list[Path] = []
    for item in approved:
        key = (str(item["course_id"]), str(item["assignment_id"]))
        snapshot = items_by_key[key]
        work = stable_work_dir(directory, snapshot["course_id"], snapshot["assignment_id"])
        result_path = work / "result.json"
        archive_path = work / "result-history" / f"pre-{digest[:20]}.json"
        if result_path.exists() and archive_path.exists():
            raise RunStateError(
                "result preparation is ambiguous because current and archived "
                f"results both exist: {result_path.as_posix()}"
            )
        if result_path.exists():
            archive_path.parent.mkdir(parents=True, exist_ok=True)
            os.replace(result_path, archive_path)
        if archive_path.exists():
            archive_paths.append(archive_path)

    prepared_at = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    marker.update(
        {
            "results_prepared_at": prepared_at,
            "results_archive_count": len(archive_paths),
            "prepared_approved_result_keys": prepared_keys,
        }
    )
    atomic_write_json(marker_path, marker)
    validate_execute_marker(marker, plan, expected_session_id=expected_session_id)
    validate_execute_result_preparation(marker, plan)
    return {
        "prepared": True,
        "idempotent": False,
        "approved_items": len(approved),
        "archived": len(archive_paths),
        "archive_paths": [path.as_posix() for path in archive_paths],
        "prepared_approved_result_keys": prepared_keys,
        "marker": marker_path.as_posix(),
    }


def write_result(path: Path | str, data: Any, *, root: Path | None = None) -> Path:
    target = Path(path)
    return atomic_write_json(
        target, validate_result(data, root=root, work_dir=target.parent)
    )


def write_plan(path: Path | str, data: Any) -> Path:
    return atomic_write_json(path, validate_plan(data))


def write_ledger(path: Path | str, data: Any) -> Path:
    return atomic_write_json(path, validate_ledger(data))


def update_plan(path: Path | str, update: Callable[[dict[str, Any]], Any]) -> dict[str, Any]:
    target = Path(path)
    plan = validate_plan(load_json(target))
    update(plan)
    plan = validate_plan(plan)
    atomic_write_json(target, plan)
    return plan


def merge_ledger_entry(path: Path | str, key: str, entry: Mapping[str, Any]) -> dict[str, Any]:
    """Preserve existing ledger entries and atomically replace one key."""

    target = Path(path)
    ledger: MutableMapping[str, Any]
    if target.exists():
        ledger = validate_ledger(load_json(target))
    else:
        ledger = {}
    ledger[key] = dict(entry)
    normalized = validate_ledger(ledger)
    atomic_write_json(target, normalized)
    return normalized


def validate_run_directory(run_dir: Path | str, *, require_ledger: bool = False) -> dict[str, Any]:
    directory = Path(run_dir)
    plan_path = directory / "plan.json"
    assignments_path = directory / "assignments.json"
    if not plan_path.exists() or not assignments_path.exists():
        raise RunStateError("run directory requires plan.json and assignments.json")
    plan, assignments = validate_plan_assignments(
        load_json(plan_path), load_json(assignments_path), run_dir=directory
    )
    marker = directory / ".scan_in_progress"
    marker_data: dict[str, Any] | None = None
    if marker.exists():
        marker_text = marker.read_text(encoding="utf-8", errors="strict").strip()
        if not marker_text:
            raise RunStateError(".scan_in_progress must contain a JSON object")
        marker_data = validate_execute_marker(json.loads(marker_text), plan)
        validate_execute_result_preparation(marker_data, plan)

    results: list[str] = []
    for item in assignments:
        result_path = stable_work_dir(
            directory, item["course_id"], item["assignment_id"]
        ) / "result.json"
        if not result_path.exists():
            raise RunStateError(f"missing result.json for assignment {item.get('assignment_id')}")
        validate_result(load_json(result_path), root=Path.cwd(), work_dir=result_path.parent)
        results.append(result_path.as_posix())

    ledger_path = directory.parent / "_processed.json"
    if ledger_path.exists():
        validate_ledger(load_json(ledger_path))
    elif require_ledger:
        raise RunStateError("runs/_processed.json is missing")
    return {
        "plan_items": len(plan["items"]),
        "assignments": len(assignments),
        "results": results,
        "marker_active": marker.exists(),
        "ledger": ledger_path.as_posix() if ledger_path.exists() else None,
    }


def _read_payload(path: Path | None) -> Any:
    if path is not None:
        return load_json(path)
    return json.loads(sys.stdin.read())


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Canvas Pilot run-state helper")
    sub = parser.add_subparsers(dest="command", required=True)

    validate_cmd = sub.add_parser("validate")
    validate_cmd.add_argument("--kind", required=True, choices=("result", "plan", "assignments", "ledger"))
    validate_cmd.add_argument("--path", required=True, type=Path)
    validate_cmd.add_argument("--root", type=Path, default=Path.cwd())

    run_cmd = sub.add_parser("validate-run")
    run_cmd.add_argument("--run-dir", required=True, type=Path)
    run_cmd.add_argument("--require-ledger", action="store_true")

    finalize_cmd = sub.add_parser("finalize")
    finalize_cmd.add_argument("--run-dir", required=True, type=Path)
    finalize_cmd.add_argument("--remove-marker", action="store_true")

    prepare_cmd = sub.add_parser("prepare-results")
    prepare_cmd.add_argument("--run-dir", required=True, type=Path)
    prepare_cmd.add_argument("--expected-session-id")

    write_cmd = sub.add_parser("write")
    write_cmd.add_argument("--kind", required=True, choices=("result", "plan", "ledger"))
    write_cmd.add_argument("--path", required=True, type=Path)
    write_cmd.add_argument("--input", type=Path, help="JSON input; omit to read stdin")
    write_cmd.add_argument("--root", type=Path, default=Path.cwd())

    merge_cmd = sub.add_parser("merge-ledger")
    merge_cmd.add_argument("--path", required=True, type=Path)
    merge_cmd.add_argument("--key", required=True)
    merge_cmd.add_argument("--input", type=Path, help="entry JSON; omit to read stdin")

    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            payload = load_json(args.path)
            if args.kind == "result":
                validate_result(payload, root=args.root)
            elif args.kind == "plan":
                validate_plan(payload)
            elif args.kind == "assignments":
                validate_assignments(payload)
            else:
                validate_ledger(payload)
            output = {"valid": True, "kind": args.kind, "path": args.path.as_posix()}
        elif args.command == "validate-run":
            output = validate_run_directory(args.run_dir, require_ledger=args.require_ledger)
            output["valid"] = True
        elif args.command == "finalize":
            output = validate_run_directory(args.run_dir, require_ledger=True)
            marker = args.run_dir / ".scan_in_progress"
            if args.remove_marker and marker.exists():
                marker.unlink()
            output.update({"valid": True, "finalized": True, "marker_active": marker.exists()})
        elif args.command == "prepare-results":
            expected_session_id = (
                args.expected_session_id
                or os.environ.get("CODEX_THREAD_ID")
                or os.environ.get("CODEX_SESSION_ID")
            )
            if not expected_session_id:
                raise RunStateError(
                    "prepare-results requires --expected-session-id or a Codex session environment variable"
                )
            output = prepare_approved_results(
                args.run_dir, expected_session_id=expected_session_id
            )
        elif args.command == "write":
            payload = _read_payload(args.input)
            if args.kind == "result":
                write_result(args.path, payload, root=args.root)
            elif args.kind == "plan":
                write_plan(args.path, payload)
            else:
                write_ledger(args.path, payload)
            output = {"written": args.path.as_posix(), "kind": args.kind}
        else:
            entry = _read_payload(args.input)
            if not isinstance(entry, Mapping):
                raise RunStateError("ledger entry input must be a JSON object")
            merge_ledger_entry(args.path, args.key, entry)
            output = {"written": args.path.as_posix(), "key": args.key}
    except (OSError, json.JSONDecodeError, RunStateError) as exc:
        print(json.dumps({"valid": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
