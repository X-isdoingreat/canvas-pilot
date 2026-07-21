# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOOKS = ROOT / ".codex" / "hooks"
TODAY = dt.date.today().isoformat()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from src.run_state import plan_digest, stable_work_dir  # noqa: E402


def run_hook(script: str, event: dict, *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
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


def load_json(stdout: str) -> dict:
    assert stdout.strip(), "expected JSON output"
    return json.loads(stdout)


def test_h1_session_start() -> None:
    cp = run_hook("session_start.py", {"hook_event_name": "SessionStart", "source": "startup"})
    assert cp.returncode == 0, cp.stderr
    data = load_json(cp.stdout)
    ctx = data["hookSpecificOutput"]["additionalContext"]
    assert "Codex primary driver active" in ctx
    assert "scan -> approval -> execute" in ctx


def test_h2_pretool_blocks_upstream_push() -> None:
    cp = run_hook(
        "pre_tool_guard.py",
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "git push upstream main"},
        },
    )
    assert cp.returncode == 0
    data = load_json(cp.stdout)
    out = data["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny"
    assert "upstream" in out["permissionDecisionReason"]


def test_h3_pretool_allows_harmless_command() -> None:
    cp = run_hook(
        "pre_tool_guard.py",
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "python -m src.router --dry-run"},
        },
    )
    assert cp.returncode == 0
    assert cp.stdout.strip() == ""


def test_h4_posttool_blocks_invalid_result() -> None:
    test_dir = ROOT / "runs" / "codex_hook_test" / "bad"
    test_dir.mkdir(parents=True, exist_ok=True)
    result = test_dir / "result.json"
    result.write_text('{"status":"not_real"}', encoding="utf-8")
    try:
        cp = run_hook(
            "post_tool_guard.py",
            {
                "hook_event_name": "PostToolUse",
                "tool_name": "apply_patch",
                "tool_input": {"command": "updated runs/codex_hook_test/bad/result.json"},
            },
        )
        assert cp.returncode == 0
        data = load_json(cp.stdout)
        assert data["decision"] == "block"
        assert "Invalid result.json schema" in data["reason"]
    finally:
        shutil.rmtree(ROOT / "runs" / "codex_hook_test", ignore_errors=True)


def setup_incomplete_today() -> Path:
    today = ROOT / "runs" / TODAY
    today.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc)
    assignments = [
        {
            "course_id": 1,
            "assignment_id": 2,
            "course_name": "Test Course",
            "name": "Missing Result",
            "skill": "canvas-skip",
            "work_dir": stable_work_dir(today, 1, 2).name,
        }
    ]
    plan = {
        "generated_at": (now - dt.timedelta(minutes=1)).isoformat(),
        "expires_at": (now + dt.timedelta(hours=1)).isoformat(),
        "items": [{
            "index": 1,
            "course_id": 1,
            "assignment_id": 2,
            "name": "Missing Result",
            "proposed_skill": "canvas-skip",
            "user_decision": "approve",
        }],
    }
    (today / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    (today / "assignments.json").write_text(json.dumps(assignments), encoding="utf-8")
    (today / ".scan_in_progress").write_text(
        json.dumps({
            "session_id": "hook-test-session",
            "owner_kind": "codex",
            "created_at": now.isoformat(),
            "plan_digest": plan_digest(plan),
            "results_prepared_at": now.isoformat(),
            "results_archive_count": 0,
            "prepared_approved_result_keys": [
                stable_work_dir(today, 1, 2).name
            ],
        }),
        encoding="utf-8",
    )
    return today


def test_h5_stop_blocks_incomplete_execute_session() -> None:
    today = setup_incomplete_today()
    try:
        cp = run_hook(
            "stop_guard.py",
            {"hook_event_name": "Stop", "stop_hook_active": False},
            env={
                "CODEX_HOOK_SKIP_BATCH": "1",
                "CODEX_SESSION_ID": "hook-test-session",
            },
        )
        assert cp.returncode == 0
        data = load_json(cp.stdout)
        assert data["decision"] == "block"
        assert "assignments are incomplete" in data["reason"]
    finally:
        shutil.rmtree(today, ignore_errors=True)


def test_h6_stop_releases_non_execute_session() -> None:
    today = ROOT / "runs" / TODAY
    if today.exists():
        shutil.rmtree(today)
    cp = run_hook(
        "stop_guard.py",
        {"hook_event_name": "Stop", "stop_hook_active": False},
        env={"CODEX_HOOK_SKIP_BATCH": "1"},
    )
    assert cp.returncode == 0
    data = load_json(cp.stdout)
    assert data["continue"] is True


def test_h7_internal_error_fails_open() -> None:
    cp = subprocess.run(
        [sys.executable, str(HOOKS / "session_start.py")],
        cwd=ROOT,
        input="{not json",
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert cp.returncode == 0


def test_h8_stop_blocks_in_progress_batch_without_report() -> None:
    report = ROOT / "runs" / "codex" / TODAY / "PARITY_BTEST.md"
    old = report.read_text(encoding="utf-8") if report.exists() else None
    if report.exists():
        report.unlink()
    try:
        cp = run_hook(
            "stop_guard.py",
            {"hook_event_name": "Stop", "stop_hook_active": False},
            env={"CODEX_TEST_BATCH_IN_PROGRESS": "BTEST"},
        )
        assert cp.returncode == 0
        data = load_json(cp.stdout)
        assert data["decision"] == "block"
        assert "Batch BTEST is still in_progress" in data["reason"]
    finally:
        if old is not None:
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(old, encoding="utf-8")


def main() -> int:
    tests = [
        test_h1_session_start,
        test_h2_pretool_blocks_upstream_push,
        test_h3_pretool_allows_harmless_command,
        test_h4_posttool_blocks_invalid_result,
        test_h5_stop_blocks_incomplete_execute_session,
        test_h6_stop_releases_non_execute_session,
        test_h7_internal_error_fails_open,
        test_h8_stop_blocks_in_progress_batch_without_report,
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
