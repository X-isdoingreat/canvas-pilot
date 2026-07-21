# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import re
import os
from pathlib import Path

from _lib import (
    ROOT,
    allowed_patterns,
    block_post,
    changed_files,
    contains_private_marker,
    current_batch,
    matches_result_json,
    path_allowed,
    read_event,
    safe_main,
    spec_grounding_issue,
    identifier_grounding_issue,
    source_manifest_issue,
    validate_result_schema,
)


def referenced_result_paths(event: dict) -> list[Path]:
    tool_input = event.get("tool_input") or {}
    candidates: list[str] = []
    for key in ("file_path", "path"):
        if isinstance(tool_input.get(key), str):
            candidates.append(tool_input[key])
    command = str(tool_input.get("command") or "")
    candidates.extend(re.findall(r"runs[/\\][^\s\"']*result\.json", command))

    out: list[Path] = []
    for item in candidates:
        if matches_result_json(item):
            p = Path(item)
            if not p.is_absolute():
                p = ROOT / p
            out.append(p)
    return out


def referenced_paths(event: dict) -> list[Path]:
    tool_input = event.get("tool_input") or {}
    candidates: list[str] = []
    if isinstance(tool_input, dict):
        for key in ("file_path", "path"):
            value = tool_input.get(key)
            if isinstance(value, str):
                candidates.append(value)
        command = str(tool_input.get("command") or "")
        candidates.extend(re.findall(r"runs[/\\][^\s\"']+", command))
    out: list[Path] = []
    for item in candidates:
        p = Path(item)
        if not p.is_absolute():
            p = ROOT / p
        out.append(p)
    return out


def runner_script_issue(path: Path) -> str | None:
    try:
        rel = path.relative_to(ROOT).as_posix()
    except ValueError:
        return None
    if not rel.startswith("runs/"):
        return None
    if path.suffix.lower() in {".py", ".sh", ".ps1", ".bat", ".js", ".ts"}:
        return f"runner script blocked under runs/: {rel}"
    return None


@safe_main
def main() -> None:
    event = read_event()

    for path in referenced_paths(event):
        issue = runner_script_issue(path)
        if issue:
            block_post(
                issue,
                "Do not create ad-hoc runner scripts under runs/**. Put reusable helpers in scripts/ or tests/.",
            )

    batch_id, status, batch_text = current_batch()
    if os.environ.get("CODEX_ENFORCE_ALLOWED_FILES") == "1" and status == "in_progress" and batch_text:
        allowed = allowed_patterns(batch_text)
        outside = [
            p for p in changed_files()
            if not path_allowed(p, allowed)
            and not p.startswith(".claude/skills/new-feature/")
            and not p.startswith(".claude/skills/validate/")
            and p not in {".gitignore", "CLAUDE.md", "Claude Code-Codex 生态.md", "architecture.html", "fingerprint_probe.py"}
        ]
        if outside:
            block_post(
                f"Batch {batch_id} changed file(s) outside allowed scope: {outside}",
                "Stay inside the current Codex batch allowed_files list.",
            )

    for path in referenced_result_paths(event):
        if not path.exists():
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeError):
            rel = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
            block_post(
                f"Invalid result.json at {rel}: unreadable/corrupt UTF-8 input",
                "Repair result.json before continuing.",
            )
        ok, err = validate_result_schema(content, work_dir=path.parent)
        if not ok:
            rel = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
            block_post(
                f"Invalid result.json schema at {rel}: {err}",
                "Every assignment needs a valid result.json before continuing.",
            )
        data = None
        try:
            import json
            data = json.loads(content)
        except Exception:
            data = None
        if isinstance(data, dict) and data.get("status") in {"draft_ready", "submitted"}:
            work_dir = path.parent
            issue = spec_grounding_issue(work_dir)
            if issue:
                block_post(issue, "Add the referenced materials under references/ before marking draft_ready.")
            issue = source_manifest_issue(work_dir, result_data=data)
            if issue:
                block_post(issue, "Load mandatory overlay section-0 sources before marking draft_ready.")
            draft_path = data.get("draft_path")
            if isinstance(draft_path, str):
                draft = Path(draft_path)
                if not draft.is_absolute():
                    draft = ROOT / draft
                issue = identifier_grounding_issue(work_dir, draft)
                if issue:
                    block_post(issue, "Ground identifiers in spec/references or rename them before marking draft_ready.")

    text = ""
    tool_input = event.get("tool_input")
    if isinstance(tool_input, dict):
        text = str(tool_input.get("command") or tool_input.get("content") or "")
    if text and contains_private_marker(text):
        block_post(
            "Codex-side edit appears to contain private identity markers.",
            "Move private identity/course data to SECRETS.md or local config.",
        )


if __name__ == "__main__":
    main()
