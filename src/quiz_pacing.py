# SPDX-License-Identifier: AGPL-3.0-or-later
"""Per-question timing + answer-sequence generators for canvas-inside human-ness.

Layers 1 and 3 of the canvas-inside human-ness work (see
.claude/skills/canvas-inside/SKILL.md "Human-ness layers").

Two public functions:

    compute_answer_schedule(questions, arbitration, time_limit_min)
        → [(qnum, seconds_to_sleep_before_this_answer), ...]
        Models per-question time as a log-normal centered on a base value
        that depends on (a) question type, (b) prompt length, (c) the
        arbitration confidence for that question. Total scheduled time is
        scaled to land in 70-90% of the quiz's time_limit.

    build_answer_sequence(questions, arbitration)
        → [("answer"|"change", qnum), ...]
        Models a real student's answering pattern: pass 1 high-confidence
        in mostly-linear order with occasional skip-ahead, pass 2 medium/low,
        pass 3 1-3 revisits to medium/low-confidence answers (which the
        caller may or may not actually flip).

The two functions are independent. The canvas-inside skill calls both, then
zips them in §8 of the skill.
"""
from __future__ import annotations

import math
import random


# Base seconds per question type — the average a moderately-confident student
# spends. Tuned from the spec's reference (quiz-course Section 1 = 20 questions, 30
# minute limit → ~1.5 minutes/question average; harder types take longer).
QUESTION_TYPE_BASE = {
    "true_false_question": 18,
    "multiple_choice_question": 32,
    "multiple_answers_question": 70,
    "matching_question": 95,
    "short_answer_question": 55,
    "fill_in_blank_question": 50,
    "fill_in_multiple_blanks_question": 80,
    "essay_question": 240,
    "numerical_question": 40,
    "calculated_question": 60,
}

# Confidence multiplier — how much longer to spend on a question whose
# answer the LLM was uncertain about.
CONFIDENCE_MULTIPLIER = {
    "high": 1.0,
    "medium": 1.5,
    "low": 2.5,
}

# Log-normal sigma — controls how spread-out per-question times are within
# a single category. 0.45 gives CV ~0.47 in the raw distribution; mixed
# with confidence multipliers and the outlier injection below, the overall
# CV lands ~0.7, matching observed real-student quiz analytics distributions.
LOGNORMAL_SIGMA = 0.45

# Fraction of time_limit we aim to use. Real students use 70-95%; we pick
# 78% as a center (fast student, finishes with some buffer).
TARGET_TIME_FRACTION = 0.78

# Outlier injection — pick 1 question on quizzes with N >= 8 and multiply
# its time by 1.8-2.5x to model "got stuck on this one for a while".
# Without this, even a wide sigma still smooths out into a flat-looking
# per-question histogram on the instructor's quiz statistics page.
OUTLIER_MIN_QUESTIONS = 8
OUTLIER_MULTIPLIER_RANGE = (1.8, 2.5)


def _confidence_of(arbitration_for_q) -> str:
    """Pull a confidence string out of an arbitration entry. Tolerates dict or
    object access; defaults to 'medium' when missing or unrecognized."""
    if arbitration_for_q is None:
        return "medium"
    if isinstance(arbitration_for_q, dict):
        c = arbitration_for_q.get("confidence", "medium")
    else:
        c = getattr(arbitration_for_q, "confidence", "medium")
    return c if c in CONFIDENCE_MULTIPLIER else "medium"


