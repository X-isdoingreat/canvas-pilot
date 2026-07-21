# SPDX-License-Identifier: AGPL-3.0-or-later
"""Safe, factual evidence derivation for Canvas Skill Opportunity.

This module does not call Canvas, start an attempt, classify prose, or rank
candidates. It projects assignment/spec and already-fetched submission data to
the minimum safe facts needed by Opportunity, and interprets settings already
returned for a Canvas Classic Quiz.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Iterable


_OPPORTUNITY_ASSIGNMENT_SCALAR_FIELDS = (
    "id",
    "course_id",
    "assignment_group_id",
    "group_category_id",
    "quiz_id",
    "annotatable_attachment_id",
    "name",
    "description",
    "html_url",
    "url",
    "created_at",
    "updated_at",
    "due_at",
    "unlock_at",
    "lock_at",
    "points_possible",
    "grading_type",
    "position",
    "allowed_attempts",
    "omit_from_final_grade",
    "peer_reviews",
    "automatic_peer_reviews",
    "anonymous_peer_reviews",
    "intra_group_peer_reviews",
    "grade_group_students_individually",
    "anonymous_instructor_annotations",
    "anonymous_grading",
    "is_quiz_assignment",
    "due_date_required",
    "important_dates",
    "published",
    "workflow_state",
    "only_visible_to_overrides",
    "locked_for_user",
    "lock_explanation",
    "frozen",
)

_OPPORTUNITY_ATTACHMENT_FIELDS = (
    "id",
    "folder_id",
    "display_name",
    "filename",
    "content-type",
    "content_type",
    "url",
    "html_url",
    "preview_url",
    "thumbnail_url",
    "size",
    "mime_class",
    "unlock_at",
    "lock_at",
    "locked",
    "hidden",
    "locked_for_user",
)

_OPPORTUNITY_RUBRIC_CRITERION_FIELDS = (
    "id",
    "description",
    "long_description",
    "points",
    "criterion_use_range",
)

_OPPORTUNITY_RUBRIC_RATING_FIELDS = (
    "id",
    "description",
    "long_description",
    "points",
)

_OPPORTUNITY_RUBRIC_SETTINGS_FIELDS = (
    "id",
    "title",
    "points_possible",
    "free_form_criterion_comments",
    "hide_score_total",
    "hide_points",
)

_OPPORTUNITY_EXTERNAL_TOOL_FIELDS = (
    "url",
    "new_tab",
    "resource_link_id",
    "content_type",
    "content_id",
)

_OPPORTUNITY_LOCK_INFO_FIELDS = (
    "asset_string",
    "unlock_at",
    "lock_at",
    "manually_locked",
    "module_prerequisite_names",
)

_OPPORTUNITY_DISCUSSION_TOPIC_FIELDS = (
    "id",
    "title",
    "message",
    "html_url",
    "published",
    "locked",
    "locked_for_user",
    "lock_at",
    "delayed_post_at",
)


_QUIZ_SETTING_FIELDS = (
    "allowed_attempts",
    "scoring_policy",
    "hide_results",
    "one_time_results",
    "show_correct_answers",
    "show_correct_answers_last_attempt",
    "show_correct_answers_at",
    "hide_correct_answers_at",
)


def _allowlisted_dict(value: Any, fields: Iterable[str]) -> dict:
    if not isinstance(value, dict):
        return {}
    return {field: value[field] for field in fields if field in value}


def project_assignment_spec_for_opportunity(assignment: dict) -> dict:
    """Return only assignment-spec facts Opportunity may inspect.

    The allowlist blocks submissions, scores, grades, answers, feedback,
    comments, and submission history even if the input was fetched with an
    unsafe include. Nested attachments and rubrics are projected separately so
    student-specific state cannot hitch a ride inside them.
    """
    if not isinstance(assignment, dict):
        raise TypeError("assignment must be a mapping")

    projected = _allowlisted_dict(
        assignment, _OPPORTUNITY_ASSIGNMENT_SCALAR_FIELDS
    )

    for field in ("submission_types", "allowed_extensions"):
        value = assignment.get(field)
        if isinstance(value, (list, tuple)):
            projected[field] = [item for item in value if isinstance(item, str)]

    attachments = assignment.get("attachments")
    if isinstance(attachments, list):
        projected["attachments"] = [
            _allowlisted_dict(item, _OPPORTUNITY_ATTACHMENT_FIELDS)
            for item in attachments
            if isinstance(item, dict)
        ]

    rubric = assignment.get("rubric")
    if isinstance(rubric, list):
        projected_rubric = []
        for criterion in rubric:
            if not isinstance(criterion, dict):
                continue
            clean = _allowlisted_dict(
                criterion, _OPPORTUNITY_RUBRIC_CRITERION_FIELDS
            )
            ratings = criterion.get("ratings")
            if isinstance(ratings, list):
                clean["ratings"] = [
                    _allowlisted_dict(rating, _OPPORTUNITY_RUBRIC_RATING_FIELDS)
                    for rating in ratings
                    if isinstance(rating, dict)
                ]
            projected_rubric.append(clean)
        projected["rubric"] = projected_rubric

    nested_fields = (
        ("rubric_settings", _OPPORTUNITY_RUBRIC_SETTINGS_FIELDS),
        ("external_tool_tag_attributes", _OPPORTUNITY_EXTERNAL_TOOL_FIELDS),
        ("external_tool_settings", _OPPORTUNITY_EXTERNAL_TOOL_FIELDS),
        ("lock_info", _OPPORTUNITY_LOCK_INFO_FIELDS),
        ("discussion_topic", _OPPORTUNITY_DISCUSSION_TOPIC_FIELDS),
    )
    for field, allowlist in nested_fields:
        if isinstance(assignment.get(field), dict):
            projected[field] = _allowlisted_dict(assignment[field], allowlist)

    return projected


def _has_payload(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (dict, list, tuple, set, bytes, bytearray)):
        return bool(value)
    return True


def project_submission_feedback_observation_for_opportunity(
    assignment: dict[str, Any],
) -> dict[str, Any]:
    """Reduce an embedded Canvas submission to non-sensitive observations.

    The input is one assignment fetched with ``include=[submission]``. Exact
    scores, display grades, responses, answer IDs, files, comments, feedback,
    and history payloads are inspected only for presence and are never copied
    into the returned mapping.
    """
    if not isinstance(assignment, dict):
        raise TypeError("assignment must be a mapping")

    issues: list[dict[str, Any]] = []
    missing_fields: set[str] = set()
    defaults = {
        "workflow": {
            "status": "unknown",
            "category": "unknown",
            "evidence_source": ["submission.workflow_state"],
        },
        "numeric_score": {
            "status": "unknown",
            "visible": "unknown",
            "evidence_source": ["submission.score"],
        },
        "display_grade": {
            "status": "unknown",
            "visible": "unknown",
            "evidence_source": ["submission.grade"],
        },
        "own_response": {
            "status": "unknown",
            "record_present": "unknown",
            "evidence_source": [
                "submission response-field presence",
                "submission.submitted_at",
                "submission.workflow_state",
            ],
        },
        "attempt": {
            "status": "unknown",
            "number": None,
            "used": "unknown",
            "evidence_source": ["submission.attempt"],
        },
        "comments_feedback": {
            "status": "unknown",
            "comment_records_present": "unknown",
            "rubric_feedback_record_present": "unknown",
            "any_feedback_record_present": "unknown",
            "grader_authorship": "unknown",
            "evidence_source": [
                "submission.submission_comments",
                "submission.rubric_assessment",
            ],
        },
    }

    if "submission" not in assignment:
        return {
            "source": {
                "kind": "canvas_assignment_submission_include",
                "status": "partial",
                "missing_fields": ["submission"],
                "raw_submission_returned": "no",
                "attempt_started": "no",
            },
            "observation_present": "unknown",
            **defaults,
            "issues": [],
        }

    submission = assignment.get("submission")
    if submission is None:
        return {
            "source": {
                "kind": "canvas_assignment_submission_include",
                "status": "absent",
                "missing_fields": [],
                "raw_submission_returned": "no",
                "attempt_started": "no",
            },
            "observation_present": "no",
            **defaults,
            "issues": [],
        }
    if not isinstance(submission, dict):
        return {
            "source": {
                "kind": "canvas_assignment_submission_include",
                "status": "conflicting",
                "missing_fields": [],
                "raw_submission_returned": "no",
                "attempt_started": "no",
            },
            "observation_present": "unknown",
            **defaults,
            "issues": [
                {
                    "code": "invalid_submission_shape",
                    "status": "conflicting",
                    "fields": ["submission"],
                    "detail": "embedded submission must be a mapping or null",
                }
            ],
        }

    raw_workflow = submission.get("workflow_state")
    workflow_categories = {
        "unsubmitted": "not_submitted",
        "submitted": "submitted",
        "pending_review": "submitted_pending_review",
        "graded": "graded",
    }
    if "workflow_state" not in submission or raw_workflow is None:
        workflow_status = "unknown"
        workflow_category = "unknown"
        missing_fields.add("submission.workflow_state")
    elif isinstance(raw_workflow, str) and raw_workflow in workflow_categories:
        workflow_status = "known"
        workflow_category = workflow_categories[raw_workflow]
    else:
        workflow_status = "unknown"
        workflow_category = "unknown"
        issues.append(
            {
                "code": "unrecognized_submission_workflow",
                "status": "unknown",
                "fields": ["submission.workflow_state"],
                "detail": "workflow state was present but not in the safe allowlist",
            }
        )

    if "score" not in submission:
        score_status = "unknown"
        score_visible = "unknown"
        missing_fields.add("submission.score")
    elif submission.get("score") is None:
        score_status = "known"
        score_visible = "no"
    elif isinstance(submission.get("score"), (int, float)) and not isinstance(
        submission.get("score"), bool
    ):
        score_status = "known"
        score_visible = "yes"
    else:
        score_status = "unknown"
        score_visible = "unknown"
        issues.append(
            {
                "code": "unrecognized_score_shape",
                "status": "unknown",
                "fields": ["submission.score"],
                "detail": "score was present but was not numeric or null",
            }
        )

    if "grade" not in submission:
        grade_status = "unknown"
        grade_visible = "unknown"
        missing_fields.add("submission.grade")
    elif submission.get("grade") in (None, ""):
        grade_status = "known"
        grade_visible = "no"
    elif isinstance(submission.get("grade"), (str, int, float)) and not isinstance(
        submission.get("grade"), bool
    ):
        grade_status = "known"
        grade_visible = "yes"
    else:
        grade_status = "unknown"
        grade_visible = "unknown"
        issues.append(
            {
                "code": "unrecognized_grade_shape",
                "status": "unknown",
                "fields": ["submission.grade"],
                "detail": "display grade was present but had an unexpected shape",
            }
        )

    response_fields = (
        "body",
        "url",
        "attachments",
        "media_comment",
        "submission_data",
        "answer",
        "answers",
    )
    response_fields_present = [
        field for field in response_fields if field in submission
    ]
    if any(_has_payload(submission[field]) for field in response_fields_present):
        response_status = "known"
        response_present = "yes"
    elif "submitted_at" in submission and _has_payload(submission.get("submitted_at")):
        response_status = "known"
        response_present = "yes"
    elif workflow_category in ("submitted", "submitted_pending_review", "graded"):
        response_status = "known"
        response_present = "yes"
    elif response_fields_present:
        response_status = "known"
        response_present = "no"
    elif workflow_category == "not_submitted":
        response_status = "known"
        response_present = "no"
    else:
        response_status = "unknown"
        response_present = "unknown"
        missing_fields.add("submission response evidence")

    raw_attempt = submission.get("attempt")
    if "attempt" not in submission or raw_attempt is None:
        attempt_status = "unknown"
        attempt_number = None
        attempt_used = "unknown"
        missing_fields.add("submission.attempt")
    elif isinstance(raw_attempt, int) and not isinstance(raw_attempt, bool) and raw_attempt >= 0:
        attempt_status = "known"
        attempt_number = raw_attempt
        attempt_used = "yes" if raw_attempt >= 1 else "no"
    else:
        attempt_status = "unknown"
        attempt_number = None
        attempt_used = "unknown"
        issues.append(
            {
                "code": "unrecognized_attempt_shape",
                "status": "unknown",
                "fields": ["submission.attempt"],
                "detail": "attempt was present but was not a non-negative integer",
            }
        )

    if "submission_comments" not in submission:
        comments_present = "unknown"
        missing_fields.add("submission.submission_comments")
    elif submission.get("submission_comments") is None:
        comments_present = "no"
    elif isinstance(submission.get("submission_comments"), list):
        comments_present = "yes" if submission["submission_comments"] else "no"
    else:
        comments_present = "unknown"
        issues.append(
            {
                "code": "unrecognized_comments_shape",
                "status": "unknown",
                "fields": ["submission.submission_comments"],
                "detail": "comment records had an unexpected shape",
            }
        )

    if "rubric_assessment" not in submission:
        rubric_feedback_present = "unknown"
        missing_fields.add("submission.rubric_assessment")
    elif submission.get("rubric_assessment") is None:
        rubric_feedback_present = "no"
    elif isinstance(submission.get("rubric_assessment"), dict):
        rubric_feedback_present = (
            "yes" if submission["rubric_assessment"] else "no"
        )
    else:
        rubric_feedback_present = "unknown"
        issues.append(
            {
                "code": "unrecognized_rubric_feedback_shape",
                "status": "unknown",
                "fields": ["submission.rubric_assessment"],
                "detail": "rubric feedback record had an unexpected shape",
            }
        )

    if "yes" in (comments_present, rubric_feedback_present):
        any_feedback_present = "yes"
    elif comments_present == rubric_feedback_present == "no":
        any_feedback_present = "no"
    else:
        any_feedback_present = "unknown"

    if any(item["status"] == "conflicting" for item in issues):
        source_status = "conflicting"
    elif missing_fields or any(item["status"] == "unknown" for item in issues):
        source_status = "partial"
    else:
        source_status = "complete"

    return {
        "source": {
            "kind": "canvas_assignment_submission_include",
            "status": source_status,
            "missing_fields": sorted(missing_fields),
            "raw_submission_returned": "no",
            "attempt_started": "no",
        },
        "observation_present": "yes",
        "workflow": {
            "status": workflow_status,
            "category": workflow_category,
            "evidence_source": ["submission.workflow_state"],
        },
        "numeric_score": {
            "status": score_status,
            "visible": score_visible,
            "evidence_source": ["submission.score"],
        },
        "display_grade": {
            "status": grade_status,
            "visible": grade_visible,
            "evidence_source": ["submission.grade"],
        },
        "own_response": {
            "status": response_status,
            "record_present": response_present,
            "evidence_source": [
                "submission response-field presence",
                "submission.submitted_at",
                "submission.workflow_state",
            ],
        },
        "attempt": {
            "status": attempt_status,
            "number": attempt_number,
            "used": attempt_used,
            "evidence_source": ["submission.attempt"],
        },
        "comments_feedback": {
            "status": (
                "known"
                if comments_present != "unknown"
                and rubric_feedback_present != "unknown"
                else "partial"
            ),
            "comment_records_present": comments_present,
            "rubric_feedback_record_present": rubric_feedback_present,
            "any_feedback_record_present": any_feedback_present,
            "grader_authorship": "unknown",
            "evidence_source": [
                "submission.submission_comments",
                "submission.rubric_assessment",
            ],
        },
        "issues": issues,
    }


def _utc_now(value: dt.datetime | None) -> dt.datetime:
    if value is None:
        return dt.datetime.now(dt.timezone.utc)
    if not isinstance(value, dt.datetime):
        raise TypeError("now must be a datetime or None")
    if value.tzinfo is None:
        return value.replace(tzinfo=dt.timezone.utc)
    return value.astimezone(dt.timezone.utc)


def _parse_timestamp(value: Any) -> tuple[dt.datetime | None, str, str | None]:
    """Return (parsed value, status, normalized display value)."""
    if value in (None, ""):
        return None, "unset", None
    if not isinstance(value, str):
        return None, "invalid", None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None, "invalid", value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    parsed = parsed.astimezone(dt.timezone.utc)
    return parsed, "set", parsed.isoformat()


def derive_quiz_feedback_capabilities(
    quiz: dict[str, Any], now: dt.datetime | None = None
) -> dict[str, Any]:
    """Derive review/retry facts from Canvas Classic Quiz settings.

    The result separates what quiz settings establish from facts that require
    a completed student attempt.  Values are categorical (for example
    ``yes``/``no``/``unknown`` or a visibility policy), never a candidate
    score.  Unexpected or mutually incompatible metadata is reported rather
    than guessed through.
    """
    if not isinstance(quiz, dict):
        raise TypeError("quiz must be a mapping")

    current_time = _utc_now(now)
    issues: list[dict[str, Any]] = []
    missing_fields: set[str] = set()

    def missing(field: str) -> None:
        missing_fields.add(field)

    def issue(
        code: str,
        fields: list[str],
        detail: str,
        severity: str = "conflicting",
    ) -> None:
        issues.append(
            {
                "code": code,
                "status": severity,
                "fields": fields,
                "detail": detail,
            }
        )

    # Attempts and retry configuration.  Remaining attempts are intentionally
    # unknown because that requires per-student submission state.
    raw_attempts = quiz.get("allowed_attempts")
    if "allowed_attempts" not in quiz or raw_attempts is None:
        missing("allowed_attempts")
        attempts_status = "unknown"
        attempts_kind = "unknown"
        allowed_attempts: int | None = None
        unlimited = "unknown"
        retry_configured = "unknown"
    elif isinstance(raw_attempts, bool) or not isinstance(raw_attempts, int):
        issue(
            "invalid_allowed_attempts",
            ["allowed_attempts"],
            "allowed_attempts must be -1 or a positive integer",
        )
        attempts_status = "conflicting"
        attempts_kind = "unknown"
        allowed_attempts = None
        unlimited = "unknown"
        retry_configured = "unknown"
    elif raw_attempts == -1:
        attempts_status = "known"
        attempts_kind = "unlimited"
        allowed_attempts = -1
        unlimited = "yes"
        retry_configured = "yes"
    elif raw_attempts >= 1:
        attempts_status = "known"
        attempts_kind = "limited"
        allowed_attempts = raw_attempts
        unlimited = "no"
        retry_configured = "yes" if raw_attempts > 1 else "no"
    else:
        issue(
            "invalid_allowed_attempts",
            ["allowed_attempts"],
            "allowed_attempts must be -1 or a positive integer",
        )
        attempts_status = "conflicting"
        attempts_kind = "unknown"
        allowed_attempts = None
        unlimited = "unknown"
        retry_configured = "unknown"

    # Scoring policy is meaningful only when the base quiz permits retries.
    raw_policy = quiz.get("scoring_policy")
    if retry_configured == "no":
        scoring_status = "not_applicable"
        scoring_policy = "not_applicable"
        best_score_protected = "not_applicable"
    elif "scoring_policy" not in quiz or raw_policy in (None, ""):
        missing("scoring_policy")
        scoring_status = "unknown"
        scoring_policy = "unknown"
        best_score_protected = "unknown"
    elif raw_policy in ("keep_highest", "keep_latest"):
        scoring_status = "known" if retry_configured == "yes" else "partial"
        scoring_policy = raw_policy
        best_score_protected = "yes" if raw_policy == "keep_highest" else "no"
    else:
        issue(
            "invalid_scoring_policy",
            ["scoring_policy"],
            "Classic Quiz scoring_policy must be keep_highest or keep_latest",
        )
        scoring_status = "conflicting"
        scoring_policy = "unknown"
        best_score_protected = "unknown"

    # Result-view timing.  This describes what the quiz setting permits; it
    # does not assert that an automatically posted numeric grade exists.
    if "hide_results" not in quiz:
        missing("hide_results")
        results_status = "unknown"
        result_visibility = "unknown"
    else:
        raw_hide_results = quiz.get("hide_results")
        if raw_hide_results is None:
            results_status = "known"
            result_visibility = "after_each_attempt"
        elif raw_hide_results == "always":
            results_status = "known"
            result_visibility = "hidden"
        elif raw_hide_results == "until_after_last_attempt":
            results_status = "known"
            result_visibility = "after_last_attempt"
            if retry_configured == "no":
                issue(
                    "last_attempt_results_without_retries",
                    ["hide_results", "allowed_attempts"],
                    "until_after_last_attempt is only valid for a multi-attempt quiz",
                )
                results_status = "conflicting"
        else:
            issue(
                "invalid_hide_results",
                ["hide_results"],
                "hide_results must be null, always, or until_after_last_attempt",
            )
            results_status = "conflicting"
            result_visibility = "unknown"

    if "one_time_results" not in quiz or quiz.get("one_time_results") is None:
        missing("one_time_results")
        one_time_setting = "unknown"
    elif isinstance(quiz.get("one_time_results"), bool):
        one_time_setting = "yes" if quiz["one_time_results"] else "no"
    else:
        issue(
            "invalid_one_time_results",
            ["one_time_results"],
            "one_time_results must be a boolean",
        )
        one_time_setting = "unknown"

    if result_visibility == "hidden":
        result_view_limit = "hidden"
        if one_time_setting == "yes":
            issue(
                "one_time_results_overridden",
                ["hide_results", "one_time_results"],
                "one_time_results has no effect when results are always hidden",
                severity="overridden",
            )
    elif one_time_setting == "yes":
        result_view_limit = "once_immediately_after_submission"
    elif one_time_setting == "no":
        result_view_limit = "revisitable"
    else:
        result_view_limit = "unknown"

    numeric_score_visibility = (
        "no" if result_visibility == "hidden" else "unknown"
    )

    # Correct-answer settings and their time window.
    raw_show_correct = quiz.get("show_correct_answers")
    if "show_correct_answers" not in quiz or raw_show_correct is None:
        missing("show_correct_answers")
        show_correct = "unknown"
    elif isinstance(raw_show_correct, bool):
        show_correct = "yes" if raw_show_correct else "no"
    else:
        issue(
            "invalid_show_correct_answers",
            ["show_correct_answers"],
            "show_correct_answers must be a boolean",
        )
        show_correct = "unknown"

    raw_last_attempt = quiz.get("show_correct_answers_last_attempt")
    if (
        "show_correct_answers_last_attempt" not in quiz
        or raw_last_attempt is None
    ):
        missing("show_correct_answers_last_attempt")
        correct_last_attempt = "unknown"
    elif isinstance(raw_last_attempt, bool):
        correct_last_attempt = "yes" if raw_last_attempt else "no"
    else:
        issue(
            "invalid_correct_answers_last_attempt",
            ["show_correct_answers_last_attempt"],
            "show_correct_answers_last_attempt must be a boolean",
        )
        correct_last_attempt = "unknown"

    show_at, show_at_status, show_at_display = _parse_timestamp(
        quiz.get("show_correct_answers_at")
    )
    hide_at, hide_at_status, hide_at_display = _parse_timestamp(
        quiz.get("hide_correct_answers_at")
    )
    if show_at_status == "invalid":
        issue(
            "invalid_show_correct_answers_at",
            ["show_correct_answers_at"],
            "show_correct_answers_at is not a valid ISO 8601 timestamp",
        )
    if hide_at_status == "invalid":
        issue(
            "invalid_hide_correct_answers_at",
            ["hide_correct_answers_at"],
            "hide_correct_answers_at is not a valid ISO 8601 timestamp",
        )
    reversed_window = bool(show_at and hide_at and show_at > hide_at)
    if reversed_window:
        issue(
            "reversed_correct_answer_window",
            ["show_correct_answers_at", "hide_correct_answers_at"],
            "correct-answer visibility begins after its hide time",
        )

    correct_status = "known"
    if result_visibility == "hidden" or show_correct == "no":
        correct_visibility = "hidden"
        if result_visibility == "hidden" and show_correct == "yes":
            issue(
                "correct_answers_overridden_by_hidden_results",
                ["hide_results", "show_correct_answers"],
                "correct answers cannot be exposed while all results are hidden",
                severity="overridden",
            )
    elif show_correct == "unknown" or result_visibility == "unknown":
        correct_status = "unknown"
        correct_visibility = "unknown"
    elif reversed_window or "invalid" in (show_at_status, hide_at_status):
        correct_status = "conflicting"
        correct_visibility = "unknown"
    else:
        if result_visibility == "after_last_attempt":
            base_visibility = "not_before_last_attempt"
        elif correct_last_attempt == "yes":
            if retry_configured == "yes" and attempts_kind != "unlimited":
                base_visibility = "after_last_attempt"
            elif attempts_kind == "unlimited":
                issue(
                    "last_attempt_answers_with_unlimited_attempts",
                    [
                        "show_correct_answers_last_attempt",
                        "allowed_attempts",
                    ],
                    "an unlimited quiz has no configured last attempt",
                )
                correct_status = "conflicting"
                base_visibility = "unknown"
            else:
                issue(
                    "last_attempt_answers_without_retries",
                    [
                        "show_correct_answers_last_attempt",
                        "allowed_attempts",
                    ],
                    "last-attempt-only answers require a multi-attempt quiz",
                )
                correct_status = "conflicting"
                base_visibility = "unknown"
        elif correct_last_attempt == "no":
            base_visibility = "after_each_attempt"
        else:
            correct_status = "unknown"
            base_visibility = "unknown"

        if hide_at and current_time > hide_at:
            correct_visibility = "expired"
        elif show_at and current_time < show_at:
            if base_visibility in (
                "after_last_attempt",
                "not_before_last_attempt",
            ):
                correct_visibility = "not_before_last_attempt_and_scheduled"
            elif base_visibility == "after_each_attempt":
                correct_visibility = "scheduled"
            else:
                correct_visibility = "unknown"
        else:
            correct_visibility = base_visibility

    if correct_visibility == "after_each_attempt":
        correct_available_now = "yes"
    elif correct_visibility in ("hidden", "expired", "scheduled"):
        correct_available_now = "no"
    else:
        correct_available_now = "unknown"

    if retry_configured == "no":
        correct_before_retry = "not_applicable"
    elif correct_visibility == "after_each_attempt":
        correct_before_retry = "yes"
    elif correct_visibility in (
        "hidden",
        "expired",
        "after_last_attempt",
        "not_before_last_attempt",
        "not_before_last_attempt_and_scheduled",
    ):
        correct_before_retry = "no"
    else:
        correct_before_retry = "unknown"

    if result_visibility == "hidden":
        item_visibility = "hidden"
        item_before_retry = "no" if retry_configured == "yes" else "not_applicable"
        item_status = "known"
    elif result_visibility == "after_last_attempt":
        item_visibility = "unknown"
        item_before_retry = "no" if retry_configured == "yes" else "not_applicable"
        item_status = "unknown"
    else:
        item_visibility = "unknown"
        item_before_retry = "unknown" if retry_configured != "no" else "not_applicable"
        item_status = "unknown"

    has_conflict = any(item["status"] == "conflicting" for item in issues)
    if has_conflict:
        overall_status = "conflicting"
    elif missing_fields:
        overall_status = "partial"
    else:
        overall_status = "complete"

    return {
        "source": {
            "kind": "canvas_classic_quiz_settings",
            "status": overall_status,
            "fields_present": [
                field for field in _QUIZ_SETTING_FIELDS if field in quiz
            ],
            "missing_fields": sorted(missing_fields),
            "student_state_used": "no",
            "attempt_started": "no",
        },
        "attempts": {
            "status": attempts_status,
            "kind": attempts_kind,
            "allowed_attempts": allowed_attempts,
            "unlimited": unlimited,
            "evidence_source": ["allowed_attempts"],
        },
        "retry": {
            "status": attempts_status,
            "configured": retry_configured,
            "remaining_now": "unknown",
            "remaining_now_reason": (
                "per-student attempt state and accommodations were not read"
            ),
            "evidence_source": ["allowed_attempts"],
        },
        "scoring": {
            "status": scoring_status,
            "policy": scoring_policy,
            "best_score_protected": best_score_protected,
            "evidence_source": ["scoring_policy", "allowed_attempts"],
        },
        "results": {
            "status": results_status,
            "visibility": result_visibility,
            "one_time_setting": one_time_setting,
            "view_limit": result_view_limit,
            "numeric_score_visibility": numeric_score_visibility,
            "numeric_score_visibility_reason": (
                "quiz settings do not establish grade posting or manual-grading timing"
                if numeric_score_visibility == "unknown"
                else "all quiz results are hidden"
            ),
            "evidence_source": ["hide_results", "one_time_results"],
        },
        "correct_answers": {
            "status": correct_status,
            "setting": show_correct,
            "last_attempt_only_setting": correct_last_attempt,
            "visibility": correct_visibility,
            "available_now_by_settings": correct_available_now,
            "available_before_retry_by_settings": correct_before_retry,
            "show_at": show_at_display,
            "hide_at": hide_at_display,
            "evidence_source": [
                "hide_results",
                "show_correct_answers",
                "show_correct_answers_last_attempt",
                "show_correct_answers_at",
                "hide_correct_answers_at",
            ],
        },
        "item_correctness": {
            "status": item_status,
            "visibility": item_visibility,
            "available_before_retry_by_settings": item_before_retry,
            "reason": (
                "Classic Quiz settings do not separately establish per-item "
                "correctness visibility"
                if item_visibility == "unknown"
                else "all quiz results are hidden"
            ),
        },
        "own_answers": {
            "status": item_status,
            "visibility": item_visibility,
            "available_before_retry_by_settings": item_before_retry,
            "reason": (
                "Classic Quiz settings do not separately establish prior-response "
                "visibility"
                if item_visibility == "unknown"
                else "all quiz results are hidden"
            ),
        },
        "issues": issues,
    }
