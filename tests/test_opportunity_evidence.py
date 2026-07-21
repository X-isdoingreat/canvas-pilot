# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import datetime as dt
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Importing canvas_client initializes its backend, but these tests never make a
# network request.
os.environ.setdefault("CANVAS_BASE", "https://canvas.example/api/v1")
os.environ.setdefault("CANVAS_AUTH", "token")
os.environ.setdefault("CANVAS_TOKEN", "test-token")

from src import canvas_client
from src.opportunity_evidence import (
    derive_quiz_feedback_capabilities,
    project_submission_feedback_observation_for_opportunity,
)


NOW = dt.datetime(2026, 7, 16, 12, 0, tzinfo=dt.timezone.utc)


def _quiz(**updates):
    quiz = {
        "allowed_attempts": 2,
        "scoring_policy": "keep_highest",
        "hide_results": None,
        "one_time_results": False,
        "show_correct_answers": True,
        "show_correct_answers_last_attempt": False,
        "show_correct_answers_at": None,
        "hide_correct_answers_at": None,
    }
    quiz.update(updates)
    return quiz


def test_two_attempts_immediate_answers_and_keep_highest():
    evidence = derive_quiz_feedback_capabilities(_quiz(), now=NOW)

    assert evidence["source"]["status"] == "complete"
    assert evidence["source"]["student_state_used"] == "no"
    assert evidence["source"]["attempt_started"] == "no"
    assert evidence["attempts"] == {
        "status": "known",
        "kind": "limited",
        "allowed_attempts": 2,
        "unlimited": "no",
        "evidence_source": ["allowed_attempts"],
    }
    assert evidence["retry"]["configured"] == "yes"
    assert evidence["retry"]["remaining_now"] == "unknown"
    assert evidence["scoring"]["policy"] == "keep_highest"
    assert evidence["scoring"]["best_score_protected"] == "yes"
    assert evidence["results"]["visibility"] == "after_each_attempt"
    assert evidence["correct_answers"]["visibility"] == "after_each_attempt"
    assert (
        evidence["correct_answers"]["available_before_retry_by_settings"]
        == "yes"
    )


def test_results_only_does_not_invent_score_or_item_feedback():
    evidence = derive_quiz_feedback_capabilities(
        _quiz(show_correct_answers=False), now=NOW
    )

    assert evidence["results"]["visibility"] == "after_each_attempt"
    assert evidence["results"]["numeric_score_visibility"] == "unknown"
    assert evidence["correct_answers"]["visibility"] == "hidden"
    assert evidence["item_correctness"]["visibility"] == "unknown"
    assert evidence["own_answers"]["visibility"] == "unknown"


def test_correct_answers_only_after_last_attempt():
    evidence = derive_quiz_feedback_capabilities(
        _quiz(show_correct_answers_last_attempt=True), now=NOW
    )

    assert evidence["results"]["visibility"] == "after_each_attempt"
    assert evidence["correct_answers"]["visibility"] == "after_last_attempt"
    assert (
        evidence["correct_answers"]["available_before_retry_by_settings"]
        == "no"
    )


def test_results_hidden_until_last_attempt_are_not_retry_feedback():
    evidence = derive_quiz_feedback_capabilities(
        _quiz(hide_results="until_after_last_attempt"), now=NOW
    )

    assert evidence["results"]["visibility"] == "after_last_attempt"
    assert (
        evidence["correct_answers"]["visibility"]
        == "not_before_last_attempt"
    )
    assert (
        evidence["correct_answers"]["available_before_retry_by_settings"]
        == "no"
    )
    assert (
        evidence["item_correctness"]["available_before_retry_by_settings"]
        == "no"
    )


