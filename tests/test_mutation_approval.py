from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from src.authorization import validate_authorization_receipt
from src.mutation_approval import (
    AUTHORITY_FILENAME,
    RECEIPT_FILENAME,
    MutationApprovalError,
    issue_interactive_authorization,
    parse_mutation_command,
)
from src.run_state import plan_digest, stable_work_dir


NOW = dt.datetime(2026, 7, 18, 12, 0, tzinfo=dt.timezone.utc)
KEY = b"interactive-authorization-test-key-32-bytes!!"


def _write_run(
    root: Path,
    *,
    submission_types: list[str] | None = None,
    quiz_id=None,
    decision: str | None = "approve",
    skill: str = "canvas-generic",
    expires_at: dt.datetime | None = None,
    write_draft_result: bool = True,
) -> tuple[Path, dict, dict]:
    run_dir = root / "runs" / "2026-07-18"
    run_dir.mkdir(parents=True)
    snapshot = {
        "course_id": "course-7",
        "assignment_id": "assignment-19",
        "name": "Synthetic assignment",
        "skill": skill,
        "submission_types": submission_types or ["online_text_entry"],
        "quiz_id": quiz_id,
        "work_dir": stable_work_dir(run_dir, "course-7", "assignment-19").name,
    }
    plan = {
        "generated_at": (NOW - dt.timedelta(minutes=5)).isoformat(),
        "expires_at": (expires_at or (NOW + dt.timedelta(hours=1))).isoformat(),
        "items": [
            {
                "index": 1,
                "course_id": snapshot["course_id"],
                "assignment_id": snapshot["assignment_id"],
                "proposed_skill": snapshot["skill"],
                "user_decision": decision,
            }
        ],
    }
    (run_dir / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    (run_dir / "assignments.json").write_text(
        json.dumps([snapshot]), encoding="utf-8"
    )
    if write_draft_result and "online_quiz" not in snapshot["submission_types"]:
        work = stable_work_dir(
            run_dir, snapshot["course_id"], snapshot["assignment_id"]
        )
        draft = work / "draft" / "answer.txt"
        draft.parent.mkdir(parents=True, exist_ok=True)
        draft.write_text("Complete synthetic response.\n", encoding="utf-8")
        (work / "verification.log").write_text(
            "PASS | substantive draft | measured: 29 bytes\n", encoding="utf-8"
        )
        (work / "result.json").write_text(
            json.dumps({"status": "draft_ready", "draft_path": str(draft)}),
            encoding="utf-8",
        )
    return run_dir, plan, snapshot


@pytest.mark.parametrize(
    ("text", "operation"),
    [
        ("submit 1", "assignment_submit"),
        ("提交第1项", "assignment_submit"),
        ("take quiz 1", "quiz_take"),
        ("参加测验第1项", "quiz_take"),
        ("retake quiz 1", "quiz_retake"),
        ("重做测验第1项", "quiz_retake"),
    ],
)
def test_exact_whole_expression_parser(text: str, operation: str) -> None:
    parsed = parse_mutation_command(text)
    assert parsed.operation == operation
    assert parsed.index == 1
    assert parsed.raw_text == text


@pytest.mark.parametrize(
    "text",
    [
        "submit all",
        "please submit 1",
        "submit 1 please",
        "submit 1 and 2",
        "submit 1,2",
        "submit 0",
        "take quiz all",
        "take quiz 1 now",
        "quiz 1",
        "提交全部",
        "请提交第1项",
        "参加测验第1项，谢谢",
    ],
)
def test_wrong_ambiguous_or_residual_expression_fails(text: str) -> None:
    with pytest.raises(MutationApprovalError):
        parse_mutation_command(text)


def test_text_receipt_binds_current_plan_session_and_verbatim_authority_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir, plan, snapshot = _write_run(tmp_path)
    monkeypatch.setenv("CODEX_THREAD_ID", "thread-current")
    raw = "  submit 1 \n"

    issued = issue_interactive_authorization(
        run_dir=run_dir,
        canvas_origin="https://canvas.example.test/api/v1",
        user_text=raw,
        now=NOW,
        signing_key=KEY,
    )

    work_dir = stable_work_dir(
        run_dir, snapshot["course_id"], snapshot["assignment_id"]
    )
    assert Path(issued["receipt_path"]) == work_dir / RECEIPT_FILENAME
    assert Path(issued["authority_record_path"]) == work_dir / AUTHORITY_FILENAME
    receipt = json.loads((work_dir / RECEIPT_FILENAME).read_text(encoding="utf-8"))
    record = json.loads((work_dir / AUTHORITY_FILENAME).read_text(encoding="utf-8"))
    assert record["user_text"] == raw
    assert record["plan_digest"] == plan_digest(plan)
    assert record["session_id_sha256"] != "thread-current"
    assert receipt["target_type"] == "assignment"
    assert receipt["target_id"] == snapshot["assignment_id"]
    assert receipt["actions"] == ["assignment.submit_text"]
    validated = validate_authorization_receipt(
        receipt,
        canvas_origin="https://canvas.example.test",
        course_id=snapshot["course_id"],
        target_type="assignment",
        target_id=snapshot["assignment_id"],
        action="assignment.submit_text",
        session_id="thread-current",
        now=NOW + dt.timedelta(minutes=1),
        signing_key=KEY,
    )
    assert validated["receipt_id"] == issued["receipt_id"]


@pytest.mark.parametrize(
    ("submission_types", "expected"),
    [
        (["online_text_entry"], {"assignment.submit_text"}),
        (
            ["online_upload"],
            {
                "assignment.upload_init",
                "assignment.upload_blob",
                "assignment.submit_files",
            },
        ),
        (["online_url"], {"assignment.submit_url"}),
        (
            ["online_text_entry", "online_upload", "online_url"],
            {
                "assignment.submit_text",
                "assignment.upload_init",
                "assignment.upload_blob",
                "assignment.submit_files",
                "assignment.submit_url",
            },
        ),
    ],
)
def test_ordinary_actions_are_derived_only_from_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    submission_types: list[str],
    expected: set[str],
) -> None:
    run_dir, _, _ = _write_run(tmp_path, submission_types=submission_types)
    monkeypatch.setenv("CODEX_THREAD_ID", "thread-actions")
    issued = issue_interactive_authorization(
        run_dir=run_dir,
        canvas_origin="https://canvas.example.test",
        user_text="submit 1",
        now=NOW,
        signing_key=KEY,
    )
    assert set(issued["actions"]) == expected


