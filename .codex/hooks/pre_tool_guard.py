# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import re
from pathlib import Path

from _lib import ROOT, validate_verification_log
from _lib import deny_pretool, read_event, safe_main


SUBMIT_PATTERNS = [
    "submit_files",
    "upload_submission_file",
    "canvas_client.submit",
    "canvas_client upload",
    "canvas submit",
]

QUIZ_LIVE_PATTERNS = [
    "submit_quiz",
    "complete_quiz",
    "answer_quiz",
    "start_quiz",
    "retake_quiz",
]


def find_work_dir(command: str) -> Path | None:
    matches = re.findall(r"runs[/\\][^\s\"']+", command)
    for match in matches:
        p = Path(match)
        if not p.is_absolute():
            p = ROOT / p
        if p.name == "verification.log":
            return p.parent
        if p.suffix:
            return p.parent
        return p
    return None


@safe_main
def main() -> None:
    event = read_event()
    if event.get("tool_name") != "Bash":
        return
    tool_input = event.get("tool_input") or {}
    command = str(tool_input.get("command") or "")
    compact = " ".join(command.lower().split())

    if "git push upstream" in compact:
        deny_pretool("Refuse upstream push until public/private boundary checks pass.")
    if "git push --all" in compact:
        deny_pretool("Refuse git push --all from Codex sidecar.")
    if "remove-item" in compact and ".claude" in compact:
        deny_pretool("Refuse destructive command touching .claude from Codex sidecar.")
    if any(pattern in compact for pattern in QUIZ_LIVE_PATTERNS):
        deny_pretool("Refuse live quiz action from public Codex sidecar; fail closed to manual/deferred handling.")
    if any(pattern in compact for pattern in SUBMIT_PATTERNS):
        work = find_work_dir(command)
        if not work:
            deny_pretool("Refuse submit/upload without an identifiable runs/<today>/<work> directory.")
        log = work / "verification.log"
        ok, reason = validate_verification_log(log)
        if not ok:
            deny_pretool(f"Refuse submit/upload: {reason}")


if __name__ == "__main__":
    main()

