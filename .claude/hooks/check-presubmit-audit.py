# SPDX-License-Identifier: AGPL-3.0-or-later
"""PreToolUse(Bash) hook: pre-submit audit gate.

Blocks any Bash command that looks like a Canvas upload
(cv.submit_files / cv.upload_submission_file / submit_quiz / the
upload_and_submit_files_with_view wrapper) unless the work directory for
the assignment being submitted has a verification.log with all PASS.

This is the deterministic-checklist gate from canvas-ics33 SKILL.md §audit:
no upload without a recorded constraints checklist that shows every line
passed.

Match is loose because Claude might submit via a variety of Python one-liners.
We trigger on any Bash command containing both 'cv.' and one of the submit
function names, or any reference to `upload_and_submit_files_with_view`.

Heuristics for locating the work_dir:
1. If the command mentions a path like 'runs/YYYY-MM-DD/<slug>/' we use that.
2. Else we look at every runs/<today>/ subdir with a result.json whose status
   is in {draft_ready, submitted}.
"""
from __future__ import annotations

import datetime as dt
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import block, passthrough, read_event, safe_main, ROOT  # noqa: E402


SUBMIT_RE = re.compile(
    r"(cv\.submit_files|cv\.upload_submission_file|submit_quiz|"
    r"upload_and_submit_files_with_view|canvas_client.*submit)",
    re.IGNORECASE,
)
PATH_RE = re.compile(r"runs/(\d{4}-\d{2}-\d{2})/([^/\"'\s\\]+)")


@safe_main
def main():
    event = read_event()
    if not event or event.get("tool_name") != "Bash":
        passthrough()

    tool_input = event.get("tool_input") or {}
    command = tool_input.get("command", "")
    if not SUBMIT_RE.search(command):
        passthrough()

    # Find the work_dir(s) being submitted
    m = PATH_RE.search(command)
    work_dirs: list[Path] = []
    if m:
        wd = ROOT / "runs" / m.group(1) / m.group(2)
        if wd.exists():
            work_dirs.append(wd)
    else:
        today = dt.date.today().isoformat()
        today_root = ROOT / "runs" / today
        if today_root.exists():
            for d in today_root.iterdir():
                if d.is_dir() and (d / "result.json").exists():
                    work_dirs.append(d)

    if not work_dirs:
        # Can't locate the work dir — fail open (let it through) but log.
        passthrough("presubmit audit: could not locate work_dir for command, passing through")

    missing: list[Path] = []
    incomplete: list[tuple[Path, list[str], int]] = []
    for wd in work_dirs:
        vlog = wd / "verification.log"
        if not vlog.exists():
            missing.append(wd)
            continue
        content = vlog.read_text(encoding="utf-8", errors="ignore")
        fail_lines = [l for l in content.splitlines() if "FAIL" in l.upper()]
        pass_lines = [l for l in content.splitlines() if "PASS" in l.upper()]
        if fail_lines or not pass_lines:
            incomplete.append((wd, fail_lines, len(pass_lines)))

    if not missing and not incomplete:
        passthrough(f"presubmit audit: {len(work_dirs)} work_dir(s) verified")

    lines = ["hook check-presubmit-audit: CANVAS UPLOAD BLOCKED.", ""]

    if missing:
        lines.append(f"{len(missing)} work_dir(s) have NO verification.log:")
        for wd in missing:
            lines.append(f"  - {wd.relative_to(ROOT).as_posix()}/verification.log (missing)")
        lines.append("")

    if incomplete:
        lines.append(f"{len(incomplete)} work_dir(s) have FAIL lines or empty verification.log:")
        for wd, fails, npass in incomplete:
            lines.append(f"  - {wd.relative_to(ROOT).as_posix()} (fails={len(fails)}, passes={npass})")
            for f in fails[:3]:
                lines.append(f"      {f.strip()}")
        lines.append("")

    lines.append(
        "→ For every item being submitted, run the audit stage from the "
        "relevant per-course SKILL.md (canvas-ics33 §audit, canvas-inside §verify, "
        "etc.) and write a verification.log in the work_dir with one line per "
        "constraint (e.g. 'PASS spec sentence limit <=3, measured=2'). Every "
        "constraint must say PASS before submit is allowed."
    )
    lines.append("")
    lines.append(
        "To bypass deliberately (with risk): delete this hook file or rename "
        "it so it doesn't trigger before the upload."
    )
    block("\n".join(lines))


if __name__ == "__main__":
    main()
