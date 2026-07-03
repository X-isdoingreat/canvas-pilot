# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "CODEX_ONBOARDING.md"


def read_doc() -> str:
    assert DOC.exists(), f"missing {DOC}"
    return DOC.read_text(encoding="utf-8")


def assert_pattern(text: str, pattern: str, label: str) -> None:
    assert re.search(pattern, text, re.IGNORECASE | re.MULTILINE), label


def test_cookie_auth_path() -> None:
    # Cookie is the only supported auth path. The API-token path was retired
    # 2026-05-15 — onboarding is cookie-only for every school / fork user.
    text = read_doc()
    assert_pattern(text, r"CANVAS_AUTH\s*=\s*cookie", "cookie auth mode")
    assert_pattern(text, r"CANVAS_BASE", "base url")
    assert_pattern(text, r"canvas_login --auto", "browser login")
    assert_pattern(text, r"--probe", "verify probe")


def test_safety_defaults() -> None:
    # The doc must state the fail-closed defaults: draft-only, no Canvas
    # submission, no live quiz action without explicit authorization.
    text = read_doc()
    assert_pattern(text, r"[Dd]raft-only", "draft-only default")
    assert_pattern(text, r"[Nn]o Canvas submission", "no-submission default")
    assert_pattern(text, r"[Nn]o live quiz submission", "no-quiz default")


def test_no_private_ids() -> None:
    text = read_doc()
    assert not re.search(r"course_id\s*[:=]\s*\d{4,}", text, re.IGNORECASE)
    assert not re.search(r"assignment_id\s*[:=]\s*\d{4,}", text, re.IGNORECASE)
    assert not re.search(r"[\w.\-+]+@[\w.\-]+\.edu\b", text, re.IGNORECASE)


def main() -> int:
    tests = [test_cookie_auth_path, test_safety_defaults, test_no_private_ids]
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
