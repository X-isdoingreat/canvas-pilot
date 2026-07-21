from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from src.run_state import (
    RunStateError,
    merge_ledger_entry,
    plan_digest,
    prepare_approved_results,
    stable_work_dir,
    validate_plan,
    validate_plan_assignments,
    validate_run_directory,
    validate_result,
    write_plan,
    write_result,
)


def _plan(items: list[dict] | None = None, *, expired: bool = False) -> dict:
    now = dt.datetime.now(dt.timezone.utc)
    generated = now - dt.timedelta(hours=2 if expired else 1)
    expires = now - dt.timedelta(hours=1) if expired else now + dt.timedelta(hours=1)
    return {
        "generated_at": generated.isoformat(),
        "expires_at": expires.isoformat(),
        "items": items or [],
    }


def _single_preparation_run(
    tmp_path: Path, *, session_id: str
) -> tuple[Path, dict, Path, Path]:
    run_dir = tmp_path / "runs" / "2026-07-18"
    run_dir.mkdir(parents=True)
    assignment = {
        "course_id": 11,
        "assignment_id": 12,
        "name": "Retryable",
        "skill": "canvas-generic",
        "work_dir": "course-11__assignment-12",
    }
    plan = _plan([{
        "index": 1,
        "course_id": 11,
        "assignment_id": 12,
        "proposed_skill": "canvas-generic",
        "user_decision": "approve",
    }])
    write_plan(run_dir / "plan.json", plan)
    (run_dir / "assignments.json").write_text(
        json.dumps([assignment]), encoding="utf-8"
    )
    marker = {
        "session_id": session_id,
        "owner_kind": "codex",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "plan_digest": plan_digest(plan),
    }
    marker_path = run_dir / ".scan_in_progress"
    marker_path.write_text(json.dumps(marker), encoding="utf-8")
    result_path = stable_work_dir(run_dir, 11, 12) / "result.json"
    archive_path = result_path.parent / "result-history" / (
        f"pre-{plan_digest(plan)[:20]}.json"
    )
    return run_dir, plan, result_path, archive_path


def _quiz_result(**overrides):
    data = {
        "kind": "quiz",
        "status": "submitted",
        "submitted_at": "2026-07-18T12:00:00Z",
        "authorization_receipt_id": "receipt-fixture",
        "authorization_consumed": True,
        "metadata": {
            "canvas_workflow_state": "submitted",
            "readback_verified": True,
        },
        "kept_score": 9.0,
        "points_possible": 10.0,
        "attempts_used": 1,
        "allowed_attempts": 2,
        "scoring_policy": "keep_highest",
        "agent_passes_count": 4,
        "human_ness_diagnostics": {"views_paired_with_answers": True},
    }
    data.update(overrides)
    return data


@pytest.mark.parametrize("status", ["graded", "already_submitted", "done"])
def test_only_four_canonical_statuses(status: str) -> None:
    with pytest.raises(RunStateError):
        validate_result({"status": status})


def test_graded_and_existing_submission_are_metadata(tmp_path: Path) -> None:
    data = validate_result(
        {
            "status": "submitted",
            "reason_code": "already_submitted",
            "submitted_at": "2026-07-18T12:00:00Z",
            "metadata": {
                "canvas_workflow_state": "graded",
                "graded": True,
                "readback_verified": True,
            },
        },
        root=tmp_path,
    )
    assert data["status"] == "submitted"
    assert data["metadata"]["graded"] is True


def test_submitted_evidence_is_text_and_graded_metadata_uses_submitted_status() -> None:
    with pytest.raises(RunStateError, match="draft_path or submitted_at"):
        validate_result({"status": "submitted", "submitted_at": True})
    with pytest.raises(RunStateError, match="canonical status='submitted'"):
        validate_result({
            "status": "skipped",
            "metadata": {"canvas_workflow_state": "graded"},
        })


