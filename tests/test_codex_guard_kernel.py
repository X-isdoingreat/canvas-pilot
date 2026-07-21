from __future__ import annotations

import datetime as dt
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import push_public_snapshot
from src.run_state import plan_digest, stable_work_dir


ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / ".codex" / "hooks"


def _load_hook_lib():
    if str(HOOKS) not in sys.path:
        sys.path.insert(0, str(HOOKS))
    spec = importlib.util.spec_from_file_location("codex_hook_kernel_lib", HOOKS / "_lib.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HOOK_LIB = _load_hook_lib()


def _run_hook(script: str, event: dict, env: dict[str, str] | None = None):
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


def test_pretool_does_not_block_harmless_quiz_or_submit_text() -> None:
    for command in (
        "Select-String -Path notes.md -Pattern 'start_quiz'",
        "Select-String -Path notes.md -Pattern 'submit_files('",
        "python -c \"print('quiz action names are documentation')\"",
    ):
        cp = _run_hook(
            "pre_tool_guard.py",
            {"tool_name": "Bash", "tool_input": {"command": command}},
        )
        assert cp.stdout.strip() == "", cp.stdout


@pytest.mark.parametrize("payload", [None, "{bad json", {"not": "a list"}])
def test_stop_marker_fails_closed_for_missing_corrupt_or_nonlist_assignments(payload) -> None:
    date = "guard-kernel-invalid"
    run_dir = ROOT / "runs" / date
    shutil.rmtree(run_dir, ignore_errors=True)
    run_dir.mkdir(parents=True)
    (run_dir / ".scan_in_progress").write_text("{}", encoding="utf-8")
    if payload is not None:
        text = payload if isinstance(payload, str) else json.dumps(payload)
        (run_dir / "assignments.json").write_text(text, encoding="utf-8")
    try:
        cp = _run_hook(
            "stop_guard.py",
            {"stop_hook_active": False},
            {"CODEX_TEST_DATE": date, "CODEX_HOOK_SKIP_BATCH": "1"},
        )
        assert json.loads(cp.stdout)["decision"] == "block"
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def test_stop_marker_invalid_utf8_fails_closed() -> None:
    date = "guard-kernel-marker-bytes"
    run_dir = ROOT / "runs" / date
    shutil.rmtree(run_dir, ignore_errors=True)
    run_dir.mkdir(parents=True)
    (run_dir / ".scan_in_progress").write_bytes(b"\xff\xfe")
    try:
        cp = _run_hook(
            "stop_guard.py",
            {"stop_hook_active": False},
            {"CODEX_TEST_DATE": date, "CODEX_HOOK_SKIP_BATCH": "1"},
        )
        payload = json.loads(cp.stdout)
        assert payload["decision"] == "block"
        assert "unreadable/corrupt" in payload["reason"]
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def test_post_result_invalid_utf8_fails_closed() -> None:
    work = ROOT / "runs" / "guard-kernel-result-bytes" / "work"
    work.mkdir(parents=True, exist_ok=True)
    result = work / "result.json"
    result.write_bytes(b"\xff\xfe")
    try:
        cp = _run_hook(
            "post_tool_guard.py",
            {"tool_input": {"file_path": str(result)}},
        )
        payload = json.loads(cp.stdout)
        assert payload["decision"] == "block"
        assert "unreadable/corrupt" in payload["reason"]
    finally:
        shutil.rmtree(ROOT / "runs" / "guard-kernel-result-bytes", ignore_errors=True)


def test_stop_retake_gate_recognizes_canvas_inside_alias() -> None:
    date = "guard-kernel-quiz"
    run_dir = ROOT / "runs" / date
    shutil.rmtree(run_dir, ignore_errors=True)
    work = stable_work_dir(run_dir, 1, 2)
    work.mkdir(parents=True)
    now = dt.datetime.now(dt.timezone.utc)
    plan = {
        "generated_at": (now - dt.timedelta(minutes=1)).isoformat(),
        "expires_at": (now + dt.timedelta(hours=1)).isoformat(),
        "items": [{
            "index": 1,
            "course_id": 1,
            "assignment_id": 2,
            "name": "Weekly Quiz",
            "proposed_skill": "canvas-inside",
            "user_decision": "approve",
        }],
    }
    assignments = [{
        "course_id": 1,
        "assignment_id": 2,
        "quiz_id": 4,
        "course_name": "Test Course",
        "name": "Weekly Quiz",
        "skill": "canvas-inside",
        "work_dir": str(work),
    }]
    (run_dir / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    (run_dir / "assignments.json").write_text(json.dumps(assignments), encoding="utf-8")
    (run_dir / ".scan_in_progress").write_text(
        json.dumps({
            "session_id": "guard-session",
            "owner_kind": "codex",
            "created_at": now.isoformat(),
            "plan_digest": plan_digest(plan),
            "results_prepared_at": now.isoformat(),
            "results_archive_count": 0,
            "prepared_approved_result_keys": ["course-1__assignment-2"],
        }),
        encoding="utf-8",
    )
    receipt_id = "guard-receipt"
    usage_path = run_dir / "authorization-usage.json"
    usage_path.write_text(
        json.dumps({receipt_id: {
            "receipt_id": receipt_id,
            "course_id": "1",
            "target_type": "quiz",
            "target_id": "4",
            "terminal_at": now.isoformat(),
            "terminal_action": "quiz.complete",
            "action_counts": {"quiz.complete": 1},
        }}),
        encoding="utf-8",
    )
    (work / "result.json").write_text(
        json.dumps({
            "kind": "quiz",
            "status": "submitted",
            "submitted_at": now.isoformat(),
            "authorization_receipt_id": receipt_id,
            "authorization_consumed": True,
            "quiz_id": 4,
            "metadata": {
                "canvas_workflow_state": "submitted",
                "readback_verified": True,
            },
            "kept_score": 8,
            "points_possible": 10,
            "attempts_used": 1,
            "allowed_attempts": 2,
            "scoring_policy": "keep_highest",
            "agent_passes_count": 4,
            "human_ness_diagnostics": {"views_paired_with_answers": True},
        }),
        encoding="utf-8",
    )
    try:
        cp = _run_hook(
            "stop_guard.py",
            {"stop_hook_active": False},
            {
                "CODEX_TEST_DATE": date,
                "CODEX_HOOK_SKIP_BATCH": "1",
                "CODEX_SESSION_ID": "guard-session",
                "CANVAS_AUTHORIZATION_USAGE_PATH": str(usage_path),
            },
        )
        reason = json.loads(cp.stdout)["reason"]
        assert "retake_required" in reason
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def test_stop_guard_rejects_unprepared_marker_even_with_valid_old_result() -> None:
    date = "guard-kernel-stale-result"
    run_dir = ROOT / "runs" / date
    shutil.rmtree(run_dir, ignore_errors=True)
    work = stable_work_dir(run_dir, 3, 9)
    work.mkdir(parents=True)
    now = dt.datetime.now(dt.timezone.utc)
    plan = {
        "generated_at": (now - dt.timedelta(minutes=1)).isoformat(),
        "expires_at": (now + dt.timedelta(hours=1)).isoformat(),
        "items": [{
            "index": 1,
            "course_id": 3,
            "assignment_id": 9,
            "name": "Synthetic Work",
            "proposed_skill": "canvas-generic",
            "user_decision": "approve",
        }],
    }
    assignments = [{
        "course_id": 3,
        "assignment_id": 9,
        "course_name": "Test Course",
        "name": "Synthetic Work",
        "skill": "canvas-generic",
        "work_dir": str(work),
    }]
    (run_dir / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    (run_dir / "assignments.json").write_text(json.dumps(assignments), encoding="utf-8")
    result = work / "result.json"
    result.write_text(
        json.dumps({"status": "skipped", "notes": "old run"}), encoding="utf-8"
    )
    (run_dir / ".scan_in_progress").write_text(
        json.dumps({
            "session_id": "stale-session",
            "owner_kind": "codex",
            "created_at": now.isoformat(),
            "plan_digest": plan_digest(plan),
        }),
        encoding="utf-8",
    )
    try:
        cp = _run_hook(
            "stop_guard.py",
            {"stop_hook_active": False},
            {
                "CODEX_TEST_DATE": date,
                "CODEX_HOOK_SKIP_BATCH": "1",
                "CODEX_SESSION_ID": "stale-session",
            },
        )
        payload = json.loads(cp.stdout)
        assert payload["decision"] == "block"
        assert "result-preparation evidence" in payload["reason"]
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def test_missing_source_receipt_cannot_bypass_mandatory_overlay() -> None:
    overlay = ROOT / "_private" / "canvas-kerneltest-app.md"
    work = ROOT / "runs" / "guard-kernel-source" / "work"
    overlay.parent.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    overlay.write_text(
        """## Course 42\n\n```yaml\nrequired_sources:\n  - id: required-reading\n    enforcement: mandatory\n    applies_to_kinds: [weekly]\n    what: synthetic source\n```\n""",
        encoding="utf-8",
    )
    try:
        issue = HOOK_LIB.source_manifest_issue(
            work,
            result_data={
                "course_id": 42,
                "skill_name": "canvas-kerneltest",
                "assignment_kind": "weekly",
            },
        )
        assert issue and "sources.json is missing" in issue
    finally:
        overlay.unlink(missing_ok=True)
        shutil.rmtree(ROOT / "runs" / "guard-kernel-source", ignore_errors=True)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _init_repo(path: Path) -> None:
    path.mkdir()
    _git(path, "init", "-b", "main")
    _git(path, "config", "user.name", "Synthetic Tester")
    _git(path, "config", "user.email", "tester@example.test")
    (path / "clean.txt").write_text("clean\n", encoding="utf-8")
    _git(path, "add", "clean.txt")
    _git(path, "commit", "-m", "clean")


def test_public_guard_covers_untracked_staged_and_combined_lifecycle(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    secret = "synthetic-student@private-campus" + ".edu"
    (repo / "new.txt").write_text(secret, encoding="utf-8")
    issue = HOOK_LIB.git_leak_issue("git add new.txt", root=repo)
    assert issue and secret not in issue
    _git(repo, "add", "new.txt")
    (repo / "new.txt").write_text("clean worktree replacement", encoding="utf-8")
    issue = HOOK_LIB.git_leak_issue("git commit -m test", root=repo)
    assert issue and "index" in issue
    issue = HOOK_LIB.git_leak_issue("git add -A; git commit -m test; git push origin main", root=repo)
    assert issue and secret not in issue


def test_public_guard_covers_committed_outgoing_and_snapshot_tree(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    remote = tmp_path / "remote.git"
    _init_repo(repo)
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, stdout=subprocess.PIPE)
    _git(repo, "remote", "add", "origin", str(remote))
    _git(repo, "push", "-u", "origin", "main")
    secret = "outgoing-student@private-campus" + ".edu"
    (repo / "committed.txt").write_text(secret, encoding="utf-8")
    _git(repo, "add", "committed.txt")
    _git(repo, "commit", "-m", "outgoing")
    outgoing = HOOK_LIB.git_leak_issue("git push origin main", root=repo)
    snapshot = HOOK_LIB.git_leak_issue(
        "python scripts/push_public_snapshot.py --source HEAD", root=repo
    )
    assert outgoing and "commit:" in outgoing and secret not in outgoing
    assert snapshot and "snapshot:HEAD" in snapshot and secret not in snapshot


def test_public_guard_scans_embedded_identifiers_in_binary_suffixes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    secret = "binary-student@private-campus" + ".edu"
    (repo / "fixture.pdf").write_bytes(b"%PDF-1.4\n" + secret.encode("ascii"))

    issue = HOOK_LIB.git_leak_issue("git add fixture.pdf", root=repo)

    assert issue and "fixture.pdf" in issue and secret not in issue


def test_snapshot_identity_and_binary_audit_follow_public_contract(tmp_path: Path) -> None:
    assert push_public_snapshot.PUBLIC_AUTHOR == "X_isdoingreat"
    assert push_public_snapshot.PUBLIC_EMAIL == "X_isdoingreat@proton.me"
    secret = "archived-student@private-campus" + ".edu"
    payload = tmp_path / "archive.zip"
    payload.write_bytes(b"PK\x03\x04" + secret.encode("ascii"))

    hits = push_public_snapshot.audit_tree(tmp_path)

    assert any(path == Path("archive.zip") and label == "academic-email" for path, _, label in hits)


def test_runner_guard_blocks_any_executable_under_runs() -> None:
    blocked_path = str(Path("runs") / "test" / "solve_all.py")
    cp = _run_hook(
        "post_tool_guard.py",
        {"tool_input": {"file_path": blocked_path}},
    )
    assert json.loads(cp.stdout)["decision"] == "block"
