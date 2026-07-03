# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "canvas-pilot-codex"
MANIFEST = PLUGIN / ".codex-plugin" / "plugin.json"

REQUIRED_SKILLS = [
    "canvas-bootstrap",
    "canvas-setup",
    "canvas-scan",
    "canvas-execute",
    "canvas-skip",
    "cc-sync-runner",
    "cc-sync-execute-loop",
]


def main() -> int:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if "manifest-only" not in (data.get("description") or "").lower():
        print("plugin manifest must document manifest-only packaging mode")
        return 1
    declared = data.get("skills") or []
    missing: list[str] = []
    for name in REQUIRED_SKILLS:
        repo_skill = ROOT / ".agents" / "skills" / name / "SKILL.md"
        if not repo_skill.exists():
            missing.append(f"repo skill missing: {name}")
        expected = f"skills/{name}"
        if expected not in declared:
            missing.append(f"plugin manifest missing: {expected}")
    if missing:
        for item in missing:
            print(item)
        return 1
    print("canvas-pilot-codex plugin drift check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
