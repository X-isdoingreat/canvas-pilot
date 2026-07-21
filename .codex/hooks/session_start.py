# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import json
import re

from _lib import ROOT, read_event, safe_main, today_dir


def _env_has_canvas_base(env_path) -> bool:
    if not env_path.exists():
        return False
    try:
        lines = env_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return False
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() == "CANVAS_BASE" and v.strip():
            return True
    return False


def _routes_nonempty(yaml_path) -> bool:
    if not yaml_path.exists():
        return False
    try:
        text = yaml_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return False
    in_routes = False
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith("routes:"):
            in_routes = True
            continue
        if not in_routes:
            continue
        if stripped.startswith("#") or not stripped:
            continue
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*:", raw):
            return False
        if re.match(r"^\s+\d+\s*:", raw):
            return True
        if re.match(r"^\s*-", raw):
            return True
    return False


@safe_main
def main() -> None:
    read_event()
    today = today_dir()
    assignments = today / "assignments.json"
    plan = today / "plan.json"
    ledger = ROOT / "runs" / "_processed.json"

    parts = [
        "Codex primary driver active.",
        "Preserve scan -> approval -> execute boundaries.",
        "Do not modify .claude/ unless explicitly asked.",
    ]

    # Setup-state detection (ported from .claude/hooks/check-setup-done.py):
    # nudge dispatching canvas-setup when unconfigured; stay quiet once ready so
    # it does not pester every session.
    env_ok = _env_has_canvas_base(ROOT / ".env")
    routes_ok = _routes_nonempty(ROOT / "courses.yaml")
    if not (env_ok and routes_ok):
        if not env_ok and not routes_ok:
            miss = "first-run setup never happened (no Canvas connection, no course list)"
        elif not env_ok:
            miss = "Canvas connection isn't configured yet"
        else:
            miss = "Canvas connection works but the course list is empty"
        parts.insert(
            0,
            "SETUP NOT READY: " + miss + ". On the student's next message, dispatch the "
            "`canvas-setup` skill (do NOT improvise setup, read SETUP.md aloud, or ask them "
            "to edit files). If their first message is off-topic, answer it first, then offer setup.",
        )
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

