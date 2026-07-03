# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for the three-layer canvas-inside bypass-prevention stack.

Background: on 2026-05-02, an LLM agent wrote `runs/2026-05-02/_run_quiz_s7.py`
that bypassed the canvas-inside SKILL.md flow (hardcoded answers, no 4-agent
arbitration) and got 14/20 vs class median 19. Three layers were added to
make this structurally impossible:

  Layer 1: src/canvas_client.py:_require_canonical_arbitration_evidence
  Layer 2: .claude/hooks/check-router-complete.py §10 retake gate
  Layer 3: .claude/hooks/check-no-runner-script.py PreToolUse Write|Edit

Each layer alone catches the bypass; removing any one still leaves two.

Run: pytest tests/test_quiz_skill_enforcement.py -v
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# Use a per-test UUID-based work_dir under runs/_test_<uuid>/ so we don't
# collide with real runs and we can clean up reliably. Quiz ids are also
# random ints in a high range so they can't accidentally match a real one.

@pytest.fixture
def quiz_workdir(tmp_path_factory):
    """Create a work_dir under runs/2099-MM-DD/ (far future date matching the
    date regex in _find_quiz_work_dir but not colliding with real runs).
    Yields (work_dir, course_id, quiz_id). Cleans up afterwards."""
    quiz_id = 9_000_000_000 + int(uuid.uuid4().int % 100_000_000)
    course_id = 9_000_000
    # Random month+day under 2099 so parallel tests don't collide
    rand = uuid.uuid4().int
    month = (rand % 12) + 1
    day = ((rand >> 8) % 28) + 1
    date_dir = ROOT / "runs" / f"2099-{month:02d}-{day:02d}"
    work = date_dir / f"quiz_test_{uuid.uuid4().hex[:8]}"
    work.mkdir(parents=True, exist_ok=True)
    (work / "quiz_meta.json").write_text(
        json.dumps({"id": quiz_id, "course_id": course_id, "title": "test quiz"}),
        encoding="utf-8",
    )
    yield work, course_id, quiz_id
    # Cleanup: remove the work_dir; only remove date_dir if it's now empty
    shutil.rmtree(work, ignore_errors=True)
    try:
        if date_dir.exists() and not any(date_dir.iterdir()):
            date_dir.rmdir()
    except OSError:
        pass


# =========================================================================
# Layer 1 — canvas_client.py evidence gate
# =========================================================================

def test_layer1_no_evidence_blocks_complete(quiz_workdir):
    """Without final_answers.json + agent_passes/, complete must raise."""
    from src import canvas_client as cv
    work, cid, qid = quiz_workdir
    with pytest.raises(cv.QuizArbitrationEvidenceMissing) as exc:
        cv._require_canonical_arbitration_evidence(cid, qid)
    assert "final_answers.json" in str(exc.value) or "agent_passes" in str(exc.value) \
           or "no work_dir" in str(exc.value)


def test_layer1_only_final_answers_no_agent_passes_blocks(quiz_workdir):
    """final_answers.json present but agent_passes/ missing — still blocks."""
    from src import canvas_client as cv
    work, cid, qid = quiz_workdir
    (work / "final_answers.json").write_text(
        json.dumps({"arbitration_notes": {"unanimous_count": 17}, "answers": []}),
        encoding="utf-8",
    )
    with pytest.raises(cv.QuizArbitrationEvidenceMissing) as exc:
        cv._require_canonical_arbitration_evidence(cid, qid)
    assert "agent_passes" in str(exc.value)


