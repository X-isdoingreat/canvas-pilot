# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import re
from pathlib import Path

from _lib import ROOT, validate_verification_log
from _lib import deny_pretool, read_event, safe_main, git_leak_issue


SUBMIT_CALL = re.compile(
    r"\b(?:cv\.|canvas_client\.|cso\.)?(?:"
    r"submit_files|submit_text|submit_url|upload_submission_file|"
    r"submit_files_with_view|submit_text_with_view|submit_url_with_view|"
    r"upload_and_submit_files_with_view"
    r")\s*\(",
    re.IGNORECASE,
)


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
    leak = git_leak_issue(command)
    if leak:
        deny_pretool(leak)
    # Canvas mutation authority is enforced at the API boundary by signed,
    # exact-target receipts.  This hook only keeps the verification.log gate
    # as defense in depth; it does not guess quiz intent from command substrings.
    looks_executable = bool(re.search(r"\b(?:python(?:\.exe)?|py(?:\.exe)?|uv\s+run|poetry\s+run)\b", command, re.IGNORECASE))
    if looks_executable and SUBMIT_CALL.search(command):
        work = find_work_dir(command)
        if not work:
            deny_pretool("Refuse submit/upload without an identifiable runs/<today>/<work> directory.")
        log = work / "verification.log"
        ok, reason = validate_verification_log(log)
        if not ok:
            deny_pretool(f"Refuse submit/upload: {reason}")


if __name__ == "__main__":
    main()

