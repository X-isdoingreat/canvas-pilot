# SPDX-License-Identifier: AGPL-3.0-or-later
"""Stable non-interactive Codex launcher for Canvas Pilot.

The Windows npm shim has historically been unreliable for long-running
``codex exec`` calls.  This module resolves the package's JavaScript entry and
launches it through Node when possible, while keeping the child inside the
workspace-write sandbox with network explicitly enabled for Canvas access.

Prompts are sent on stdin, never interpolated into a shell command.  The
launcher returns the real child exit code and terminates the exact process tree
on timeout.  It does not grant assignment or Canvas-mutation authority; those
remain separate run-state and authorization receipts.
"""
from __future__ import annotations

import dataclasses
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Mapping, Sequence


class CodexRunnerUnavailable(RuntimeError):
    """Raised when no safe Codex executable path can be resolved."""


@dataclasses.dataclass(frozen=True)
class CodexRunResult:
    returncode: int
    log_path: Path
    timed_out: bool
    argv: tuple[str, ...]


def _existing_file(value: str | os.PathLike[str] | None) -> Path | None:
    if not value:
        return None
    path = Path(value).expanduser().resolve()
    return path if path.is_file() else None


def _node_executable(env: Mapping[str, str]) -> Path | None:
    explicit = _existing_file(env.get("CANVAS_CODEX_NODE"))
    if explicit:
        return explicit
    found = shutil.which("node")
    return _existing_file(found)


def _codex_js_candidates(env: Mapping[str, str], node: Path | None) -> list[Path]:
    candidates: list[Path] = []
    explicit = env.get("CANVAS_CODEX_JS")
    if explicit:
        candidates.append(Path(explicit))

    managed_root = env.get("CODEX_MANAGED_PACKAGE_ROOT")
    if managed_root:
        candidates.append(Path(managed_root) / "bin" / "codex.js")

    if node is not None:
        candidates.append(
            node.parent / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
        )

    codex_on_path = shutil.which("codex") or shutil.which("codex.cmd")
    if codex_on_path:
        shim = Path(codex_on_path).resolve()
        candidates.append(
            shim.parent / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
        )

    out: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        key = os.path.normcase(str(resolved))
        if key not in seen:
            seen.add(key)
            out.append(resolved)
    return out


def resolve_codex_command(
    env: Mapping[str, str] | None = None,
) -> tuple[str, ...]:
    """Return an argv prefix that can safely receive Codex arguments.

    ``CANVAS_CODEX_COMMAND_JSON`` is a test/deployment escape hatch containing
    a JSON array, for example ``["C:/tools/codex.exe"]``.  It is intentionally
    JSON rather than a shell string so paths and arguments cannot be
    reinterpreted by a shell.
    """

    source = dict(os.environ if env is None else env)
    explicit = source.get("CANVAS_CODEX_COMMAND_JSON")
    if explicit:
        try:
            parsed = json.loads(explicit)
        except json.JSONDecodeError as exc:
            raise CodexRunnerUnavailable(
                "CANVAS_CODEX_COMMAND_JSON must be a JSON array"
            ) from exc
        if not isinstance(parsed, list) or not parsed or not all(
            isinstance(part, str) and part for part in parsed
        ):
            raise CodexRunnerUnavailable(
                "CANVAS_CODEX_COMMAND_JSON must be a non-empty JSON string array"
            )
        return tuple(parsed)

    native = _existing_file(source.get("CANVAS_CODEX_EXE"))
    if native:
        return (str(native),)

    node = _node_executable(source)
    if node:
        for candidate in _codex_js_candidates(source, node):
            if candidate.is_file():
                return (str(node), str(candidate))

    on_path = shutil.which("codex")
    if on_path and os.name != "nt":
        return (str(Path(on_path).resolve()),)

    raise CodexRunnerUnavailable(
        "Codex CLI not found. Install @openai/codex or set "
        "CANVAS_CODEX_NODE + CANVAS_CODEX_JS (or CANVAS_CODEX_EXE)."
    )