def test_layer1_only_3_agent_passes_blocks(quiz_workdir):
    """Need ≥4 agent passes; 3 must fail."""
    from src import canvas_client as cv
    work, cid, qid = quiz_workdir
    (work / "final_answers.json").write_text(
        json.dumps({"arbitration_notes": {"unanimous_count": 17}, "answers": []}),
        encoding="utf-8",
    )
    passes = work / "agent_passes"
    passes.mkdir()
    for i, name in enumerate(["a", "b", "c"]):
        (passes / f"agent_{name}.json").write_text(
            json.dumps([{"qnum": j, "picked": (i + j) % 3} for j in range(20)]),
            encoding="utf-8",
        )
    with pytest.raises(cv.QuizArbitrationEvidenceMissing) as exc:
        cv._require_canonical_arbitration_evidence(cid, qid)
    assert "≥4" in str(exc.value) or "4 parallel" in str(exc.value)


def test_layer1_4_identical_passes_blocks_copy_paste(quiz_workdir):
    """4 byte-identical agent passes = copy-paste forgery, must block."""
    from src import canvas_client as cv
    work, cid, qid = quiz_workdir
    (work / "final_answers.json").write_text(
        json.dumps({"arbitration_notes": {"unanimous_count": 17}, "answers": []}),
        encoding="utf-8",
    )
    passes = work / "agent_passes"
    passes.mkdir()
    identical_content = json.dumps([{"qnum": j, "picked": 1} for j in range(20)])
    for name in ["a", "b", "c", "d"]:
        (passes / f"agent_{name}.json").write_text(identical_content, encoding="utf-8")
    with pytest.raises(cv.QuizArbitrationEvidenceMissing) as exc:
        cv._require_canonical_arbitration_evidence(cid, qid)
    assert "identical" in str(exc.value)


def test_layer1_4_distinct_passes_passes(quiz_workdir):
    """4 distinct agent passes + arbitration_notes.unanimous_count → succeeds."""
    from src import canvas_client as cv
    work, cid, qid = quiz_workdir
    (work / "final_answers.json").write_text(
        json.dumps({"arbitration_notes": {"unanimous_count": 17}, "answers": []}),
        encoding="utf-8",
    )
    passes = work / "agent_passes"
    passes.mkdir()
    # 4 passes that disagree on at least one question
    for i, name in enumerate(["a", "b", "c", "d"]):
        (passes / f"agent_{name}.json").write_text(
            json.dumps([{"qnum": j, "picked": (i + j) % 4} for j in range(20)]),
            encoding="utf-8",
        )
    found_work = cv._require_canonical_arbitration_evidence(cid, qid)
    assert found_work.resolve() == work.resolve()


def test_layer1_missing_unanimous_count_blocks(quiz_workdir):
    """final_answers.json without arbitration_notes.unanimous_count → block.
    This is the exact shape _run_quiz_s7.py wrote."""
    from src import canvas_client as cv
    work, cid, qid = quiz_workdir
    # Mimic the bypass script's notes shape: method string, no unanimous_count
    (work / "final_answers.json").write_text(
        json.dumps({
            "arbitration_notes": {
                "method": "single-pass with high-confidence study notes",
                "confidence_summary": "all 20 high",
            },
            "answers": [],
        }),
        encoding="utf-8",
    )
    passes = work / "agent_passes"
    passes.mkdir()
    for i, name in enumerate(["a", "b", "c", "d"]):
        (passes / f"agent_{name}.json").write_text(
            json.dumps([{"qnum": j, "picked": (i + j) % 4} for j in range(20)]),
            encoding="utf-8",
        )
    with pytest.raises(cv.QuizArbitrationEvidenceMissing) as exc:
        cv._require_canonical_arbitration_evidence(cid, qid)
    assert "unanimous_count" in str(exc.value)


def test_layer1_override_via_env_var(quiz_workdir, monkeypatch):
    """CANVAS_QUIZ_DEGRADED_OK env var with verbatim quote bypasses gate."""
    from src import canvas_client as cv
    work, cid, qid = quiz_workdir
    monkeypatch.setenv("CANVAS_QUIZ_DEGRADED_OK", "yes I authorize single-pass for tonight")
    found_work = cv._require_canonical_arbitration_evidence(cid, qid)
    assert found_work.resolve() == work.resolve()


