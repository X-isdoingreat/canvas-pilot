# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

import pytest

from src import authorization, canvas_submit_origin, mutation_approval, run_state


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / ".agents" / "skills" / "canvas-submit" / "SKILL.md"
OPENAI_YAML = SKILL.parent / "agents" / "openai.yaml"


def _text() -> str:
    assert SKILL.is_file()
    return SKILL.read_text(encoding="utf-8")


def test_canvas_submit_has_minimal_skill_metadata_and_ui_metadata() -> None:
    text = _text()
    assert len(text.splitlines()) < 500
    assert text.startswith("---\nname: canvas-submit\ndescription:")
    frontmatter = text.split("---", 2)[1]
    keys = [
        line.split(":", 1)[0]
        for line in frontmatter.splitlines()
        if line.strip() and not line.startswith((" ", "\t"))
    ]
    assert keys == ["name", "description"]
    assert OPENAI_YAML.is_file()
    ui = OPENAI_YAML.read_text(encoding="utf-8")
    assert 'display_name: "Canvas Submit"' in ui
    assert "$canvas-submit" in ui


@pytest.mark.parametrize(
    "command",
    (
        "submit 1",
        "提交第1项",
        "take quiz 1",
        "参加测验第1项",
        "retake quiz 1",
        "重做测验第1项",
    ),
)
def test_documented_exact_later_message_commands_match_runtime(command: str) -> None:
    text = _text()
    assert f"`{command.replace('1', 'N')}`" in text or command in text
    assert mutation_approval.parse_mutation_command(command).index == 1


@pytest.mark.parametrize(
    "command",
    (
        "submit all",
        "approve all",
        "please submit 1",
        "submit 1 and 2",
        "take quiz 1 now",
    ),
)
def test_documented_broad_or_residual_commands_fail_closed(command: str) -> None:
    assert f"`{command}`" in _text()
    with pytest.raises(mutation_approval.MutationApprovalError):
        mutation_approval.parse_mutation_command(command)


def test_trigger_is_separate_from_plan_approval_and_never_automatic() -> None:
    text = _text()
    for required in (
        "raw text of the **current user message**",
        "Never reconstruct authority\nfrom an earlier message",
        "Plan approval is not submission authority",
        "One message\nauthorizes at most one indexed target",
        "not an\nautomatic-submit or cron workflow",
        "must never mint or substitute for a mutation receipt",
    ):
        assert required in text
    assert text.index("## 1. Enforce the later-message boundary") < text.index(
        "## 2. Bind the current plan target"
    )


def test_current_plan_and_stable_work_directory_are_mandatory() -> None:
    text = _text()
    for required in (
        "validate_plan_assignments",
        "require_current=True",
        "contiguous 1-based plan item",
        "one-to-one snapshot match",
        "stable_work_dir(run_dir, course_id, assignment_id)",
        "course-<course_id>__assignment-<assignment_id>",
        "do not search older run directories",
    ):
        assert required in text
    assert hasattr(run_state, "validate_plan_assignments")
    assert hasattr(run_state, "stable_work_dir")


def test_ordinary_submission_requires_existing_verified_draft_before_receipt() -> None:
    text = _text()
    assert text.index("## 3. Require a verified ordinary-assignment draft") < text.index(
        "## 4. Issue one exact signed receipt"
    )
    for required in (
        "<work_dir>/result.json",
        "src.run_state.validate_result",
        "exactly `draft_ready`",
        "contained inside\n   the stable work directory",
        "src.run_state.validate_verification_log",
        "at least one `PASS` line",
        "no `FAIL` line",
        "no unresolved placeholder/skeleton sentinel",
        "stop before Canvas mutation",
    ):
        assert required in text
    assert hasattr(run_state, "validate_result")
    assert hasattr(run_state, "validate_verification_log")


def test_receipt_is_verbatim_target_exact_private_and_not_self_consuming() -> None:
    text = _text()
    for required in (
        "src.mutation_approval.issue_interactive_authorization",
        "user_text` equal to the verbatim current user message",
        "src.canvas_client.BASE",
        "mutation_authority.json",
        "mutation_authorization.json",
        "Synthetic_qa=True".lower(),
        "Receipt issuance by\nitself is not receipt consumption",
    ):
        assert required in text or required in text.lower()
    assert hasattr(mutation_approval, "issue_interactive_authorization")
    assert hasattr(authorization, "load_authorization_receipt")


def test_submission_type_dispatch_uses_only_receipt_aware_origin_wrappers() -> None:
    text = _text()
    for required in (
        "online_text_entry",
        "online_upload",
        "online_url",
        "online_quiz",
        "submit_text_with_view",
        "upload_and_submit_files_with_view",
        "submit_url_with_view",
        "assignment.submit_text",
        "assignment.upload_init",
        "assignment.upload_blob",
        "assignment.submit_files",
        "assignment.submit_url",
        "result.metadata.submission_type",
        "python -m scripts.submit_canvas",
        "--authorization-receipt",
        "Never use\n`--batch-manifest`",
        "Never call `cv.submit_text`",
        "raw Canvas mutation endpoints",
    ):
        assert required in text
    for symbol in (
        "submit_text_with_view",
        "upload_and_submit_files_with_view",
        "submit_url_with_view",
        "existing_submission_result",
    ):
        assert hasattr(canvas_submit_origin, symbol)


def test_classic_quiz_handoff_is_exact_and_does_not_mutate_inline() -> None:
    text = _text()
    for required in (
        "route to `canvas-inside`",
        "work_dir=<stable ID-based work directory>",
        "course_id=<exact snapshot course ID>",
        "assignment_id=<exact snapshot assignment ID>",
        "quiz_id=<exact snapshot quiz ID>",
        "authorization_receipt_path=<work_dir>/mutation_authorization.json",
        "mutation_operation=quiz_take|quiz_retake",
        "first-attempt receipt must not contain `quiz.retake`",
        "Do not start, answer, complete,\nor retake the quiz inline",
        "finalize receipt usage when required",
    ):
        assert required in text


def test_success_and_already_submitted_results_have_opposite_consumption_claims() -> None:
    text = _text()
    for required in (
        '"status": "submitted"',
        '"submitted_at":',
        '"authorization_receipt_id":',
        '"authorization_consumed": true',
        '"canvas_workflow_state":',
        '"readback_verified": true',
        "authorization_usage_status(receipt)",
        "src.run_state.write_result",
        "reason_code=already_submitted",
        "omit `authorization_receipt_id`",
        "omit\n`authorization_consumed`",
        "do not retry\nautomatically",
    ):
        assert required in text
    assert hasattr(authorization, "authorization_usage_status")
    assert hasattr(run_state, "write_result")


def test_draft_skills_name_canvas_submit_as_the_only_later_entry() -> None:
    for name in ("canvas-essay", "canvas-reading-annotation"):
        text = (ROOT / ".agents" / "skills" / name / "SKILL.md").read_text(
            encoding="utf-8"
        )
        assert "later exact-target" in text
        assert "only through" in text
        assert "`canvas-submit`" in text
