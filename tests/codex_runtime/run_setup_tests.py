# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / ".agents" / "skills" / "canvas-setup" / "SKILL.md"


def read_skill() -> str:
    assert SKILL.exists(), f"missing {SKILL}"
    return SKILL.read_text(encoding="utf-8")


def assert_pattern(text: str, pattern: str, label: str) -> None:
    assert re.search(pattern, text, re.IGNORECASE | re.MULTILINE), label


def test_frontmatter_and_runtime_ready() -> None:
    text = read_skill()
    assert_pattern(text, r"^name:\s*canvas-setup", "frontmatter name")
    assert_pattern(text, r"description:.*first-run Canvas Pilot configuration", "description")
    assert "PLANNED_SKILL_SKELETON v1" not in text


def test_setup_state_matrix() -> None:
    text = read_skill()
    for state in [
        "missing-env",
        "incomplete-canvas-config",
        "auth-configured-empty-routes",
        "complete",
    ]:
        assert_pattern(text, state, state)
    assert_pattern(text, r"canvas-bootstrap", "bootstrap handoff")
    assert_pattern(text, r"canvas-scan", "scan as next user action")


def test_stop_boundaries() -> None:
    text = read_skill()
    assert_pattern(text, r"Do not scan assignments", "no assignment scan")
    assert_pattern(text, r"Do not execute assignments", "no execute")
    assert_pattern(text, r"Do not submit|submit, upload, answer quizzes", "no live actions")
    assert_pattern(text, r"Do not write `assignments\.json`, `plan\.json`, `result\.json`, or `REPORT\.md`", "no run artifacts")
    assert_pattern(text, r"Keep `?\.claude/`? read-only|Keep `?\.claude", "claude read-only")


def test_student_facing_contract() -> None:
    text = read_skill()
    assert_pattern(text, r"Ask the student only domain questions", "domain questions")
    assert_pattern(text, r"Do not tell the student to edit `?\.env", "no manual env edit")
    assert_pattern(text, r"run shell commands", "no shell command instruction")
    assert_pattern(text, r"inspect internal config files", "no internal file instruction")


def test_no_private_ids() -> None:
    text = read_skill()
    assert not re.search(r"course_id\s*[:=]\s*\d{4,}", text, re.IGNORECASE)
    assert not re.search(r"assignment_id\s*[:=]\s*\d{4,}", text, re.IGNORECASE)
    assert not re.search(r"[\w.\-+]+@[\w.\-]+\.edu\b", text, re.IGNORECASE)
    assert not re.search(r"https?://[^\s`)]*canvas[^\s`)]*", text, re.IGNORECASE)


def main() -> int:
    tests = [
        test_frontmatter_and_runtime_ready,
        test_setup_state_matrix,
        test_stop_boundaries,
        test_student_facing_contract,
        test_no_private_ids,
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