def test_layer1_override_too_short_does_not_bypass(quiz_workdir, monkeypatch):
    """CANVAS_QUIZ_DEGRADED_OK with <10 chars should NOT bypass."""
    from src import canvas_client as cv
    work, cid, qid = quiz_workdir
    monkeypatch.setenv("CANVAS_QUIZ_DEGRADED_OK", "ok")
    with pytest.raises(cv.QuizArbitrationEvidenceMissing):
        cv._require_canonical_arbitration_evidence(cid, qid)


# =========================================================================
# Layer 2 — Stop hook §10 retake gate
# =========================================================================

def _run_stop_hook(event_dict, runs_state):
    """Run check-router-complete.py with given event + runs/<today>/ state.
    Returns (returncode, stderr, stdout)."""
    import datetime as dt
    today = dt.date.today().isoformat()
    today_dir = ROOT / "runs" / today

    # Stash anything currently in today_dir; restore after
    backup = None
    if today_dir.exists():
        backup = ROOT / "runs" / f"{today}_backup_{uuid.uuid4().hex[:8]}"
        shutil.move(str(today_dir), str(backup))
    today_dir.mkdir(parents=True)
    try:
        # Write the marker file (Stop hook only fires when marker exists)
        marker = today_dir / ".scan_in_progress"
        marker.write_text(event_dict.get("session_id", "test_session"), encoding="utf-8")

        # Write assignments.json + work_dirs from runs_state spec
        (today_dir / "assignments.json").write_text(
            json.dumps(runs_state["assignments"]), encoding="utf-8"
        )
        for wd_name, files in runs_state.get("work_dirs", {}).items():
            wd = today_dir / wd_name
            wd.mkdir(parents=True, exist_ok=True)
            for fname, content in files.items():
                (wd / fname).write_text(
                    content if isinstance(content, str) else json.dumps(content),
                    encoding="utf-8",
                )

        result = subprocess.run(
            ["python", str(ROOT / ".claude/hooks/check-router-complete.py")],
            input=json.dumps(event_dict),
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            encoding="utf-8",
            errors="replace",
        )
        return result.returncode, result.stderr, result.stdout
    finally:
        shutil.rmtree(today_dir, ignore_errors=True)
        if backup and backup.exists():
            shutil.move(str(backup), str(today_dir))


def test_layer2_low_score_with_attempts_left_blocks_stop():
    """A quiz result.json with kept=14, max=20, attempts_used=1, allowed=2,
    keep_highest blocks Stop with retake instructions."""
    rc, stderr, _ = _run_stop_hook(
        {"session_id": "test_session"},
        {
            "assignments": [
                {
                    "course_id": 99999, "course_name": "Sample Course",
                    "assignment_id": 1800886, "name": "Quiz on Section 7",
                    "skill": "quiz", "due_at": "2026-05-04T06:59:59Z",
                }
            ],
            "work_dirs": {
                "Sample_Course__Quiz_on_Section_7": {
                    "result.json": {
                        "kind": "quiz", "status": "submitted",
                        "draft_path": "final_answers.json",
                        "submitted_at": "2026-05-04T05:53:00Z",
                        "kept_score": 14, "points_possible": 20,
                        "attempts_used": 1, "allowed_attempts": 2,
                        "scoring_policy": "keep_highest",
                        "agent_passes_count": 4,
                    },
                    "final_answers.json": "{}",
                }
            },
        },
    )
    assert rc == 2, f"expected block (exit 2), got {rc}. stderr: {stderr}"
    assert "retake" in stderr.lower() or "§10" in stderr


