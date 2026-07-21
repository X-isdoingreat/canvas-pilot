from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from src.authorization import (
    AuthorizationDenied,
    authorization_usage_status,
    create_authorization_receipt,
    create_delegated_authorization_receipt,
    finalize_authorization_usage,
    load_authorization_receipt,
    track_authorization_usage,
    validate_authorization_receipt,
)


KEY = b"test-signing-key-material-32-bytes-long!!"
NOW = dt.datetime(2026, 7, 18, 12, 0, tzinfo=dt.timezone.utc)


def _receipt(**overrides):
    kwargs = {
        "canvas_origin": "https://canvas.example.test/api/v1",
        "course_id": 10,
        "target_type": "assignment",
        "target_id": 20,
        "actions": ["assignment.submit_text"],
        "session_id": "thread-1",
        "issued_at": NOW,
        "expires_at": NOW + dt.timedelta(minutes=10),
        "authority_reference": {"approval_id": "approval-1"},
        "signing_key": KEY,
    }
    kwargs.update(overrides)
    return create_authorization_receipt(**kwargs)


def _validate(receipt, **overrides):
    kwargs = {
        "canvas_origin": "https://canvas.example.test",
        "course_id": 10,
        "target_type": "assignment",
        "target_id": 20,
        "action": "assignment.submit_text",
        "session_id": "thread-1",
        "now": NOW + dt.timedelta(minutes=1),
        "signing_key": KEY,
    }
    kwargs.update(overrides)
    return validate_authorization_receipt(receipt, **kwargs)


def test_exact_receipt_round_trip_and_path_load(tmp_path: Path) -> None:
    path = tmp_path / "receipt.json"
    receipt = _receipt(output_path=path)
    loaded = load_authorization_receipt(path)
    assert _validate(loaded)["receipt_id"] == receipt["receipt_id"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("canvas_origin", "https://other.example.test"),
        ("course_id", 11),
        ("target_id", 21),
        ("action", "assignment.submit_url"),
        ("session_id", "thread-2"),
    ],
)
def test_wrong_scope_is_denied(field, value) -> None:
    with pytest.raises(AuthorizationDenied):
        _validate(_receipt(), **{field: value})


def test_expiry_and_tampering_are_denied() -> None:
    receipt = _receipt()
    with pytest.raises(AuthorizationDenied, match="expired"):
        _validate(receipt, now=NOW + dt.timedelta(hours=1))
    tampered = dict(receipt)
    tampered["target_id"] = "999"
    with pytest.raises(AuthorizationDenied, match="signature"):
        _validate(tampered)


def test_synthetic_qa_is_loopback_only() -> None:
    with pytest.raises(AuthorizationDenied, match="loopback"):
        _receipt(synthetic_qa=True)
    qa = _receipt(
        canvas_origin="http://127.0.0.1:3101/api/v1",
        synthetic_qa=True,
    )
    assert _validate(qa, canvas_origin="http://127.0.0.1:3101")["synthetic_qa"] is True
    with pytest.raises(AuthorizationDenied):
        _validate(qa, canvas_origin="http://localhost:3101")


def test_durable_template_can_be_validated_without_session() -> None:
    receipt = _receipt(
        target_type="automation_template",
        target_id="weekly-drafts",
        actions=["assignment.submit_text"],
        session_id="durable:weekly-drafts",
    )
    validated = validate_authorization_receipt(
        receipt,
        canvas_origin="https://canvas.example.test",
        course_id=10,
        target_type="automation_template",
        target_id="weekly-drafts",
        action="assignment.submit_text",
        session_id=None,
        now=NOW + dt.timedelta(minutes=1),
        signing_key=KEY,
    )
    assert validated["target_type"] == "automation_template"


def test_delegated_receipt_is_mechanically_bounded_by_parent() -> None:
    now = dt.datetime.now(dt.timezone.utc)
    parent = create_authorization_receipt(
        canvas_origin="https://canvas.example.test",
        course_id=10,
        target_type="automation_template",
        target_id="weekly-drafts",
        actions=["assignment.submit_text"],
        session_id="durable:weekly-drafts",
        issued_at=now - dt.timedelta(minutes=1),
        expires_at=now + dt.timedelta(hours=1),
        authority_reference={"approval_id": "delegation-fixture"},
        signing_key=KEY,
    )
    child = create_delegated_authorization_receipt(
        parent,
        target_type="assignment",
        target_id=20,
        actions=["assignment.submit_text"],
        session_id="thread-child",
        expires_at=now + dt.timedelta(minutes=10),
        signing_key=KEY,
    )
    assert child["target_id"] == "20"
    assert child["actions"] == ["assignment.submit_text"]

    with pytest.raises(AuthorizationDenied):
        create_delegated_authorization_receipt(
            parent,
            target_type="assignment",
            target_id=20,
            actions=["assignment.submit_url"],
            session_id="thread-child",
            expires_at=now + dt.timedelta(minutes=10),
            signing_key=KEY,
        )
    with pytest.raises(AuthorizationDenied, match="outlive"):
        create_delegated_authorization_receipt(
            parent,
            target_type="assignment",
            target_id=20,
            actions=["assignment.submit_text"],
            session_id="thread-child",
            expires_at=now + dt.timedelta(hours=2),
            signing_key=KEY,
        )


def test_multi_attempt_quiz_receipt_can_be_finalized_after_first_completion(
    tmp_path: Path,
) -> None:
    receipt = _receipt(
        target_type="quiz",
        target_id=30,
        actions=["quiz.start", "quiz.answer", "quiz.complete", "quiz.retake"],
    )
    usage_path = tmp_path / "usage.json"
    track_authorization_usage(
        receipt, action="quiz.complete", record=True, usage_path=usage_path
    )
    assert authorization_usage_status(receipt, usage_path=usage_path).get("terminal_at") is None

    final = finalize_authorization_usage(
        receipt,
        reason="first attempt met the verified score threshold",
        usage_path=usage_path,
    )
    assert final["terminal_action"] == "quiz.complete"
    assert final["finalization_reason"].startswith("first attempt")
    with pytest.raises(AuthorizationDenied, match="already been consumed"):
        track_authorization_usage(
            receipt, action="quiz.retake", record=False, usage_path=usage_path
        )


def test_quiz_receipt_cannot_be_finalized_before_a_completion(tmp_path: Path) -> None:
    receipt = _receipt(
        target_type="quiz",
        target_id=30,
        actions=["quiz.start", "quiz.complete", "quiz.retake"],
    )
    usage_path = tmp_path / "usage.json"
    track_authorization_usage(
        receipt, action="quiz.start", record=True, usage_path=usage_path
    )
    with pytest.raises(AuthorizationDenied, match="before quiz.complete"):
        finalize_authorization_usage(
            receipt, reason="not actually complete", usage_path=usage_path
        )


def test_separate_retake_receipt_consumes_on_its_first_completion(tmp_path: Path) -> None:
    receipt = _receipt(
        target_type="quiz",
        target_id=30,
        actions=["quiz.retake", "quiz.answer", "quiz.complete"],
    )
    usage_path = tmp_path / "usage.json"
    track_authorization_usage(
        receipt, action="quiz.retake", record=True, usage_path=usage_path
    )
    final = track_authorization_usage(
        receipt, action="quiz.complete", record=True, usage_path=usage_path
    )
    assert final["terminal_action"] == "quiz.complete"
    assert final["action_counts"] == {"quiz.retake": 1, "quiz.complete": 1}
