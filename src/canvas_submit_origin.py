# SPDX-License-Identifier: AGPL-3.0-or-later
"""Verified Canvas assignment submission wrappers.

Every path performs authoritative pre-reads, uses the same signed mutation
receipt for the write(s), and verifies the final Canvas state by read-back.
The module contains no course-specific or private identity data and therefore
works in a clean public clone.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from . import canvas_client as cv
from .authorization import require_mutation_authorization


class AlreadySubmitted(RuntimeError):
    def __init__(self, submission: Mapping[str, Any], course_id: Any, assignment_id: Any):
        self.submission = dict(submission)
        self.course_id = course_id
        self.assignment_id = assignment_id
        super().__init__(f"Canvas assignment {assignment_id} already has a submission")


class SubmissionVerificationError(RuntimeError):
    """Canvas read-back did not prove the requested submission completed."""


def _preflight_actions(
    course_id: Any,
    assignment_id: Any,
    authorization_receipt: Any,
    actions: Sequence[str],
) -> None:
    """Validate a multi-write operation completely before its first write."""

    for action in actions:
        require_mutation_authorization(
            authorization_receipt,
            canvas_origin=cv.BASE,
            course_id=course_id,
            target_type="assignment",
            target_id=assignment_id,
            action=action,
        )


def _is_submitted(submission: Mapping[str, Any]) -> bool:
    return bool(submission.get("submitted_at")) or submission.get("workflow_state") in {
        "submitted",
        "graded",
    }


def _pre_gate(course_id: Any, assignment_id: Any) -> dict[str, Any]:
    cv.get_assignment(course_id, assignment_id)
    submission = cv.get_submission(course_id, assignment_id)
    if _is_submitted(submission):
        raise AlreadySubmitted(submission, course_id, assignment_id)
    return submission


def _post_verify(course_id: Any, assignment_id: Any) -> dict[str, Any]:
    submission = cv.get_submission(course_id, assignment_id)
    if not _is_submitted(submission):
        raise SubmissionVerificationError(
            "Canvas submission POST returned, but read-back is not submitted/graded"
        )
    return submission


def existing_submission_result(exc_or_submission: AlreadySubmitted | Mapping[str, Any]) -> dict[str, Any]:
    """Canonical result shape for a pre-existing Canvas submission."""

    submission = (
        exc_or_submission.submission
        if isinstance(exc_or_submission, AlreadySubmitted)
        else dict(exc_or_submission)
    )
    submitted_at = submission.get("submitted_at")
    if not submitted_at:
        raise SubmissionVerificationError("pre-existing submission has no submitted_at timestamp")
    return {
        "status": "submitted",
        "reason_code": "already_submitted",
        "submitted_at": submitted_at,
        "metadata": {
            "canvas_workflow_state": submission.get("workflow_state"),
            "readback_verified": True,
            "attempt": submission.get("attempt"),
            "graded": submission.get("workflow_state") == "graded",
        },
        "notes": "Canvas already contained a submission; no new attempt was created.",
    }


def submit_files_with_view(
    course_id: Any,
    assignment_id: Any,
    file_ids: list[Any],
    *,
    authorization_receipt=None,
) -> dict[str, Any]:
    _pre_gate(course_id, assignment_id)
    _preflight_actions(
        course_id,
        assignment_id,
        authorization_receipt,
        ["assignment.submit_files"],
    )
    cv.submit_files(
        course_id,
        assignment_id,
        file_ids,
        authorization_receipt=authorization_receipt,
    )
    return _post_verify(course_id, assignment_id)


def submit_text_with_view(
    course_id: Any,
    assignment_id: Any,
    body: str,
    *,
    authorization_receipt=None,
) -> dict[str, Any]:
    _pre_gate(course_id, assignment_id)
    _preflight_actions(
        course_id,
        assignment_id,
        authorization_receipt,
        ["assignment.submit_text"],
    )
    cv.submit_text(
        course_id,
        assignment_id,
        body,
        authorization_receipt=authorization_receipt,
    )
    return _post_verify(course_id, assignment_id)


def submit_url_with_view(
    course_id: Any,
    assignment_id: Any,
    url: str,
    *,
    authorization_receipt=None,
) -> dict[str, Any]:
    _pre_gate(course_id, assignment_id)
    _preflight_actions(
        course_id,
        assignment_id,
        authorization_receipt,
        ["assignment.submit_url"],
    )
    cv.submit_url(
        course_id,
        assignment_id,
        url,
        authorization_receipt=authorization_receipt,
    )
    return _post_verify(course_id, assignment_id)


def upload_and_submit_files_with_view(
    course_id: Any,
    assignment_id: Any,
    local_paths: Sequence[Path | str],
    *,
    authorization_receipt=None,
) -> dict[str, Any]:
    """Pre-check, upload every file, submit once, then verify by read-back."""

    _pre_gate(course_id, assignment_id)
    _preflight_actions(
        course_id,
        assignment_id,
        authorization_receipt,
        [
            "assignment.upload_init",
            "assignment.upload_blob",
            "assignment.submit_files",
        ],
    )
    paths = [Path(path) for path in local_paths]
    if not paths or any(not path.is_file() for path in paths):
        raise FileNotFoundError("every local submission path must be an existing file")
    file_objects = [
        cv.upload_submission_file(
            course_id,
            assignment_id,
            path,
            authorization_receipt=authorization_receipt,
        )
        for path in paths
    ]
    file_ids = [obj.get("id") for obj in file_objects if isinstance(obj, Mapping)]
    if len(file_ids) != len(paths) or any(value is None for value in file_ids):
        raise SubmissionVerificationError("Canvas upload did not return one file id per path")
    cv.submit_files(
        course_id,
        assignment_id,
        file_ids,
        authorization_receipt=authorization_receipt,
    )
    return _post_verify(course_id, assignment_id)