@pytest.mark.parametrize(
    ("command", "expected_actions"),
    [
        (
            "take quiz 1",
            {"quiz.start", "quiz.event", "quiz.answer", "quiz.complete"},
        ),
        (
            "retake quiz 1",
            {
                "quiz.event",
                "quiz.answer",
                "quiz.complete",
                "quiz.retake",
            },
        ),
    ],
)
def test_classic_quiz_requires_exact_quiz_id_and_explicit_retake(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    command: str,
    expected_actions: set[str],
) -> None:
    run_dir, _, snapshot = _write_run(
        tmp_path,
        submission_types=["online_quiz"],
        quiz_id="quiz-88",
        skill="canvas-inside",
    )
    if command == "retake quiz 1":
        work = stable_work_dir(
            run_dir, snapshot["course_id"], snapshot["assignment_id"]
        )
        work.mkdir(parents=True, exist_ok=True)
        (work / "result.json").write_text(
            json.dumps({
                "kind": "quiz",
                "status": "submitted",
                "submitted_at": NOW.isoformat(),
                "authorization_receipt_id": "prior-receipt",
                "authorization_consumed": True,
                "quiz_id": "quiz-88",
                "metadata": {
                    "canvas_workflow_state": "submitted",
                    "readback_verified": True,
                },
                "kept_score": 8,
                "points_possible": 10,
                "attempts_used": 1,
                "allowed_attempts": 2,
                "scoring_policy": "keep_highest",
                "agent_passes_count": 4,
                "human_ness_diagnostics": {"views_paired_with_answers": True},
            }),
            encoding="utf-8",
        )
    monkeypatch.setenv("CODEX_THREAD_ID", "thread-quiz")
    issued = issue_interactive_authorization(
        run_dir=run_dir,
        canvas_origin="https://canvas.example.test",
        user_text=command,
        now=NOW,
        signing_key=KEY,
    )
    assert issued["target_type"] == "quiz"
    assert issued["target_id"] == "quiz-88"
    assert set(issued["actions"]) == expected_actions


def test_unapproved_and_stale_plan_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CODEX_THREAD_ID", "thread-state")
    unapproved, _, _ = _write_run(tmp_path / "unapproved", decision=None)
    with pytest.raises(MutationApprovalError, match="approve/swap"):
        issue_interactive_authorization(
            run_dir=unapproved,
            canvas_origin="https://canvas.example.test",
            user_text="submit 1",
            now=NOW,
            signing_key=KEY,
        )

    stale, _, _ = _write_run(
        tmp_path / "stale", expires_at=NOW - dt.timedelta(seconds=1)
    )
    with pytest.raises(MutationApprovalError, match="expired"):
        issue_interactive_authorization(
            run_dir=stale,
            canvas_origin="https://canvas.example.test",
            user_text="submit 1",
            now=NOW,
            signing_key=KEY,
        )


def test_swap_decision_is_an_approved_execution_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir, _, _ = _write_run(tmp_path, decision="swap:canvas-essay")
    monkeypatch.setenv("CODEX_THREAD_ID", "thread-swap")
    issued = issue_interactive_authorization(
        run_dir=run_dir,
        canvas_origin="https://canvas.example.test",
        user_text="submit 1",
        now=NOW,
        signing_key=KEY,
    )
    assert issued["issued"] is True


