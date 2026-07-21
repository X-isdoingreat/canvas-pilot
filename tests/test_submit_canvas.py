from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.submit_canvas import (
    SubmissionInputError,
    load_batch_manifest,
    main,
    submit_one,
    submit_text_one,
    submit_url_one,
)


class FakeSubmissionOrigin:
    class AlreadySubmitted(RuntimeError):
        def __init__(self, submission):
            self.submission = submission

    def __init__(self):
        self.file_calls = []
        self.text_calls = []
        self.url_calls = []

    def upload_and_submit_files_with_view(
        self, course_id, assignment_id, paths, *, authorization_receipt
    ):
        self.file_calls.append(
            (course_id, assignment_id, list(paths), authorization_receipt)
        )
        return {
            "workflow_state": "submitted",
            "attempt": 1,
            "submitted_at": "2026-07-18T12:00:00Z",
            "attachments": [{"display_name": Path(paths[0]).name, "size": 4}],
        }

    def submit_text_with_view(
        self, course_id, assignment_id, body, *, authorization_receipt
    ):
        self.text_calls.append(
            (course_id, assignment_id, body, authorization_receipt)
        )
        return {
            "workflow_state": "submitted",
            "attempt": 1,
            "submitted_at": "2026-07-18T12:00:00Z",
            "attachments": [],
        }

    def submit_url_with_view(
        self, course_id, assignment_id, url, *, authorization_receipt
    ):
        self.url_calls.append(
            (course_id, assignment_id, url, authorization_receipt)
        )
        return {
            "workflow_state": "submitted",
            "attempt": 1,
            "submitted_at": "2026-07-18T12:00:00Z",
            "attachments": [],
        }


def _receipt(
    *,
    course_id: str = "course-7",
    assignment_id: str = "assignment-19",
    receipt_id: str = "receipt-1",
    actions=None,
):
    return {
        "version": 1,
        "receipt_id": receipt_id,
        "course_id": course_id,
        "target_type": "assignment",
        "target_id": assignment_id,
        "actions": actions
        or [
            "assignment.upload_init",
            "assignment.upload_blob",
            "assignment.submit_files",
        ],
        "signature": "validated-again-at-real-boundary",
    }


def test_file_submission_passes_required_receipt_without_network(tmp_path: Path) -> None:
    draft = tmp_path / "draft.pdf"
    draft.write_bytes(b"test")
    receipt = _receipt()
    fake = FakeSubmissionOrigin()

    result = submit_one(
        "course-7",
        "assignment-19",
        draft,
        authorization_receipt=receipt,
        submission_origin=fake,
    )

    assert result["status"] == "OK"
    assert len(fake.file_calls) == 1
    assert fake.file_calls[0][3] == receipt
    assert fake.text_calls == []


def test_text_submission_passes_required_receipt_without_network() -> None:
    receipt = _receipt(actions=["assignment.submit_text"])
    fake = FakeSubmissionOrigin()

    result = submit_text_one(
        "course-7",
        "assignment-19",
        "A complete response.",
        authorization_receipt=receipt,
        submission_origin=fake,
    )

    assert result["status"] == "OK"
    assert len(fake.text_calls) == 1
    assert fake.text_calls[0][3] == receipt
    assert fake.file_calls == []


def test_url_submission_requires_exact_action_and_reaches_readback_wrapper() -> None:
    receipt = _receipt(actions=["assignment.submit_url"])
    fake = FakeSubmissionOrigin()

    result = submit_url_one(
        "course-7",
        "assignment-19",
        "https://example.test/artifact",
        authorization_receipt=receipt,
        submission_origin=fake,
    )

    assert result["status"] == "OK"
    assert result["workflow_state"] == "submitted"
    assert result["readback_verified"] is True
    assert fake.url_calls[0][2] == "https://example.test/artifact"
    with pytest.raises(SubmissionInputError, match="required action"):
        submit_url_one(
            "course-7",
            "assignment-19",
            "https://example.test/artifact",
            authorization_receipt=_receipt(actions=["assignment.submit_text"]),
            submission_origin=fake,
        )


def test_wrong_target_or_undeclared_action_fails_before_submission(tmp_path: Path) -> None:
    draft = tmp_path / "draft.pdf"
    draft.write_bytes(b"test")
    fake = FakeSubmissionOrigin()
    with pytest.raises(SubmissionInputError, match="assignment does not match"):
        submit_one(
            "course-7",
            "assignment-other",
            draft,
            authorization_receipt=_receipt(),
            submission_origin=fake,
        )
    with pytest.raises(SubmissionInputError, match="required action"):
        submit_text_one(
            "course-7",
            "assignment-19",
            "text",
            authorization_receipt=_receipt(),
            submission_origin=fake,
        )
    assert fake.file_calls == []
    assert fake.text_calls == []


def test_batch_manifest_rejects_receipt_id_reuse_across_targets(tmp_path: Path) -> None:
    first_receipt = tmp_path / "first.json"
    second_receipt = tmp_path / "second.json"
    first_receipt.write_text(
        json.dumps(_receipt(receipt_id="copied-receipt")), encoding="utf-8"
    )
    second_receipt.write_text(
        json.dumps(
            _receipt(
                assignment_id="assignment-20",
                receipt_id="copied-receipt",
            )
        ),
        encoding="utf-8",
    )
    (tmp_path / "a.pdf").write_bytes(b"a")
    (tmp_path / "b.pdf").write_bytes(b"b")
    manifest = tmp_path / "batch.json"
    manifest.write_text(
        json.dumps(
            [
                {
                    "course_id": "course-7",
                    "assignment_id": "assignment-19",
                    "files": ["a.pdf"],
                    "authorization_receipt": "first.json",
                },
                {
                    "course_id": "course-7",
                    "assignment_id": "assignment-20",
                    "files": ["b.pdf"],
                    "authorization_receipt": "second.json",
                },
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(SubmissionInputError, match="cannot be reused"):
        load_batch_manifest(manifest)


def test_batch_manifest_is_windows_safe_and_maps_each_target_to_its_receipt(
    tmp_path: Path,
) -> None:
    draft = tmp_path / "answer.txt"
    draft.write_text("answer", encoding="utf-8")
    receipt = tmp_path / "text-receipt.json"
    receipt.write_text(
        json.dumps(_receipt(actions=["assignment.submit_text"])), encoding="utf-8"
    )
    manifest = tmp_path / "batch.json"
    manifest.write_text(
        json.dumps(
            [
                {
                    "course_id": "course-7",
                    "assignment_id": "assignment-19",
                    "text_file": str(draft),
                    "authorization_receipt": str(receipt),
                }
            ]
        ),
        encoding="utf-8",
    )

    jobs = load_batch_manifest(manifest)
    assert jobs[0]["text"] == "answer"
    assert jobs[0]["authorization_receipt"]["receipt_id"] == "receipt-1"


def test_cli_requires_receipt_before_loading_canvas(capsys) -> None:
    exit_code = main(
        [
            "--course-id",
            "course-7",
            "--assignment-id",
            "assignment-19",
            "--text",
            "answer",
        ]
    )
    assert exit_code == 2
    assert "authorization-receipt" in capsys.readouterr().err
