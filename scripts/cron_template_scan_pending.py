# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read-only scheduled Canvas scan executed by a fresh Codex session."""
from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path
from typing import Optional

from scripts.cron_base import (
    PT,
    ROOT,
    RUNS,
    CronInstance,
    ScanTemplate,
    TemplateSpec,
    check_manual_session_active,
)


SPEC = TemplateSpec(
    name="scan_pending",
    kind="scan",
    description="Run canvas-scan in a fresh Codex session; never execute or submit work.",
    param_schema=[],
    execution_time_limit="PT15M",
)


class ScanPending(ScanTemplate):
    CODEX_TIMEOUT_S = 15 * 60

    def pre_run(self, inst: CronInstance, dry_run: bool) -> Optional[str]:
        if dry_run:
            return None
        return check_manual_session_active()

    def classify(self, inst: CronInstance) -> dict:
        """Capture pre-run artifact state without contacting or mutating Canvas."""
        today_dir = RUNS / dt.datetime.now(PT).date().isoformat()
        paths = [
            today_dir / "scan.json",
            today_dir / "plan.json",
            today_dir / "assignments.json",
        ]
        return {
            "today_dir": today_dir,
            "before_mtime_ns": {
                str(path): path.stat().st_mtime_ns if path.exists() else None
                for path in paths
            },
        }

    def build_codex_prompt(self, inst: CronInstance, targets: list[dict]) -> str:
        return f"""[CANVAS_CRON_SCAN_ONLY] This is a scheduled read-only scan.

Working dir: {ROOT}
Configured scope label: course_id={inst.course_id}

Use the canvas-scan skill exactly once. Let it inspect the real Canvas state and write today's scan.json plus assignments.json. When pending items exist it must also write plan.json; when there are no pending items, the documented terminal state is a fresh complete scan.json with an empty assignments.json and no new empty plan. Then stop at the approval boundary.

Hard constraints:
- Do not invoke canvas-execute or any course-solving skill.
- Do not upload, submit, start/answer/complete a quiz, or call any Canvas POST/PUT helper.
- Do not create an authorization receipt; this template intentionally has no mutation authority.
- Do not install, enable, disable, run, or otherwise change a scheduled task.
- Finish with `CRON_SCAN_RESULT: pending_count=<N> plan_written=<true|false> assignments_written=<true|false>`.
"""

    def act_dry(self, inst: CronInstance, classification: dict) -> dict:
        self.log(inst, "  [dry-run] would start one scan-only Codex session")
        return {"would_scan": True}

    def act_real(self, inst: CronInstance, classification: dict) -> dict:
        started_at_ns = time.time_ns()
        exit_code, codex_log = self.fire_codex_session(inst, [], dry_run=False)
        return {
            "exit_code": exit_code,
            "codex_log": codex_log,
            "started_at_ns": started_at_ns,
            "today_dir": classification["today_dir"],
        }

    def verify(self, inst: CronInstance, result: dict) -> dict:
        if int(result.get("exit_code", 1)) != 0:
            return {"ok": False, "reason": "Codex child failed"}
        today_dir = Path(result["today_dir"])
        started_at_ns = int(result.get("started_at_ns", 0))
        missing: list[str] = []
        invalid: list[str] = []
        payloads: dict[str, object] = {}
        for name in ("scan.json", "assignments.json"):
            path = today_dir / name
            if not path.is_file() or path.stat().st_mtime_ns < started_at_ns:
                missing.append(name)
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                invalid.append(name)
                continue
            if not isinstance(payload, (dict, list)):
                invalid.append(name)
                continue
            payloads[name] = payload

        scan = payloads.get("scan.json")
        assignments = payloads.get("assignments.json")
        pending_count: int | None = None
        if isinstance(scan, dict):
            items = scan.get("items")
            if scan.get("complete") is not True or not isinstance(items, list):
                invalid.append("scan.json")
            else:
                pending_count = len(items)
        if isinstance(assignments, list) and pending_count is not None:
            if len(assignments) != pending_count:
                invalid.append("assignments.json:item_count")

        # A zero-pending scan intentionally has no new approval plan.  For a
        # non-empty scan, require a fresh plan and mechanically validate its
        # identity/skill mapping against the fresh snapshot.
        if pending_count:
            plan_path = today_dir / "plan.json"
            if not plan_path.is_file() or plan_path.stat().st_mtime_ns < started_at_ns:
                missing.append("plan.json")
            else:
                try:
                    from src.run_state import validate_plan_assignments

                    plan = json.loads(plan_path.read_text(encoding="utf-8"))
                    validate_plan_assignments(
                        plan, assignments, run_dir=today_dir, require_current=True
                    )
                except Exception:
                    invalid.append("plan.json")
        ok = not missing and not invalid
        if not ok:
            self.log(
                inst,
                f"  scan verification failed: missing_or_stale={missing} invalid={invalid}",
            )
        return {
            "ok": ok,
            "pending_count": pending_count,
            "no_pending": pending_count == 0,
            "missing_or_stale": missing,
            "invalid": invalid,
        }

    def result_exit_code(
        self,
        inst: CronInstance,
        result: dict,
        verification: dict,
    ) -> int:
        child_code = super().result_exit_code(inst, result, verification)
        if child_code != 0:
            return child_code
        return 0 if verification.get("ok") is True else 1


template = ScanPending(SPEC)