def test_results_hidden_always_override_answer_and_one_time_settings():
    evidence = derive_quiz_feedback_capabilities(
        _quiz(hide_results="always", one_time_results=True), now=NOW
    )

    assert evidence["results"]["visibility"] == "hidden"
    assert evidence["results"]["view_limit"] == "hidden"
    assert evidence["results"]["numeric_score_visibility"] == "no"
    assert evidence["correct_answers"]["visibility"] == "hidden"
    assert evidence["item_correctness"]["visibility"] == "hidden"
    assert {item["code"] for item in evidence["issues"]} >= {
        "one_time_results_overridden",
        "correct_answers_overridden_by_hidden_results",
    }


def test_one_attempt_immediate_feedback_has_no_retry():
    evidence = derive_quiz_feedback_capabilities(
        _quiz(allowed_attempts=1), now=NOW
    )

    assert evidence["retry"]["configured"] == "no"
    assert evidence["scoring"]["status"] == "not_applicable"
    assert evidence["scoring"]["best_score_protected"] == "not_applicable"
    assert evidence["results"]["visibility"] == "after_each_attempt"
    assert evidence["correct_answers"]["visibility"] == "after_each_attempt"
    assert (
        evidence["correct_answers"]["available_before_retry_by_settings"]
        == "not_applicable"
    )


def test_unlimited_attempts_are_explicit_not_a_negative_limit():
    evidence = derive_quiz_feedback_capabilities(
        _quiz(allowed_attempts=-1), now=NOW
    )

    assert evidence["attempts"]["kind"] == "unlimited"
    assert evidence["attempts"]["allowed_attempts"] == -1
    assert evidence["attempts"]["unlimited"] == "yes"
    assert evidence["retry"]["configured"] == "yes"
    assert evidence["scoring"]["best_score_protected"] == "yes"


def test_missing_metadata_stays_unknown():
    evidence = derive_quiz_feedback_capabilities({}, now=NOW)

    assert evidence["source"]["status"] == "partial"
    assert evidence["attempts"]["status"] == "unknown"
    assert evidence["retry"]["configured"] == "unknown"
    assert evidence["results"]["visibility"] == "unknown"
    assert evidence["correct_answers"]["visibility"] == "unknown"
    assert evidence["item_correctness"]["visibility"] == "unknown"
    assert evidence["own_answers"]["visibility"] == "unknown"


def test_contradictory_metadata_is_reported_instead_of_guessed():
    evidence = derive_quiz_feedback_capabilities(
        _quiz(
            show_correct_answers_at="2026-07-20T12:00:00Z",
            hide_correct_answers_at="2026-07-18T12:00:00Z",
        ),
        now=NOW,
    )

    assert evidence["source"]["status"] == "conflicting"
    assert evidence["correct_answers"]["status"] == "conflicting"
    assert evidence["correct_answers"]["visibility"] == "unknown"
    assert "reversed_correct_answer_window" in {
        item["code"] for item in evidence["issues"]
    }


def test_scheduled_and_expired_correct_answer_windows_are_factual():
    scheduled = derive_quiz_feedback_capabilities(
        _quiz(show_correct_answers_at="2026-07-17T12:00:00Z"), now=NOW
    )
    expired = derive_quiz_feedback_capabilities(
        _quiz(hide_correct_answers_at="2026-07-15T12:00:00Z"), now=NOW
    )

    assert scheduled["correct_answers"]["visibility"] == "scheduled"
    assert (
        scheduled["correct_answers"]["available_before_retry_by_settings"]
        == "unknown"
    )
    assert expired["correct_answers"]["visibility"] == "expired"
    assert (
        expired["correct_answers"]["available_before_retry_by_settings"]
        == "no"
    )


