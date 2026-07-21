from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

import pytest
import requests

os.environ.setdefault("CANVAS_BASE", "http://127.0.0.1:3101/api/v1")
os.environ.setdefault("CANVAS_AUTH", "token")
os.environ.setdefault("CANVAS_TOKEN", "synthetic-test-token")

from src import canvas_client as cv  # noqa: E402
from src import canvas_submit_origin as cso  # noqa: E402
from src.authorization import (  # noqa: E402
    AuthorizationDenied,
    authorization_usage_status,
    create_authorization_receipt,
    require_mutation_authorization,
)


class FakeBackend:
    def __init__(self):
        self.calls: list[tuple] = []

    def post_form(self, url, data):
        self.calls.append(("post_form", url, data))
        return {"ok": True}

    def post_json(self, url, data):
        self.calls.append(("post_json", url, data))
        return {"ok": True}

    def put_json(self, url, data):
        self.calls.append(("put_json", url, data))
        return {"ok": True}


def _receipt(monkeypatch, tmp_path: Path, *, target_type="assignment", target_id=20, actions=None):
    monkeypatch.setenv("CODEX_THREAD_ID", "thread-test")
    monkeypatch.setenv("CANVAS_AUTHORIZATION_KEY_PATH", str(tmp_path / "signing.key"))
    return create_authorization_receipt(
        canvas_origin=cv.BASE,
        course_id=10,
        target_type=target_type,
        target_id=target_id,
        actions=actions or ["assignment.submit_text"],
        session_id="thread-test",
        expires_at=dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=10),
        authority_reference={"approval_id": "synthetic-unit-test"},
        synthetic_qa=True,
    )


def test_assignment_mutation_denied_before_backend_without_receipt(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cv, "BASE", "http://127.0.0.1:3101/api/v1")
    monkeypatch.setenv("CODEX_THREAD_ID", "thread-test")
    fake = FakeBackend()
    monkeypatch.setattr(cv, "_backend", fake)
    with pytest.raises(AuthorizationDenied):
        cv.submit_text(10, 20, "draft")
    assert fake.calls == []


def test_exact_assignment_receipt_reaches_backend(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cv, "BASE", "http://127.0.0.1:3101/api/v1")
    fake = FakeBackend()
    monkeypatch.setattr(cv, "_backend", fake)
    receipt = _receipt(monkeypatch, tmp_path)
    cv.submit_text(10, 20, "draft", authorization_receipt=receipt)
    assert [call[0] for call in fake.calls] == ["post_form"]


def test_terminal_assignment_receipt_cannot_be_replayed(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cv, "BASE", "http://127.0.0.1:3101/api/v1")
    fake = FakeBackend()
    monkeypatch.setattr(cv, "_backend", fake)
    receipt = _receipt(monkeypatch, tmp_path)
    cv.submit_text(10, 20, "draft", authorization_receipt=receipt)
    with pytest.raises(AuthorizationDenied, match="already been consumed"):
        cv.submit_text(10, 20, "draft again", authorization_receipt=receipt)
    assert len(fake.calls) == 1
    usage = authorization_usage_status(receipt)
    assert usage["terminal_action"] == "assignment.submit_text"


