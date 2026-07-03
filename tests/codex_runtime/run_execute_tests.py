# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / ".agents" / "skills" / "canvas-execute" / "SKILL.md"


def read_skill() -> str:
    assert SKILL.exists(), f"missing {SKILL}"
    return SKILL.read_text(encoding="utf-8")


def assert_pattern(text: str, pattern: str, label: str) -> None:
    assert re.search(pattern, text, re.IGNORECASE | re.MULTILINE), label


def test_preconditions_and_approval() -> None:
    text = read_skill()
    assert_pattern(text, r"plan\.json", "plan")
    assert_pattern(text, r"assignments\.json", "assignments")
    assert_pattern(text, r"expires_at|expired", "expiration")
    assert_pattern(text, r"approve all", "approve all")
    assert_pattern(text, r"urgent only", "urgent only")
    assert_pattern(text, r"range|1-4", "range")
    assert_pattern(text, r"swap", "swap")
    assert_pattern(text, r"defer|cancel", "defer/cancel")


def test_marker_dispatch_and_results() -> None:
    text = read_skill()
    assert_pattern(text, r"\.scan_in_progress", "marker")
    assert_pattern(text, r"sequential|one at a time", "sequential")
    assert_pattern(text, r"Skill tool|Dispatch via the Skill", "skill dispatch")
    assert_pattern(text, r"result\.json", "result json")
    assert_pattern(text, r"_processed\.json", "ledger")
    assert_pattern(text, r"os\.replace|atomically", "atomic writes")


def test_unapproved_deferred_and_no_submit() -> None:
    text = read_skill()
    assert_pattern(text, r"not approved this run", "not approved")
    assert_pattern(text, r"deferred_to_next_run", "deferred retry")
    assert_pattern(text, r"skipped", "skipped")
    assert_pattern(text, r"Do not submit|Never.*submit|Do not submit to Canvas by default", "no submit")
    assert_pattern(text, r"Do not execute unapproved", "no unapproved execution")


def test_report_error_delivery_finalize() -> None:
    text = read_skill()
    assert_pattern(text, r"REPORT\.md", "report")
    assert_pattern(text, r"urgent banner", "urgent banner")
    assert_pattern(text, r"Error Help Section|debug-help", "error help")
    assert_pattern(text, r"skeleton sentinel", "error checklist sentinel")
    assert_pattern(text, r"Delivery Sync|delivery folder", "delivery sync")
    assert_pattern(text, r"removed", "marker removal")


def parse_approval(spec: str, indices: list[int], buckets: dict[int, str]) -> dict[int, str]:
    s = spec.lower().strip()
    if s in {"all", "approve all"}:
        return {i: "approve" for i in indices}
    if s == "urgent only":
        return {i: ("approve" if buckets.get(i) == "urgent" else "defer") for i in indices}
    if s == "cancel":
        return {i: "defer" for i in indices}
    m = re.fullmatch(r"(\d+)-(\d+)", s)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        return {i: ("approve" if lo <= i <= hi else "defer") for i in indices}
    nums = [int(x) for x in re.findall(r"\d+", s)]
    return {i: ("approve" if i in nums else "defer") for i in indices}


def test_approval_fixture() -> None:
    indices = [1, 2, 3]
    buckets = {1: "urgent", 2: "soon", 3: "urgent"}
    assert parse_approval("approve all", indices, buckets) == {1: "approve", 2: "approve", 3: "approve"}
    assert parse_approval("urgent only", indices, buckets) == {1: "approve", 2: "defer", 3: "approve"}
    assert parse_approval("1-2", indices, buckets) == {1: "approve", 2: "approve", 3: "defer"}
    assert parse_approval("cancel", indices, buckets) == {1: "defer", 2: "defer", 3: "defer"}


def test_result_fixture() -> None:
    result = {"status": "skipped", "notes": "not approved this run", "deferred_to_next_run": True}
    encoded = json.dumps(result)
    assert "skipped" in encoded
    assert "deferred_to_next_run" in encoded


def main() -> int:
    tests = [
        test_preconditions_and_approval,
        test_marker_dispatch_and_results,
        test_unapproved_deferred_and_no_submit,
        test_report_error_delivery_finalize,
        test_approval_fixture,
        test_result_fixture,
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
