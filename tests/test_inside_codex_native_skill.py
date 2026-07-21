from __future__ import annotations

import re
from pathlib import Path

from src import authorization
from src import canvas_client as cv
from src import course_artifacts, quiz_focus_events, quiz_pacing, quiz_strategic_miss
from src import run_state


ROOT = Path(__file__).resolve().parents[1]
SKILL_PATH = ROOT / ".agents" / "skills" / "canvas-inside" / "SKILL.md"


def skill_text() -> str:
    return SKILL_PATH.read_text(encoding="utf-8")


def test_inside_skill_is_compact_codex_native_and_has_clean_frontmatter() -> None:
    text = skill_text()
    assert len(text.splitlines()) < 500
    assert text.startswith("---\nname: canvas-inside\ndescription:")
    frontmatter = text.split("---", 2)[1]
    keys = [
        line.split(":", 1)[0]
        for line in frontmatter.splitlines()
        if line.strip() and not line.startswith((" ", "\t"))
    ]
    assert keys == ["name", "description"]
    assert "native Codex" in text

    stale = re.compile(
        r"(?:\.claude[/\\]|\bclaude\b|agent tool|skill tool|subagent_type|"
        r"auto[- ]ported|\bcc\s+context\b)",
        re.IGNORECASE,
    )
    assert not stale.search(text)


def test_classic_quiz_classifier_and_all_answer_types_are_explicit() -> None:
    text = skill_text()
    for token in (
        "online_quiz",
        "quiz_id",
        "question_count >= 5",
        "time_limit",
        "external_tool",
        "locked_for_user",
        "multiple_choice_question",
        "multiple_answers_question",
        "true_false_question",
        "matching_question",
        "short_answer_question",
        "fill_in_multiple_blanks_question",
        "multiple_dropdowns_question",
        "numerical_question",
        "essay_question",
    ):
        assert token in text
    assert "[variable_name]" in text
    assert "answers[].blank_id" in text


def test_stable_id_work_dir_and_real_reading_pipeline_are_required() -> None:
    text = skill_text()
    assert "ensure_stable_work_dir(run_dir, course_id, assignment_id)" in text
    assert "course-<course_id>__assignment-<assignment_id>" in text

    stage_order = [
        text.index("**Section/week module:**"),
        text.index("**Course files plus syllabus:**"),
        text.index("**Local extraction:**"),
        text.index("**Public-source fallback:**"),
    ]
    assert stage_order == sorted(stage_order)
    for section in (
        "central thesis",
        "source claims distinguishable from inference",
        "study_notes.md",
        "required_reading_unavailable",
    ):
        assert section in text


def test_read_only_notes_precede_mutation_gates_and_every_draft_has_a_path() -> None:
    text = skill_text()
    assert text.index("## 2. Discover the real readings") < text.index(
        "## 3. Preflight every mutation gate"
    )
    assert "before checking scheduling toggles or mutation\nauthority" in text
    assert "draft_path=study_notes.md" in text
    assert "draft_path=quiz_meta.json" in text
    assert "Every `draft_ready` branch must point to an\nexisting" in text
    assert "never claim notes before Stage 2\ncreated them" in text
    assert "Gate 1: a signed receipt is required" not in text


def test_exact_signed_quiz_action_scopes_are_fail_closed() -> None:
    text = skill_text()
    expected = {
        "quiz.start",
        "quiz.event",
        "quiz.answer",
        "quiz.complete",
        "quiz.retake",
    }
    assert expected <= set(re.findall(r"`(quiz\.[a-z]+)`", text))
    assert "quiz.events" not in text
    for binding in (
        "current Canvas\norigin",
        'target_type="quiz"',
        "exact `target_id=quiz_id`",
        "current Codex\nsession",
        "signed,\nunexpired",
        "load_authorization_receipt",
        "validate_authorization_receipt",
    ):
        assert binding in text
    assert "No action implies another" in text
    assert "Pass the same validated receipt to every client mutation" in text

    for symbol in (
        "validate_authorization_receipt",
        "load_authorization_receipt",
        "require_mutation_authorization",
    ):
        assert hasattr(authorization, symbol)


def test_four_parallel_native_subagents_and_canonical_evidence_are_required() -> None:
    text = skill_text()
    assert "Spawn four separate native Codex subagents in one parallel dispatch" in text
    for role in ("notes-first", "grep-first", "framework-aware", "contrarian"):
        assert role in text
    for name in (
        "notes_first.json",
        "grep_first.json",
        "framework_aware.json",
        "contrarian.json",
    ):
        assert name in text
    for evidence in (
        "final_answers.json",
        "arbitration_notes",
        "unanimous_count",
        "agent_passes/",
        "_require_canonical_arbitration_evidence",
        "canonically identical substantive arrays",
        "Answer consensus\nis valid",
    ):
        assert evidence in text
    assert "Do not synthesize four\npersonas in one response" in text
    assert "do not give it another pass, a proposed final answer" in text


