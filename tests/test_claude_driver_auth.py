"""Mutation-authorization enforcement when Claude Code is the driver.

Receipt enforcement and session binding were originally keyed only on Codex
environment variables, leaving a Claude Code session unenforced. These tests
pin the Claude path to the same fail-closed behavior.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("CANVAS_BASE", "http://127.0.0.1:3101/api/v1")
os.environ.setdefault("CANVAS_AUTH", "token")
os.environ.setdefault("CANVAS_TOKEN", "synthetic-test-token")

from src import canvas_client as cv  # noqa: E402
from src.authorization import (  # noqa: E402
    AuthorizationDenied,
    create_authorization_receipt,
    current_authorization_session,
    mutation_authorization_enforced,
    validate_authorization_receipt,
)
from src.mutation_approval import issue_interactive_authorization  # noqa: E402
from src.run_state import (  # noqa: E402
    RunStateError,
    plan_digest,
    stable_work_dir,
    validate_execute_marker,
)

from tests.test_mutation_approval import KEY, NOW, _write_run  # noqa: E402

AGENT_VARS = ("CODEX_THREAD_ID", "CODEX_SESSION_ID", "CLAUDE_CODE_SESSION_ID",
              "CANVAS_ENFORCE_MUTATION_AUTH")


@pytest.fixture
def claude_env(monkeypatch):
    for name in AGENT_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "claude-session-1")
    return monkeypatch


class FakeBackend:
    def __init__(self):
        self.calls: list[tuple] = []

    def post_form(self, url, data):
        self.calls.append(("post_form", url, data))
        return {"ok": True}


def test_claude_session_turns_on_enforcement_and_binds_session(claude_env) -> None:
    assert mutation_authorization_enforced()
    assert current_authorization_session() == "claude-session-1"


def test_no_agent_session_leaves_enforcement_off(monkeypatch) -> None:
    for name in AGENT_VARS:
        monkeypatch.delenv(name, raising=False)
    assert not mutation_authorization_enforced()
    assert current_authorization_session() is None


def test_claude_submit_without_receipt_never_reaches_backend(claude_env) -> None:
    claude_env.setattr(cv, "BASE", "http://127.0.0.1:3101/api/v1")
    fake = FakeBackend()
    claude_env.setattr(cv, "_backend", fake)
    with pytest.raises(AuthorizationDenied):
        cv.submit_text(10, 20, "draft")
    assert fake.calls == []


def test_claude_receipt_from_other_session_is_rejected(claude_env, tmp_path: Path) -> None:
    claude_env.setattr(cv, "BASE", "http://127.0.0.1:3101/api/v1")
    claude_env.setenv("CANVAS_AUTHORIZATION_KEY_PATH", str(tmp_path / "signing.key"))
    fake = FakeBackend()
    claude_env.setattr(cv, "_backend", fake)
    receipt = create_authorization_receipt(
        canvas_origin=cv.BASE,
        course_id=10,
        target_type="assignment",
        target_id=20,
        actions=["assignment.submit_text"],
        session_id="some-other-session",
        expires_at=dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=10),
        authority_reference={"approval_id": "synthetic-unit-test"},
        synthetic_qa=True,
    )
    with pytest.raises(AuthorizationDenied):
        cv.submit_text(10, 20, "draft", authorization_receipt=receipt)
    assert fake.calls == []


def test_claude_exact_submit_command_issues_session_bound_receipt(
    claude_env, tmp_path: Path
) -> None:
    run_dir, _, _ = _write_run(tmp_path)
    issued = issue_interactive_authorization(
        run_dir=run_dir,
        canvas_origin="https://canvas.example.test",
        user_text="submit 1",
        now=NOW,
        signing_key=KEY,
    )
    assert issued["issued"] is True
    receipt = json.loads(Path(issued["receipt_path"]).read_text(encoding="utf-8"))
    validate_authorization_receipt(
        receipt,
        canvas_origin="https://canvas.example.test",
        course_id="course-7",
        target_type="assignment",
        target_id="assignment-19",
        action="assignment.submit_text",
        session_id="claude-session-1",
        now=NOW + dt.timedelta(minutes=1),
        signing_key=KEY,
    )
    with pytest.raises(AuthorizationDenied):
        validate_authorization_receipt(
            receipt,
            canvas_origin="https://canvas.example.test",
            course_id="course-7",
            target_type="assignment",
            target_id="assignment-19",
            action="assignment.submit_text",
            session_id="some-other-session",
            now=NOW + dt.timedelta(minutes=1),
            signing_key=KEY,
        )


def test_execute_marker_accepts_claude_owner_and_rejects_unknown(tmp_path: Path) -> None:
    run_dir, plan, _ = _write_run(tmp_path)
    marker = {
        "session_id": "claude-session-1",
        "owner_kind": "claude",
        "created_at": NOW.isoformat(),
        "plan_digest": plan_digest(plan),
    }
    assert validate_execute_marker(marker, plan)["owner_kind"] == "claude"
    with pytest.raises(RunStateError):
        validate_execute_marker({**marker, "owner_kind": "someone-else"}, plan)
    assert stable_work_dir(run_dir, "course-7", "assignment-19").name.startswith("course-")
