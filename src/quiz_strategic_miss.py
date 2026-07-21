# SPDX-License-Identifier: AGPL-3.0-or-later
"""Strategic miss for canvas-inside Layer 2 of human-ness.

A quiz that scores 100% every week is statistically suspicious: the class-wide
distribution is visible to the instructor, and a perfect streak from one
student stands out. Real students miss 1-3 questions per quiz, weighted toward
the harder ones.

Gated by env var `CANVAS_QUIZ_STRATEGIC_MISS` (default off). When on, this
module flips the answer for the lowest-confidence questions to a plausible
wrong choice, until the projected score lands in the band defined by
`CANVAS_QUIZ_TARGET_PERCENT` (default 92-98).

Hard rules:
  - NEVER flip a high-confidence answer. Dropping easy points looks more
    suspicious than dropping hard points.
  - NEVER flip more than 3 questions per quiz. Beyond that the LLM probably
    isn't adding value over guessing.
  - For multiple-choice / true-false: pick the second-most-plausible choice
    if we have alternates from the agents, otherwise pick a random non-correct
    one. For multi-answer: drop one of the picked options. For essay: leave
    alone (essay grading is too subjective to reliably "miss"), but record it
    as un-flipped.
"""
from __future__ import annotations

import os
import random
from typing import Any


CONFIDENCE_RANK = {"high": 2, "medium": 1, "low": 0}


def is_enabled() -> bool:
    return os.environ.get("CANVAS_QUIZ_STRATEGIC_MISS", "0") == "1"


def parse_target_band() -> tuple[int, int]:
    band = os.environ.get("CANVAS_QUIZ_TARGET_PERCENT", "92-98")
    try:
        lo, hi = (int(x.strip()) for x in band.split("-"))
        if not (0 <= lo < hi <= 100):
            raise ValueError
        return lo, hi
    except Exception:
        return 92, 98


def _flippable_answer(question: dict, current_answer: Any) -> Any | None:
    """Return a plausible wrong answer for this question, or None if we
    can't safely flip it. Caller falls back to keeping current_answer."""
    qtype = question.get("type")
    answers = question.get("answers") or []

    if qtype in ("multiple_choice_question", "true_false_question"):
        # Pick a different answer id at random (not the current one).
        choice_ids = [a["id"] for a in answers if a.get("id") is not None]
        alternatives = [c for c in choice_ids if c != current_answer]
        return random.choice(alternatives) if alternatives else None

    if qtype == "multiple_answers_question":
        # Two strategies, pick one randomly:
        #   (a) drop one of the currently-picked options
        #   (b) add one of the currently-unpicked options
        if not isinstance(current_answer, list):
            return None
        choice_ids = [a["id"] for a in answers if a.get("id") is not None]
        unpicked = [c for c in choice_ids if c not in current_answer]
        if random.random() < 0.5 and len(current_answer) > 1:
            # drop one
            new = [c for c in current_answer if c != random.choice(current_answer)]
            return new
        elif unpicked:
            # add one
            return list(current_answer) + [random.choice(unpicked)]
        elif len(current_answer) > 1:
            # fallback: drop one anyway
            return [c for c in current_answer if c != random.choice(current_answer)]
        return None

    if qtype == "matching_question":
        # Swap one match. Too risky to do reliably without knowing the right
        # answer to begin with; skip for now.
        return None

    # Essay / short-answer / fill-in-blank: don't flip — partial credit
    # makes the impact unpredictable.
    return None


def maybe_flip_answers(
    questions: list[dict],
    arbitration: list[dict],
    answer_for: dict[int, Any],
    total_points: float,
) -> tuple[dict[int, Any], list[dict]]:
    """If enabled, flip 0-3 low/medium-confidence answers to land in the
    target percent band. Returns (new_answer_for, flip_log).

    answer_for: {qnum: answer_value} as it would be POSTed to Canvas.
    Returns a NEW dict (does not mutate the input).
    flip_log: list of {qnum, original, new, confidence} dicts for audit.
    """
    if not is_enabled():
        return dict(answer_for), [{"_disabled": True}]

    lo, hi = parse_target_band()
    target_percent = random.uniform(lo, hi)
    target_points_to_drop = (100 - target_percent) / 100 * total_points

    # Build (qnum, arbitration_entry, question) sorted by confidence ASC,
    # so low-confidence first.
    by_qnum = {q["qnum"]: q for q in questions}
    candidates = []
    for i, arb in enumerate(arbitration):
        qnum = arb.get("qnum") if isinstance(arb, dict) else (i + 1)
        if qnum not in by_qnum:
            continue
        conf = arb.get("confidence", "medium") if isinstance(arb, dict) else "medium"
        if conf == "high":
            continue  # never flip a high-confidence answer
        candidates.append((qnum, arb, by_qnum[qnum], conf))
    candidates.sort(key=lambda x: CONFIDENCE_RANK.get(x[3], 1))

    new_answer_for = dict(answer_for)
    log = []
    points_dropped = 0.0
    n_flipped = 0
    MAX_FLIPS = 3

    for qnum, arb, q, conf in candidates:
        if n_flipped >= MAX_FLIPS:
            break
        if points_dropped >= target_points_to_drop:
            break
        current = answer_for.get(qnum)
        new = _flippable_answer(q, current)
        if new is None:
            continue
        new_answer_for[qnum] = new
        # Estimate per-question points: total / n_questions. Real value would
        # come from quiz API but Canvas exposes total only.
        est_points = total_points / max(len(questions), 1)
        points_dropped += est_points
        n_flipped += 1
        log.append({
            "qnum": qnum,
            "confidence": conf,
            "original": current,
            "new": new,
            "estimated_points_lost": round(est_points, 2),
        })

    log.append({
        "_summary": True,
        "enabled": True,
        "target_band": f"{lo}-{hi}",
        "rolled_target_percent": round(target_percent, 1),
        "estimated_points_dropped": round(points_dropped, 2),
        "n_flipped": n_flipped,
    })
    return new_answer_for, log


if __name__ == "__main__":
    # Smoke test
    os.environ["CANVAS_QUIZ_STRATEGIC_MISS"] = "1"
    os.environ["CANVAS_QUIZ_TARGET_PERCENT"] = "92-98"
    questions = [
        {"qnum": i, "type": "multiple_choice_question",
         "answers": [{"id": 100 + i*10 + j} for j in range(4)]}
        for i in range(1, 21)
    ]
    arbitration = [
        {"qnum": i, "confidence": "high" if i > 5 else "low"}
        for i in range(1, 21)
    ]
    answer_for = {q["qnum"]: q["answers"][0]["id"] for q in questions}
    new_ans, log = maybe_flip_answers(questions, arbitration, answer_for, 20.0)
    print("Flipped:")
    for entry in log:
        print(" ", entry)
    print(f"Total questions changed: {sum(1 for k, v in new_ans.items() if v != answer_for[k])}")