@pytest.mark.parametrize(
    "field",
    ["kept_score", "points_possible", "attempts_used", "allowed_attempts"],
)
def test_quiz_numeric_fields_reject_bool(field: str) -> None:
    with pytest.raises(RunStateError, match="bool is invalid"):
        validate_result(_quiz_result(**{field: True}))


def test_quiz_requires_claimed_humanness_diagnostics() -> None:
    with pytest.raises(RunStateError, match="human_ness_diagnostics"):
        validate_result(_quiz_result(human_ness_diagnostics=None))
    with pytest.raises(RunStateError, match="views_paired"):
        validate_result(_quiz_result(human_ness_diagnostics={}))
    assert validate_result(_quiz_result())["status"] == "submitted"


def test_atomic_result_plan_and_ledger_writes(tmp_path: Path) -> None:
    draft = tmp_path / "draft.txt"
    draft.write_text("draft", encoding="utf-8")
    result_path = tmp_path / "work" / "result.json"
    result_path.parent.mkdir(parents=True)
    (result_path.parent / "verification.log").write_text(
        "PASS | draft exists | measured: 1\n", encoding="utf-8"
    )
    write_result(
        result_path,
        {"status": "draft_ready", "draft_path": str(draft)},
        root=tmp_path,
    )
    assert json.loads(result_path.read_text(encoding="utf-8"))["status"] == "draft_ready"

    plan_path = tmp_path / "plan.json"
    write_plan(plan_path, _plan([{"index": 1, "user_decision": None}]))
    assert validate_plan(json.loads(plan_path.read_text(encoding="utf-8")))["items"][0]["index"] == 1

    ledger = tmp_path / "_processed.json"
    merge_ledger_entry(ledger, "first", {"status": "skipped"})
    merge_ledger_entry(ledger, "second", {"status": "error"})
    stored = json.loads(ledger.read_text(encoding="utf-8"))
    assert set(stored) == {"first", "second"}
    assert not list(tmp_path.rglob("*.tmp"))


def test_plan_requires_aware_ordered_current_timestamps_and_contiguous_indices() -> None:
    with pytest.raises(RunStateError, match="generated_at"):
        validate_plan({"items": []})
    with pytest.raises(RunStateError, match="timezone"):
        validate_plan({
            "generated_at": "2026-07-18T10:00:00",
            "expires_at": "2026-07-18T11:00:00",
            "items": [],
        })
    with pytest.raises(RunStateError, match="contiguous"):
        validate_plan(_plan([{"index": 2, "user_decision": None}]))
    with pytest.raises(RunStateError, match="expired"):
        validate_plan(_plan(expired=True), require_current=True)


