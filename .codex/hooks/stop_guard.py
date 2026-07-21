# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

from _lib import (
    ROOT,
    batch_status,
    block_stop,
    current_batch,
    pass_stop,
    read_event,
    safe_main,
    source_manifest_issue,
    spec_grounding_issue,
    identifier_grounding_issue,
    today_dir,
    validate_result_schema,
)

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from src.run_state import (  # noqa: E402
    RunStateError,
    stable_work_dir,
    validate_execute_marker,
    validate_execute_result_preparation,
    validate_plan_assignments,
)
from src.authorization import (  # noqa: E402
    AuthorizationDenied,
    authorization_usage_status,
)


def report_date() -> str:
    return os.environ.get("CODEX_TEST_DATE") or dt.date.today().isoformat()


def check_batch() -> str | None:
    forced = os.environ.get("CODEX_TEST_BATCH_IN_PROGRESS")
    if forced:
        report = ROOT / "runs" / "codex" / report_date() / f"PARITY_{forced}.md"
        if not report.exists():
            return (
                f"Batch {forced} is still in_progress. Continue by running its "
                f"acceptance/regression checks and writing {report.as_posix()}."
            )
        return None

    batch_id, status, text = current_batch()
    if not batch_id or not status:
        return None
    if status == "in_progress":
        report = ROOT / "runs" / "codex" / report_date() / f"PARITY_{batch_id}.md"
        if not report.exists():
            return (
                f"Batch {batch_id} is still in_progress. Continue by running its "
                f"acceptance/regression checks and writing {report.as_posix()}."
            )
    return None