def test_safe_assignment_spec_keeps_prompt_and_pointers_but_strips_state(
    monkeypatch,
):
    raw = {
        "id": 77,
        "course_id": 12,
        "assignment_group_id": 4,
        "name": "Ledger Week 3",
        "description": "<p>Complete the attached worksheet.</p>",
        "due_at": "2026-07-20T23:59:00Z",
        "points_possible": 20,
        "grading_type": "points",
        "submission_types": ["online_upload"],
        "allowed_extensions": ["docx", "xlsx"],
        "quiz_id": None,
        "published": True,
        "locked_for_user": False,
        "annotatable_attachment_id": 99,
        "attachments": [
            {
                "id": 99,
                "display_name": "worksheet.docx",
                "url": "https://canvas.example/files/99/download",
                "submission": {"score": 20},
            }
        ],
        "rubric": [
            {
                "id": "criterion-1",
                "description": "Balances",
                "points": 5,
                "ratings": [
                    {
                        "id": "rating-1",
                        "description": "Complete",
                        "points": 5,
                        "comments": "student-specific",
                    }
                ],
                "rubric_assessment": {"points": 4},
            }
        ],
        "external_tool_tag_attributes": {
            "url": "https://tool.example/launch",
            "new_tab": True,
            "oauth_consumer_key": "must-not-pass",
        },
        "submission": {"grade": "A", "score": 20},
        "grade": "A",
        "score": 20,
        "answers": ["secret"],
        "feedback": "student feedback",
        "submission_history": [{"attempt": 1}],
        "comments": [{"comment": "private"}],
    }
    calls = []

    def fake_get(path, **params):
        calls.append((path, params))
        return raw

    monkeypatch.setattr(canvas_client, "get", fake_get)
    projected = canvas_client.get_assignment_spec_for_opportunity(12, 77)

    assert calls == [("/courses/12/assignments/77", {})]
    assert projected["name"] == "Ledger Week 3"
    assert projected["description"].startswith("<p>")
    assert projected["allowed_extensions"] == ["docx", "xlsx"]
    assert projected["attachments"][0] == {
        "id": 99,
        "display_name": "worksheet.docx",
        "url": "https://canvas.example/files/99/download",
    }
    assert projected["rubric"][0]["ratings"][0] == {
        "id": "rating-1",
        "description": "Complete",
        "points": 5,
    }
    assert projected["external_tool_tag_attributes"] == {
        "url": "https://tool.example/launch",
        "new_tab": True,
    }
    for forbidden in (
        "submission",
        "grade",
        "score",
        "answers",
        "feedback",
        "submission_history",
        "comments",
    ):
        assert forbidden not in projected
    assert "rubric_assessment" not in projected["rubric"][0]
    assert "submission" not in projected["attachments"][0]


def test_opportunity_assignment_list_never_requests_or_returns_submission(
    monkeypatch,
):
    calls = []

    def fake_paginate(path, **params):
        calls.append((path, params))
        return [
            {
                "id": 1,
                "name": "Quiz 1",
                "submission_types": ["online_quiz"],
                "submission": {"score": 9},
            }
        ]

    monkeypatch.setattr(canvas_client, "paginate", fake_paginate)
    assignments = canvas_client.list_assignments_for_opportunity(12)

    assert calls == [
        (
            "/courses/12/assignments",
            {"per_page": 50, "order_by": "due_at"},
        )
    ]
    assert assignments == [
        {"id": 1, "name": "Quiz 1", "submission_types": ["online_quiz"]}
    ]
    assert "submission" not in calls[0][1]
    assert "include" not in calls[0][1]


