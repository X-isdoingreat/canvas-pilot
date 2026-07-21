# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from src.scan_service import (
    IncompleteScanError,
    is_actionable_assignment,
    scan_product,
    write_product_outputs,
)


NOW = dt.datetime(2026, 7, 18, 12, 0, tzinfo=dt.timezone.utc)


def _assignment(
    assignment_id: int,
    name: str,
    due_at: str,
    submission_types=None,
    **updates,
):
    value = {
        "id": assignment_id,
        "name": name,
        "due_at": due_at,
        "lock_at": None,
        "submission_types": submission_types or ["online_upload"],
        "points_possible": 10,
        "quiz_id": None,
        "submission": {"workflow_state": "unsubmitted"},
    }
    value.update(updates)
    return value


class FakeCanvas:
    AUTH_MODE = "token"

    def __init__(self, assignments, *, failing_courses=(), submissions=None, quizzes=None):
        self.assignments = assignments
        self.failing_courses = {str(value) for value in failing_courses}
        self.submissions = submissions or {}
        self.quizzes = quizzes or {}
        self.quiz_calls = []

    def list_assignments(self, course_id):
        if str(course_id) in self.failing_courses:
            raise RuntimeError(f"course {course_id} unavailable")
        return self.assignments.get(str(course_id), [])

    def get_submission(self, course_id, assignment_id):
        return {
            "workflow_state": self.submissions.get(
                (str(course_id), str(assignment_id)), "unsubmitted"
            )
        }

    def get_quiz(self, course_id, quiz_id):
        self.quiz_calls.append((str(course_id), str(quiz_id)))
        value = self.quizzes.get((str(course_id), str(quiz_id)), {})
        if isinstance(value, Exception):
            raise value
        return value


class UnknownStateCanvas(FakeCanvas):
    def get_submission(self, course_id, assignment_id):
        raise RuntimeError("live state unavailable")


def test_actionable_overdue_is_retained_until_locked_or_done():
    overdue = _assignment(1, "Late project", "2026-07-16T12:00:00Z")
    locked = _assignment(
        2,
        "Locked project",
        "2026-07-16T12:00:00Z",
        lock_at="2026-07-17T12:00:00Z",
    )
    done = _assignment(
        3,
        "Done project",
        "2026-07-16T12:00:00Z",
        submission={"workflow_state": "submitted"},
    )

    assert is_actionable_assignment(overdue, 7, now=NOW) is True
    assert is_actionable_assignment(locked, 7, now=NOW) is False
    assert is_actionable_assignment(done, 7, now=NOW) is False


def test_uncertain_overdue_state_is_retained_but_bucketed_urgent():
    assignment = _assignment(1, "Late project", "2026-07-16T12:00:00Z")
    assignment.pop("submission")
    payload = scan_product(
        {"routes": {"1": "canvas-generic"}},
        UnknownStateCanvas({"1": [assignment]}),
        now=NOW,
    )

    item = payload["items"][0]
    assert item["live_state"] == "unknown"
    assert item["bucket"] == "urgent"
    assert item["hours_left"] < 0


def test_missing_or_unparseable_due_date_remains_visible_in_unknown_bucket():
    assignments = {
        "1": [
            _assignment(1, "No due date", None),
            _assignment(2, "Bad due date", "not-an-iso-date"),
        ]
    }
    payload = scan_product(
        {"routes": {"1": "canvas-generic"}},
        FakeCanvas(assignments),
        now=NOW,
    )
    assert [item["assignment_id"] for item in payload["items"]] == ["1", "2"]
    assert {item["bucket"] for item in payload["items"]} == {"unknown"}
    assert all(item["hours_left"] is None for item in payload["items"])