def test_quiz_evidence_is_bound_to_exact_work_session_attempt_and_receipt() -> None:
    text = skill_text()
    for binding in (
        "course_id",
        "quiz_id",
        "assignment_id",
        "session_id",
        "attempt",
        "authorization_receipt_id",
        "explicit `work_dir`",
        "same validated receipt",
    ):
        assert binding in text
    assert "atomically update\n`quiz_meta.json`" in text
    assert "evidence envelope" in text
    assert 'attempt=sub["attempt"]' in text


def test_pacing_event_order_and_false_negative_readback_are_explicit() -> None:
    text = skill_text()
    for helper in (
        "compute_answer_schedule",
        "build_answer_sequence",
        "pick_blur_slots",
        "pick_flagged_questions",
        "maybe_flip_answers",
    ):
        assert helper in text

    event_order = [
        text.index("post `question_viewed`"),
        text.index("`page_blurred` and `page_focused`"),
        text.index("post `question_flagged`"),
        text.index("call `cv.answer_quiz_questions`"),
        text.index("post `question_answered`"),
    ]
    assert event_order == sorted(event_order)
    assert "at least 30 seconds" in text
    assert "about 78%" in text
    assert "An HTTP 500 from an answer save is a possible false negative" in text
    assert "cv.get_quiz_submission_questions(submission_id)" in text
    assert "A completion HTTP 500 is also inconclusive" in text
    assert "cv.get_submission(course_id, assignment_id)" in text
    assert "do not automatically repeat `/complete`" in text

    for symbol in (
        "start_quiz_submission",
        "post_quiz_events",
        "get_quiz_submission_questions",
        "answer_quiz_questions",
        "complete_quiz_submission",
        "get_quiz_attempt_feedback",
    ):
        assert hasattr(cv, symbol)
    assert hasattr(quiz_pacing, "compute_answer_schedule")
    assert hasattr(quiz_pacing, "build_answer_sequence")
    assert hasattr(quiz_focus_events, "pick_blur_slots")
    assert hasattr(quiz_focus_events, "pick_flagged_questions")
    assert hasattr(quiz_strategic_miss, "maybe_flip_answers")


def test_retake_learning_audit_and_result_contract_are_complete() -> None:
    text = skill_text()
    for policy in ("keep_highest", "keep_latest", "keep_average"):
        assert policy in text
    for token in (
        "0.95",
        "question banks may reshuffle".capitalize(),
        "four fresh\nparallel subagents for attempt 2",
        "feedback-driven",
        "rearbitration",
        "audit/learning_log.json",
        "high-confidence misses",
        "non-gating learning step",
    ):
        assert token in text

    for status in ("draft_ready", "submitted", "skipped", "error"):
        assert status in text
    assert '"status": "graded"' not in text
    assert "metadata.canvas_workflow_state" in text
    for field in (
        "authorization_receipt_id",
        "kept_score",
        "points_possible",
        "attempts_used",
        "allowed_attempts",
        "scoring_policy",
        "agent_passes_count",
        "human_ness_diagnostics",
        "views_paired_with_answers",
    ):
        assert field in text

    assert hasattr(course_artifacts, "ensure_stable_work_dir")
    assert hasattr(run_state, "write_result")
    assert hasattr(run_state, "validate_result")


def test_authorization_usage_is_terminal_before_consumed_result() -> None:
    text = skill_text()
    assert "authorization_usage_status(receipt)" in text
    assert "finalize_authorization_usage(receipt, reason=...)" in text
    assert "Only a ledger entry with `terminal_at` permits" in text
    assert "`authorization_consumed=true`" in text


def test_first_run_stage_mode_keeps_all_runtime_guards() -> None:
    text = skill_text()
    assert "STAGE-BY-STAGE MODE" in text
    assert ".first_run_stage_by_stage" in text
    for stage in (
        "classify",
        "reading-discovery",
        "study-notes",
        "safety-gates",
        "open-submission",
        "arbitration",
        "paced-submit",
        "complete",
        "score-check",
        "retake",
        "learning-audit",
    ):
        assert stage in text
    assert "require all prior artifacts" in text
    assert "Mutation stages still require the same signed\nreceipt" in text
    assert "Never use first-run mode to\nbypass a gate" in text
