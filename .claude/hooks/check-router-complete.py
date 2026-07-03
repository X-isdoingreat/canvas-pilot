# SPDX-License-Identifier: AGPL-3.0-or-later
"""Stop hook: the closeout gate.

When a Claude session wants to stop, this hook verifies that every assignment
in today's assignments.json has a corresponding result.json with a valid status.
If any are missing, exit 2 + stderr forces Claude to keep going.

To prevent infinite loops, we honor the `stop_hook_active` flag in the event.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import (  # noqa: E402
    block,
    passthrough,
    read_event,
    safe_main,
    today_dir,
    validate_result_schema,
)


def slugify(s: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_\- ]", "", s or "")
    return re.sub(r"\s+", "_", s).strip("_")[:60] or "untitled"


@safe_main
def main():
    event = read_event()

    # Avoid infinite loops: if we already blocked once and Claude is back here,
    # let it stop. The CC docs say this flag is set when the previous Stop was
    # blocked by a hook.
    if event.get("stop_hook_active"):
        passthrough("hook check-router-complete: stop_hook_active=true, releasing")

    today = today_dir()

    # ONLY gate the session that created the marker. The marker file's
    # contents are the creating session's session_id. If a different session
    # in the same project (e.g. a debug session that never invoked
    # canvas-execute) checks this marker, it sees the mismatch and passes
    # through, instead of being held hostage by another session's incomplete
    # execute run. (canvas-scan never creates this marker — scan produces
    # plan.json and ends cleanly with no gate.)
    marker = today / ".scan_in_progress"
    if not marker.exists():
        passthrough(
            "hook check-router-complete: no .scan_in_progress marker, "
            "this session is not in router mode, releasing"
        )

    try:
        marker_session_id = marker.read_text(encoding="utf-8").strip()
    except Exception:
        marker_session_id = ""

    current_session_id = (event.get("session_id") or "").strip()

    # Session-scope check: marker was created by a different session.
    # Pass through — that session is responsible for its own gate.
    # Empty marker (legacy / write failure) falls through to the strict gate
    # below; it's safer to over-gate than to under-gate when ownership is
    # unknown.
    if marker_session_id and current_session_id and marker_session_id != current_session_id:
        passthrough(
            f"hook check-router-complete: marker owned by different session "
            f"({marker_session_id[:8]}...), this session ({current_session_id[:8]}...) "
            "passes through"
        )

    aj = today / "assignments.json"
    if not aj.exists():
        # Marker exists but assignments.json doesn't — router started but
        # crashed before scanning. Let it stop with a warning.
        passthrough("hook check-router-complete: marker exists but no assignments.json, releasing")

    try:
        items = json.loads(aj.read_text(encoding="utf-8"))
    except Exception as e:
        # Don't block stop just because the json is bad — surface but pass
        passthrough(f"hook check-router-complete: assignments.json unreadable ({e}), passing")

    if not isinstance(items, list) or not items:
        passthrough("hook check-router-complete: assignments.json empty, nothing to verify")

    missing = []
    invalid = []

    for item in items:
        course_slug = slugify(item.get("course_name", ""))
        asg_slug = slugify(item.get("name", ""))
        wd = today / f"{course_slug}__{asg_slug}"
        rj = wd / "result.json"

        if not rj.exists():
            missing.append({
                "course_id": item.get("course_id"),
                "assignment_id": item.get("assignment_id"),
                "name": item.get("name"),
                "skill": item.get("skill"),
                "expected_path": str(rj.relative_to(today.parent.parent)),
            })
            continue

        try:
            content = rj.read_text(encoding="utf-8")
            ok, err = validate_result_schema(content, rj)
            if not ok:
                invalid.append({
                    "name": item.get("name"),
                    "path": str(rj.relative_to(today.parent.parent)),
                    "error": err,
                })
        except Exception as e:
            invalid.append({
                "name": item.get("name"),
                "path": str(rj.relative_to(today.parent.parent)),
                "error": f"could not read: {e}",
            })

    # Quiz §10 retake gate: any quiz result.json with status=submitted
    # whose score is below 95% AND has attempts left AND policy=keep_highest
    # blocks Stop. Gives the session an explicit retake-or-acknowledge fork.
    retake_required = []
    for item in items:
        if item.get("skill") != "quiz":
            continue
        course_slug = slugify(item.get("course_name", ""))
        asg_slug = slugify(item.get("name", ""))
        wd = today / f"{course_slug}__{asg_slug}"
        rj = wd / "result.json"
        if not rj.exists():
            continue
        try:
            r = json.loads(rj.read_text(encoding="utf-8"))
        except Exception:
            continue
        if r.get("status") != "submitted":
            continue
        # Explicit override field — CEO can decline retake
        consent = r.get("degraded_method_user_consent")
        if isinstance(consent, str) and len(consent.strip()) >= 10:
            continue
        kept = r.get("kept_score")
        max_pts = r.get("points_possible")
        attempts_used = r.get("attempts_used")
        allowed_attempts = r.get("allowed_attempts")
        policy = r.get("scoring_policy")
        if not isinstance(kept, (int, float)) or not isinstance(max_pts, (int, float)) or max_pts <= 0:
            continue
        if not isinstance(attempts_used, int) or not isinstance(allowed_attempts, int):
            continue
        if policy != "keep_highest":
            continue
        ratio = kept / max_pts
        if ratio >= 0.95:
            continue
        if attempts_used >= allowed_attempts:
            continue
        retake_required.append({
            "name": item.get("name"),
            "course_id": item.get("course_id"),
            "kept": kept,
            "max": max_pts,
            "pct": round(ratio * 100, 1),
            "attempts_used": attempts_used,
            "allowed_attempts": allowed_attempts,
            "path": str(rj.relative_to(today.parent.parent)),
        })

    if not missing and not invalid and not retake_required:
        passthrough(f"hook check-router-complete: all {len(items)} assignments accounted for")

    msg_lines = ["hook check-router-complete: SESSION CANNOT STOP YET."]
    msg_lines.append("")

    if missing:
        msg_lines.append(f"{len(missing)} assignment(s) have no result.json:")
        for m in missing:
            msg_lines.append(
                f"  - {m['course_id']}:{m['assignment_id']} | "
                f"skill={m['skill']} | {m['name']}"
            )
            msg_lines.append(f"      expected at: {m['expected_path']}")
        msg_lines.append("")
        msg_lines.append(
            "→ For each missing assignment, you must EITHER invoke the appropriate "
            "sub-skill (canvas-ics33 / canvas-reading-annotation / canvas-inside / canvas-skip) "
            "OR write a result.json directly with status='skipped' + notes explaining "
            "why this assignment cannot be done now."
        )
        msg_lines.append("")

    if invalid:
        msg_lines.append(f"{len(invalid)} result.json file(s) are invalid:")
        for inv in invalid:
            msg_lines.append(f"  - {inv['name']}")
            msg_lines.append(f"      path: {inv['path']}")
            msg_lines.append(f"      → {inv['error']}")
        msg_lines.append("")
        msg_lines.append("→ Fix the schemas above before stopping.")

    if retake_required:
        msg_lines.append(
            f"{len(retake_required)} quiz(zes) require retake per SKILL.md §10:"
        )
        for r in retake_required:
            msg_lines.append(
                f"  - {r['name']} | kept {r['kept']}/{r['max']} = {r['pct']}% | "
                f"attempts {r['attempts_used']}/{r['allowed_attempts']} | "
                f"policy=keep_highest"
            )
            msg_lines.append(f"      path: {r['path']}")
        msg_lines.append("")
        msg_lines.append(
            "→ For each quiz above, EITHER (a) run attempt 2 with the §10 "
            "feedback-driven retake flow (call cv.get_quiz_attempt_feedback after "
            "attempt 1, use returned correct_answer_ids as ground truth for the "
            "answer rewrites the wrong qnums; under keep_highest the better "
            "score wins), OR (b) write a degraded_method_user_consent field "
            "into result.json with the verbatim user authorization quote "
            "explaining why retake is being declined."
        )
        msg_lines.append("")

    msg_lines.append("")
    msg_lines.append("After fixing, you can attempt to stop again.")

    block("\n".join(msg_lines))


if __name__ == "__main__":
    main()