def check_execute_marker() -> str | None:
    today = today_dir()
    marker = today / ".scan_in_progress"
    if not marker.exists():
        return None
    current_session = os.environ.get("CODEX_SESSION_ID") or os.environ.get("CODEX_THREAD_ID")
    try:
        marker_text = marker.read_text(encoding="utf-8", errors="strict").strip()
    except (OSError, UnicodeError):
        return "Canvas execute marker is unreadable/corrupt; refusing to stop."
    try:
        marker_data = json.loads(marker_text) if marker_text else {}
    except json.JSONDecodeError:
        return "Canvas execute marker is corrupt; refusing to stop until ownership is repaired."
    if not isinstance(marker_data, dict):
        return "Canvas execute marker must be a JSON object; refusing to stop."
    assignments = today / "assignments.json"
    plan = today / "plan.json"
    if not assignments.exists() or not plan.exists():
        return "Canvas execute marker is active but plan.json or assignments.json is missing."
    try:
        plan_data = json.loads(plan.read_text(encoding="utf-8"))
        validate_execute_marker(marker_data, plan_data)
        validate_execute_result_preparation(marker_data, plan_data)
        _, items = validate_plan_assignments(
            plan_data,
            json.loads(assignments.read_text(encoding="utf-8")),
            run_dir=today,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, RunStateError) as exc:
        return f"Canvas execute marker is active but run state is invalid: {exc}"
    if current_session and marker_data["session_id"] != current_session:
        return None

    missing: list[str] = []
    invalid: list[str] = []
    for item in items:
        work = stable_work_dir(today, item["course_id"], item["assignment_id"])
        result = work / "result.json"
        label = f"{item.get('course_id')}:{item.get('assignment_id')} {item.get('name')}"
        if not result.exists():
            missing.append(label)
            continue
        try:
            result_text = result.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeError) as exc:
            invalid.append(f"{label} -> result.json is unreadable: {exc}")
            continue
        ok, err = validate_result_schema(result_text, work_dir=work)
        if not ok:
            invalid.append(f"{label} -> {err}")
            continue
        try:
            result_data = json.loads(result_text)
        except Exception as exc:
            invalid.append(f"{label} -> result read failed: {exc}")
            continue
        if (
            result_data.get("status") == "submitted"
            and result_data.get("reason_code") != "already_submitted"
        ):
            receipt_id = result_data.get("authorization_receipt_id")
            try:
                usage = authorization_usage_status(str(receipt_id))
            except AuthorizationDenied as exc:
                invalid.append(f"{label} -> authorization usage ledger is invalid: {exc}")
                continue
            if not usage or not usage.get("terminal_at"):
                invalid.append(
                    f"{label} -> authorization receipt is not terminally consumed in the usage ledger"
                )
                continue
            expected_type = "quiz" if result_data.get("kind") == "quiz" else "assignment"
            expected_target = (
                result_data.get("quiz_id")
                if expected_type == "quiz"
                else item.get("assignment_id")
            )
            if (
                str(usage.get("course_id")) != str(item.get("course_id"))
                or usage.get("target_type") != expected_type
                or str(usage.get("target_id")) != str(expected_target)
                or usage.get("receipt_id") != receipt_id
            ):
                invalid.append(
                    f"{label} -> authorization usage does not match the submitted Canvas target"
                )
                continue
        if result_data.get("status") in {"draft_ready", "submitted"}:
            issue = spec_grounding_issue(work) or source_manifest_issue(
                work, result_data=result_data
            )
            draft_value = result_data.get("draft_path")
            if not issue and isinstance(draft_value, str):
                draft = Path(draft_value)
                if not draft.is_absolute():
                    draft = ROOT / draft
                issue = identifier_grounding_issue(work, draft)
            if issue:
                invalid.append(f"{label} -> {issue}")
    # Quiz §10 retake gate: a submitted quiz scoring < 95% with attempts left
    # under keep_highest blocks Stop, forcing an explicit retake-or-acknowledge
    # fork. Ported 1:1 from .claude/hooks/check-router-complete.py.
    retake: list[str] = []
    for item in items:
        skill = item.get("skill") or item.get("proposed_skill")
        if skill not in {"quiz", "canvas-quiz", "inside", "canvas-inside"}:
            continue
        work = stable_work_dir(today, item["course_id"], item["assignment_id"])
        rj = work / "result.json"
        if not rj.exists():
            continue
        try:
            r = json.loads(rj.read_text(encoding="utf-8"))
        except Exception:
            continue
        if r.get("status") != "submitted":
            continue
        consent = r.get("degraded_method_user_consent")
        if isinstance(consent, str) and len(consent.strip()) >= 10:
            continue
        kept = r.get("kept_score")
        mx = r.get("points_possible")
        au = r.get("attempts_used")
        aa = r.get("allowed_attempts")
        if (
            not isinstance(kept, (int, float)) or isinstance(kept, bool)
            or not isinstance(mx, (int, float)) or isinstance(mx, bool) or mx <= 0
        ):
            continue
        if not isinstance(au, int) or isinstance(au, bool) or not isinstance(aa, int) or isinstance(aa, bool):
            continue
        if r.get("scoring_policy") != "keep_highest":
            continue
        if kept / mx >= 0.95 or au >= aa:
            continue
        retake.append(
            f"{item.get('name')} kept {kept}/{mx}={round(kept / mx * 100, 1)}% "
            f"attempts {au}/{aa}"
        )

    if missing or invalid or retake:
        return (
            "Canvas execute marker is active and assignments are incomplete. "
            f"Missing={missing}; invalid={invalid}; retake_required={retake}. "
            "For each retake item: EITHER run attempt 2 with the SKILL.md §10 "
            "feedback-driven retake flow (use the returned correct_answer_ids from "
            "attempt 1 feedback as ground truth; keep_highest keeps the better score), "
            "OR write a degraded_method_user_consent field (verbatim user authorization, "
            ">=10 chars) into result.json to decline the retake."
        )
    return None


@safe_main
def main() -> None:
    event = read_event()
    if event.get("stop_hook_active"):
        pass_stop()

    reason = None
    if os.environ.get("CODEX_HOOK_SKIP_BATCH") != "1":
        reason = check_batch()
    reason = reason or check_execute_marker()
    if reason:
        block_stop(reason)
    pass_stop()


if __name__ == "__main__":
    main()
