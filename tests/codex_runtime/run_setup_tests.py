# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / ".agents" / "skills" / "canvas-setup" / "SKILL.md"
REQUIREMENTS = ROOT / "requirements.txt"
GITIGNORE = ROOT / ".gitignore"
ENV_EXAMPLE = ROOT / ".env.example"
CANVAS_CLIENT = ROOT / "src" / "canvas_client.py"
CANVAS_CREDENTIALS = ROOT / "src" / "canvas_credentials.py"


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
    assert_pattern(text, r"canvas-skill-opportunity", "opportunity handoff")
    assert_pattern(text, r"student.*choice.*before.*canvas-bootstrap|before any later `canvas-bootstrap`", "choice before bootstrap")
    assert_pattern(text, r"canvas-scan", "scan as next user action")


def test_stop_boundaries() -> None:
    text = read_skill()
    assert_pattern(text, r"Do not scan assignments", "no assignment scan")
    assert_pattern(text, r"Do not execute assignments", "no execute")
    assert_pattern(text, r"Do not submit|submit, upload, answer quizzes", "no live actions")
    assert_pattern(text, r"Do not write `assignments\.json`, `plan\.json`, `result\.json`, or `REPORT\.md`", "no run artifacts")
    assert_pattern(text, r"Keep `?\.claude/`? read-only|Keep `?\.claude", "claude read-only")


def test_protected_credential_setup() -> None:
    text = read_skill()
    client_text = CANVAS_CLIENT.read_text(encoding="utf-8")
    credential_text = CANVAS_CREDENTIALS.read_text(encoding="utf-8")
    assert_pattern(text, r"pip install -r requirements\.txt", "tracked requirements install")
    assert_pattern(text, r"playwright install chromium", "browser install")
    assert_pattern(text, r"_pick_method", "credential method probe")
    assert_pattern(text, r"Never write new credentials with base64", "base64 fails closed")
    assert_pattern(text, r"--forget-credentials", "privacy-first credential removal")
    assert_pattern(text, r"has_stored_credentials\(\).*false", "credential removal assertion")
    assert_pattern(text, r"probe once more", "post-removal auth verification")
    assert_pattern(REQUIREMENTS.read_text(encoding="utf-8"), r"^cryptography", "tracked crypto dependency")
    assert_pattern(GITIGNORE.read_text(encoding="utf-8"), r"^\.venv/$", "repo-local venv ignored")
    assert_pattern(
        ENV_EXAMPLE.read_text(encoding="utf-8"),
        r"^CANVAS_REMEMBER_CREDENTIALS=false$",
        "password persistence default off",
    )
    assert_pattern(
        client_text,
        r"if remember_credentials:[\s\S]{0,240}expose_function",
        "capture listener gated by opt-in",
    )
    assert_pattern(credential_text, r"base64 is refused", "base64 write refusal")
    assert_pattern(credential_text, r"raise CredentialStorageError", "cleanup fails closed")
    assert_pattern(
        client_text,
        r"stored credentials were rejected but could not be deleted",
        "runtime cleanup failure stops login",
    )


def test_student_facing_contract() -> None:
    text = read_skill()
    assert_pattern(text, r"Ask the student only domain questions", "domain questions")
    assert_pattern(text, r"Which school do you use Canvas through\?", "school-first question")
    assert_pattern(
        text,
        r"Canvas login URL.*instead of guessing|Never guess a host",
        "Canvas URL ambiguity fallback",
    )
    assert_pattern(text, r"School name first", "school before technical host")
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
        test_protected_credential_setup,
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
