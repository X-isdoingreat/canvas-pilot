from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / ".agents" / "skills" / "canvas-ics33" / "SKILL.md"
CANONICAL_STATUSES = {"draft_ready", "submitted", "skipped", "error"}


def _text() -> str:
    assert SKILL.is_file()
    return SKILL.read_text(encoding="utf-8")


def test_ics33_skill_is_compact_codex_native_and_has_minimal_frontmatter() -> None:
    text = _text()
    frontmatter = text.split("---", 2)[1]
    keys = {
        line.split(":", 1)[0].strip()
        for line in frontmatter.splitlines()
        if line.strip() and ":" in line
    }
    assert keys == {"name", "description"}
    assert len(text.splitlines()) < 500
    stale = re.compile(
        r"(?:\.claude[/\\]|\bclaude\b|agent tool|skill tool|subagent_type|"
        r"auto[- ]?port(?:ed)?|\bCC\b|/tmp(?:/|\b)|(?:^|\s)cp\s+)",
        re.IGNORECASE | re.MULTILINE,
    )
    assert not stale.search(text)
    assert "native Codex subagent" in text


def test_ics33_skill_preserves_full_code_assignment_pipeline() -> None:
    text = _text()
    required = (
        "course-<course_id>__assignment-<assignment_id>",
        "_private/canvas-ics33-app.md",
        "## Course <course_id>",
        "### <kind>",
        "#### <kind>",
        "naming_regex",
        "external_site",
        "front_page_link",
        "attached_pdf",
        "starter_readme",
        "reference_fetch_patterns",
        "references/manifest.json",
        "required_reference_unavailable",
        "git_bundle",
        "zip_url",
        "github_classroom",
        "inline_in_spec",
        "REQUIREMENTS.md",
        "constraints.md",
        "Research before improvising",
        "Implement test-first",
        "process history",
        "verification.log",
        "Identifier grounding",
        "independent semantic audit",
        "tempfile.TemporaryDirectory",
        "pre-submit-reviewer",
        "mutation_authorization.json",
        "assignment.upload_init",
        "assignment.upload_blob",
        "assignment.submit_files",
        "assignment.submit_text",
        "src.canvas_submit_origin",
        "upload_and_submit_files_with_view",
        "submit_text_with_view",
        ".first_run_stage_by_stage",
        "src.course_artifacts.write_course_result",
        "src.run_state.write_result",
    )
    missing = [item for item in required if item not in text]
    assert not missing, missing


def test_ics33_skill_uses_only_canonical_results_and_separate_mutation_authority() -> None:
    text = _text()
    emitted = set(
        re.findall(
            r'(?:status\s*[=:]\s*["`]|canonical\s+`)([a-z_]+)',
            text,
            flags=re.IGNORECASE,
        )
    )
    assert emitted <= CANONICAL_STATUSES, emitted
    assert "reason_code=already_submitted" in text
    assert "eligible to request a mutation; it is not\nCanvas authority" in text
    assert "Do not create or broaden a receipt in this skill" in text
    assert "never call a lower-level\nCanvas mutation helper" in text
    assert "Canvas file formats: call\n  `upload_and_submit_files_with_view" in text
    assert "`online_text_entry`: read the frozen `draft/submission.txt`" in text
    assert "Do not upload the text snapshot as a file" in text


def test_ics33_skill_requires_real_measurements_and_windows_safe_retest() -> None:
    text = _text()
    assert "one line per check" in text
    assert "PASS | requirement | measured: value" in text
    assert "Any remaining `FAIL`" in text
    assert "clone or re-extract the packaged artifact" in text
    assert "run the full tests and coverage again" in text
    assert "Do not depend on a\nUnix shell or command chaining" in text
