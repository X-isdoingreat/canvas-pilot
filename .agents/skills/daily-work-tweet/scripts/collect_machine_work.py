# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import argparse
import concurrent.futures
import ctypes
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import date, datetime, time as datetime_time, timedelta, timezone, tzinfo
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import collect_daily_work as repo_collector


CACHE_VERSION = 1
DEFAULT_SCAN_SECONDS = 45.0
DEFAULT_MAX_DIRECTORIES = 250_000
DEFAULT_MAX_REPOSITORIES = 500
DEFAULT_MAX_COMMITS_PER_REPOSITORY = 8
DEFAULT_MAX_TOTAL_COMMITS = 80
DEFAULT_GIT_WORKERS = 4
DEFAULT_MAX_ACTIVE_REPOSITORIES = 60
DEFAULT_MAX_GIT_SECONDS = 45.0
MACHINE_MAX_STATUS_LINES = 12
MACHINE_MAX_STAT_CHARACTERS = 1_200
MACHINE_MAX_CHANGED_FILES_PER_COMMIT = 12
MAX_OUTPUT_BYTES = 384_000

SKIP_DIRECTORIES = {
    "$recycle.bin",
    ".aws",
    ".azure",
    ".bun",
    ".cache",
    ".cargo",
    ".claude",
    ".codex",
    ".cookies",
    ".git",
    ".gnupg",
    ".gradle",
    ".kube",
    ".m2",
    ".next",
    ".npm",
    ".nvm",
    ".nuget",
    ".pnpm-store",
    ".rustup",
    ".ssh",
    ".terraform",
    ".venv",
    ".yarn",
    "__pycache__",
    "_private",
    "appdata",
    "build",
    "cache",
    "caches",
    "credentials",
    "dist",
    "final_drafts",
    "node_modules",
    "program files",
    "program files (x86)",
    "programdata",
    "recovery",
    "runs",
    "secrets",
    "system volume information",
    "target",
    "temp",
    "tmp",
    "venv",
    "windows",
}

FILE_CATEGORIES = {
    "code": {
        ".c",
        ".cc",
        ".cpp",
        ".css",
        ".go",
        ".html",
        ".ipynb",
        ".java",
        ".js",
        ".jsx",
        ".kt",
        ".php",
        ".py",
        ".rb",
        ".rs",
        ".scss",
        ".sh",
        ".sql",
        ".swift",
        ".ts",
        ".tsx",
        ".vue",
    },
    "document": {
        ".docx", ".md", ".odt", ".pdf", ".pptx", ".rst", ".tex", ".txt", ".xlsx",
    },
    "media": {
        ".aac", ".flac", ".gif", ".jpeg", ".jpg", ".m4a", ".mkv", ".mov",
        ".mp3", ".mp4", ".png", ".wav", ".webm",
    },
    "design": {".ai", ".fig", ".psd", ".sketch", ".svg"},
}

SENSITIVE_FILENAMES = {
    ".env",
    "auth.json",
    "credentials.json",
    "hosts.yml",
    "secrets.md",
}

EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
URL_RE = re.compile(r"(?i)\bhttps?://[^\s<>'\"]+")
WINDOWS_PATH_RE = re.compile(r"(?i)(?:[A-Z]:[\\/]|\\\\)[^\r\n<>'\"|,;]+")
WSL_PATH_RE = re.compile(r"(?i)(?:/mnt/[a-z]/|/home/)[^\s<>'\"]+")
UUID_RE = re.compile(r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b")
JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\b")
SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret)\b\s*[:=]\s*\S+"
)
LONG_ID_RE = re.compile(r"\b\d{8,}\b")


@dataclass
class DiscoveryResult:
    repositories: set[Path] = field(default_factory=set)
    vercel_roots: set[Path] = field(default_factory=set)
    modified_file_categories: Counter[str] = field(default_factory=Counter)
    directories_scanned: int = 0
    denied_or_unreadable: int = 0
    complete: bool = True
    limits_hit: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0


def configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def load_timezone(name: str | None) -> tuple[tzinfo, str]:
    if name:
        try:
            return ZoneInfo(name), name
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown timezone: {name}") from exc
    local = datetime.now().astimezone().tzinfo or timezone.utc
    return local, str(local)


def parse_day(raw: str | None, zone: tzinfo) -> date:
    if raw is None:
        return datetime.now(zone).date()
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("date must use YYYY-MM-DD") from exc


def day_bounds(day: date, zone: tzinfo) -> tuple[datetime, datetime]:
    start = datetime.combine(day, datetime_time.min, tzinfo=zone)
    return start, start + timedelta(days=1)


def path_key(path: Path) -> str:
    return os.path.normcase(os.path.abspath(path))


def path_is_within(path: Path, roots: list[Path]) -> bool:
    try:
        candidate = path.resolve()
    except OSError:
        return False
    for root in roots:
        try:
            candidate.relative_to(root.resolve())
            return True
        except (OSError, ValueError):
            continue
    return False


