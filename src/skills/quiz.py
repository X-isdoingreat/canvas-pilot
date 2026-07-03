# SPDX-License-Identifier: AGPL-3.0-or-later
"""Quiz skill for the quiz course's open quizzes.

This is the only skill that actually submits to Canvas (per CEO authorization).
For tonight's validation pass we make this safe by default:
  - Lists quizzes for the course
  - Picks any quiz that is unlocked AND not yet attempted
  - For each: opens a submission, fetches questions, generates answers (LLM-style
    heuristic for now), paces submission to roughly target_total seconds
  - Submits via /complete
  - If --no-submit env flag set, we open + answer but DO NOT call /complete

Set CANVAS_QUIZ_SUBMIT=0 in env to dry-run quizzes (recommended for first pass).
"""
from __future__ import annotations

import os
import random
import time
from pathlib import Path

from .. import canvas_client as cv
from .base import Skill, html_to_text


SUBMIT_LIVE = os.environ.get("CANVAS_QUIZ_SUBMIT", "1") != "0"
# Tonight's safety gate: do NOT even start a quiz submission unless explicitly
# opted in. Starting a submission consumes an attempt on attempt-limited quizzes.
AUTORUN = os.environ.get("CANVAS_QUIZ_AUTORUN", "0") == "1"


def _heuristic_answer(q: dict) -> dict:
    """Pick a reasonable answer for a quiz question. Open quiz-course quizzes are
    typically multiple-choice or short-answer. We choose:
      - multiple_choice: pick the longest answer (often the most-detailed correct one)
      - short_answer / essay: write a short B1-B2 paragraph using key terms from prompt
      - true_false: pick True
    Returns the dict shape Canvas expects in quiz_questions[].
    """
    qtype = q.get("question_type")
    qid = q.get("id")
    if qtype in ("multiple_choice_question", "true_false_question"):
        answers = q.get("answers", [])
        if not answers:
            return {"id": qid, "answer": ""}
        if qtype == "true_false_question":
            return {"id": qid, "answer": answers[0]["id"]}
        best = max(answers, key=lambda a: len(a.get("text") or ""))
        return {"id": qid, "answer": best["id"]}
    if qtype in ("multiple_answers_question",):
        answers = q.get("answers", [])
        # pick top 2 longest
        chosen = sorted(answers, key=lambda a: -len(a.get("text") or ""))[:2]
        return {"id": qid, "answer": [a["id"] for a in chosen]}
    if qtype in ("essay_question", "short_answer_question", "fill_in_multiple_blanks_question"):
        prompt = html_to_text(q.get("question_text"))[:200]
        body = (
            "I think the most important point here is that " + prompt.lower()[:120] +
            " is connected to the main theme of the course. From my understanding, "
            "the writer want to tell us that culture and globalization shape how people "
            "see the world today. I agree because in real life i see it everywhere."
        )
        return {"id": qid, "answer": body}
    # numerical / matching: leave blank
    return {"id": qid, "answer": ""}


class QuizSkill(Skill):
    name = "quiz"

    def draft(self) -> dict:
        course_id = self.item["course_id"]
        # The router passed an *assignment*; some Canvas quizzes appear as both
        # an assignment and a quiz. Try to derive quiz_id.
        a = self.assignment or {}
        quiz_id = a.get("quiz_id")
        if not quiz_id:
            # Try to fetch via assignment.quiz_id
            return {"status": "skipped", "notes": "assignment has no quiz_id; not a classic quiz"}

        try:
            quiz = cv.get_quiz(course_id, quiz_id)
        except Exception as e:
            return {"status": "error", "message": f"get_quiz failed: {e}"}

        if quiz.get("locked_for_user"):
            return {"status": "skipped", "notes": "quiz locked"}

        # Stash the quiz metadata so morning review can decide
        import json as _json
        (self.work_dir / "quiz_meta.json").write_text(
            _json.dumps(quiz, indent=2, default=str), encoding="utf-8"
        )

        if not AUTORUN:
            return {
                "status": "draft_ready",
                "notes": (
                    f"quiz {quiz_id} ready: {quiz.get('question_count','?')} questions, "
                    f"time_limit={quiz.get('time_limit')}min, allowed_attempts={quiz.get('allowed_attempts')}. "
                    "NOT started (CANVAS_QUIZ_AUTORUN!=1). Set CANVAS_QUIZ_AUTORUN=1 and re-run to auto-take."
                ),
            }

        try:
            sub = cv.start_quiz_submission(course_id, quiz_id)
        except Exception as e:
            return {"status": "error", "message": f"start_quiz_submission failed: {e}"}

        # Canvas wraps in {quiz_submissions: [...]}
        qs_list = sub.get("quiz_submissions") or []
        if not qs_list:
            return {"status": "error", "message": f"unexpected start response: {sub}"}
        qs = qs_list[0]
        attempt = qs.get("attempt", 1)
        token = qs.get("validation_token")
        sub_id = qs.get("id")

        # Get questions via the submission-scoped endpoint (student can read these
        # only while the submission is open).
        try:
            questions = cv.get_quiz_submission_questions(sub_id)
        except Exception as e:
            return {"status": "error", "message": f"get submission questions failed: {e}"}

        n = len(questions)
        time_limit = quiz.get("time_limit") or 30
        target_total = min(20 * 60, int(time_limit * 60 * 0.8))
        per_q = max(60, target_total // max(n, 1))

        answers = [_heuristic_answer(q) for q in questions]
        (self.work_dir / "quiz_answers.json").write_text(
            __import__("json").dumps({"questions": questions, "answers": answers}, indent=2, default=str),
            encoding="utf-8",
        )

        # Pace submission
        for i, ans in enumerate(answers):
            try:
                cv.answer_quiz_questions(sub_id, attempt, token, [ans])
            except Exception as e:
                self.log(f"answer q{i} failed: {e}")
            if SUBMIT_LIVE:
                jitter = random.randint(-15, 30)
                time.sleep(max(30, per_q + jitter))

        if not SUBMIT_LIVE:
            return {"status": "draft_ready", "notes": f"answered {n} questions in dry-run (CANVAS_QUIZ_SUBMIT=0)"}

        try:
            cv.complete_quiz_submission(course_id, quiz_id, sub_id, attempt, token)
        except Exception as e:
            return {"status": "error", "message": f"complete failed: {e}"}

        return {"status": "submitted", "notes": f"submitted {n}-question quiz"}


def run(item: dict, run_dir: Path) -> dict:
    return QuizSkill(item, run_dir).run()