def per_question_seconds(question: dict, confidence: str) -> int:
    """Sample a single question's answer time. Always >= 15 seconds.

    Combines the type base, a length penalty (longer prompts take longer to
    read), the confidence multiplier, a small uniform jitter, and a final
    log-normal draw. This means even two questions with identical type +
    confidence will get different times, but with the right central tendency.
    """
    base = QUESTION_TYPE_BASE.get(question.get("type"), 60)
    prompt_len = len(question.get("prompt") or "")
    base += (prompt_len // 50) * 5
    base *= CONFIDENCE_MULTIPLIER.get(confidence, 1.5)
    base *= random.uniform(0.85, 1.2)
    seconds = int(random.lognormvariate(math.log(max(base, 1)), LOGNORMAL_SIGMA))
    return max(15, seconds)


def compute_answer_schedule(
    questions: list[dict],
    arbitration: dict | list,
    time_limit_min: int | None,
) -> list[tuple[int, int]]:
    """Build a per-question time schedule. Returns [(qnum, seconds), ...].

    arbitration may be either a dict keyed by qnum, or a list indexed by qnum-1
    (the canvas-inside skill produces both shapes in different versions).

    time_limit_min may be None for un-timed quizzes — in that case we don't
    rescale, we just use the raw lognormal draws.
    """
    def lookup(qnum):
        if isinstance(arbitration, dict):
            return arbitration.get(qnum) or arbitration.get(str(qnum))
        try:
            return arbitration[qnum - 1] if 1 <= qnum <= len(arbitration) else None
        except (IndexError, TypeError):
            return None

    raw = []
    for q in questions:
        qnum = q.get("qnum")
        conf = _confidence_of(lookup(qnum))
        raw.append(per_question_seconds(q, conf))

    # Pick outlier (1 question on quizzes >= OUTLIER_MIN_QUESTIONS) and inflate.
    # The rescale below holds the outlier value fixed while non-outliers absorb
    # the deficit, so the "stuck on this one" signal survives end-to-end
    # instead of getting flattened back to the mean by a uniform rescale.
    n = len(raw)
    outlier_idx = random.randrange(n) if n >= OUTLIER_MIN_QUESTIONS else None
    final = list(raw)
    if outlier_idx is not None:
        mult = random.uniform(*OUTLIER_MULTIPLIER_RANGE)
        final[outlier_idx] = int(raw[outlier_idx] * mult)

    if time_limit_min and time_limit_min > 0:
        target = int(time_limit_min * 60 * TARGET_TIME_FRACTION)
        if outlier_idx is None:
            total = sum(final) or 1
            scale = target / total
            final = [max(15, int(t * scale)) for t in final]
        else:
            outlier_seconds = final[outlier_idx]
            non_outlier_baseline = sum(raw[i] for i in range(n) if i != outlier_idx) or 1
            non_outlier_target = target - outlier_seconds
            if non_outlier_target < 15 * (n - 1):
                # Outlier alone would consume too much — fall back to scaling
                # everyone (outlier included) to fit. The "stuck" signal
                # degrades but the quiz still fits the time limit.
                total = sum(final) or 1
                scale = target / total
                final = [max(15, int(t * scale)) for t in final]
            else:
                scale = non_outlier_target / non_outlier_baseline
                final = [
                    final[i] if i == outlier_idx else max(15, int(raw[i] * scale))
                    for i in range(n)
                ]

    return [(q["qnum"], s) for q, s in zip(questions, final)]


def build_answer_sequence(
    questions: list[dict],
    arbitration: dict | list,
) -> list[tuple[str, int]]:
    """Build a (op, qnum) sequence simulating a real student's answer order.

    Operations:
      ('answer', qnum)  — first answer for this question
      ('change', qnum)  — revisiting an already-answered question

    Pattern:
      Pass 1: high-confidence questions, mostly in qnum order with 10-15%
              probability of skip-ahead (e.g. answer Q3 before Q2)
      Pass 2: medium and low-confidence questions, in qnum order
      Pass 3: 0-3 revisits to medium/low-confidence questions, where the
              caller decides whether to flip the answer or just re-confirm

    Every question appears exactly once with op='answer'. Some appear a
    second time with op='change'. Total ops is in [n, n+3].
    """
    def lookup(qnum):
        if isinstance(arbitration, dict):
            return arbitration.get(qnum) or arbitration.get(str(qnum))
        try:
            return arbitration[qnum - 1] if 1 <= qnum <= len(arbitration) else None
        except (IndexError, TypeError):
            return None

    high, medlow = [], []
    for q in questions:
        qnum = q.get("qnum")
        conf = _confidence_of(lookup(qnum))
        if conf == "high":
            high.append(qnum)
        else:
            medlow.append(qnum)

    seq: list[tuple[str, int]] = []

    # Pass 1: high-confidence with occasional skip-ahead
    remaining = list(high)
    while remaining:
        if len(remaining) > 3 and random.random() < 0.12:
            # Skip ahead 1-3 positions
            idx = random.randint(1, min(3, len(remaining) - 1))
            seq.append(("answer", remaining.pop(idx)))
        else:
            seq.append(("answer", remaining.pop(0)))

    # Pass 2: medium / low in qnum order
    for qnum in medlow:
        seq.append(("answer", qnum))

    # Pass 3: 0-3 revisits, only on medium/low (real students re-check
    # uncertain answers, not their easy ones)
    n = len(questions)
    revisit_count = max(0, min(3, int(n * random.uniform(0.05, 0.15))))
    revisit_pool = medlow[:]  # list copy
    if revisit_count and revisit_pool:
        for qnum in random.sample(revisit_pool, min(revisit_count, len(revisit_pool))):
            seq.append(("change", qnum))

    return seq


if __name__ == "__main__":
    # Smoke test: 20 questions, 10 high-conf + 10 low-conf, 30 min limit
    qs = []
    arb = {}
    for i in range(1, 21):
        qs.append({"qnum": i, "type": "multiple_choice_question", "prompt": "x" * 100})
        arb[i] = {"confidence": "high" if i <= 10 else "low"}
    sched = compute_answer_schedule(qs, arb, 30)
    seconds = [s for _, s in sched]
    print(f"schedule: {sched}")
    print(f"total seconds: {sum(seconds)} (target ~{int(30*60*TARGET_TIME_FRACTION)})")
    print(f"min/max/mean: {min(seconds)}/{max(seconds)}/{sum(seconds)//len(seconds)}")
    print(f"max-to-mean ratio: {max(seconds) / (sum(seconds)/len(seconds)):.2f}x  (>=1.8 = outlier present)")
    # CV
    mean_s = sum(seconds) / len(seconds)
    var = sum((s - mean_s) ** 2 for s in seconds) / len(seconds)
    cv = (var ** 0.5) / mean_s if mean_s else 0
    print(f"per-question CV: {cv:.2f}  (target ~0.5-0.7)")
    seq = build_answer_sequence(qs, arb)
    print(f"sequence ({len(seq)} ops): {seq}")