def is_fixed_local_path(path: Path) -> bool:
    if os.name != "nt":
        return path_is_within(path, [Path.home()])
    try:
        anchor = path.resolve().anchor
    except OSError:
        return False
    if not anchor or anchor.startswith("\\\\"):
        return False
    return ctypes.windll.kernel32.GetDriveTypeW(anchor) == 3


def unique_existing_paths(paths: Iterable[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        try:
            candidate = path.resolve()
        except OSError:
            continue
        key = path_key(candidate)
        if key in seen or not candidate.exists():
            continue
        seen.add(key)
        result.append(candidate)
    return result


def fixed_drive_roots() -> list[Path]:
    if os.name != "nt":
        return [Path.home()]
    bitmask = ctypes.windll.kernel32.GetLogicalDrives()
    roots: list[Path] = []
    for index in range(26):
        if not bitmask & (1 << index):
            continue
        root = f"{chr(ord('A') + index)}:\\"
        if ctypes.windll.kernel32.GetDriveTypeW(root) == 3:
            roots.append(Path(root))
    return roots


def is_reparse_point(entry: os.DirEntry[str]) -> bool:
    try:
        attributes = getattr(entry.stat(follow_symlinks=False), "st_file_attributes", 0)
    except OSError:
        return True
    return bool(attributes & 0x400)


def is_other_windows_user(parent: Path, child_name: str) -> bool:
    if os.name != "nt":
        return False
    system_drive = os.environ.get("SystemDrive", "C:")
    users_root = Path(f"{system_drive}\\Users")
    if path_key(parent) != path_key(users_root):
        return False
    allowed = {Path.home().name.casefold()}
    return child_name.casefold() not in allowed


def file_category(name: str) -> str | None:
    if name.casefold() in SENSITIVE_FILENAMES or name.casefold().startswith(".env."):
        return None
    suffix = Path(name).suffix.casefold()
    for category, extensions in FILE_CATEGORIES.items():
        if suffix in extensions:
            return category
    return None


def discover_machine(
    roots: list[Path],
    start_epoch: float,
    end_epoch: float,
    *,
    max_seconds: float,
    max_directories: int,
    max_repositories: int,
) -> DiscoveryResult:
    result = DiscoveryResult()
    started = time.monotonic()
    deadline = started + max_seconds
    queue: deque[Path] = deque(unique_existing_paths(roots))
    visited: set[str] = set()

    while queue:
        if time.monotonic() >= deadline:
            result.complete = False
            result.limits_hit.append("time_budget")
            break
        if result.directories_scanned >= max_directories:
            result.complete = False
            result.limits_hit.append("directory_budget")
            break
        if len(result.repositories) >= max_repositories:
            result.complete = False
            result.limits_hit.append("repository_budget")
            break

        directory = queue.popleft()
        key = path_key(directory)
        if key in visited:
            continue
        visited.add(key)
        result.directories_scanned += 1

        try:
            entries = list(os.scandir(directory))
        except OSError:
            result.denied_or_unreadable += 1
            continue

        names = {entry.name.casefold(): entry for entry in entries}
        git_marker = names.get(".git")
        if git_marker is not None:
            result.repositories.add(directory)
        vercel_marker = names.get(".vercel")
        if vercel_marker is not None and (directory / ".vercel" / "project.json").is_file():
            result.vercel_roots.add(directory)

        for entry in entries:
            name_lower = entry.name.casefold()
            try:
                if entry.is_dir(follow_symlinks=False):
                    if (
                        name_lower in SKIP_DIRECTORIES
                        or is_other_windows_user(directory, entry.name)
                        or is_reparse_point(entry)
                    ):
                        continue
                    queue.append(Path(entry.path))
                    continue
                category = file_category(entry.name)
                if category is None:
                    continue
                modified = entry.stat(follow_symlinks=False).st_mtime
                if start_epoch <= modified < end_epoch:
                    result.modified_file_categories[category] += 1
            except OSError:
                result.denied_or_unreadable += 1

    result.elapsed_seconds = round(time.monotonic() - started, 3)
    return result


def cache_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base / "CanvasPilot" / "daily-work-tweet" / "repo-index-v1.json"


def load_cache(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or data.get("version") != CACHE_VERSION:
        return None
    return data


def cache_fresh(data: dict[str, Any], max_age_hours: float) -> bool:
    try:
        updated = datetime.fromisoformat(str(data["updated_at_utc"]).replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError):
        return False
    age = datetime.now(timezone.utc) - updated
    return timedelta(0) <= age <= timedelta(hours=max_age_hours)


def cache_usable(
    data: dict[str, Any] | None,
    max_age_hours: float,
    *,
    refresh: bool,
) -> bool:
    return bool(
        data
        and data.get("scan_complete") is True
        and cache_fresh(data, max_age_hours)
        and not refresh
    )


def cached_paths(data: dict[str, Any] | None, key: str) -> set[Path]:
    if not data:
        return set()
    values = data.get(key, [])
    if not isinstance(values, list):
        return set()
    paths: set[Path] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        path = Path(value)
        if not path.exists() or not is_fixed_local_path(path):
            continue
        if key == "repositories" and not (path / ".git").exists():
            continue
        if key == "vercel_roots" and not (path / ".vercel" / "project.json").is_file():
            continue
        paths.add(path)
    return paths


def write_cache(path: Path, discovery: DiscoveryResult) -> None:
    payload = {
        "version": CACHE_VERSION,
        "updated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "scan_complete": discovery.complete,
        "directories_scanned": discovery.directories_scanned,
        "denied_or_unreadable": discovery.denied_or_unreadable,
        "limits_hit": discovery.limits_hit,
        "repositories": sorted(str(path) for path in discovery.repositories),
        "vercel_roots": sorted(str(path) for path in discovery.vercel_roots),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def sanitize_text(raw: str, *, max_chars: int = 600) -> str | None:
    if JWT_RE.search(raw) or SECRET_ASSIGNMENT_RE.search(raw):
        return None
    text = URL_RE.sub("<url>", raw)
    text = EMAIL_RE.sub("<email>", text)
    text = WINDOWS_PATH_RE.sub("<local-path>", text)
    text = WSL_PATH_RE.sub("<local-path>", text)
    text = UUID_RE.sub("<id>", text)
    text = LONG_ID_RE.sub("<id>", text)
    text = " ".join(text.split())
    if not text:
        return None
    return text[:max_chars]


def newest_codex_state_db() -> Path | None:
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    candidates = sorted(
        codex_home.glob("state_*.sqlite"),
        key=lambda path: path.stat().st_mtime if path.exists() else 0,
        reverse=True,
    )
    return candidates[0] if candidates else None


def tail_task_completes(
    rollout_path: Path,
    start_epoch: int,
    end_epoch: int,
    *,
    max_bytes: int = 2_000_000,
    max_completions: int = 3,
) -> tuple[list[dict[str, Any]], bool, bool]:
    try:
        size = rollout_path.stat().st_size
        with rollout_path.open("rb") as handle:
            if size > max_bytes:
                handle.seek(size - max_bytes)
                handle.readline()
            lines = handle.readlines()
    except OSError:
        return [], False, False

    tail_truncated = size > max_bytes
    completions: list[dict[str, Any]] = []
    matching_completions = 0
    for raw_line in reversed(lines):
        try:
            record = json.loads(raw_line.decode("utf-8", errors="replace"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if record.get("type") != "event_msg":
            continue
        payload = record.get("payload") or {}
        if payload.get("type") != "task_complete":
            continue
        completed_at = payload.get("completed_at")
        if not isinstance(completed_at, (int, float)) or not start_epoch <= completed_at < end_epoch:
            continue
        summary = sanitize_text(str(payload.get("last_agent_message") or ""))
        if summary:
            matching_completions += 1
            if len(completions) < max_completions:
                completions.append({"completed_at": int(completed_at), "summary": summary})
    return completions, tail_truncated, matching_completions > max_completions


def collect_codex_activity(
    start: datetime,
    end: datetime,
    zone: tzinfo,
    *,
    max_threads: int = 40,
    allowed_roots: list[Path] | None = None,
) -> tuple[dict[str, Any], list[Path]]:
    database = newest_codex_state_db()
    if database is None:
        return {"status": "unavailable", "reason": "Codex state database not found"}, []

    start_epoch = int(start.timestamp())
    end_epoch = int(end.timestamp())
    try:
        connection = sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True, timeout=2)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        rows = connection.execute(
            """
            SELECT rollout_path, cwd, created_at, updated_at
            FROM threads
            WHERE created_at < ? AND updated_at >= ?
              AND (agent_path IS NULL OR agent_path = '')
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (end_epoch, start_epoch, max_threads + 1),
        ).fetchall()
        connection.close()
    except sqlite3.Error as exc:
        return {"status": "unavailable", "reason": f"Codex state query failed: {type(exc).__name__}"}, []

    threads_truncated = len(rows) > max_threads
    rows = rows[:max_threads]
    summaries: list[dict[str, Any]] = []
    cwd_seeds: list[Path] = []
    dropped = 0
    eligible_threads = 0
    rollout_tails_truncated = 0
    completion_lists_truncated = 0
    for row in rows:
        cwd = row["cwd"]
        if allowed_roots is not None and (
            not isinstance(cwd, str) or not path_is_within(Path(cwd), allowed_roots)
        ):
            continue
        eligible_threads += 1
        if isinstance(cwd, str) and Path(cwd).exists():
            cwd_seeds.append(Path(cwd))
        rollout = row["rollout_path"]
        if not isinstance(rollout, str):
            continue
        completions, tail_truncated, completions_truncated = tail_task_completes(
            Path(rollout),
            start_epoch,
            end_epoch,
        )
        rollout_tails_truncated += int(tail_truncated)
        completion_lists_truncated += int(completions_truncated)
        if not completions:
            continue
        workspace = sanitize_text(Path(cwd).name if isinstance(cwd, str) else "workspace", max_chars=80)
        if workspace is None:
            workspace = "workspace"
            dropped += 1
        for completion in completions:
            completed_local = datetime.fromtimestamp(completion["completed_at"], zone)
            summaries.append(
                {
                    "workspace": workspace,
                    "completed_at": completed_local.isoformat(timespec="seconds"),
                    "summary": completion["summary"],
                    "evidence_strength": "agent_report_only",
                    "public_safe": False,
                }
            )

    source_partial = bool(
        threads_truncated or rollout_tails_truncated or completion_lists_truncated
    )
    return (
        {
            "status": "partial" if source_partial else "ok",
            "root_threads_considered": eligible_threads,
            "root_threads_truncated": threads_truncated,
            "rollout_tails_truncated": rollout_tails_truncated,
            "thread_completion_lists_truncated": completion_lists_truncated,
            "task_complete_summaries": summaries,
            "records_dropped_during_redaction": dropped,
            "note": "Codex summaries support context but do not prove deployment or test success.",
        },
        cwd_seeds,
    )


def remote_host(root: Path, *, deadline_monotonic: float | None = None) -> str | None:
    raw = repo_collector.run_git(
        root,
        ["remote", "get-url", "origin"],
        check=False,
        deadline_monotonic=deadline_monotonic,
    ).strip()
    if not raw:
        return None
    if "://" in raw:
        return (urlsplit(raw).hostname or "").casefold() or None
    if "@" in raw and ":" in raw:
        return raw.split("@", 1)[1].split(":", 1)[0].casefold()
    return None


def collect_repository(
    candidate: Path,
    start: datetime,
    end: datetime,
    *,
    max_commits: int,
    include_untracked: bool,
    deadline_monotonic: float,
) -> tuple[Path | None, dict[str, Any] | None, str | None]:
    try:
        root = repo_collector.resolve_root(
            str(candidate),
            deadline_monotonic=deadline_monotonic,
        )
        commits, commits_truncated = repo_collector.collect_commits_between(
            root,
            start,
            end,
            max_commits,
            all_refs=True,
            deadline_monotonic=deadline_monotonic,
        )
        for commit in commits:
            if len(commit["changed_files"]) > MACHINE_MAX_CHANGED_FILES_PER_COMMIT:
                commit["changed_files"] = commit["changed_files"][:MACHINE_MAX_CHANGED_FILES_PER_COMMIT]
                commit["changed_files_truncated"] = True
        tree = repo_collector.working_tree(
            root,
            untracked_mode="normal" if include_untracked else "no",
            max_status_lines=MACHINE_MAX_STATUS_LINES,
            max_stat_characters=MACHINE_MAX_STAT_CHARACTERS,
            deadline_monotonic=deadline_monotonic,
        )
        if not commits and not tree["status"]:
            return root, None, None
        return (
            root,
            {
                "repository": root.name,
                "path": str(root),
                "checked_out_branch": repo_collector.current_branch(
                    root,
                    deadline_monotonic=deadline_monotonic,
                ),
                "remote_host": remote_host(
                    root,
                    deadline_monotonic=deadline_monotonic,
                ),
                "commits": commits,
                "commit_authorship_counts": dict(
                    Counter(commit["authorship"] for commit in commits)
                ),
                "commits_truncated": commits_truncated,
                "working_tree": tree,
                "dirty_state_is_date_unverified": bool(tree["status"]),
                "public_safe": False,
            },
            None,
        )
    except (repo_collector.GitError, OSError, ValueError) as exc:
        return None, None, type(exc).__name__


def collect_repositories(
    candidates: set[Path],
    priority_roots: set[str],
    start: datetime,
    end: datetime,
    *,
    max_commits_per_repository: int,
    max_total_commits: int,
    max_active_repositories: int,
    workers: int,
    max_seconds: float,
) -> dict[str, Any]:
    candidates = set(unique_existing_paths(candidates))
    active_by_root: dict[str, dict[str, Any]] = {}
    verified_roots: set[str] = set()
    failures = 0
    started = time.monotonic()
    deadline = started + max_seconds
    ordered_candidates = sorted(
        candidates,
        key=lambda candidate: (
            0 if path_key(candidate) in priority_roots else 1,
            path_key(candidate),
        ),
    )
    next_index = 0
    completed_candidates = 0
    budget_hit = False
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
    futures: dict[concurrent.futures.Future[tuple[Path | None, dict[str, Any] | None, str | None]], Path] = {}

    def submit_until_full() -> None:
        nonlocal next_index
        while (
            len(futures) < workers
            and next_index < len(ordered_candidates)
            and time.monotonic() < deadline
        ):
            candidate = ordered_candidates[next_index]
            next_index += 1
            future = executor.submit(
                collect_repository,
                candidate,
                start,
                end,
                max_commits=max_commits_per_repository,
                include_untracked=path_key(candidate) in priority_roots,
                deadline_monotonic=deadline,
            )
            futures[future] = candidate

    submit_until_full()
    try:
        while futures:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                budget_hit = True
                break
            done, _ = concurrent.futures.wait(
                futures,
                timeout=remaining,
                return_when=concurrent.futures.FIRST_COMPLETED,
            )
            if not done:
                budget_hit = True
                break
            for future in done:
                futures.pop(future, None)
                completed_candidates += 1
                try:
                    root, evidence, error = future.result()
                except Exception:
                    failures += 1
                    continue
                if root is not None:
                    verified_roots.add(path_key(root))
                if error:
                    failures += 1
                if evidence:
                    key = path_key(root) if root is not None else path_key(Path(evidence["path"]))
                    previous = active_by_root.get(key)
                    if (
                        previous is None
                        or evidence["working_tree"]["status_count"]
                        > previous["working_tree"]["status_count"]
                    ):
                        active_by_root[key] = evidence
            submit_until_full()
        if next_index < len(ordered_candidates) or futures:
            budget_hit = True
    finally:
        for future in futures:
            future.cancel()
        executor.shutdown(wait=True, cancel_futures=True)

    active = list(active_by_root.values())
    active.sort(
        key=lambda item: max(
            [commit["committed_at"] for commit in item["commits"]] or [""],
        ),
        reverse=True,
    )
    active_repositories_found = len(active)
    active = active[:max_active_repositories]
    active_repositories_truncated = active_repositories_found > len(active)
    total_commits_found = sum(len(item["commits"]) for item in active)
    remaining = max_total_commits
    for item in active:
        commits = item["commits"]
        if len(commits) > remaining:
            item["commits"] = commits[-max(remaining, 0) :] if remaining > 0 else []
            item["commits_truncated"] = True
        remaining -= len(item["commits"])
        remaining = max(remaining, 0)

    return {
        "status": "ok" if not failures and not budget_hit else "partial",
        "repository_candidates": len(candidates),
        "repositories_considered": completed_candidates,
        "repositories_skipped_or_incomplete": max(len(candidates) - completed_candidates, 0),
        "git_elapsed_seconds": round(time.monotonic() - started, 3),
        "git_time_budget_hit": budget_hit,
        "repositories_verified": len(verified_roots),
        "active_repositories": active,
        "active_repositories_found": active_repositories_found,
        "active_repositories_truncated": active_repositories_truncated,
        "total_commits_found_in_returned_repositories": total_commits_found,
        "total_commits_truncated": total_commits_found > max_total_commits,
        "inactive_repositories_omitted": max(len(verified_roots) - active_repositories_found, 0),
        "repository_failures": failures,
    }


def read_linked_vercel_projects(roots: set[Path]) -> dict[str, str]:
    projects: dict[str, str] = {}
    for root in roots:
        path = root / ".vercel" / "project.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        project_name = data.get("projectName")
        if isinstance(project_name, str) and project_name:
            projects[project_name] = root.name
    return projects


def run_external(command: list[str], *, timeout_seconds: float) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.update({"NO_COLOR": "1", "VERCEL_TELEMETRY_DISABLED": "1"})
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
        check=False,
        env=environment,
    )


def vercel_prefix() -> list[str] | None:
    command = shutil.which("vercel")
    if command:
        return [command]
    return None


def collect_vercel_activity(
    linked_projects: dict[str, str],
    start: datetime,
    end: datetime,
    *,
    timeout_seconds: float,
) -> dict[str, Any]:
    if not linked_projects:
        return {
            "status": "not_configured",
            "reason": "No locally linked Vercel projects were discovered.",
        }
    prefix = vercel_prefix()
    if prefix is None:
        return {"status": "unavailable", "reason": "Vercel CLI is not available"}
    try:
        identity = run_external([*prefix, "whoami"], timeout_seconds=timeout_seconds)
        if identity.returncode != 0:
            return {"status": "unavailable", "reason": "Persisted Vercel authentication is unavailable"}
        listing = run_external(
            [
                *prefix,
                "list",
                "--all",
                "--format",
                "json",
                "--limit",
                "100",
                "--non-interactive",
            ],
            timeout_seconds=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return {"status": "partial", "reason": "Vercel read timed out"}
    if listing.returncode != 0:
        return {"status": "partial", "reason": "Vercel deployment listing failed"}
    try:
        payload = json.loads(listing.stdout)
    except json.JSONDecodeError:
        return {"status": "partial", "reason": "Vercel returned unreadable JSON"}

    deployments = payload.get("deployments", []) if isinstance(payload, dict) else []
    pagination = payload.get("pagination", {}) if isinstance(payload, dict) else {}
    pagination_truncated = bool(
        isinstance(pagination, dict)
        and any(pagination.get(key) for key in ("next", "nextPage", "nextCursor"))
    )
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    evidence: list[dict[str, Any]] = []
    unlinked_count = 0
    for deployment in deployments:
        if not isinstance(deployment, dict):
            continue
        created_at = deployment.get("createdAt")
        if not isinstance(created_at, (int, float)) or not start_ms <= created_at < end_ms:
            continue
        project_name = deployment.get("name")
        if not isinstance(project_name, str) or project_name not in linked_projects:
            unlinked_count += 1
            continue
        evidence.append(
            {
                "workspace": linked_projects[project_name],
                "project": project_name,
                "created_at": datetime.fromtimestamp(created_at / 1000, start.tzinfo).isoformat(timespec="seconds"),
                "state": deployment.get("state"),
                "target": deployment.get("target"),
                "public_safe": False,
            }
        )
    return {
        "status": "partial" if pagination_truncated else "ok",
        "linked_projects_considered": len(linked_projects),
        "deployments": evidence,
        "unlinked_deployments_aggregated": unlinked_count,
        "pagination_truncated": pagination_truncated,
        "note": "READY proves a deployment completed; verify a public URL before claiming it is live.",
    }


def github_capability() -> dict[str, Any]:
    command = shutil.which("gh")
    if not command:
        return {
            "status": "unavailable",
            "reason": "GitHub CLI is not installed; use a connected GitHub app when available.",
        }
    try:
        status = run_external([command, "auth", "status"], timeout_seconds=5)
    except subprocess.TimeoutExpired:
        return {"status": "unavailable", "reason": "GitHub CLI auth check timed out"}
    if status.returncode != 0:
        return {"status": "unavailable", "reason": "GitHub CLI is not authenticated"}
    return {
        "status": "available",
        "note": "Use read-only GitHub queries for today's PR, review, release, and CI activity.",
    }


def common_scan_roots(cwd_seeds: list[Path]) -> list[Path]:
    home = Path.home()
    candidates = [
        Path.cwd(),
        *cwd_seeds,
        home / "Desktop",
        home / "Documents",
        home / "Downloads",
        home / "Videos",
        home / "Projects",
        home / "repos",
        home / "source",
        *fixed_drive_roots(),
    ]
    return [path for path in unique_existing_paths(candidates) if is_fixed_local_path(path)]


def normalize_explicit_repositories(values: list[str]) -> list[Path]:
    normalized: list[Path] = []
    for raw in values:
        candidate = Path(raw)
        if not candidate.exists() or not candidate.is_dir():
            raise ValueError("every --repo value must name an existing directory")
        try:
            normalized.append(repo_collector.resolve_root(str(candidate)))
        except repo_collector.GitError as exc:
            raise ValueError("every --repo value must be inside a Git repository") from exc
    return unique_existing_paths(normalized)


def normalize_scan_roots(values: list[str]) -> list[Path]:
    roots: list[Path] = []
    for raw in values:
        candidate = Path(raw)
        if not candidate.exists() or not candidate.is_dir():
            raise ValueError("every --scan-root value must name an existing directory")
        roots.append(candidate)
    return unique_existing_paths(roots)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect privacy-filtered daily work evidence across this machine."
    )
    parser.add_argument("--date", help="Calendar date in YYYY-MM-DD format.")
    parser.add_argument("--timezone", help="IANA timezone, for example America/Los_Angeles.")
    parser.add_argument(
        "--repo",
        action="append",
        default=[],
        help="Restrict collection to this repository; repeat for multiple repositories.",
    )
    parser.add_argument(
        "--scan-root",
        action="append",
        default=[],
        help="Override machine discovery roots; useful for testing.",
    )
    parser.add_argument("--max-scan-seconds", type=float, default=DEFAULT_SCAN_SECONDS)
    parser.add_argument("--max-directories", type=int, default=DEFAULT_MAX_DIRECTORIES)
    parser.add_argument("--max-repositories", type=int, default=DEFAULT_MAX_REPOSITORIES)
    parser.add_argument(
        "--max-commits-per-repo",
        type=int,
        default=DEFAULT_MAX_COMMITS_PER_REPOSITORY,
    )
    parser.add_argument("--max-total-commits", type=int, default=DEFAULT_MAX_TOTAL_COMMITS)
    parser.add_argument(
        "--max-active-repositories",
        type=int,
        default=DEFAULT_MAX_ACTIVE_REPOSITORIES,
    )
    parser.add_argument("--git-workers", type=int, default=DEFAULT_GIT_WORKERS)
    parser.add_argument("--max-git-seconds", type=float, default=DEFAULT_MAX_GIT_SECONDS)
    parser.add_argument("--cache-hours", type=float, default=24.0)
    parser.add_argument("--refresh", action="store_true", help="Refresh the machine repository index.")
    parser.add_argument("--no-cache", action="store_true", help="Do not read or write the private index cache.")
    parser.add_argument("--no-codex", action="store_true", help="Skip Codex task-completion summaries.")
    parser.add_argument("--no-vercel", action="store_true", help="Skip read-only Vercel deployment lookup.")
    parser.add_argument("--network-timeout", type=float, default=20.0)
    parser.add_argument("--compact", action="store_true", help="Emit compact JSON.")
    args = parser.parse_args()
    positive_fields = (
        "max_scan_seconds",
        "max_directories",
        "max_repositories",
        "max_commits_per_repo",
        "max_total_commits",
        "max_active_repositories",
        "git_workers",
        "max_git_seconds",
        "cache_hours",
        "network_timeout",
    )
    for field_name in positive_fields:
        if getattr(args, field_name) <= 0:
            parser.error(f"--{field_name.replace('_', '-')} must be positive")
    return args


def serialized_payload_size(payload: dict[str, Any]) -> int:
    return len(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))


def enforce_output_limit(payload: dict[str, Any]) -> dict[str, Any]:
    scope = payload["scope"]
    git = payload["sources"]["git"]
    codex = payload["sources"]["codex"]
    active = git.get("active_repositories", [])
    summaries = codex.get("task_complete_summaries", []) if isinstance(codex, dict) else []
    if isinstance(codex, dict) and isinstance(summaries, list):
        codex["task_complete_summaries_found"] = len(summaries)

    scope.update(
        {
            "output_limit_bytes": MAX_OUTPUT_BYTES,
            "output_truncated": False,
            "output_repositories_omitted": 0,
            "output_codex_summaries_omitted": 0,
            "output_bytes": 0,
        }
    )
    target = MAX_OUTPUT_BYTES - 4_096
    original_repositories = len(active) if isinstance(active, list) else 0
    original_summaries = len(summaries) if isinstance(summaries, list) else 0

    while serialized_payload_size(payload) > target and isinstance(active, list) and active:
        active.pop()
        scope["output_truncated"] = True
    while serialized_payload_size(payload) > target and isinstance(summaries, list) and summaries:
        summaries.pop()
        scope["output_truncated"] = True

    scope["output_repositories_omitted"] = original_repositories - len(active)
    scope["output_codex_summaries_omitted"] = original_summaries - len(summaries)
    if scope["output_repositories_omitted"]:
        git["active_repositories_truncated"] = True
    if scope["output_codex_summaries_omitted"] and isinstance(codex, dict):
        codex["output_truncated"] = True

    if serialized_payload_size(payload) > target:
        git["active_repositories"] = []
        if isinstance(codex, dict) and "task_complete_summaries" in codex:
            codex["task_complete_summaries"] = []
        scope["output_truncated"] = True
        scope["output_reduced_to_summary_only"] = True

    scope["output_bytes"] = serialized_payload_size(payload)
    if serialized_payload_size(payload) > MAX_OUTPUT_BYTES:
        source_statuses: dict[str, dict[str, Any]] = {}
        for source_name, source in payload.get("sources", {}).items():
            status = source.get("status", "unknown") if isinstance(source, dict) else "unknown"
            source_statuses[str(source_name)[:40]] = {
                "status": str(status)[:80],
                "details_omitted_for_output_limit": True,
            }
        raw_limits = scope.get("limits_hit", [])
        safe_limits = (
            [str(value)[:80] for value in raw_limits[:20]]
            if isinstance(raw_limits, list)
            else []
        )
        minimal = {
            "date": str(payload.get("date", ""))[:40],
            "timezone": str(payload.get("timezone", ""))[:80],
            "scope": {
                "mode": str(scope.get("mode", "unknown"))[:40],
                "scan_complete": bool(scope.get("scan_complete", False)),
                "limits_hit": safe_limits,
                "output_limit_bytes": MAX_OUTPUT_BYTES,
                "output_truncated": True,
                "output_reduced_to_summary_only": True,
                "output_bytes": 0,
            },
            "sources": source_statuses,
            "privacy": {
                "public_copy_requires_redaction": True,
                "source_details_omitted_for_output_limit": True,
            },
            "notes": [
                "Source details exceeded the output budget and were omitted.",
                "Inspect a narrower explicit repository scope before drafting.",
            ],
        }
        minimal["scope"]["output_bytes"] = serialized_payload_size(minimal)
        return minimal
    return payload


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    zone, zone_name = load_timezone(args.timezone)
    requested_day = parse_day(args.date, zone)
    start, end = day_bounds(requested_day, zone)

    explicit_paths = normalize_explicit_repositories(args.repo)
    scan_override_paths = normalize_scan_roots(args.scan_root)
    if args.repo:
        codex_allowed_roots = explicit_paths
    elif args.scan_root:
        codex_allowed_roots = scan_override_paths
    else:
        codex_allowed_roots = None
    codex, cwd_seeds = (
        ({"status": "skipped"}, [])
        if args.no_codex
        else collect_codex_activity(
            start,
            end,
            zone,
            allowed_roots=codex_allowed_roots,
        )
    )
    if args.repo:
        priority_paths = explicit_paths
    elif args.scan_root:
        priority_paths = []
    else:
        priority_paths = [
            path
            for path in unique_existing_paths([Path.cwd(), *cwd_seeds])
            if is_fixed_local_path(path)
        ]
    priority_keys = {path_key(path) for path in priority_paths}

    discovery = DiscoveryResult()
    cache = None if args.no_cache else load_cache(cache_path())
    repositories = cached_paths(cache, "repositories")
    vercel_roots = cached_paths(cache, "vercel_roots")
    if args.refresh:
        repositories = set()
        vercel_roots = set()
    cache_used = cache_usable(cache, args.cache_hours, refresh=args.refresh)

    if args.repo:
        repositories = set(explicit_paths)
        vercel_roots = {
            path
            for path in explicit_paths
            if (path / ".vercel" / "project.json").is_file()
        }
        cache_used = False
    else:
        if args.scan_root:
            repositories = set()
            vercel_roots = set()
            cache_used = False
        if not cache_used:
            scan_roots = (
                scan_override_paths
                if args.scan_root
                else common_scan_roots(cwd_seeds)
            )
            discovery = discover_machine(
                scan_roots,
                start.timestamp(),
                end.timestamp(),
                max_seconds=args.max_scan_seconds,
                max_directories=args.max_directories,
                max_repositories=args.max_repositories,
            )
            if discovery.complete:
                repositories = set(discovery.repositories)
                vercel_roots = set(discovery.vercel_roots)
            else:
                repositories.update(discovery.repositories)
                vercel_roots.update(discovery.vercel_roots)
            if not args.no_cache and not args.scan_root:
                discovery.repositories = repositories
                discovery.vercel_roots = vercel_roots
                try:
                    write_cache(cache_path(), discovery)
                except OSError:
                    discovery.limits_hit.append("cache_write_failed")

    repositories.update(priority_paths)
    git = collect_repositories(
        repositories,
        priority_keys,
        start,
        end,
        max_commits_per_repository=args.max_commits_per_repo,
        max_total_commits=args.max_total_commits,
        max_active_repositories=args.max_active_repositories,
        workers=args.git_workers,
        max_seconds=args.max_git_seconds,
    )

    linked_projects = read_linked_vercel_projects(vercel_roots)
    vercel = (
        {"status": "skipped"}
        if args.no_vercel
        else collect_vercel_activity(
            linked_projects,
            start,
            end,
            timeout_seconds=args.network_timeout,
        )
    )

    scan_complete = bool(cache.get("scan_complete")) if cache_used and cache else discovery.complete
    denied_or_unreadable = (
        int(cache.get("denied_or_unreadable", 0))
        if cache_used and cache
        else discovery.denied_or_unreadable
    )
    indexed_directories = (
        int(cache.get("directories_scanned", 0))
        if cache_used and cache
        else discovery.directories_scanned
    )
    limits_hit = (
        list(cache.get("limits_hit", []))
        if cache_used and cache and isinstance(cache.get("limits_hit", []), list)
        else list(discovery.limits_hit)
    )
    if git["git_time_budget_hit"]:
        limits_hit.append("git_time_budget")
    payload = {
        "date": requested_day.isoformat(),
        "timezone": zone_name,
        "scope": {
            "mode": "explicit_repositories" if args.repo else "machine",
            "cache_used": cache_used,
            "scan_complete": scan_complete,
            "directories_scanned_this_run": discovery.directories_scanned,
            "directories_scanned_when_indexed": indexed_directories,
            "denied_or_unreadable_directories": denied_or_unreadable,
            "scan_elapsed_seconds": discovery.elapsed_seconds,
            "limits_hit": limits_hit,
            "modified_file_metadata_signals": dict(discovery.modified_file_categories),
            "modified_file_signal_strength": "weak; filenames and contents were not collected",
        },
        "sources": {
            "git": git,
            "codex": codex,
            "vercel": vercel,
            "github": github_capability(),
        },
        "privacy": {
            "arbitrary_file_contents_read": False,
            "credential_values_intentionally_collected": False,
            "raw_git_metadata_may_contain_sensitive_text": True,
            "public_copy_requires_redaction": True,
            "external_clis_may_consult_persisted_auth": True,
            "browser_mail_and_calendar_read": False,
            "codex_rollout_tail_read": not args.no_codex,
            "only_codex_task_complete_summaries_retained": not args.no_codex,
            "full_codex_transcripts_retained": False,
            "repository_paths_are_local_only": True,
            "fields_prohibited_in_public_copy": [
                "repository paths",
                "private repository or workspace names",
                "raw filenames",
                "commit subjects and branch names",
                "Git status and diff-stat entries",
                "Codex summaries",
                "linked project names",
            ],
        },
        "notes": [
            "Attribute a commit without confirmation only when authorship is verified_configured_email.",
            "Use verified deployment evidence for deployment claims.",
            "Treat dirty Git state, file modification counts, and Codex summaries as clues until verified.",
            "Never copy local paths, private repository names, course details, or unannounced work into a post.",
        ],
    }
    return enforce_output_limit(payload)


def main() -> int:
    configure_stdout()
    args = parse_args()
    try:
        payload = build_payload(args)
    except (OSError, ValueError, repo_collector.GitError) as exc:
        print(f"daily-work-tweet machine collector: {exc}", file=sys.stderr)
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
