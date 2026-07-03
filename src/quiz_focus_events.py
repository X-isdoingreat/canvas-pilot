# SPDX-License-Identifier: AGPL-3.0-or-later
"""Per-question focus + flag event helpers for canvas-inside Layer 4D.

Models two things real students do that token-level API automation does not:

1. **Page blur / focus** — students tab away mid-quiz to look something up,
   check email, etc. The Canvas web UI emits page_blurred / page_focused
   events as part of `quiz_submission_events`. A timeline with zero blur
   events looks atypical even at a casual glance.

2. **Mark for review (question_flagged)** — students flag uncertain
   questions to revisit. Roughly 30% of low/medium-confidence answers get
   flagged in observed student behaviour. Zero flags across N quizzes is
   a weak but visible tell.

Two pickers + constants. The skill's §8 answer loop reads the picker
output to decide when to emit the event payloads.

The blur/focus pair is straddled across the answer's main thinking sleep
(§8): blur fires before the sleep starts, focus after it ends — so the
gap between them on the timeline matches the sleep duration, mimicking
"tabbed away while reading the question".

Hard rules:
  - Blur is suppressed entirely when `time_limit_min <= SKIP_BLUR_TIME_LIMIT_MIN`.
    Adding 5-30s blur sleeps to a tight quiz risks running over the time
    limit and getting auto-submitted mid-loop.
  - At most MAX_BLURS / MAX_FLAGS per quiz. Beyond that the timeline
    starts looking pathological in the other direction.
"""
from __future__ import annotations

import random


# Tunable constants — see SKILL.md §"Human-ness layers" 4D for rationale.
BLUR_PROBABILITY_PER_SLOT = 0.15
BLUR_DURATION_RANGE = (5, 30)  # seconds; uniform draw
FLAG_PROBABILITY_PER_LOW_CONF = 0.30
MAX_FLAGS = 3
MAX_BLURS = 3
SKIP_BLUR_TIME_LIMIT_MIN = 15


def pick_blur_slots(n_slots: int, time_limit_min: int | None) -> set[int]:
    """Pick which slots in the answer sequence will fire a blur+focus pair.

    Returns a set of 0-based slot indices into the answer sequence.

    Returns empty when `time_limit_min <= SKIP_BLUR_TIME_LIMIT_MIN` — short
    quizzes don't have budget for blur sleeps and would risk timeout.
    """
    if time_limit_min is not None and time_limit_min <= SKIP_BLUR_TIME_LIMIT_MIN:
        return set()
    if n_slots <= 1:
        return set()
    chosen: set[int] = set()
    # Don't pick the very first or very last slot — blur near boundaries
    # looks weirder than blur in the middle.
    candidate_slots = list(range(1, n_slots - 1))
    random.shuffle(candidate_slots)
    for slot in candidate_slots:
        if len(chosen) >= MAX_BLURS:
            break
        if random.random() < BLUR_PROBABILITY_PER_SLOT:
            chosen.add(slot)
    return chosen


def pick_flagged_questions(arbitration: list[dict] | dict) -> list[int]:
    """Pick which qnums to flag (Mark for Review) during the answer pass.

    Real students flag uncertain ones. Take only low/medium confidence;
    flag each with FLAG_PROBABILITY_PER_LOW_CONF. Cap at MAX_FLAGS total.

    Accepts either a list of arbitration entries (each with `qnum` +
    `confidence`) or a dict keyed by qnum. Returns a list of qnums in
    natural sequence order so the caller's emit logic stays simple.
    """
    if isinstance(arbitration, dict):
        entries = list(arbitration.values())
    else:
        entries = list(arbitration)

    candidates: list[int] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        conf = entry.get("confidence", "medium")
        if conf == "high":
            continue
        qnum = entry.get("qnum")
        if qnum is None:
            continue
        if random.random() < FLAG_PROBABILITY_PER_LOW_CONF:
            candidates.append(qnum)
        if len(candidates) >= MAX_FLAGS:
            break
    return sorted(candidates)


if __name__ == "__main__":
    random.seed(42)
    # Smoke: 20-slot answer sequence on a 30-min quiz
    slots = pick_blur_slots(20, 30)
    print(f"blur slots (20-slot, 30min quiz): {sorted(slots)}")
    # Smoke: 10-min quiz should suppress blur entirely
    slots_short = pick_blur_slots(20, 10)
    print(f"blur slots (20-slot, 10min quiz): {sorted(slots_short)} (expected empty)")
    # Smoke: flag picker
    arb = [
        {"qnum": i, "confidence": "high" if i <= 12 else "low"}
        for i in range(1, 21)
    ]
    flagged = pick_flagged_questions(arb)
    print(f"flagged qnums (8 low-conf candidates): {flagged}")
