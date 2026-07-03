# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "CODEX_AUTOMATION.md"
WF = ROOT / ".github" / "workflows" / "codex.yml"


def read(path: Path) -> str:
    assert path.exists(), f"missing {path}"
    return path.read_text(encoding="utf-8")


def assert_pattern(text: str, pattern: str, label: str) -> None:
    assert re.search(pattern, text, re.IGNORECASE | re.MULTILINE), label


def test_noninteractive_docs() -> None:
    text = read(DOC)
    assert_pattern(text, r"codex exec", "codex exec")
    assert_pattern(text, r"--batch B", "batch flag")
    assert_pattern(text, r"non-interactive", "non-interactive")


def test_least_privilege_ci() -> None:
    text = read(WF)
    assert_pattern(text, r"permissions:", "permissions")
    assert_pattern(text, r"contents:\s*read", "contents read")
    assert_pattern(text, r"pull-requests:\s*write", "pr write")


def test_no_committed_auth() -> None:
    text = read(DOC) + "\n" + read(WF)
    assert_pattern(text, r"Never commit", "never commit warning")
    assert_pattern(text, r"\.cookies|CANVAS_TOKEN", "auth warning")


def main() -> int:
    tests = [test_noninteractive_docs, test_least_privilege_ci, test_no_committed_auth]
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
