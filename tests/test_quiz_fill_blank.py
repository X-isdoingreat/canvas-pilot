# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for canvas-quiz fill-in-the-blank question-type support.

Added when canvas-quiz learned to answer Classic Quiz fill-blank types
(short_answer / fill_in_multiple_blanks / multiple_dropdowns / numerical).
The answer for these types is stored polymorphically in the `answer` field
(terse string / dict / number) rather than new schema fields, so the Layer-1
evidence gate and the human-ness helpers must tolerate non-int/list answers.

These tests lock the Python contract the SKILL.md §7a/§7c changes rely on:
  - quiz_pacing handles the new types (no KeyError; a missing `answers` key
    on fill-blank simplified items is fine)
  - strategic_miss never flips fill-blank / numerical / short-answer answers
    (dict / number values pass through untouched and never crash)
  - the evidence gate's copy-paste / unanimity detection works on dict answers

The §7a extraction itself is LLM-executed pseudocode in SKILL.md, validated
on the first real fill-blank quiz via the draft-only gate — not unit-tested
here (no real fill-blank quiz exists to fixture against).

Run: pytest tests/test_quiz_fill_blank.py -v
"""
from __future__ import annotations

import json
import random
import shutil
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _blank_type_questions():
    """Simplified-question items as SKILL.md §7a now produces them for the four
    blank types. fill-blank items carry blank_ids/blanks and NO `answers` key —
    the human-ness helpers must not assume `answers` exists."""
    return [
        {"qnum": 1, "id": 5001, "type": "short_answer_question",
         "prompt": "The treaty was signed in ____."},
        {"qnum": 2, "id": 5002, "type": "numerical_question",
         "prompt": "2 + 2 = ?"},
        {"qnum": 3, "id": 5003, "type": "fill_in_multiple_blanks_question",
         "prompt": "[city] in [year].",
         "blank_ids": ["city", "year"],
         "blanks": {"city": [], "year": []}},  # free-text: no visible options
        {"qnum": 4, "id": 5004, "type": "multiple_dropdowns_question",
         "prompt": "The verb is [v].",
         "blank_ids": ["v"],
         "blanks": {"v": [{"id": 71, "text": "ran"}, {"id": 72, "text": "run"}]}},
    ]


def _blank_type_answers():
    """answer_for as it would be POSTed — polymorphic value per type."""
    return {
        1: "vienna",                            # short_answer: terse string
        2: 4,                                   # numerical: number
        3: {"city": "vienna", "year": "1815"},  # fill_in_multiple_blanks: dict of strings
        4: {"v": 71},                           # multiple_dropdowns: {blank: answer_id}
    }


# ---------- quiz_pacing handles the new types ----------

def test_pacing_no_keyerror_on_blank_types():
    from src.quiz_pacing import compute_answer_schedule, build_answer_sequence
    random.seed(11)
    qs = _blank_type_questions()
    arb = {q["qnum"]: {"confidence": "medium"} for q in qs}
    sched = compute_answer_schedule(qs, arb, time_limit_min=20)
    assert len(sched) == len(qs)
    assert all(sec >= 15 for _, sec in sched)
    seq = build_answer_sequence(qs, arb)
    answered = sorted(q for op, q in seq if op == "answer")
    assert answered == [1, 2, 3, 4]


# ---------- strategic_miss never corrupts blank-type answers ----------

def test_strategic_miss_leaves_blank_types_untouched(monkeypatch):
    from src.quiz_strategic_miss import maybe_flip_answers
    monkeypatch.setenv("CANVAS_QUIZ_STRATEGIC_MISS", "1")
    monkeypatch.setenv("CANVAS_QUIZ_TARGET_PERCENT", "10-20")  # aggressive: wants a big drop
    random.seed(5)
    qs = _blank_type_questions()
    arb = [{"qnum": q["qnum"], "confidence": "low"} for q in qs]  # all low → all candidates
    answer_for = _blank_type_answers()
    new, log = maybe_flip_answers(qs, arb, answer_for, total_points=4)
    # None of the blank types are flippable → every answer unchanged, no crash on dict/number
    assert new == answer_for


def test_strategic_miss_mixed_quiz_only_flips_mcq(monkeypatch):
    from src.quiz_strategic_miss import maybe_flip_answers
    monkeypatch.setenv("CANVAS_QUIZ_STRATEGIC_MISS", "1")
    monkeypatch.setenv("CANVAS_QUIZ_TARGET_PERCENT", "10-20")
    random.seed(2)
    qs = _blank_type_questions() + [
        {"qnum": 5, "id": 5005, "type": "multiple_choice_question",
         "answers": [{"id": 90}, {"id": 91}, {"id": 92}, {"id": 93}]},
    ]
    arb = [{"qnum": q["qnum"], "confidence": "low"} for q in qs]
    answer_for = dict(_blank_type_answers())
    answer_for[5] = 90
    new, log = maybe_flip_answers(qs, arb, answer_for, total_points=5)
    for qnum in (1, 2, 3, 4):
        assert new[qnum] == answer_for[qnum], f"blank type q{qnum} must not change"
    assert new[5] in (90, 91, 92, 93)  # MCQ may flip, but stays a valid option id


# ---------- evidence gate handles dict answers ----------

@pytest.fixture
def quiz_workdir():
    """work_dir under runs/2099-MM-DD/ (matches _find_quiz_work_dir's date regex,
    far-future so it won't collide with real runs). Cleans up after."""
    quiz_id = 9_000_000_000 + int(uuid.uuid4().int % 100_000_000)
    course_id = 9_000_000
    rand = uuid.uuid4().int
    month = (rand % 12) + 1
    day = ((rand >> 8) % 28) + 1
    date_dir = ROOT / "runs" / f"2099-{month:02d}-{day:02d}"
    work = date_dir / f"quiz_fillblank_{uuid.uuid4().hex[:8]}"
    work.mkdir(parents=True, exist_ok=True)
    (work / "quiz_meta.json").write_text(
        json.dumps({"id": quiz_id, "course_id": course_id, "title": "fill-blank test"}),
        encoding="utf-8",
    )
    yield work, course_id, quiz_id
    shutil.rmtree(work, ignore_errors=True)
    try:
        if date_dir.exists() and not any(date_dir.iterdir()):
            date_dir.rmdir()
    except OSError:
        pass


def _write_final_answers(work):
    (work / "final_answers.json").write_text(
        json.dumps({
            "arbitration_notes": {"unanimous_count": 3},
            "answers": [
                {"qnum": 1, "question_id": 5001, "type": "short_answer_question",
                 "answer": "vienna"},
                {"qnum": 2, "question_id": 5003, "type": "fill_in_multiple_blanks_question",
                 "answer": {"city": "vienna", "year": "1815"}},
                {"qnum": 3, "question_id": 5004, "type": "multiple_dropdowns_question",
                 "answer": {"v": 71}},
            ],
        }),
        encoding="utf-8",
    )


def test_gate_accepts_distinct_dict_answer_passes(quiz_workdir):
    """4 agent passes whose fill-blank answers are dicts and differ on >=1 blank
    must pass the evidence gate — proving json.dumps handles dict agreement."""
    from src import canvas_client as cv
    work, cid, qid = quiz_workdir
    _write_final_answers(work)
    passes = work / "agent_passes"
    passes.mkdir()
    variants = [
        {"city": "vienna", "year": "1815"},
        {"city": "Vienna", "year": "1815"},   # case disagreement
        {"city": "vienna", "year": "1814"},   # value disagreement
        {"city": "vienna", "year": "1815"},
    ]
    for name, v in zip(["a", "b", "c", "d"], variants):
        (passes / f"agent_{name}.json").write_text(
            json.dumps([
                {"qnum": 1, "answer": "vienna"},
                {"qnum": 2, "answer": v},          # fill-blank dict under `answer`
                {"qnum": 3, "answer": {"v": 71}},
            ]),
            encoding="utf-8",
        )
    found = cv._require_canonical_arbitration_evidence(cid, qid)
    assert found.resolve() == work.resolve()


def test_gate_blocks_identical_dict_answer_passes(quiz_workdir):
    """4 byte-identical dict-answer passes = copy-paste forgery → must block,
    proving the copy-paste detector normalizes dict answers correctly."""
    from src import canvas_client as cv
    work, cid, qid = quiz_workdir
    _write_final_answers(work)
    passes = work / "agent_passes"
    passes.mkdir()
    identical = json.dumps([
        {"qnum": 1, "answer": "vienna"},
        {"qnum": 2, "answer": {"city": "vienna", "year": "1815"}},
        {"qnum": 3, "answer": {"v": 71}},
    ])
    for name in ["a", "b", "c", "d"]:
        (passes / f"agent_{name}.json").write_text(identical, encoding="utf-8")
    with pytest.raises(cv.QuizArbitrationEvidenceMissing) as exc:
        cv._require_canonical_arbitration_evidence(cid, qid)
    assert "identical" in str(exc.value)