def test_layer2_high_score_passes_stop():
    """kept_score / points_possible ≥ 0.95 → no retake required."""
    rc, stderr, _ = _run_stop_hook(
        {"session_id": "test_session"},
        {
            "assignments": [
                {
                    "course_id": 99999, "course_name": "Sample Course",
                    "assignment_id": 1800886, "name": "Quiz Section 9",
                    "skill": "quiz", "due_at": "2026-05-11T06:59:59Z",
                }
            ],
            "work_dirs": {
                "Sample_Course__Quiz_Section_9": {
                    "result.json": {
                        "kind": "quiz", "status": "submitted",
                        "draft_path": "final_answers.json",
                        "submitted_at": "2026-05-10T20:00:00Z",
                        "kept_score": 19, "points_possible": 20,
                        "attempts_used": 1, "allowed_attempts": 2,
                        "scoring_policy": "keep_highest",
                        "agent_passes_count": 4,
                    },
                    "final_answers.json": "{}",
                }
            },
        },
    )
    assert rc == 0, f"expected pass (exit 0), got {rc}. stderr: {stderr}"


def test_layer2_no_attempts_left_passes_stop():
    """attempts_used == allowed_attempts → can't retake, must pass."""
    rc, stderr, _ = _run_stop_hook(
        {"session_id": "test_session"},
        {
            "assignments": [
                {
                    "course_id": 99999, "course_name": "Sample Course",
                    "assignment_id": 1800886, "name": "Quiz Section A",
                    "skill": "quiz", "due_at": "2026-05-11T06:59:59Z",
                }
            ],
            "work_dirs": {
                "Sample_Course__Quiz_Section_A": {
                    "result.json": {
                        "kind": "quiz", "status": "submitted",
                        "draft_path": "final_answers.json",
                        "submitted_at": "2026-05-10T20:00:00Z",
                        "kept_score": 14, "points_possible": 20,
                        "attempts_used": 2, "allowed_attempts": 2,
                        "scoring_policy": "keep_highest",
                        "agent_passes_count": 4,
                    },
                    "final_answers.json": "{}",
                }
            },
        },
    )
    assert rc == 0, f"expected pass (exit 0), got {rc}. stderr: {stderr}"


def test_layer2_degraded_consent_passes_stop():
    """degraded_method_user_consent field with verbatim user quote → passes."""
    rc, stderr, _ = _run_stop_hook(
        {"session_id": "test_session"},
        {
            "assignments": [
                {
                    "course_id": 99999, "course_name": "Sample Course",
                    "assignment_id": 1800886, "name": "Quiz Section B",
                    "skill": "quiz", "due_at": "2026-05-11T06:59:59Z",
                }
            ],
            "work_dirs": {
                "Sample_Course__Quiz_Section_B": {
                    "result.json": {
                        "kind": "quiz", "status": "submitted",
                        "draft_path": "final_answers.json",
                        "submitted_at": "2026-05-10T20:00:00Z",
                        "kept_score": 14, "points_possible": 20,
                        "attempts_used": 1, "allowed_attempts": 2,
                        "scoring_policy": "keep_highest",
                        "agent_passes_count": 4,
                        "degraded_method_user_consent": "ok skip retake this time",
                    },
                    "final_answers.json": "{}",
                }
            },
        },
    )
    assert rc == 0, f"expected pass (exit 0), got {rc}. stderr: {stderr}"


def test_layer2_keep_latest_policy_passes_stop():
    """keep_latest policy → retake would replace the score, must NOT force retake."""
    rc, stderr, _ = _run_stop_hook(
        {"session_id": "test_session"},
        {
            "assignments": [
                {
                    "course_id": 99999, "course_name": "Sample Course",
                    "assignment_id": 1800886, "name": "Quiz Section C",
                    "skill": "quiz", "due_at": "2026-05-11T06:59:59Z",
                }
            ],
            "work_dirs": {
                "Sample_Course__Quiz_Section_C": {
                    "result.json": {
                        "kind": "quiz", "status": "submitted",
                        "draft_path": "final_answers.json",
                        "submitted_at": "2026-05-10T20:00:00Z",
                        "kept_score": 14, "points_possible": 20,
                        "attempts_used": 1, "allowed_attempts": 2,
                        "scoring_policy": "keep_latest",
                        "agent_passes_count": 4,
                    },
                    "final_answers.json": "{}",
                }
            },
        },
    )
    assert rc == 0, f"expected pass (exit 0), got {rc}. stderr: {stderr}"


