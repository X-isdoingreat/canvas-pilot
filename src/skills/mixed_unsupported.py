# SPDX-License-Identifier: AGPL-3.0-or-later
"""Mixed/unsupported skill (the zyBooks math course etc.). Records to todo.md, doesn't do work."""
from __future__ import annotations

from pathlib import Path

from .base import Skill, html_to_text


class MixedUnsupportedSkill(Skill):
    name = "mixed_unsupported"

    def draft(self) -> dict:
        a = self.assignment or {}
        desc = html_to_text(a.get("description"))[:400]
        has_zybooks = "zybook" in (a.get("description") or "").lower()
        todo_path = self.run_dir / "todo.md"
        with open(todo_path, "a", encoding="utf-8") as f:
            f.write(f"## {self.item['course_name']} / {self.item['name']}\n")
            f.write(f"- due: {self.item['due_at']}\n")
            f.write(f"- url: {a.get('html_url')}\n")
            f.write(f"- submission_types: {a.get('submission_types')}\n")
            f.write(f"- zybooks: {has_zybooks}\n")
            f.write(f"- description (excerpt):\n\n  > {desc}\n\n")
        return {
            "status": "skipped",
            "notes": "logged to todo.md (zybooks/unsupported)" if has_zybooks else "logged to todo.md",
        }


def run(item: dict, run_dir: Path) -> dict:
    return MixedUnsupportedSkill(item, run_dir).run()
