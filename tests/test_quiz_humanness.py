# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for the 5 canvas-inside human-ness layers.

Run: pytest tests/test_quiz_humanness.py -v
"""
from __future__ import annotations

import os
import random
import statistics
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ---------- Layer 4A: browser-like User-Agent on canvas_client backend ----------

def test_layer4a_user_agent_is_chrome():
    """Token mode: RequestsBackend sets a Chrome UA on its session.
    (Cookie mode gets browser headers natively from Playwright Chromium —
    not asserted here because importing in cookie mode would launch a
    headless browser.)"""
    from src import canvas_client
    ua = canvas_client.get_user_agent()
    assert "Mozilla" in ua and "Chrome" in ua, f"UA looks robotic: {ua!r}"
    assert "python-requests" not in ua


def test_layer4a_token_backend_request_headers():
    """Token mode keeps the browser-like Accept-Language and X-Requested-With
    on the requests.Session — verify directly so future refactors don't drop them."""
    from src import canvas_client
    if canvas_client.AUTH_MODE != "token":
        pytest.skip("only meaningful for token-mode backend")
    headers = canvas_client._backend._session.headers
    assert headers.get("X-Requested-With") == "XMLHttpRequest"
    assert "en" in headers.get("Accept-Language", "")


# ---------- Layer 1: log-normal per-question schedule ----------

@pytest.fixture
def mock_quiz():
    qs = [
        {"qnum": i, "type": "multiple_choice_question", "prompt": "x" * 100}
        for i in range(1, 21)
    ]
    # first 10 = high confidence, last 10 = low
    arb = {i: {"confidence": "high" if i <= 10 else "low"} for i in range(1, 21)}
    return qs, arb


def test_layer1_schedule_total_within_time_limit(mock_quiz):
    from src.quiz_pacing import compute_answer_schedule
    random.seed(42)
    qs, arb = mock_quiz
    sched = compute_answer_schedule(qs, arb, time_limit_min=30)
    total = sum(s for _, s in sched)
    # Target 78% of 30 min = 1404s. Allow slack for integer rounding and floor at 15s.
    assert 0.65 * 30 * 60 <= total <= 0.95 * 30 * 60, f"total={total}"


def test_layer1_low_conf_slower_than_high(mock_quiz):
    from src.quiz_pacing import compute_answer_schedule
    random.seed(7)
    qs, arb = mock_quiz
    sched = dict(compute_answer_schedule(qs, arb, time_limit_min=30))
    hi_avg = statistics.mean(sched[i] for i in range(1, 11))
    lo_avg = statistics.mean(sched[i] for i in range(11, 21))
    assert lo_avg > hi_avg, f"low-conf ({lo_avg:.0f}) should beat high ({hi_avg:.0f})"


def test_layer1_variance_not_robotic(mock_quiz):
    from src.quiz_pacing import compute_answer_schedule
    random.seed(99)
    qs, arb = mock_quiz
    times = [s for _, s in compute_answer_schedule(qs, arb, time_limit_min=30)]
    cv = statistics.stdev(times) / statistics.mean(times)
    assert cv > 0.15, f"variance too low (CV={cv:.2f}), looks robotic"


# ---------- Layer 3: skip + revisit + change ----------

def test_layer3_every_question_answered_once(mock_quiz):
    from src.quiz_pacing import build_answer_sequence
    random.seed(1)
    qs, arb = mock_quiz
    seq = build_answer_sequence(qs, arb)
    answered = [q for op, q in seq if op == "answer"]
    assert sorted(answered) == list(range(1, 21))


def test_layer3_sequence_has_revisits(mock_quiz):
    from src.quiz_pacing import build_answer_sequence
    # Run many seeds — at least some should produce revisits
    qs, arb = mock_quiz
    has_change = 0
    for seed in range(50):
        random.seed(seed)
        seq = build_answer_sequence(qs, arb)
        if any(op == "change" for op, _ in seq):
            has_change += 1
    assert has_change > 10, f"only {has_change}/50 sequences had revisits"


def test_layer3_not_pure_linear(mock_quiz):
    from src.quiz_pacing import build_answer_sequence
    qs, arb = mock_quiz
    non_linear = 0
    for seed in range(30):
        random.seed(seed)
        seq = build_answer_sequence(qs, arb)
        answered = [q for op, q in seq if op == "answer"]
        if answered != list(range(1, 21)):
            non_linear += 1
    # With 10 high-confidence first then 10 low, pass 1 (high) has 12% skip; not 100% will be non-linear
    assert non_linear > 5, f"only {non_linear}/30 were non-linear"


# ---------- Layer 2: strategic miss (env-gated) ----------

def test_layer2_disabled_by_default(monkeypatch):
    from src.quiz_strategic_miss import maybe_flip_answers
    monkeypatch.delenv("CANVAS_QUIZ_STRATEGIC_MISS", raising=False)
    qs = [{"qnum": i, "type": "multiple_choice_question",
           "answers": [{"id": 100 + i * 10 + j} for j in range(4)]} for i in range(1, 5)]
    arb = [{"qnum": i, "confidence": "low"} for i in range(1, 5)]
    answer_for = {i: 100 + i * 10 for i in range(1, 5)}
    new, log = maybe_flip_answers(qs, arb, answer_for, total_points=4)
    assert new == answer_for, "disabled should not mutate"
    assert log == [{"_disabled": True}]


def test_layer2_never_flips_high_confidence(monkeypatch):
    from src.quiz_strategic_miss import maybe_flip_answers
    monkeypatch.setenv("CANVAS_QUIZ_STRATEGIC_MISS", "1")
    monkeypatch.setenv("CANVAS_QUIZ_TARGET_PERCENT", "50-60")  # aggressive: wants to drop ~40%
    qs = [{"qnum": i, "type": "multiple_choice_question",
           "answers": [{"id": 100 + i * 10 + j} for j in range(4)]} for i in range(1, 11)]
    arb = [{"qnum": i, "confidence": "high"} for i in range(1, 11)]
    answer_for = {i: 100 + i * 10 for i in range(1, 11)}
    random.seed(3)
    new, log = maybe_flip_answers(qs, arb, answer_for, total_points=10)
    assert new == answer_for, "high-conf must never flip"


def test_layer2_caps_at_3_flips(monkeypatch):
    from src.quiz_strategic_miss import maybe_flip_answers
    monkeypatch.setenv("CANVAS_QUIZ_STRATEGIC_MISS", "1")
    monkeypatch.setenv("CANVAS_QUIZ_TARGET_PERCENT", "10-20")  # aggressive drop
    qs = [{"qnum": i, "type": "multiple_choice_question",
           "answers": [{"id": 100 + i * 10 + j} for j in range(4)]} for i in range(1, 21)]
    arb = [{"qnum": i, "confidence": "low"} for i in range(1, 21)]
    answer_for = {i: 100 + i * 10 for i in range(1, 21)}
    random.seed(0)
    new, log = maybe_flip_answers(qs, arb, answer_for, total_points=20)
    flipped = sum(1 for k, v in new.items() if v != answer_for[k])
    assert flipped <= 3, f"flipped {flipped}, should cap at 3"


# ---------- Layer 5A: human-hours gate (helper logic) ----------

def test_layer5_gate_window_parse():
    # Just smoke-test the env parse pattern used in SKILL.md §4
    import os
    os.environ.pop("CANVAS_QUIZ_HUMAN_HOURS", None)
    band = os.environ.get("CANVAS_QUIZ_HUMAN_HOURS", "9-22")
    lo, hi = (int(x) for x in band.split("-"))
    assert 0 <= lo < hi <= 24
    assert (lo, hi) == (9, 22)