def test_submission_observation_never_returns_sensitive_raw_values():
    raw = {
        "id": 7654321,
        "name": "Completed sibling",
        "submission": {
            "workflow_state": "graded",
            "score": 9876543.125,
            "grade": "PRIVATE-GRADE-ALPHA",
            "attempt": 2,
            "submitted_at": "2026-07-15T11:30:00Z",
            "body": "PRIVATE-BODY-SENTINEL",
            "url": "https://private.example/PRIVATE-RESPONSE-URL",
            "submission_data": {"answer_id": 987654321},
            "answers": ["PRIVATE-ANSWER-SENTINEL"],
            "attachments": [
                {"filename": "PRIVATE-ATTACHMENT-SENTINEL.docx"}
            ],
            "submission_comments": [
                {"comment": "PRIVATE-COMMENT-SENTINEL"}
            ],
            "rubric_assessment": {
                "criterion-private": {
                    "comments": "PRIVATE-RUBRIC-SENTINEL",
                    "points": 4.5,
                }
            },
            "submission_history": [
                {"body": "PRIVATE-HISTORY-SENTINEL", "score": 1}
            ],
            "feedback": "PRIVATE-FEEDBACK-SENTINEL",
        },
    }

    observation = project_submission_feedback_observation_for_opportunity(raw)

    assert observation["source"]["status"] == "complete"
    assert observation["source"]["raw_submission_returned"] == "no"
    assert observation["source"]["attempt_started"] == "no"
    assert observation["observation_present"] == "yes"
    assert observation["workflow"]["category"] == "graded"
    assert observation["numeric_score"]["visible"] == "yes"
    assert observation["display_grade"]["visible"] == "yes"
    assert observation["own_response"]["record_present"] == "yes"
    assert observation["attempt"]["number"] == 2
    assert observation["attempt"]["used"] == "yes"
    assert (
        observation["comments_feedback"]["comment_records_present"] == "yes"
    )
    assert (
        observation["comments_feedback"]["rubric_feedback_record_present"]
        == "yes"
    )
    assert observation["comments_feedback"]["grader_authorship"] == "unknown"

    rendered = repr(observation)
    for secret in (
        "9876543.125",
        "PRIVATE-GRADE-ALPHA",
        "PRIVATE-BODY-SENTINEL",
        "PRIVATE-RESPONSE-URL",
        "987654321",
        "PRIVATE-ANSWER-SENTINEL",
        "PRIVATE-ATTACHMENT-SENTINEL",
        "PRIVATE-COMMENT-SENTINEL",
        "PRIVATE-RUBRIC-SENTINEL",
        "PRIVATE-HISTORY-SENTINEL",
        "PRIVATE-FEEDBACK-SENTINEL",
    ):
        assert secret not in rendered


def test_submission_observation_missing_fields_remain_unknown():
    missing_submission = (
        project_submission_feedback_observation_for_opportunity({})
    )
    absent_submission = project_submission_feedback_observation_for_opportunity(
        {"submission": None}
    )
    partial_submission = project_submission_feedback_observation_for_opportunity(
        {"submission": {"workflow_state": "submitted"}}
    )

    assert missing_submission["observation_present"] == "unknown"
    assert missing_submission["source"]["status"] == "partial"
    assert absent_submission["observation_present"] == "no"
    assert absent_submission["source"]["status"] == "absent"
    assert partial_submission["source"]["status"] == "partial"
    assert partial_submission["numeric_score"]["visible"] == "unknown"
    assert partial_submission["display_grade"]["visible"] == "unknown"
    assert partial_submission["own_response"]["record_present"] == "yes"
    assert partial_submission["attempt"]["used"] == "unknown"
    assert (
        partial_submission["comments_feedback"]["any_feedback_record_present"]
        == "unknown"
    )


def test_submission_observation_wrapper_returns_projection_only(monkeypatch):
    calls = []

    def fake_get(path, **params):
        calls.append((path, params))
        return {
            "id": 77,
            "submission": {
                "workflow_state": "graded",
                "score": 19.75,
                "grade": "PRIVATE-WRAPPER-GRADE",
                "attempt": 1,
                "body": "PRIVATE-WRAPPER-BODY",
                "submission_comments": [],
                "rubric_assessment": None,
            },
        }

    monkeypatch.setattr(canvas_client, "get", fake_get)
    observation = (
        canvas_client.get_submission_feedback_observation_for_opportunity(12, 77)
    )

    assert calls == [
        (
            "/courses/12/assignments/77",
            {"include": ["submission"]},
        )
    ]
    assert observation["observation_present"] == "yes"
    assert observation["numeric_score"]["visible"] == "yes"
    assert observation["display_grade"]["visible"] == "yes"
    assert observation["attempt"]["number"] == 1
    assert "PRIVATE-WRAPPER-GRADE" not in repr(observation)
    assert "PRIVATE-WRAPPER-BODY" not in repr(observation)
    assert "submission" not in observation