def test_quiz_receipt_tracks_multiwrite_then_consumes_at_completion(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(cv, "BASE", "http://127.0.0.1:3101/api/v1")
    receipt = _receipt(
        monkeypatch,
        tmp_path,
        target_type="quiz",
        target_id=30,
        actions=["quiz.start", "quiz.answer", "quiz.event", "quiz.complete"],
    )

    def use(action: str) -> None:
        require_mutation_authorization(
            receipt,
            canvas_origin=cv.BASE,
            course_id=10,
            target_type="quiz",
            target_id=30,
            action=action,
            track_usage=True,
        )

    use("quiz.start")
    use("quiz.event")
    use("quiz.answer")
    use("quiz.answer")
    use("quiz.complete")
    with pytest.raises(AuthorizationDenied, match="already been consumed"):
        use("quiz.event")
    usage = authorization_usage_status(receipt)
    assert usage["action_counts"]["quiz.answer"] == 2
    assert usage["terminal_action"] == "quiz.complete"


def test_wrong_action_or_target_never_reaches_backend(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cv, "BASE", "http://127.0.0.1:3101/api/v1")
    fake = FakeBackend()
    monkeypatch.setattr(cv, "_backend", fake)
    receipt = _receipt(monkeypatch, tmp_path)
    with pytest.raises(AuthorizationDenied):
        cv.submit_url(10, 20, "https://example.test", authorization_receipt=receipt)
    with pytest.raises(AuthorizationDenied):
        cv.submit_text(10, 21, "draft", authorization_receipt=receipt)
    assert fake.calls == []


def test_low_level_post_binds_receipt_context_to_request_path(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cv, "BASE", "http://127.0.0.1:3101/api/v1")
    fake = FakeBackend()
    monkeypatch.setattr(cv, "_backend", fake)
    receipt = _receipt(monkeypatch, tmp_path)

    with pytest.raises(AuthorizationDenied):
        cv.post_form(
            "/courses/10/assignments/21/submissions",
            {"submission[body]": "draft"},
            authorization_receipt=receipt,
            mutation_action="assignment.submit_text",
            mutation_course_id=10,
            mutation_target_type="assignment",
            mutation_target_id=20,
        )

    assert fake.calls == []


def test_quiz_start_has_separate_exact_action(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cv, "BASE", "http://127.0.0.1:3101/api/v1")
    fake = FakeBackend()
    monkeypatch.setattr(cv, "_backend", fake)
    receipt = _receipt(
        monkeypatch,
        tmp_path,
        target_type="quiz",
        target_id=30,
        actions=["quiz.start"],
    )
    cv.start_quiz_submission(10, 30, authorization_receipt=receipt)
    with pytest.raises(AuthorizationDenied):
        cv.start_quiz_submission(10, 30, is_retake=True, authorization_receipt=receipt)
    assert len(fake.calls) == 1


def test_upload_checks_init_and_blob_actions(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cv, "BASE", "http://127.0.0.1:3101/api/v1")
    fake = FakeBackend()

    def init_response(url, data):
        fake.calls.append(("post_form", url, data))
        return {"upload_url": "https://upload.example.test", "upload_params": {}}

    fake.post_form = init_response
    monkeypatch.setattr(cv, "_backend", fake)
    draft = tmp_path / "draft.bin"
    draft.write_bytes(b"draft")
    init_only = _receipt(
        monkeypatch,
        tmp_path,
        actions=["assignment.upload_init"],
    )
    with pytest.raises(AuthorizationDenied):
        cv.upload_submission_file(10, 20, draft, authorization_receipt=init_only)
    assert fake.calls == []  # the complete upload scope is checked before initialization


def test_upload_wrapper_preflights_final_submit_before_any_mutation(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(cso.cv, "BASE", "http://127.0.0.1:3101/api/v1")
    canvas_calls: list[str] = []
    monkeypatch.setattr(
        cso.cv,
        "get_assignment",
        lambda *_: canvas_calls.append("get_assignment") or {"id": 20},
    )
    monkeypatch.setattr(
        cso.cv,
        "get_submission",
        lambda *_: canvas_calls.append("get_submission") or {"workflow_state": "unsubmitted"},
    )
    draft = tmp_path / "draft.bin"
    draft.write_bytes(b"draft")
    upload_only = _receipt(
        monkeypatch,
        tmp_path,
        actions=["assignment.upload_init", "assignment.upload_blob"],
    )

    with pytest.raises(AuthorizationDenied):
        cso.upload_and_submit_files_with_view(
            10,
            20,
            [draft],
            authorization_receipt=upload_only,
        )

    assert canvas_calls == ["get_assignment", "get_submission"]


def test_token_session_probe_detects_revocation(monkeypatch) -> None:
    backend = cv._RequestsBackend()

    class Response:
        def __init__(self, status_code):
            self.status_code = status_code

    class Session:
        def __init__(self, outcome):
            self.outcome = outcome

        def get(self, url, timeout):
            if isinstance(self.outcome, Exception):
                raise self.outcome
            return Response(self.outcome)

    backend._session = Session(200)
    assert backend.is_session_alive(timeout_s=1) is True
    backend._session = Session(401)
    assert backend.is_session_alive(timeout_s=1) is False
    backend._session = Session(requests.Timeout())
    assert backend.is_session_alive(timeout_s=1) is False


def test_clean_install_read_only_helpers(monkeypatch) -> None:
    def fake_get(path, **params):
        if path == "/courses/10":
            return {"syllabus_body": "<p>Syllabus</p>"}
        if path.endswith("/assignments/20") and params.get("include") == ["rubric"]:
            return {"rubric": [{"id": "criterion"}]}
        if path.endswith("/assignments/20"):
            return {
                "attachments": [{"id": 7, "filename": "attached.pdf"}],
                "description": '<a href="/courses/10/files/8">linked</a>',
            }
        if path == "/files/8":
            return {"id": 8, "filename": "linked.pdf"}
        raise AssertionError(path)

    monkeypatch.setattr(cv, "get", fake_get)
    assert cv.get_syllabus_body(10) == "<p>Syllabus</p>"
    assert [item["id"] for item in cv.list_assignment_files(10, 20)] == [7, 8]
    assert cv.get_rubric(10, 20) == [{"id": "criterion"}]


def test_submit_wrapper_canonicalizes_preexisting_submission(monkeypatch) -> None:
    monkeypatch.setattr(cso.cv, "get_assignment", lambda *_: {"id": 20})
    existing = {
        "workflow_state": "graded",
        "submitted_at": "2026-07-18T12:00:00Z",
        "attempt": 1,
    }
    monkeypatch.setattr(cso.cv, "get_submission", lambda *_: existing)
    with pytest.raises(cso.AlreadySubmitted) as raised:
        cso.submit_text_with_view(10, 20, "draft", authorization_receipt={})
    result = cso.existing_submission_result(raised.value)
    assert result["status"] == "submitted"
    assert result["reason_code"] == "already_submitted"
    assert result["metadata"]["graded"] is True
