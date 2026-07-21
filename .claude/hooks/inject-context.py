# SPDX-License-Identifier: AGPL-3.0-or-later
"""SessionStart hook: inject Canvas project context into Claude's prompt.

stdout from a SessionStart hook is shown to Claude as additional context
(unlike most other events where stdout goes to debug log).

We inject:
1. The North Star pointer (canvas-skill.md section0.5)
2. Today's pending list summary (or "no scan run today" if assignments.json missing)
3. _processed.json status counts
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import ROOT, today_dir, read_event, safe_main  # noqa: E402


@safe_main
def main():
    # We don't actually care about the event JSON for SessionStart, but read it
    # so the pipe doesn't break.
    _ = read_event()

    lines = []
    lines.append("=" * 70)
    lines.append("CANVAS SKILL — autonomous homework system")
    lines.append("=" * 70)
    lines.append("")
    lines.append("You are running in the Canvas Skill project. Your job is to scan")
    lines.append("your school's Canvas for pending assignments and dispatch each to the right")
    lines.append("course-specific skill. Read canvas-skill.md section0.5 for the North Star.")
    lines.append("")
    lines.append("ESSENTIAL CONTEXT:")
    lines.append("- Working directory: " + str(ROOT))
    lines.append("- Project doc: canvas-skill.md (read section0.5 first)")
    lines.append("- Skills: .claude/skills/canvas-{router,ics33,ac-eng,quiz,skip}/SKILL.md")
    lines.append("- API client: src/canvas_client.py (probe + assignments + files + quizzes + upload/submit)")
    lines.append("- Daily output: runs/<today>/")
    lines.append("- Cross-day dedup ledger: runs/_processed.json")
    lines.append("")

    # Today's pending state
    today = today_dir()
    aj = today / "assignments.json"
    if aj.exists():
        try:
            items = json.loads(aj.read_text(encoding="utf-8"))
            lines.append(f"TODAY'S PENDING SCAN ({today.name}): {len(items)} items")
            for item in items[:30]:
                marker = ""
                wd = today / _slugify(item.get("course_name", "")) / _slugify(item.get("name", ""))
                # Two patterns of work_dir naming
                wd1 = today / f"{_slugify(item.get('course_name',''))}__{_slugify(item.get('name',''))}"
                rj = wd1 / "result.json"
                if rj.exists():
                    try:
                        r = json.loads(rj.read_text(encoding="utf-8"))
                        marker = f" [{r.get('status', '?')}]"
                    except Exception:
                        marker = " [result.json unreadable]"
                else:
                    marker = " [PENDING]"
                lines.append(
                    f"  - {item.get('skill','?'):18} | {item.get('course_name','?')[:24]:24} | "
                    f"{item.get('name','?')[:50]}{marker}"
                )
            if len(items) > 30:
                lines.append(f"  ... and {len(items) - 30} more")
        except Exception as e:
            lines.append(f"TODAY'S PENDING SCAN: failed to read assignments.json: {e}")
    else:
        lines.append("TODAY'S PENDING SCAN: not run yet today.")
        lines.append("First action should be: invoke canvas-scan skill (which runs the dry-run + produces plan.json).")

    lines.append("")

    # Cross-day ledger summary
    pj = ROOT / "runs" / "_processed.json"
    if pj.exists():
        try:
            ledger = json.loads(pj.read_text(encoding="utf-8"))
            real = {k: v for k, v in ledger.items() if not k.startswith("_")}
            counts = {}
            for v in real.values():
                if isinstance(v, dict):
                    counts[v.get("status", "?")] = counts.get(v.get("status", "?"), 0) + 1
            lines.append(f"CROSS-DAY LEDGER ({len(real)} items): {counts}")
        except Exception as e:
            lines.append(f"CROSS-DAY LEDGER: unreadable: {e}")
    else:
        lines.append("CROSS-DAY LEDGER: empty (no prior runs)")

    lines.append("")
    lines.append("HOOK GUARDRAILS ACTIVE:")
    lines.append("- After every Write/Edit, hook validates result.json schema if path matches")
    lines.append("- After every Bash, hook validates pytest/coverage/git output where applicable")
    lines.append("- On Stop, hook checks every assignment in assignments.json has a valid result.json")
    lines.append("  → if any are missing you will be required to continue and produce them.")
    lines.append("")
    lines.append("=" * 70)

    print("\n".join(lines))


def _slugify(s: str) -> str:
    import re
    s = re.sub(r"[^A-Za-z0-9_\- ]", "", s or "")
    return re.sub(r"\s+", "_", s).strip("_")[:60] or "untitled"


if __name__ == "__main__":
    main()
