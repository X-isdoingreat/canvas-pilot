# SPDX-License-Identifier: AGPL-3.0-or-later
"""Issue signed Canvas mutation receipts from an exact user command.

Execution-plan approval and Canvas mutation authority are separate steps.  This
module implements the second step for an interactive Codex session: it accepts
one whole-expression command, binds it to one already-approved plan item, and
writes a short-lived, target-exact receipt into that item's stable work
directory.

The parser intentionally has no broad selector, wildcard, free-form suffix, or
implicit fallback.  A caller must pass the verbatim text from the *current*,
separate user message.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .authorization import (
    AuthorizationDenied,
    create_authorization_receipt,
    current_authorization_session,
    write_authorization_receipt,
)
from .run_state import (
    RunStateError,
    atomic_write_json,
    load_json,
    plan_digest,
    stable_work_dir,
    validate_result,
    validate_plan_assignments,
)


RECEIPT_TTL = dt.timedelta(minutes=15)
RECEIPT_FILENAME = "mutation_authorization.json"
AUTHORITY_FILENAME = "mutation_authority.json"

_COMMAND_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("assignment_submit", re.compile(r"submit[ \t]+([1-9][0-9]*)", re.IGNORECASE)),
    ("assignment_submit", re.compile(r"提交[ \t]*(?:第[ \t]*)?([1-9][0-9]*)[ \t]*(?:项)?")),
    ("quiz_take", re.compile(r"take[ \t]+quiz[ \t]+([1-9][0-9]*)", re.IGNORECASE)),
    ("quiz_take", re.compile(r"(?:参加|做)[ \t]*测验[ \t]*(?:第[ \t]*)?([1-9][0-9]*)[ \t]*(?:项)?")),
    ("quiz_retake", re.compile(r"retake[ \t]+quiz[ \t]+([1-9][0-9]*)", re.IGNORECASE)),
    ("quiz_retake", re.compile(r"(?:重做|重考)[ \t]*测验[ \t]*(?:第[ \t]*)?([1-9][0-9]*)[ \t]*(?:项)?")),
)

_ASSIGNMENT_ACTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("online_text_entry", ("assignment.submit_text",)),
    (
        "online_upload",
        (
            "assignment.upload_init",
            "assignment.upload_blob",
            "assignment.submit_files",
        ),
    ),
    ("online_url", ("assignment.submit_url",)),
)
_ORDINARY_SUBMISSION_TYPES = frozenset(kind for kind, _ in _ASSIGNMENT_ACTIONS)
_QUIZ_INITIAL_ACTIONS = (
    "quiz.start",
    "quiz.event",
    "quiz.answer",
    "quiz.complete",
)
_QUIZ_RETAKE_ACTIONS = (
    "quiz.retake",
    "quiz.event",
    "quiz.answer",
    "quiz.complete",
)


class MutationApprovalError(ValueError):
    """The current message cannot grant the requested Canvas mutation."""


@dataclass(frozen=True)
class MutationCommand:
    operation: str
    index: int
    raw_text: str

    @property
    def is_quiz(self) -> bool:
        return self.operation in {"quiz_take", "quiz_retake"}

    @property
    def is_retake(self) -> bool:
        return self.operation == "quiz_retake"


def parse_mutation_command(text: str) -> MutationCommand:
    """Parse one exact mutation command; reject all residual prose.

    Leading/trailing whitespace is ignored for recognition so stdin's final
    newline is harmless.  ``raw_text`` always retains the exact supplied value
    for the durable authority record.
    """

    if not isinstance(text, str):
        raise MutationApprovalError("mutation authority requires current user text")
    expression = text.strip()
    if not expression:
        raise MutationApprovalError("mutation authority command is empty")
    matches: list[tuple[str, str]] = []
    for operation, pattern in _COMMAND_PATTERNS:
        match = pattern.fullmatch(expression)
        if match:
            matches.append((operation, match.group(1)))
    if len(matches) != 1:
        raise MutationApprovalError(
            "use exactly one of: submit N, take quiz N, retake quiz N, "
            "or the documented Chinese equivalent; no other prose is allowed"
        )
    operation, raw_index = matches[0]
    return MutationCommand(operation=operation, index=int(raw_index), raw_text=text)


def _validated_submission_types(snapshot: Mapping[str, Any]) -> tuple[str, ...]:
    raw = snapshot.get("submission_types")
    if not isinstance(raw, list) or not raw:
        raise MutationApprovalError("assignment snapshot has no declared submission type")
    if any(not isinstance(value, str) or not value.strip() for value in raw):
        raise MutationApprovalError("assignment snapshot submission_types must be non-empty text")
    normalized = tuple(value.strip() for value in raw)
    if len(set(normalized)) != len(normalized):
        raise MutationApprovalError("assignment snapshot submission_types contains duplicates")
    return normalized


def _approved(decision: Any) -> bool:
    return decision == "approve" or (
        isinstance(decision, str) and decision.startswith("swap:canvas-")
    )


def _scope_for(
    command: MutationCommand,
    snapshot: Mapping[str, Any],
) -> tuple[str, str, tuple[str, ...]]:
    submission_types = _validated_submission_types(snapshot)
    declared = frozenset(submission_types)

    if command.is_quiz:
        if declared != {"online_quiz"}:
            raise MutationApprovalError(
                "take/retake authority requires a Classic Quiz snapshot with only online_quiz"
            )
        quiz_id = snapshot.get("quiz_id")
        if isinstance(quiz_id, bool) or quiz_id in (None, ""):
            raise MutationApprovalError("Classic Quiz authority requires the exact snapshot quiz_id")
        if not isinstance(quiz_id, (str, int)) or not str(quiz_id).strip():
            raise MutationApprovalError("Classic Quiz snapshot quiz_id is invalid")
        actions = _QUIZ_RETAKE_ACTIONS if command.is_retake else _QUIZ_INITIAL_ACTIONS
        return "quiz", str(quiz_id), actions

    if "online_quiz" in declared or snapshot.get("quiz_id") not in (None, ""):
        raise MutationApprovalError("submit N cannot authorize a quiz; use take quiz N")
    undeclared = declared - _ORDINARY_SUBMISSION_TYPES
    if undeclared:
        raise MutationApprovalError(
            "ordinary submission has unsupported/undeclared mutation scope: "
            + ", ".join(sorted(undeclared))
        )
    actions: list[str] = []
    for submission_type, exact_actions in _ASSIGNMENT_ACTIONS:
        if submission_type in declared:
            actions.extend(exact_actions)
    if not actions:
        raise MutationApprovalError("ordinary assignment declares no supported submission action")
    return "assignment", str(snapshot["assignment_id"]), tuple(actions)


def _load_current_target(
    run_dir: Path,
    command: MutationCommand,
    *,
    now: dt.datetime,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    plan_path = run_dir / "plan.json"
    assignments_path = run_dir / "assignments.json"
    if not plan_path.is_file() or not assignments_path.is_file():
        raise MutationApprovalError("run directory requires plan.json and assignments.json")
    try:
        plan, assignments = validate_plan_assignments(
            load_json(plan_path),
            load_json(assignments_path),
            run_dir=run_dir,
            require_current=True,
            now=now,
        )
    except (OSError, json.JSONDecodeError, RunStateError) as exc:
        raise MutationApprovalError(f"current run state is invalid: {exc}") from exc

    if command.index > len(plan["items"]):
        raise MutationApprovalError(f"current plan has no item {command.index}")
    plan_item = plan["items"][command.index - 1]
    if int(plan_item["index"]) != command.index:
        # validate_plan currently guarantees this, but retain the local wall if
        # the shared schema evolves.
        raise MutationApprovalError("plan index does not resolve deterministically")
    if not _approved(plan_item.get("user_decision")):
        raise MutationApprovalError(
            f"plan item {command.index} must already be approve/swap before mutation authority"
        )

    key = (str(plan_item["course_id"]), str(plan_item["assignment_id"]))
    by_key = {
        (str(item["course_id"]), str(item["assignment_id"])): item
        for item in assignments
    }
    snapshot = by_key.get(key)
    if snapshot is None:
        raise MutationApprovalError("approved plan target is absent from assignments snapshot")
    return plan, plan_item, snapshot


def _require_local_precondition(
    command: MutationCommand,
    *,
    run_dir: Path,
    snapshot: Mapping[str, Any],
) -> None:
    """Bind mutation authority to a verified local draft or prior quiz result."""

    work_dir = stable_work_dir(
        run_dir, snapshot["course_id"], snapshot["assignment_id"]
    )
    result_path = work_dir / "result.json"
    if not result_path.is_file():
        if command.operation == "quiz_take":
            return
        prerequisite = (
            "a verified draft_ready result"
            if command.operation == "assignment_submit"
            else "a prior submitted quiz result"
        )
        raise MutationApprovalError(
            f"{command.operation} requires {prerequisite} in the stable work directory"
        )
    try:
        result = validate_result(
            load_json(result_path), root=run_dir.parent.parent, work_dir=work_dir
        )
    except (OSError, json.JSONDecodeError, RunStateError) as exc:
        raise MutationApprovalError(f"local result is not safe to mutate from: {exc}") from exc

    status = result.get("status")
    if command.operation == "assignment_submit":
        if status != "draft_ready":
            raise MutationApprovalError(
                "submit N requires a verified draft_ready result; it cannot reuse a "
                "submitted, skipped, or error result"
            )
        draft_value = result.get("draft_path")
        draft_path = Path(str(draft_value))
        if not draft_path.is_absolute():
            draft_path = run_dir.parent.parent / draft_path
        try:
            draft_path.resolve().relative_to(work_dir.resolve())
        except ValueError as exc:
            raise MutationApprovalError(
                "submit N draft_path must stay inside the stable work directory"
            ) from exc
        return
    if command.operation == "quiz_take":
        if status == "submitted":
            raise MutationApprovalError(
                "quiz already has a local submitted result; use explicit retake quiz N"
            )
        if status not in {"draft_ready", "skipped", "error"}:
            raise MutationApprovalError("quiz local result has an unsupported state")
        return

    if result.get("kind") != "quiz" or status != "submitted":
        raise MutationApprovalError(
            "retake quiz N requires a prior canonical submitted quiz result"
        )
    attempts_used = result.get("attempts_used")
    allowed_attempts = result.get("allowed_attempts")
    if (
        not isinstance(attempts_used, int)
        or isinstance(attempts_used, bool)
        or not isinstance(allowed_attempts, int)
        or isinstance(allowed_attempts, bool)
        or attempts_used >= allowed_attempts
    ):
        raise MutationApprovalError("retake quiz N has no verified remaining attempt")


def issue_interactive_authorization(
    *,
    run_dir: Path | str,
    canvas_origin: str,
    user_text: str,
    synthetic_qa: bool = False,
    now: dt.datetime | None = None,
    signing_key: bytes | str | None = None,
    key_path: Path | str | None = None,
) -> dict[str, Any]:
    """Issue one receipt bound to the current plan, target, and Codex session."""

    command = parse_mutation_command(user_text)
    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise MutationApprovalError("authorization clock must include a timezone")
    current = current.astimezone(dt.timezone.utc)

    directory = Path(run_dir)
    plan, plan_item, snapshot = _load_current_target(directory, command, now=current)
    target_type, target_id, actions = _scope_for(command, snapshot)
    _require_local_precondition(command, run_dir=directory, snapshot=snapshot)
    session_id = current_authorization_session()
    if not session_id:
        raise MutationApprovalError(
            "interactive mutation authority requires the current Codex thread/session"
        )

    digest = plan_digest(plan)
    authority_id = str(uuid.uuid4())
    authority_reference = {
        "approval_id": authority_id,
        "authority_kind": "interactive_current_user_message",
        "plan_digest": digest,
        "user_text_sha256": hashlib.sha256(user_text.encode("utf-8")).hexdigest(),
    }
    expires_at = current + RECEIPT_TTL
    try:
        receipt = create_authorization_receipt(
            canvas_origin=canvas_origin,
            course_id=snapshot["course_id"],
            target_type=target_type,
            target_id=target_id,
            actions=actions,
            session_id=session_id,
            issued_at=current,
            expires_at=expires_at,
            authority_reference=authority_reference,
            synthetic_qa=synthetic_qa,
            signing_key=signing_key,
            key_path=key_path,
        )
    except AuthorizationDenied as exc:
        raise MutationApprovalError(str(exc)) from exc

    work_dir = stable_work_dir(
        directory, snapshot["course_id"], snapshot["assignment_id"]
    )
    work_dir.mkdir(parents=True, exist_ok=True)
    authority_path = work_dir / AUTHORITY_FILENAME
    receipt_path = work_dir / RECEIPT_FILENAME
    authority_record = {
        "version": 1,
        "authority_id": authority_id,
        "authority_kind": "interactive_current_user_message",
        "recorded_at": receipt["issued_at"],
        "expires_at": receipt["expires_at"],
        "user_text": user_text,
        "plan_digest": digest,
        "plan_item_index": command.index,
        "plan_user_decision": plan_item["user_decision"],
        "course_id": str(snapshot["course_id"]),
        "assignment_id": str(snapshot["assignment_id"]),
        "quiz_id": str(snapshot["quiz_id"]) if target_type == "quiz" else None,
        "target_type": target_type,
        "target_id": target_id,
        "actions": list(actions),
        "command_operation": command.operation,
        "session_id_sha256": hashlib.sha256(session_id.encode("utf-8")).hexdigest(),
        "receipt_id": receipt["receipt_id"],
        "authority_reference_sha256": receipt["authority_reference"]["sha256"],
        "synthetic_qa": bool(synthetic_qa),
    }
    try:
        atomic_write_json(authority_path, authority_record)
        write_authorization_receipt(receipt_path, receipt)
    except OSError as exc:
        raise MutationApprovalError(f"authorization artifacts could not be written: {exc}") from exc

    return {
        "issued": True,
        "operation": command.operation,
        "plan_item_index": command.index,
        "course_id": str(snapshot["course_id"]),
        "assignment_id": str(snapshot["assignment_id"]),
        "target_type": target_type,
        "target_id": target_id,
        "actions": list(actions),
        "plan_digest": digest,
        "receipt_id": receipt["receipt_id"],
        "expires_at": receipt["expires_at"],
        "receipt_path": receipt_path.as_posix(),
        "authority_record_path": authority_path.as_posix(),
    }


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Issue one exact interactive Canvas mutation authorization"
    )
    parser.add_argument("issue", choices=("issue",))
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--canvas-origin", required=True)
    parser.add_argument("--text", help="verbatim current user message; omit to read stdin")
    parser.add_argument("--synthetic-qa", action="store_true")
    parser.add_argument("--key-path", type=Path)
    args = parser.parse_args(argv)
    raw_text = args.text if args.text is not None else sys.stdin.read()
    try:
        result = issue_interactive_authorization(
            run_dir=args.run_dir,
            canvas_origin=args.canvas_origin,
            user_text=raw_text,
            synthetic_qa=args.synthetic_qa,
            key_path=args.key_path,
        )
    except MutationApprovalError as exc:
        print(json.dumps({"issued": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
