# SPDX-License-Identifier: AGPL-3.0-or-later
"""SessionStart hook: dispatch canvas-setup on a fresh repo, otherwise stay silent.

Detects whether the project has been configured by the student yet:

- `.env` missing or `CANVAS_BASE` empty/blank → never configured
- `courses.yaml` missing or `routes:` empty/all-commented → never finished setup
- both filled → already configured, hook stays silent (does NOT pester the user
  every session — that was the very behavior we wrote canvas-setup to replace)

When the repo is unconfigured, this hook prints a context message that nudges
Claude to dispatch the `canvas-setup` skill on the student's next prompt. It does
NOT instruct the student to run any command — it tells Claude what to do.

Output goes to stdout: SessionStart hook stdout is shown to Claude as additional
context (unlike most other events where stdout is debug-only).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import ROOT, read_event, safe_main  # noqa: E402


def _env_has_canvas_base(env_path: Path) -> bool:
    if not env_path.exists():
        return False
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() == "CANVAS_BASE" and v.strip():
            return True
    return False


def _routes_nonempty(yaml_path: Path) -> bool:
    if not yaml_path.exists():
        return False
    text = yaml_path.read_text(encoding="utf-8")
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
def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    _ = read_event()

    env_ok = _env_has_canvas_base(ROOT / ".env")
    routes_ok = _routes_nonempty(ROOT / "courses.yaml")

    if env_ok and routes_ok:
        return

    if not env_ok and not routes_ok:
        what_is_missing = "first-run setup never happened (no Canvas connection, no course list)"
    elif not env_ok:
        what_is_missing = "Canvas connection isn't configured yet"
    else:
        what_is_missing = "Canvas connection works but the course list is empty"

    print("\n".join([
        "",
        "=" * 70,
        "Canvas Pilot setup state: NOT READY",
        "=" * 70,
        "",
        f"Detected: {what_is_missing}.",
        "",
        "When the student sends their next message — even if it's just 'hi' or",
        "'scan canvas' — dispatch the `canvas-setup` skill via the Skill tool.",
        "That skill walks them through a fixed first-run flow and then hands off",
        "to canvas-bootstrap. Do NOT improvise a setup conversation; do NOT read",
        "SETUP.md to them; do NOT ask them to edit files or run commands.",
        "canvas-setup is the entry point.",
        "",
        "If the student's first message is clearly off-topic (a question about",
        "the project, the README, etc.), answer their question first, then",
        "offer to run setup.",
        "=" * 70,
        "",
    ]))


if __name__ == "__main__":
    main()
