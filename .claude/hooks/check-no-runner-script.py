# SPDX-License-Identifier: AGPL-3.0-or-later
"""PreToolUse(Write|Edit) hook: ban ad-hoc runner scripts under runs/.

Background: on 2026-05-02, an LLM agent under time pressure dropped a one-off
Python script `runs/2026-05-02/_run_quiz_s7.py` that bypassed the entire
canvas-inside SKILL.md flow (hardcoded answers, no 4-agent arbitration, no
retake). It got 14/20 vs class median 19. This hook makes the file shape
that started it all unwritable.

Block rule: any Write/Edit whose target path matches `runs/**/_*.py`,
`runs/**/_*.sh`, or `runs/**/run.py` is rejected. Files inside a work_dir
that don't start with underscore (study_notes.md, final_answers.json,
quiz_meta.json, the agent_passes/ JSON files, etc.) are unaffected.

This is Layer 3 of the three-layer defense from
`C:\\Users\\32247\\.claude\\plans\\subagent-skill-rustling-haven.md`. Layer 1
is canvas_client._require_canonical_arbitration_evidence; Layer 2 is the
Stop hook §10 retake gate in check-router-complete.py. Removing this layer
still leaves the other two — but this layer is the cheapest and catches
the literal pattern that caused the incident.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import (  # noqa: E402
    block,
    passthrough,
    read_event,
    safe_main,
)


# Match POSIX-normalized paths under runs/ that look like one-off runners.
_BANNED_PATTERNS = [
    # `runs/<anything>/_<name>.py` and same for .sh — leading underscore
    # is the de-facto "ad-hoc runner" naming convention used in the incident
    re.compile(r"(^|/)runs/.+/_[^/]+\.(py|sh)$"),
    # `runs/<anything>/run.py` or `run_*.py` — generic runner names too
    re.compile(r"(^|/)runs/.+/run(_[^/]*)?\.py$"),
]


@safe_main
def main():
    event = read_event()
    if not event:
        passthrough()

    tool_name = event.get("tool_name")
    if tool_name not in ("Write", "Edit"):
        passthrough()

    tool_input = event.get("tool_input") or {}
    file_path = tool_input.get("file_path") or ""
    if not file_path:
        passthrough()

    # Normalize to POSIX-style for stable regex matching across Windows
    posix_path = Path(file_path).as_posix()

    matched = next((p for p in _BANNED_PATTERNS if p.search(posix_path)), None)
    if matched is None:
        passthrough(f"hook check-no-runner-script: {posix_path} OK")

    block(
        "BLOCKED: ad-hoc runner script under runs/ — pattern matches "
        f"{matched.pattern!r}.\n\n"
        f"  path: {posix_path}\n\n"
        "Background: on 2026-05-02, a one-off `runs/2026-05-02/_run_quiz_s7.py` "
        "bypassed the entire canvas-inside SKILL.md flow (hardcoded answers, "
        "no 4-agent arbitration). The quiz got 14/20 vs class median 19. "
        "That file shape is now banned.\n\n"
        "If you need to submit a quiz, follow .claude/skills/canvas-inside/SKILL.md "
        "§7 (4-agent arbitration → final_answers.json + agent_passes/) → §8 "
        "(paced submission with per-question events) → §9 complete → §10 retake "
        "decision. The canvas_client.complete_quiz_submission gate (Layer 1) will "
        "ALSO refuse the call if you skip §7, so renaming this file won't help — "
        "do the actual flow.\n\n"
        "If you genuinely need a one-off helper script, put it in src/ where "
        "the user can audit it before it runs."
    )


if __name__ == "__main__":
    main()
