# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOOKS = ROOT / ".codex" / "hooks"


def run_hook(script: str, event: dict, *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged = None
    if env:
        import os
        merged = os.environ.copy()
        merged.update(env)
    return subprocess.run(
        [sys.executable, str(HOOKS / script)],
        cwd=ROOT,
        input=json.dumps(event),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=merged,
        check=False,
    )


def load(stdout: str) -> dict:
    assert stdout.strip(), "expected JSON output"
    return json.loads(stdout)


def test_pre_submit_negative() -> None:
    cp = run_hook(
        "pre_tool_guard.py",
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "python -c \"cv.submit_files('runs/adv/nope')\""},
        },
    )
    data = load(cp.stdout)
    assert data["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "verification" in data["hookSpecificOutput"]["permissionDecisionReason"]


def test_pre_submit_positive() -> None:
    work = ROOT / "runs" / "adv" / "ok"
    work.mkdir(parents=True, exist_ok=True)
    (work / "verification.log").write_text("PASS all checks\n", encoding="utf-8")
    try:
        cp = run_hook(
            "pre_tool_guard.py",
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "python -c \"cv.submit_files('runs/adv/ok')\""},
            },
        )
        assert cp.stdout.strip() == ""
    finally:
        shutil.rmtree(ROOT / "runs" / "adv", ignore_errors=True)


def test_quiz_live_action_fails_closed() -> None:
    cp = run_hook(
        "pre_tool_guard.py",
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "python -m src.canvas_client submit_quiz runs/adv/quiz"},
        },
    )
    data = load(cp.stdout)
    assert data["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "quiz" in data["hookSpecificOutput"]["permissionDecisionReason"].lower()


def test_spec_grounding_negative() -> None:
    work = ROOT / "runs" / "adv_spec"
    work.mkdir(parents=True, exist_ok=True)
    (work / "spec.md").write_text("Use the provided external reference.", encoding="utf-8")
    draft = work / "draft.txt"
    draft.write_text("draft", encoding="utf-8")
    result = work / "result.json"
    result.write_text(json.dumps({"status": "draft_ready", "draft_path": str(draft)}), encoding="utf-8")
    try:
        cp = run_hook(
            "post_tool_guard.py",
            {
                "hook_event_name": "PostToolUse",
                "tool_name": "apply_patch",
                "tool_input": {"command": "updated runs/adv_spec/result.json"},
            },
        )
        data = load(cp.stdout)
        assert data["decision"] == "block"
        assert "spec grounding failed" in data["reason"]
    finally:
        shutil.rmtree(work, ignore_errors=True)


def test_identifier_grounding_negative() -> None:
    work = ROOT / "runs" / "adv_ident"
    work.mkdir(parents=True, exist_ok=True)
    (work / "spec.md").write_text("Write simple code.", encoding="utf-8")
    draft = work / "draft.py"
    draft.write_text("mysteryFabricatedName = 1\nprint(mysteryFabricatedName)\n", encoding="utf-8")
    result = work / "result.json"
    result.write_text(json.dumps({"status": "draft_ready", "draft_path": str(draft)}), encoding="utf-8")
    try:
        cp = run_hook(
            "post_tool_guard.py",
            {
                "hook_event_name": "PostToolUse",
                "tool_name": "apply_patch",
                "tool_input": {"command": "updated runs/adv_ident/result.json"},
            },
        )
        data = load(cp.stdout)
        assert data["decision"] == "block"
        assert "identifier grounding failed" in data["reason"]
    finally:
        shutil.rmtree(work, ignore_errors=True)


def test_runner_script_blocked_under_runs() -> None:
    cp = run_hook(
        "post_tool_guard.py",
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "apply_patch",
            "tool_input": {"file_path": "runs/adv_guard/run_helper.py"},
        },
    )
    data = load(cp.stdout)
    assert data["decision"] == "block"
    assert "runner script blocked" in data["reason"]


def test_normal_run_artifact_allowed() -> None:
    cp = run_hook(
        "post_tool_guard.py",
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "apply_patch",
            "tool_input": {"file_path": "runs/adv_guard/notes.md"},
        },
    )
    assert cp.stdout.strip() == ""


def test_stop_marker_other_session_passes() -> None:
    today = ROOT / "runs" / "adv_session"
    today.mkdir(parents=True, exist_ok=True)
    marker = today / ".scan_in_progress"
    old_env_date = "adv_session"
    marker.write_text(json.dumps({"session_id": "other-session"}), encoding="utf-8")
    (today / "assignments.json").write_text(json.dumps([{
        "course_id": 1,
        "assignment_id": 2,
        "course_name": "Test Course",
        "name": "Missing Result",
    }]), encoding="utf-8")
    try:
        cp = run_hook(
            "stop_guard.py",
            {"hook_event_name": "Stop", "stop_hook_active": False},
            env={
                "CODEX_HOOK_SKIP_BATCH": "1",
                "CODEX_TEST_DATE": old_env_date,
                "CODEX_SESSION_ID": "current-session",
            },
        )
        data = load(cp.stdout)
        assert data["continue"] is True
    finally:
        shutil.rmtree(today, ignore_errors=True)


def test_stop_marker_matching_session_blocks() -> None:
    today = ROOT / "runs" / "adv_session"
    today.mkdir(parents=True, exist_ok=True)
    (today / ".scan_in_progress").write_text(json.dumps({"session_id": "current-session"}), encoding="utf-8")
    (today / "assignments.json").write_text(json.dumps([{
        "course_id": 1,
        "assignment_id": 2,
        "course_name": "Test Course",
        "name": "Missing Result",
    }]), encoding="utf-8")
    try:
        cp = run_hook(
            "stop_guard.py",
            {"hook_event_name": "Stop", "stop_hook_active": False},
            env={
                "CODEX_HOOK_SKIP_BATCH": "1",
                "CODEX_TEST_DATE": "adv_session",
                "CODEX_SESSION_ID": "current-session",
            },
        )
        data = load(cp.stdout)
        assert data["decision"] == "block"
        assert "assignments are incomplete" in data["reason"]
    finally:
        shutil.rmtree(today, ignore_errors=True)


def main() -> int:
    tests = [
        test_pre_submit_negative,
        test_pre_submit_positive,
        test_quiz_live_action_fails_closed,
        test_spec_grounding_negative,
        test_identifier_grounding_negative,
        test_runner_script_blocked_under_runs,
        test_normal_run_artifact_allowed,
        test_stop_marker_other_session_passes,
        test_stop_marker_matching_session_blocks,
    ]
    failures: list[str] = []
    for test in tests:
        try:
            test()
            print(f"PASS {test.__name__}")
        except Exception as exc:
            failures.append(f"{test.__name__}: {exc}")
            print(f"FAIL {test.__name__}: {exc}")
    if failures:
        print("\nFailures:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
