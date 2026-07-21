# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / ".agents" / "skills" / "canvas-scan" / "SKILL.md"


def read_skill() -> str:
    assert SKILL.exists(), f"missing {SKILL}"
    return SKILL.read_text(encoding="utf-8")


def assert_pattern(text: str, pattern: str, label: str) -> None:
    assert re.search(pattern, text, re.IGNORECASE | re.MULTILINE), label


def test_frontmatter_and_handoff() -> None:
    text = read_skill()
    assert_pattern(text, r"^name:\s*canvas-scan", "frontmatter")
    assert_pattern(text, r"canvas-skill-opportunity", "opportunity handoff")
    assert_pattern(text, r"representative real specs", "real-spec opportunity evidence")
    assert_pattern(text, r"feedback-policy evidence", "safe feedback-policy evidence")
    assert "from read-only metadata" not in text.lower(), "no metadata-only ranking"
    assert_pattern(text, r"student.*chooses|student replies|selected candidate", "choice before bootstrap")
    assert_pattern(text, r"canvas-bootstrap", "later bootstrap handoff")
    assert_pattern(text, r"routes.*empty|routes.*commented|routes.*None", "empty route handling")
    assert_pattern(text, r"stop", "stop after opportunity analysis")


def test_probe_and_dry_run() -> None:
    text = read_skill()
    assert_pattern(text, r"canvas_client --probe|src\.canvas_client --probe", "auth probe")
    assert_pattern(text, r"router --dry-run|src\.router --dry-run", "router dry-run")
    assert_pattern(text, r"assignments\.json", "assignments snapshot")


def test_no_execute_boundary() -> None:
    text = read_skill()
    assert_pattern(text, r"MUST NOT execute|must not execute|Do not.*execute", "no execute")
    assert_pattern(text, r"MUST NOT write.*result\.json|Do not.*result\.json", "no result")
    assert_pattern(text, r"MUST NOT write.*REPORT\.md|Do not.*REPORT\.md", "no report")
    assert_pattern(text, r"MUST NOT create.*\.scan_in_progress|Do not.*\.scan_in_progress", "no marker")


def test_dedup_live_state_and_plan_schema() -> None:
    text = read_skill()
    assert_pattern(text, r"_processed\.json", "ledger")
    assert_pattern(text, r"deferred_to_next_run", "deferred re-entry")
    assert_pattern(text, r"get_submission", "live submission")
    assert_pattern(text, r"live_state", "live state")
    assert_pattern(text, r"os\.replace|atomic", "atomic write")
    assert_pattern(text, r"generated_at", "generated_at")
    assert_pattern(text, r"expires_at", "expires_at")
    assert_pattern(text, r"user_decision", "user_decision")


def test_student_table() -> None:
    text = read_skill()
    assert_pattern(text, r"Due within 3 days|三天内", "three day table")
    assert_pattern(text, r"Due within 7 days|七天内", "seven day table")
    assert_pattern(text, r"submitted", "submitted column")
    assert_pattern(text, r"Reply all, numbers like 1,3, or skip", "simple prompt")


def test_plan_fixture_sorting_shape() -> None:
    items = [
        {"bucket": "soon", "hours_left": 100, "name": "b"},
        {"bucket": "urgent", "hours_left": 10, "name": "a"},
        {"bucket": "overdue", "hours_left": -2, "name": "c"},
    ]
    priority = {"overdue": 0, "urgent": 1, "soon": 2, "later": 3, "unknown": 4}
    ordered = sorted(items, key=lambda item: (priority[item["bucket"]], item["hours_left"]))
    assert [item["name"] for item in ordered] == ["c", "a", "b"]
    plan = {
        "generated_at": "2026-04-30T00:00:00-07:00",
        "expires_at": "2026-05-01T00:00:00-07:00",
        "items": [
            {
                "index": 1,
                "bucket": "urgent",
                "course_id": 1,
                "course_name": "Course",
                "assignment_id": 2,
                "assignment_name": "Assignment",
                "due_at": "2026-05-01T23:59:00Z",
                "hours_left": 10,
                "live_state": "unsubmitted",
                "proposed_skill": "canvas-example",
                "user_decision": None,
            }
        ],
    }
    encoded = json.dumps(plan)
    assert "generated_at" in encoded
    assert "user_decision" in encoded


def main() -> int:
    tests = [
        test_frontmatter_and_handoff,
        test_probe_and_dry_run,
        test_no_execute_boundary,
        test_dedup_live_state_and_plan_schema,
        test_student_table,
        test_plan_fixture_sorting_shape,
    ]
    failures: list[str] = []
    for test in tests:
        try:
            test()
            print(f"PASS {test.__name__}")
        except Exception as exc:
            failures.append(f"{test.__name__}: {exc}")
            print(f"FAIL {test.__name__}: {exc}")
    if failures:
        print("\nFailures:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
