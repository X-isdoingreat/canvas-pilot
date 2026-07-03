# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / ".agents" / "skills" / "canvas-bootstrap" / "SKILL.md"


def read_skill() -> str:
    assert SKILL.exists(), f"missing {SKILL}"
    return SKILL.read_text(encoding="utf-8")


def assert_pattern(text: str, pattern: str, label: str) -> None:
    assert re.search(pattern, text, re.IGNORECASE | re.MULTILINE), label


def test_frontmatter() -> None:
    text = read_skill()
    assert_pattern(text, r"^name:\s*canvas-bootstrap", "frontmatter name")
    assert_pattern(text, r"^description:", "frontmatter description")


def test_empty_routes_and_fingerprints() -> None:
    text = read_skill()
    assert_pattern(text, r"routes.*empty|routes.*commented|first", "empty routes path")
    assert_pattern(text, r"courses\.yaml", "courses.yaml")
    assert_pattern(text, r"bucket_recurring", "bucket_recurring")
    assert_pattern(text, r"min_freq=3", "min_freq=3")
    assert_pattern(text, r"patterns", "patterns")
    assert_pattern(text, r"is_course_active|ended courses|7-day", "active course filter")


def test_course_triage_buckets() -> None:
    text = read_skill()
    assert_pattern(text, r"`main`", "main bucket")
    assert_pattern(text, r"`likely-real`", "likely-real bucket")
    assert_pattern(text, r"`noise`", "noise bucket")
    assert_pattern(text, r"Noise courses are hidden from default mapping|hidden by default", "noise hidden")
    assert_pattern(text, r"lower-confidence|too little history", "likely-real lower confidence")


def test_generated_skeleton_guard() -> None:
    text = read_skill()
    assert_pattern(text, r"UNFILLED_SKELETON", "skeleton sentinel")
    assert_pattern(text, r"STOP if you are Codex", "dispatch stop guard")
    assert_pattern(text, r"deferred_to_next_run=true", "deferred result")
    assert_pattern(text, r"verification\.log", "verification log")
    assert_pattern(text, r"result\.json", "result json")


def test_public_side_only() -> None:
    text = read_skill()
    assert ".agents/skills/canvas-" in text
    assert_pattern(text, r"Do not write `?\.claude|Do not write \.claude", "no .claude writes")
    assert_pattern(text, r"private", "private boundary")


def mapping_is_single_course(numbers: list[int], lookup: dict[int, tuple[str, int]]) -> bool:
    return len({lookup[n][1] for n in numbers}) == 1


def test_cross_course_rejection_fixture() -> None:
    text = read_skill()
    assert_pattern(text, r"cross-course|different courses|one skill maps to one course", "cross-course rule")
    lookup = {
        1: ("pattern", 101),
        2: ("pattern", 101),
        3: ("pattern", 202),
        4: ("course", 303),
    }
    assert mapping_is_single_course([1, 2], lookup)
    assert not mapping_is_single_course([1, 3], lookup)
    assert not mapping_is_single_course([2, 4], lookup)


def main() -> int:
    tests = [
        test_frontmatter,
        test_empty_routes_and_fingerprints,
        test_course_triage_buckets,
        test_generated_skeleton_guard,
        test_public_side_only,
        test_cross_course_rejection_fixture,
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