def test_plan_snapshot_identity_skill_and_stable_result_directory(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "2026-07-18"
    run_dir.mkdir(parents=True)
    item = {
        "course_id": "course_7",
        "assignment_id": "assignment_19",
        "course_name": "Mutable Name",
        "name": "Renamable Assignment",
        "skill": "canvas-generic",
        "work_dir": "course-course_7__assignment-assignment_19",
    }
    plan = _plan([{
        "index": 1,
        "course_id": item["course_id"],
        "assignment_id": item["assignment_id"],
        "proposed_skill": item["skill"],
        "user_decision": "approve",
    }])
    validate_plan_assignments(plan, [item], run_dir=run_dir)

    write_plan(run_dir / "plan.json", plan)
    (run_dir / "assignments.json").write_text(json.dumps([item]), encoding="utf-8")
    work = stable_work_dir(run_dir, item["course_id"], item["assignment_id"])
    work.mkdir()
    write_result(work / "result.json", {"status": "skipped", "notes": "fixture"})
    report = validate_run_directory(run_dir)
    assert report["results"] == [(work / "result.json").as_posix()]

    mismatched = [dict(item, work_dir="Mutable_Name__Renamable_Assignment")]
    with pytest.raises(RunStateError, match="stable ID directory"):
        validate_plan_assignments(plan, mismatched, run_dir=run_dir)


def test_prepare_results_archives_only_approved_and_is_idempotent(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "2026-07-18"
    run_dir.mkdir(parents=True)
    assignments = [
        {
            "course_id": 7,
            "assignment_id": 19,
            "name": "Approved",
            "skill": "canvas-generic",
            "work_dir": "course-7__assignment-19",
        },
        {
            "course_id": 7,
            "assignment_id": 20,
            "name": "Deferred",
            "skill": "canvas-generic",
            "work_dir": "course-7__assignment-20",
        },
    ]
    plan = _plan([
        {
            "index": 1,
            "course_id": 7,
            "assignment_id": 19,
            "proposed_skill": "canvas-generic",
            "user_decision": "approve",
        },
        {
            "index": 2,
            "course_id": 7,
            "assignment_id": 20,
            "proposed_skill": "canvas-generic",
            "user_decision": "defer",
        },
    ])
    write_plan(run_dir / "plan.json", plan)
    (run_dir / "assignments.json").write_text(json.dumps(assignments), encoding="utf-8")
    marker = {
        "session_id": "prepare-session",
        "owner_kind": "codex",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "plan_digest": plan_digest(plan),
    }
    (run_dir / ".scan_in_progress").write_text(json.dumps(marker), encoding="utf-8")
    approved_result = stable_work_dir(run_dir, 7, 19) / "result.json"
    deferred_result = stable_work_dir(run_dir, 7, 20) / "result.json"
    write_result(approved_result, {"status": "error", "notes": "old approved"})
    write_result(deferred_result, {"status": "skipped", "notes": "old deferred"})

    prepared = prepare_approved_results(
        run_dir, expected_session_id="prepare-session"
    )
    assert prepared["archived"] == 1
    assert not approved_result.exists()
    assert deferred_result.exists()
    archive = approved_result.parent / "result-history" / (
        f"pre-{plan_digest(plan)[:20]}.json"
    )
    assert json.loads(archive.read_text(encoding="utf-8"))["notes"] == "old approved"

    write_result(approved_result, {"status": "skipped", "notes": "current approved"})
    resumed = prepare_approved_results(
        run_dir, expected_session_id="prepare-session"
    )
    assert resumed["idempotent"] is True
    assert json.loads(approved_result.read_text(encoding="utf-8"))["notes"] == "current approved"


def test_prepare_results_recovers_archive_completed_before_marker_stamp(tmp_path: Path) -> None:
    run_dir, _, result_path, archive_path = _single_preparation_run(
        tmp_path, session_id="partial-session"
    )
    write_result(result_path, {"status": "error", "notes": "old retryable result"})
    archive_path.parent.mkdir(parents=True)
    result_path.replace(archive_path)

    prepared = prepare_approved_results(
        run_dir, expected_session_id="partial-session"
    )

    assert prepared["archived"] == 1
    assert prepared["prepared_approved_result_keys"] == [
        "course-11__assignment-12"
    ]
    assert archive_path.exists()
    assert not result_path.exists()


def test_prepare_results_fails_closed_when_archive_and_current_both_exist(tmp_path: Path) -> None:
    run_dir, _, result_path, archive_path = _single_preparation_run(
        tmp_path, session_id="ambiguous-session"
    )
    write_result(result_path, {"status": "error", "notes": "current ambiguous"})
    archive_path.parent.mkdir(parents=True)
    write_result(archive_path, {"status": "error", "notes": "archived ambiguous"})

    with pytest.raises(RunStateError, match="ambiguous"):
        prepare_approved_results(run_dir, expected_session_id="ambiguous-session")

    marker = json.loads((run_dir / ".scan_in_progress").read_text(encoding="utf-8"))
    assert "prepared_approved_result_keys" not in marker
    assert json.loads(result_path.read_text(encoding="utf-8"))["notes"] == "current ambiguous"
    assert json.loads(archive_path.read_text(encoding="utf-8"))["notes"] == "archived ambiguous"


def test_active_execute_requires_new_result_in_every_prepared_approved_slot(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "2026-07-18"
    run_dir.mkdir(parents=True)
    assignments = [
        {
            "course_id": 8,
            "assignment_id": 1,
            "name": "Approved",
            "skill": "canvas-generic",
            "work_dir": "course-8__assignment-1",
        },
        {
            "course_id": 8,
            "assignment_id": 2,
            "name": "Deferred",
            "skill": "canvas-generic",
            "work_dir": "course-8__assignment-2",
        },
    ]
    plan = _plan([
        {
            "index": 1,
            "course_id": 8,
            "assignment_id": 1,
            "proposed_skill": "canvas-generic",
            "user_decision": "approve",
        },
        {
            "index": 2,
            "course_id": 8,
            "assignment_id": 2,
            "proposed_skill": "canvas-generic",
            "user_decision": "defer",
        },
    ])
    write_plan(run_dir / "plan.json", plan)
    (run_dir / "assignments.json").write_text(json.dumps(assignments), encoding="utf-8")
    (run_dir / ".scan_in_progress").write_text(
        json.dumps({
            "session_id": "freshness-session",
            "owner_kind": "codex",
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "plan_digest": plan_digest(plan),
        }),
        encoding="utf-8",
    )
    approved_result = stable_work_dir(run_dir, 8, 1) / "result.json"
    deferred_result = stable_work_dir(run_dir, 8, 2) / "result.json"
    write_result(approved_result, {"status": "error", "notes": "old"})
    write_result(deferred_result, {"status": "skipped", "notes": "old deferred"})
    prepare_approved_results(run_dir, expected_session_id="freshness-session")

    with pytest.raises(RunStateError, match="missing result.json"):
        validate_run_directory(run_dir)

    write_result(approved_result, {"status": "skipped", "notes": "fresh approved"})
    assert validate_run_directory(run_dir)["marker_active"] is True


def test_draft_ready_requires_substantive_artifact_and_all_pass_verification(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    draft = work / "draft.md"
    draft.write_text("", encoding="utf-8")
    (work / "verification.log").write_text("PASS | shape | measured: 1\n", encoding="utf-8")
    with pytest.raises(RunStateError, match="non-empty substantive"):
        validate_result(
            {"status": "draft_ready", "draft_path": str(draft)},
            root=tmp_path,
            work_dir=work,
        )

    draft.write_text("[ANSWER NEEDED]\n", encoding="utf-8")
    with pytest.raises(RunStateError, match="placeholder"):
        validate_result(
            {"status": "draft_ready", "draft_path": str(draft)},
            root=tmp_path,
            work_dir=work,
        )

    draft.write_text("A real draft.\n", encoding="utf-8")
    (work / "verification.log").write_text("FAIL | rubric | measured: 0\n", encoding="utf-8")
    with pytest.raises(RunStateError, match="FAIL evidence"):
        validate_result(
            {"status": "draft_ready", "draft_path": str(draft)},
            root=tmp_path,
            work_dir=work,
        )


def test_new_submitted_result_requires_receipt_consumption_and_readback() -> None:
    base = {
        "status": "submitted",
        "submitted_at": "2026-07-18T12:00:00Z",
        "metadata": {
            "canvas_workflow_state": "submitted",
            "readback_verified": True,
        },
    }
    with pytest.raises(RunStateError, match="authorization_receipt_id"):
        validate_result(base)
    with pytest.raises(RunStateError, match="authorization_consumed"):
        validate_result(dict(base, authorization_receipt_id="receipt-1"))
    assert validate_result(
        dict(
            base,
            authorization_receipt_id="receipt-1",
            authorization_consumed=True,
        )
    )["status"] == "submitted"