def build_exec_argv(
    command_prefix: Sequence[str],
    *,
    sandbox: str = "workspace-write",
    network_access: bool = True,
) -> tuple[str, ...]:
    if sandbox not in {"read-only", "workspace-write", "danger-full-access"}:
        raise ValueError(f"unsupported Codex sandbox: {sandbox!r}")
    argv = [
        *command_prefix,
        "--ask-for-approval",
        "never",
        "--sandbox",
        sandbox,
        "--enable",
        "hooks",
    ]
    if sandbox == "workspace-write":
        argv.extend(
            [
                "--config",
                "sandbox_workspace_write.network_access="
                + ("true" if network_access else "false"),
            ]
        )
    argv.extend(["exec", "--ephemeral", "--json", "-"])
    return tuple(str(part) for part in argv)


def _terminate_process_tree(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=15,
            )
        except Exception:
            pass
    if proc.poll() is None:
        try:
            proc.kill()
        except Exception:
            pass


def run_codex(
    prompt: str,
    *,
    cwd: str | os.PathLike[str],
    log_path: str | os.PathLike[str],
    timeout_s: int = 30 * 60,
    sandbox: str = "workspace-write",
    network_access: bool = True,
    env: Mapping[str, str] | None = None,
) -> CodexRunResult:
    """Run one fresh ephemeral Codex turn and preserve its JSONL trace.

    The returned ``returncode`` is never rewritten to success.  Timeout uses
    the conventional value 124.  ``CANVAS_DRIVER=codex`` is set for child tool
    processes so the Canvas API mutation kernel can enforce scoped receipts.
    """

    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be non-empty")
    if timeout_s <= 0:
        raise ValueError("timeout_s must be positive")

    workdir = Path(cwd).resolve()
    if not workdir.is_dir():
        raise FileNotFoundError(f"Codex working directory does not exist: {workdir}")
    output = Path(log_path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    child_env = dict(os.environ)
    if env:
        child_env.update({str(k): str(v) for k, v in env.items()})
    child_env["CANVAS_DRIVER"] = "codex"
    prefix = resolve_codex_command(child_env)
    argv = build_exec_argv(
        prefix, sandbox=sandbox, network_access=network_access
    )

    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    timed_out = False
    with output.open("w", encoding="utf-8", newline="\n") as log:
        proc = subprocess.Popen(
            list(argv),
            cwd=str(workdir),
            stdin=subprocess.PIPE,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=child_env,
            shell=False,
            creationflags=creationflags,
        )
        try:
            proc.communicate(input=prompt, timeout=timeout_s)
            returncode = int(proc.returncode or 0)
        except subprocess.TimeoutExpired:
            timed_out = True
            _terminate_process_tree(proc)
            try:
                proc.wait(timeout=15)
            except Exception:
                pass
            returncode = 124
            log.write(f"\n{{\"canvas_pilot\":\"timeout\",\"seconds\":{timeout_s}}}\n")
            log.flush()

    return CodexRunResult(
        returncode=returncode,
        log_path=output,
        timed_out=timed_out,
        argv=argv,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Small diagnostic CLI; it never starts Codex unless ``--probe`` is used."""

    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", action="store_true", help="run a no-write Codex probe")
    parser.add_argument("--cwd", default=str(Path.cwd()))
    parser.add_argument("--log", default="runs/codex/codex-runner-probe.jsonl")
    parser.add_argument("--timeout", type=int, default=90)
    args = parser.parse_args(list(argv) if argv is not None else None)

    if not args.probe:
        print(json.dumps({"command_prefix": resolve_codex_command()}, ensure_ascii=False))
        return 0
    result = run_codex(
        "Return exactly CODEX_RUNNER_OK. Do not use tools.",
        cwd=args.cwd,
        log_path=args.log,
        timeout_s=args.timeout,
        sandbox="workspace-write",
        network_access=False,
    )
    print(
        json.dumps(
            {
                "returncode": result.returncode,
                "timed_out": result.timed_out,
                "log_path": str(result.log_path),
            },
            ensure_ascii=False,
        )
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
