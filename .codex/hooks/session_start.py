# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import json

from _lib import ROOT, read_event, safe_main, today_dir


@safe_main
def main() -> None:
    read_event()
    today = today_dir()
    assignments = today / "assignments.json"
    plan = today / "plan.json"
    ledger = ROOT / "runs" / "_processed.json"

    parts = [
        "Codex sidecar driver active.",
        "Preserve scan -> approval -> execute boundaries.",
        "Do not modify .claude/ unless explicitly asked.",
    ]
    if assignments.exists():
        try:
            items = json.loads(assignments.read_text(encoding="utf-8"))
            parts.append(f"Today assignments: {len(items)} item(s).")
        except Exception:
            parts.append("Today assignments: unreadable assignments.json.")
    else:
        parts.append("Today assignments: no assignments.json yet.")
    parts.append(f"Plan exists: {'yes' if plan.exists() else 'no'}.")
    parts.append(f"Ledger exists: {'yes' if ledger.exists() else 'no'}.")

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": "\n".join(parts),
        }
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()

