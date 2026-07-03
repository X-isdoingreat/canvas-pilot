# SPDX-License-Identifier: AGPL-3.0-or-later
"""Router: scan pending Canvas assignments and dispatch to skills.

Usage:
    python -m src.router --dry-run     # only list pending, write assignments.json
    python -m src.router --run         # full execution
    python -m src.router --only <course-id>          # restrict to one course_id
    python -m src.router --assignment <cid>:<aid>    # one specific assignment
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import traceback
from pathlib import Path

import yaml

from . import canvas_client as cv
from . import report as report_mod

ROOT = Path(__file__).resolve().parent.parent
TODAY = dt.date.today().isoformat()
RUN_DIR = ROOT / "runs" / TODAY


def _load_routes() -> dict:
    return yaml.safe_load((ROOT / "courses.yaml").read_text(encoding="utf-8"))


def _is_pending(a: dict, window_days: int) -> bool:
    sub = a.get("submission") or {}
    if sub.get("workflow_state") in ("submitted", "graded"):
        return False
    due = a.get("due_at")
    if not due:
        return False
    try:
        due_dt = dt.datetime.fromisoformat(due.replace("Z", "+00:00"))
    except Exception:
        return False
    now = dt.datetime.now(dt.timezone.utc)
    delta = (due_dt - now).total_seconds()
    if delta < -3600:  # already past due by >1h
        return False
    if delta > window_days * 86400:
        return False
    return True


def _matches_override(assignment: dict, match_spec: dict) -> bool:
    """Returns True if all keys in match_spec match the corresponding fields
    on the assignment. Currently supports list-equality (e.g.
    submission_types: ["online_quiz"]) and scalar equality."""
    for key, expected in match_spec.items():
        actual = assignment.get(key)
        if isinstance(expected, list):
            if not isinstance(actual, list):
                return False
            if set(actual) != set(expected):
                return False
        else:
            if actual != expected:
                return False
    return True


def _resolve_skill(route: dict, assignment: dict) -> str:
    """Apply per-course overrides on top of the default skill."""
    default = route["skill"]
    overrides = route.get("overrides") or []
    for ov in overrides:
        match = ov.get("match") or {}
        if _matches_override(assignment, match):
            return ov["skill"]
    return default


def scan() -> tuple[dict, list[dict]]:
    cfg = _load_routes()
    routes = cfg["routes"]
    window = cfg.get("pending_window_days", 7)
    pending: list[dict] = []
    for course_id, route in routes.items():
        try:
            assignments = cv.list_assignments(course_id)
        except Exception as e:
            print(f"!! list_assignments({course_id}) failed: {e}")
            continue
        for a in assignments:
            if not _is_pending(a, window):
                continue
            pending.append({
                "course_id": str(course_id),
                "course_name": route["name"],
                "skill": _resolve_skill(route, a),
                "assignment_id": str(a.get("id")),
                "name": a.get("name"),
                "due_at": a.get("due_at"),
                "html_url": a.get("html_url"),
                "submission_types": a.get("submission_types"),
                "points_possible": a.get("points_possible"),
            })
    pending.sort(key=lambda x: x.get("due_at") or "")
    return cfg, pending


def dispatch(item: dict) -> dict:
    """Run the appropriate skill on a single assignment. Returns result dict."""
    skill = item["skill"]
    if skill == "ac_english":
        from .skills import ac_english as mod
    elif skill == "code_py":
        from .skills import code_py as mod
    elif skill == "quiz":
        from .skills import quiz as mod
    elif skill == "mixed_unsupported":
        from .skills import mixed_unsupported as mod
    else:
        return {"status": "error", "message": f"unknown skill {skill}"}
    return mod.run(item, RUN_DIR)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--run", action="store_true")
    p.add_argument("--only", help="restrict to one course_id")
    p.add_argument("--assignment", help="format course_id:assignment_id")
    args = p.parse_args()

    RUN_DIR.mkdir(parents=True, exist_ok=True)
    cfg, pending = scan()

    if args.only:
        pending = [x for x in pending if x["course_id"] == args.only]
    if args.assignment:
        cid, aid = args.assignment.split(":")
        pending = [x for x in pending if x["course_id"] == cid and x["assignment_id"] == aid]

    (RUN_DIR / "assignments.json").write_text(json.dumps(pending, indent=2), encoding="utf-8")
    print(f"\n=== {len(pending)} pending assignments ===")
    for it in pending:
        print(f"  [{it['skill']:20}] {it['course_name'][:30]:30} | due {it['due_at']} | {it['name']}")

    if args.dry_run or not args.run:
        print(f"\nDry run only. assignments.json -> {RUN_DIR / 'assignments.json'}")
        return

    # Real run
    results: list[dict] = []
    for it in pending:
        print(f"\n--- {it['course_name']} | {it['name']} ---")
        try:
            r = dispatch(it)
        except Exception as e:
            traceback.print_exc()
            r = {"status": "error", "message": str(e)}
        r.setdefault("item", it)
        results.append(r)

    report_mod.write_report(RUN_DIR, results)
    print(f"\nDone. Report -> {RUN_DIR / 'REPORT.md'}")


if __name__ == "__main__":
    main()