@pytest.mark.parametrize(
    ("submission_types", "quiz_id", "command", "error"),
    [
        (["external_tool"], None, "submit 1", "unsupported/undeclared"),
        (["online_quiz"], None, "take quiz 1", "quiz_id"),
        (["online_text_entry"], None, "take quiz 1", "Classic Quiz"),
        (["online_quiz"], "quiz-88", "submit 1", "cannot authorize a quiz"),
    ],
)
def test_wrong_or_undeclared_snapshot_scope_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    submission_types: list[str],
    quiz_id,
    command: str,
    error: str,
) -> None:
    skill = "canvas-inside" if "online_quiz" in submission_types else "canvas-generic"
    run_dir, _, _ = _write_run(
        tmp_path,
        submission_types=submission_types,
        quiz_id=quiz_id,
        skill=skill,
    )
    monkeypatch.setenv("CODEX_THREAD_ID", "thread-scope")
    with pytest.raises(MutationApprovalError, match=error):
        issue_interactive_authorization(
            run_dir=run_dir,
            canvas_origin="https://canvas.example.test",
            user_text=command,
            now=NOW,
            signing_key=KEY,
        )


def test_current_codex_session_is_mandatory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir, _, _ = _write_run(tmp_path)
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    monkeypatch.delenv("CODEX_SESSION_ID", raising=False)
    with pytest.raises(MutationApprovalError, match="thread/session"):
        issue_interactive_authorization(
            run_dir=run_dir,
            canvas_origin="https://canvas.example.test",
            user_text="submit 1",
            now=NOW,
            signing_key=KEY,
        )


def test_assignment_submit_requires_verified_draft_ready_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CODEX_THREAD_ID", "thread-draft-gate")
    run_dir, _, _ = _write_run(tmp_path, write_draft_result=False)
    with pytest.raises(MutationApprovalError, match="verified draft_ready"):
        issue_interactive_authorization(
            run_dir=run_dir,
            canvas_origin="https://canvas.example.test",
            user_text="submit 1",
            now=NOW,
            signing_key=KEY,
        )


def test_assignment_submit_rejects_valid_but_out_of_workdir_draft(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CODEX_THREAD_ID", "thread-draft-containment")
    run_dir, _, snapshot = _write_run(tmp_path)
    work = stable_work_dir(run_dir, snapshot["course_id"], snapshot["assignment_id"])
    outside = tmp_path / "outside.txt"
    outside.write_text("Substantive but wrong target artifact.\n", encoding="utf-8")
    (work / "result.json").write_text(
        json.dumps({"status": "draft_ready", "draft_path": str(outside)}),
        encoding="utf-8",
    )
    with pytest.raises(MutationApprovalError, match="inside the stable work directory"):
        issue_interactive_authorization(
            run_dir=run_dir,
            canvas_origin="https://canvas.example.test",
            user_text="submit 1",
            now=NOW,
            signing_key=KEY,
        )


def test_retake_requires_prior_submitted_result_with_attempt_remaining(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CODEX_THREAD_ID", "thread-retake-gate")
    run_dir, _, snapshot = _write_run(
        tmp_path,
        submission_types=["online_quiz"],
        quiz_id="quiz-88",
        skill="canvas-inside",
    )
    with pytest.raises(MutationApprovalError, match="prior submitted"):
        issue_interactive_authorization(
            run_dir=run_dir,
            canvas_origin="https://canvas.example.test",
            user_text="retake quiz 1",
            now=NOW,
            signing_key=KEY,
        )

    work = stable_work_dir(run_dir, snapshot["course_id"], snapshot["assignment_id"])
    work.mkdir(parents=True, exist_ok=True)
    result = {
        "kind": "quiz",
        "status": "submitted",
        "submitted_at": NOW.isoformat(),
        "authorization_receipt_id": "prior-receipt",
        "authorization_consumed": True,
        "quiz_id": "quiz-88",
        "metadata": {
            "canvas_workflow_state": "submitted",
            "readback_verified": True,
        },
        "kept_score": 8,
        "points_possible": 10,
        "attempts_used": 1,
        "allowed_attempts": 2,
        "scoring_policy": "keep_highest",
        "agent_passes_count": 4,
        "human_ness_diagnostics": {"views_paired_with_answers": True},
    }
    (work / "result.json").write_text(json.dumps(result), encoding="utf-8")
    issued = issue_interactive_authorization(
        run_dir=run_dir,
        canvas_origin="https://canvas.example.test",
        user_text="retake quiz 1",
        now=NOW,
        signing_key=KEY,
    )
    assert "quiz.retake" in issued["actions"]
    assert "quiz.start" not in issued["actions"]
