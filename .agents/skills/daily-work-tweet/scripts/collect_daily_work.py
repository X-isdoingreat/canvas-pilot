# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time as time_module
from datetime import date, datetime, time, timedelta, tzinfo
from pathlib import Path
from typing import Any


RECORD_SEPARATOR = "\x1e"
FIELD_SEPARATOR = "\x1f"
DEFAULT_GIT_TIMEOUT_SECONDS = 8.0
MAX_CHANGED_FILES_PER_COMMIT = 30
MAX_GIT_LINE_CHARACTERS = 500
MAX_COMMIT_SUBJECT_CHARACTERS = 500
MAX_COMMIT_STAT_CHARACTERS = 1_000
DEFAULT_MAX_STATUS_LINES = 200
DEFAULT_MAX_STAT_CHARACTERS = 4_000


class GitError(RuntimeError):
    pass


def run_git(
    root: Path,
    arguments: list[str],
    *,
    check: bool = True,
    timeout_seconds: float = DEFAULT_GIT_TIMEOUT_SECONDS,
    deadline_monotonic: float | None = None,
) -> str:
    environment = os.environ.copy()
    environment.update(
        {
            "GIT_TERMINAL_PROMPT": "0",
            "GCM_INTERACTIVE": "Never",
            "GIT_OPTIONAL_LOCKS": "0",
        }
    )
    if deadline_monotonic is not None:
        remaining = deadline_monotonic - time_module.monotonic()
        if remaining <= 0:
            raise GitError("aggregate Git time budget exhausted")
        timeout_seconds = min(timeout_seconds, remaining)
    try:
        completed = subprocess.run(
            [
                "git",
                "--no-optional-locks",
                "-c",
                "core.fsmonitor=false",
                "-C",
                str(root),
                *arguments,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=timeout_seconds,
            env=environment,
        )
    except subprocess.TimeoutExpired as exc:
        raise GitError(f"git command timed out after {timeout_seconds:g}s") from exc
    if check and completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "unknown git error"
        raise GitError(detail)
    return completed.stdout


def resolve_root(candidate: str, *, deadline_monotonic: float | None = None) -> Path:
    requested = Path(candidate).resolve()
    top_level = run_git(
        requested,
        ["rev-parse", "--show-toplevel"],
        deadline_monotonic=deadline_monotonic,
    ).strip()
    if not top_level:
        raise GitError(f"not a Git repository: {requested}")
    return Path(top_level).resolve()


def parse_day(raw: str | None) -> date:
    if raw is None:
        return date.today()
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD") from exc


def day_bounds(day: date) -> tuple[str, str]:
    start = datetime.combine(day, time.min)
    end = start + timedelta(days=1)
    return start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds")


def changed_files(
    root: Path,
    commit: str,
    *,
    deadline_monotonic: float | None = None,
) -> tuple[list[str], bool]:
    output = run_git(
        root,
        [
            "show",
            "--no-ext-diff",
            "--no-textconv",
            "--format=",
            "--name-status",
            "--find-renames",
            commit,
        ],
        deadline_monotonic=deadline_monotonic,
    )
    raw_files = [line for line in output.splitlines() if line.strip()]
    files = [line[:MAX_GIT_LINE_CHARACTERS] for line in raw_files]
    truncated = len(raw_files) > MAX_CHANGED_FILES_PER_COMMIT or any(
        len(line) > MAX_GIT_LINE_CHARACTERS for line in raw_files
    )
    return files[:MAX_CHANGED_FILES_PER_COMMIT], truncated


def commit_stat(
    root: Path,
    commit: str,
    *,
    deadline_monotonic: float | None = None,
) -> str:
    output = run_git(
        root,
        ["show", "--no-ext-diff", "--no-textconv", "--format=", "--shortstat", commit],
        deadline_monotonic=deadline_monotonic,
    )
    summary = " ".join(line.strip() for line in output.splitlines() if line.strip())
    return summary[:MAX_COMMIT_STAT_CHARACTERS]


def configured_identity(
    root: Path,
    *,
    deadline_monotonic: float | None = None,
) -> tuple[str, str]:
    name = run_git(
        root,
        ["config", "--get", "user.name"],
        check=False,
        deadline_monotonic=deadline_monotonic,
    ).strip().casefold()
    email = run_git(
        root,
        ["config", "--get", "user.email"],
        check=False,
        deadline_monotonic=deadline_monotonic,
    ).strip().casefold()
    return name, email


def collect_commits_between(
    root: Path,
    start: datetime,
    end: datetime,
    max_commits: int,
    *,
    all_refs: bool = False,
    deadline_monotonic: float | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    record_format = (
        f"%H{FIELD_SEPARATOR}%h{FIELD_SEPARATOR}%aI{FIELD_SEPARATOR}%cI"
        f"{FIELD_SEPARATOR}%an{FIELD_SEPARATOR}%ae{FIELD_SEPARATOR}%s{RECORD_SEPARATOR}"
    )
    revision_scope = ["--all"] if all_refs else []
    output = run_git(
        root,
        [
            "log",
            "--reverse",
            *revision_scope,
            f"--since={start.isoformat(timespec='seconds')}",
            f"--until={end.isoformat(timespec='seconds')}",
            f"--max-count={max_commits + 1}",
            f"--pretty=format:{record_format}",
        ],
        deadline_monotonic=deadline_monotonic,
    )
    configured_name, configured_email = configured_identity(
        root,
        deadline_monotonic=deadline_monotonic,
    )
    records = [record.strip() for record in output.split(RECORD_SEPARATOR) if record.strip()]
    truncated = len(records) > max_commits
    records = records[:max_commits]

    commits: list[dict[str, Any]] = []
    for record in records:
        fields = record.split(FIELD_SEPARATOR, maxsplit=6)
        if len(fields) != 7:
            raise GitError("could not parse git log output")
        full_hash, short_hash, authored_at, committed_at, author_name, author_email, subject = fields
        files, files_truncated = changed_files(
            root,
            full_hash,
            deadline_monotonic=deadline_monotonic,
        )
        if configured_email and author_email.strip().casefold() == configured_email:
            authorship = "verified_configured_email"
        elif configured_name and author_name.strip().casefold() == configured_name:
            authorship = "probable_configured_name"
        else:
            authorship = "unverified"
        commits.append(
            {
                "hash": full_hash,
                "short_hash": short_hash,
                "authored_at": authored_at,
                "committed_at": committed_at,
                "authorship": authorship,
                "subject": subject[:MAX_COMMIT_SUBJECT_CHARACTERS],
                "subject_truncated": len(subject) > MAX_COMMIT_SUBJECT_CHARACTERS,
                "stat": commit_stat(
                    root,
                    full_hash,
                    deadline_monotonic=deadline_monotonic,
                ),
                "changed_files": files,
                "changed_files_truncated": files_truncated,
            }
        )
    return commits, truncated


def collect_commits(
    root: Path,
    day: date,
    max_commits: int,
    *,
    timezone: tzinfo | None = None,
    all_refs: bool = False,
    deadline_monotonic: float | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    start = datetime.combine(day, time.min, tzinfo=timezone)
    end = start + timedelta(days=1)
    return collect_commits_between(
        root,
        start,
        end,
        max_commits,
        all_refs=all_refs,
        deadline_monotonic=deadline_monotonic,
    )


def current_branch(root: Path, *, deadline_monotonic: float | None = None) -> str:
    branch = run_git(
        root,
        ["branch", "--show-current"],
        deadline_monotonic=deadline_monotonic,
    ).strip()
    return branch or "(detached HEAD)"


def truncate_text(raw: str, max_characters: int) -> tuple[str, bool]:
    if len(raw) <= max_characters:
        return raw, False
    return raw[:max_characters].rstrip(), True


def working_tree(
    root: Path,
    *,
    untracked_mode: str = "all",
    max_status_lines: int = DEFAULT_MAX_STATUS_LINES,
    max_stat_characters: int = DEFAULT_MAX_STAT_CHARACTERS,
    deadline_monotonic: float | None = None,
) -> dict[str, Any]:
    if untracked_mode not in {"no", "normal", "all"}:
        raise ValueError(f"unsupported untracked mode: {untracked_mode}")
    if max_status_lines < 1 or max_stat_characters < 1:
        raise ValueError("working-tree output limits must be positive")
    status = [
        line
        for line in run_git(
            root,
            [
                "status",
                "--porcelain=v1",
                f"--untracked-files={untracked_mode}",
                "--ignore-submodules=all",
            ],
            deadline_monotonic=deadline_monotonic,
        ).splitlines()
        if line.strip()
    ]
    status_lines_truncated = any(len(line) > MAX_GIT_LINE_CHARACTERS for line in status)
    status = [line[:MAX_GIT_LINE_CHARACTERS] for line in status]
    unstaged_stat, unstaged_stat_truncated = truncate_text(
        run_git(
            root,
            ["diff", "--no-ext-diff", "--no-textconv", "--ignore-submodules", "--stat"],
            deadline_monotonic=deadline_monotonic,
        ).strip(),
        max_stat_characters,
    )
    staged_stat, staged_stat_truncated = truncate_text(
        run_git(
            root,
            [
                "diff",
                "--cached",
                "--no-ext-diff",
                "--no-textconv",
                "--ignore-submodules",
                "--stat",
            ],
            deadline_monotonic=deadline_monotonic,
        ).strip(),
        max_stat_characters,
    )
    return {
        "status": status[:max_status_lines],
        "status_count": len(status),
        "status_truncated": len(status) > max_status_lines or status_lines_truncated,
        "unstaged_stat": unstaged_stat,
        "unstaged_stat_truncated": unstaged_stat_truncated,
        "staged_stat": staged_stat,
        "staged_stat_truncated": staged_stat_truncated,
    }


def build_payload(
    root: Path,
    day: date,
    max_commits: int,
    *,
    timezone: tzinfo | None = None,
    all_refs: bool = False,
    untracked_mode: str = "all",
) -> dict[str, Any]:
    commits, truncated = collect_commits(
        root,
        day,
        max_commits,
        timezone=timezone,
        all_refs=all_refs,
    )
    tree = working_tree(root, untracked_mode=untracked_mode)
    notes: list[str] = []
    if not commits:
        notes.append("No commits were authored in this repository during the requested local day.")
    if tree["status"]:
        notes.append("The working tree has uncommitted changes; verify whether they belong to the day.")
    if truncated:
        notes.append(f"Commit evidence was truncated at {max_commits} entries.")

    return {
        "date": day.isoformat(),
        "repository": root.name,
        "branch": current_branch(root),
        "commits": commits,
        "commits_truncated": truncated,
        "working_tree": tree,
        "notes": notes,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect read-only Git evidence for a daily bilingual social post."
    )
    parser.add_argument("--repo", default=".", help="Path inside the target Git repository.")
    parser.add_argument("--date", help="Local calendar date in YYYY-MM-DD format.")
    parser.add_argument(
        "--max-commits",
        type=int,
        default=30,
        help="Maximum commits to include before marking the result truncated.",
    )
    parser.add_argument("--compact", action="store_true", help="Emit compact JSON.")
    args = parser.parse_args()
    if args.max_commits < 1:
        parser.error("--max-commits must be at least 1")
    return args


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    try:
        root = resolve_root(args.repo)
        requested_day = parse_day(args.date)
        payload = build_payload(root, requested_day, args.max_commits)
    except (GitError, argparse.ArgumentTypeError) as exc:
        print(f"daily-work-tweet: {exc}", file=sys.stderr)
        return 2

    json.dump(
        payload,
        sys.stdout,
        ensure_ascii=False,
        indent=None if args.compact else 2,
        sort_keys=False,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