def test_enriched_scan_routes_unsupported_and_lockdown_and_excludes_live_done():
    assignments = {
        "1": [
            _assignment(1, "Overdue project", "2026-07-17T12:00:00Z"),
            _assignment(
                2,
                "Paper exercise",
                "2026-07-19T12:00:00Z",
                ["on_paper"],
            ),
            _assignment(
                3,
                "Classic Quiz",
                "2026-07-20T12:00:00Z",
                ["online_quiz"],
                quiz_id=333,
            ),
            _assignment(
                4,
                "New Quiz",
                "2026-07-20T13:00:00Z",
                ["external_tool"],
            ),
            _assignment(5, "Already done", "2026-07-20T14:00:00Z"),
        ]
    }
    canvas = FakeCanvas(
        assignments,
        submissions={("1", "5"): "graded"},
        quizzes={("1", "333"): {"require_lockdown_browser": True}},
    )
    config = {
        "pending_window_days": 7,
        "routes": {"1": {"name": "Synthetic", "skill": "quiz"}},
    }

    payload = scan_product(config, canvas, now=NOW)

    assert payload["complete"] is True
    assert [item["assignment_id"] for item in payload["items"]] == ["1", "2", "3", "4"]
    by_id = {item["assignment_id"]: item for item in payload["items"]}
    assert by_id["1"]["bucket"] == "overdue"
    assert by_id["1"]["skill"] == "canvas-inside"
    assert by_id["2"]["skill"] == "canvas-skip"
    assert by_id["2"]["skip_reason_code"] == "on_paper"
    assert by_id["3"]["skill"] == "canvas-skip"
    assert by_id["3"]["skip_reason_code"] == "lockdown_browser"
    assert by_id["3"]["ldb_locked"] is True
    assert by_id["4"]["skip_reason_code"] == "external_tool_unsupported"
    assert canvas.quiz_calls == [("1", "333")]


@pytest.mark.parametrize("configured_skill", ["quiz", "canvas-inside"])
def test_lockdown_check_recognizes_legacy_and_canonical_quiz_aliases(configured_skill):
    canvas = FakeCanvas(
        {
            "1": [
                _assignment(
                    9,
                    "Classic Quiz",
                    "2026-07-19T12:00:00Z",
                    ["online_quiz"],
                    quiz_id=90,
                )
            ]
        },
        quizzes={("1", "90"): {"require_lockdown_browser_monitor": True}},
    )
    payload = scan_product(
        {"routes": {"1": {"name": "Q", "skill": configured_skill}}},
        canvas,
        now=NOW,
    )

    assert payload["items"][0]["skill"] == "canvas-skip"
    assert payload["items"][0]["skip_reason_code"] == "lockdown_browser"


def test_lockdown_lookup_failure_is_recorded_not_claimed_as_lockdown():
    canvas = FakeCanvas(
        {
            "1": [
                _assignment(
                    9,
                    "Classic Quiz",
                    "2026-07-19T12:00:00Z",
                    ["online_quiz"],
                    quiz_id=90,
                )
            ]
        },
        quizzes={("1", "90"): RuntimeError("metadata unavailable")},
    )
    payload = scan_product(
        {"routes": {"1": "quiz"}}, canvas, now=NOW
    )

    item = payload["items"][0]
    assert item["skill"] == "canvas-inside"
    assert item["ldb_locked"] is False
    assert item["ldb_check_failed"] is True


def test_course_failure_is_structured_and_never_approval_ready(tmp_path: Path):
    canvas = FakeCanvas(
        {
            "1": [_assignment(1, "Good", "2026-07-19T12:00:00Z")],
        },
        failing_courses={"2"},
    )
    payload = scan_product(
        {
            "routes": {
                "1": {"name": "Good", "skill": "canvas-generic"},
                "2": {"name": "Broken", "skill": "canvas-generic"},
            }
        },
        canvas,
        now=NOW,
    )

    assert payload["complete"] is False
    assert payload["items"] == []
    assert payload["diagnostics"] == {
        "partial_candidate_count": 1,
        "approval_ready": False,
    }
    assert payload["course_errors"][0]["code"] == "list_assignments_failed"
    with pytest.raises(IncompleteScanError):
        write_product_outputs(tmp_path, payload)
    assert not (tmp_path / "scan.json").exists()
    assert not (tmp_path / "assignments.json").exists()


def test_invalid_course_list_shape_fails_closed():
    canvas = FakeCanvas({"1": {"id": 1}})

    payload = scan_product(
        {"routes": {"1": "canvas-generic"}}, canvas, now=NOW
    )

    assert payload["complete"] is False
    assert payload["items"] == []
    assert payload["course_errors"][0]["code"] == "list_assignments_failed"


def test_success_outputs_are_complete_and_leave_no_temp_files(tmp_path: Path):
    payload = {
        "complete": True,
        "generated_at": NOW.isoformat(),
        "now_utc": NOW.isoformat(),
        "items": [{"assignment_id": "1", "skill": "canvas-generic"}],
        "course_errors": [],
    }

    scan_path, assignments_path = write_product_outputs(tmp_path, payload)

    assert json.loads(scan_path.read_text(encoding="utf-8"))["complete"] is True
    assert json.loads(assignments_path.read_text(encoding="utf-8")) == payload["items"]
    assert list(tmp_path.glob("*.tmp")) == []
