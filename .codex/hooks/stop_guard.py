# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import datetime as dt
import json
import os

from _lib import (
    ROOT,
    batch_status,
    block_stop,
    current_batch,
    pass_stop,
    read_event,
    safe_main,
    slugify,
    today_dir,
    validate_result_schema,
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
    current_session = os.environ.get("CODEX_SESSION_ID")
    if current_session:
        marker_text = marker.read_text(encoding="utf-8", errors="ignore").strip()
        try:
            marker_data = json.loads(marker_text) if marker_text else {}
        except json.JSONDecodeError:
            marker_data = {}
        marker_session = marker_data.get("session_id") or marker_data.get("owner")
        if marker_session and marker_session != current_session:
            return None
    assignments = today / "assignments.json"
    if not assignments.exists():
        return None
    try:
        items = json.loads(assignments.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(items, list):
        return None

    missing: list[str] = []
    invalid: list[str] = []
    for item in items:
        work = today / f"{slugify(item.get('course_name', ''))}__{slugify(item.get('name', ''))}"
        result = work / "result.json"
        label = f"{item.get('course_id')}:{item.get('assignment_id')} {item.get('name')}"
        if not result.exists():
            missing.append(label)
            continue
        ok, err = validate_result_schema(result.read_text(encoding="utf-8"))
        if not ok:
            invalid.append(f"{label} -> {err}")
    if missing or invalid:
        return (
            "Canvas execute marker is active and assignments are incomplete. "
            f"Missing={missing}; invalid={invalid}."
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