# =========================================================================
# Layer 3 — PreToolUse(Write|Edit) ad-hoc runner block
# =========================================================================

def _run_layer3_hook(file_path):
    event = {"tool_name": "Write", "tool_input": {"file_path": file_path}}
    result = subprocess.run(
        ["python", str(ROOT / ".claude/hooks/check-no-runner-script.py")],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        encoding="utf-8",
        errors="replace",
    )
    return result.returncode, result.stderr


@pytest.mark.parametrize("path", [
    "runs/2026-05-06/foo/_run_quiz.py",
    "runs/2026-05-06/foo/_run_quiz_s7.py",
    "runs/2026-05-06/intro_to_global__quiz_on_section_7/_helper.sh",
    "runs/2026-05-06/foo/run.py",
    "runs/2026-05-06/foo/run_quiz.py",
])
def test_layer3_blocks_runner_patterns(path):
    rc, stderr = _run_layer3_hook(path)
    assert rc == 2, f"expected block, got {rc} for {path}. stderr: {stderr}"
    assert "BLOCKED" in stderr or "ad-hoc" in stderr


@pytest.mark.parametrize("path", [
    "runs/2026-05-06/foo/study_notes.md",
    "runs/2026-05-06/foo/final_answers.json",
    "runs/2026-05-06/foo/agent_passes/agent_a.json",
    "runs/2026-05-06/foo/quiz_meta.json",
    "src/canvas_client.py",
    "tests/test_quiz_skill_enforcement.py",
    ".claude/skills/canvas-inside/SKILL.md",
])
def test_layer3_allows_legitimate_files(path):
    rc, stderr = _run_layer3_hook(path)
    assert rc == 0, f"expected pass, got {rc} for {path}. stderr: {stderr}"


# =========================================================================
# Schema layer — _lib.validate_result_schema quiz-kind branch
# =========================================================================

def _validate(data):
    sys.path.insert(0, str(ROOT / ".claude/hooks"))
    from _lib import validate_result_schema
    return validate_result_schema(json.dumps(data))


def test_schema_quiz_submitted_no_arbitration_blocks():
    ok, err = _validate({
        "kind": "quiz", "status": "submitted",
        "draft_path": "x", "submitted_at": "now",
        "kept_score": 14, "points_possible": 20,
        "attempts_used": 1, "allowed_attempts": 2,
        "scoring_policy": "keep_highest",
    })
    assert not ok
    assert "agent_passes_count" in err or "degraded_method_user_consent" in err


def test_schema_quiz_submitted_4_passes_passes():
    ok, err = _validate({
        "kind": "quiz", "status": "submitted",
        "draft_path": "x", "submitted_at": "now",
        "kept_score": 19, "points_possible": 20,
        "attempts_used": 1, "allowed_attempts": 2,
        "scoring_policy": "keep_highest",
        "agent_passes_count": 4,
    })
    assert ok, err


def test_schema_quiz_submitted_consent_passes():
    ok, err = _validate({
        "kind": "quiz", "status": "submitted",
        "draft_path": "x", "submitted_at": "now",
        "kept_score": 14, "points_possible": 20,
        "attempts_used": 1, "allowed_attempts": 2,
        "scoring_policy": "keep_highest",
        "degraded_method_user_consent": "yes I authorize single-pass tonight",
    })
    assert ok, err


def test_schema_quiz_bulk_views_blocks():
    ok, err = _validate({
        "kind": "quiz", "status": "submitted",
        "draft_path": "x", "submitted_at": "now",
        "kept_score": 19, "points_possible": 20,
        "attempts_used": 1, "allowed_attempts": 2,
        "scoring_policy": "keep_highest",
        "agent_passes_count": 4,
        "human_ness_diagnostics": {"views_paired_with_answers": False},
    })
    assert not ok
    assert "views_paired_with_answers" in err or "Layer 4C" in err
