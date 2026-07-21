# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from src import router


class FakeCanvas:
    AUTH_MODE = "token"

    def __init__(self, fail=False):
        self.fail = fail

    def list_assignments(self, course_id):
        if self.fail and str(course_id) == "2":
            raise RuntimeError("synthetic list failure")
        return [
            {
                "id": int(course_id) * 10,
                "name": "Synthetic assignment",
                "due_at": "2099-07-20T12:00:00Z",
                "lock_at": None,
                "submission_types": ["online_upload"],
                "points_possible": 10,
                "submission": {"workflow_state": "unsubmitted"},
            }
        ]

    def get_submission(self, course_id, assignment_id):
        return {"workflow_state": "unsubmitted"}

    def get_quiz(self, course_id, quiz_id):
        return {}


def _config(two_courses=False):
    routes = {"1": {"name": "One", "skill": "canvas-generic"}}
    if two_courses:
        routes["2"] = {"name": "Two", "skill": "canvas-generic"}
    return {"pending_window_days": 30000, "routes": routes}


def test_run_flag_fails_before_loading_canvas(monkeypatch, capsys):
    def should_not_load():
        raise AssertionError("Canvas client must not load for --run refusal")

    monkeypatch.setattr(router, "_load_client", should_not_load)

    code = router.main(["--run"])

    assert code == router.EXIT_EXECUTION_DISABLED
    assert "canvas-scan" in capsys.readouterr().err


def test_incomplete_product_scan_returns_nonzero_and_writes_only_timing(tmp_path: Path):
    code = router._emit_scan_json(
        run_dir=tmp_path,
        config=_config(two_courses=True),
        client=FakeCanvas(fail=True),
    )

    assert code == router.EXIT_INCOMPLETE
    assert not (tmp_path / "scan.json").exists()
    assert not (tmp_path / "assignments.json").exists()
    timing = json.loads((tmp_path / "scan_timing.json").read_text(encoding="utf-8"))
    assert timing["error"]["code"] == "course_scan_failed"
    assert timing["error"]["course_errors"][0]["course_id"] == "2"


def test_successful_product_scan_writes_complete_outputs(tmp_path: Path):
    code = router._emit_scan_json(
        run_dir=tmp_path,
        config=_config(),
        client=FakeCanvas(),
    )

    assert code == router.EXIT_OK
    scan = json.loads((tmp_path / "scan.json").read_text(encoding="utf-8"))
    assignments = json.loads(
        (tmp_path / "assignments.json").read_text(encoding="utf-8")
    )
    assert scan["complete"] is True
    assert assignments == scan["items"]
    assert list(tmp_path.glob("*.tmp")) == []


def test_debug_scan_never_writes_product_outputs(tmp_path: Path):
    args = router.build_parser().parse_args(["--dry-run"])
    code = router._debug_scan(
        args,
        run_dir=tmp_path,
        config=_config(),
        client=FakeCanvas(),
    )

    assert code == router.EXIT_OK
    assert (tmp_path / "scan_timing.json").exists()
    assert not (tmp_path / "scan.json").exists()
    assert not (tmp_path / "assignments.json").exists()


def test_product_scan_rejects_debug_filters(capsys):
    code = router.main(["--scan-json", "--only", "1"])

    assert code == router.EXIT_FATAL
    assert "every configured course" in capsys.readouterr().err
