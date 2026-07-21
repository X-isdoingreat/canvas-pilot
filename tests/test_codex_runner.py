from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from src.codex_runner import (
    CodexRunnerUnavailable,
    build_exec_argv,
    resolve_codex_command,
    run_codex,
)


def _fake_command(script: str) -> str:
    return json.dumps([sys.executable, "-c", script])


def test_explicit_command_is_json_argv_not_shell_text() -> None:
    env = {"CANVAS_CODEX_COMMAND_JSON": json.dumps(["tool path", "arg one"])}
    assert resolve_codex_command(env) == ("tool path", "arg one")


def test_invalid_explicit_command_fails_loudly() -> None:
    with pytest.raises(CodexRunnerUnavailable):
        resolve_codex_command({"CANVAS_CODEX_COMMAND_JSON": "not-json"})


def test_build_exec_argv_uses_canonical_hooks_and_workspace_network() -> None:
    argv = build_exec_argv(("codex",), sandbox="workspace-write")
    assert argv[:7] == (
        "codex",
        "--ask-for-approval",
        "never",
        "--sandbox",
        "workspace-write",
        "--enable",
        "hooks",
    )
    assert "sandbox_workspace_write.network_access=true" in argv
    assert argv[-4:] == ("exec", "--ephemeral", "--json", "-")


def test_run_codex_preserves_child_exit_and_prompt(tmp_path: Path) -> None:
    script = (
        "import sys; p=sys.stdin.read(); print('PROMPT='+p); "
        "print('CANVAS_DRIVER_CHECK'); raise SystemExit(7)"
    )
    log = tmp_path / "trace.jsonl"
    result = run_codex(
        "synthetic prompt",
        cwd=tmp_path,
        log_path=log,
        timeout_s=10,
        env={"CANVAS_CODEX_COMMAND_JSON": _fake_command(script)},
    )
    assert result.returncode == 7
    assert result.timed_out is False
    assert "PROMPT=synthetic prompt" in log.read_text(encoding="utf-8")


def test_run_codex_timeout_is_nonzero(tmp_path: Path) -> None:
    log = tmp_path / "timeout.jsonl"
    result = run_codex(
        "wait",
        cwd=tmp_path,
        log_path=log,
        timeout_s=1,
        env={
            "CANVAS_CODEX_COMMAND_JSON": _fake_command(
                "import time; time.sleep(10)"
            )
        },
    )
    assert result.returncode == 124
    assert result.timed_out is True
    assert '"canvas_pilot":"timeout"' in log.read_text(encoding="utf-8")
