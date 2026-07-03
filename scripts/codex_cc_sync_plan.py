# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = ROOT / "runs" / "codex" / "cc_sync_baseline.json"

WATCH_PATHS = [
    ".claude/settings.json",
    ".claude/hooks",
    ".claude/skills",
    ".claude/agents",
]

IGNORE_PARTS = {"__pycache__", ".pytest_cache"}
IGNORE_SUFFIXES = {".pyc", ".pyo"}
IGNORE_NAMES = {"hook-errors.log"}

PRIVATE_RE = re.compile(
    r"[\w.\-+]+@[\w.\-]+\.edu\b|"
    r"\bcourse_id\s*[:=]\s*\d{4,}\b|"
    r"\bassignment_id\s*[:=]\s*\d{4,}\b",
    re.IGNORECASE,
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def iter_files() -> list[Path]:
    files: list[Path] = []
    for item in WATCH_PATHS:
        path = ROOT / item
        if path.is_file():
            if should_watch(path):
                files.append(path)
        elif path.is_dir():
            files.extend(p for p in path.rglob("*") if p.is_file() and should_watch(p))
    return sorted(files, key=lambda p: rel(p).lower())


def should_watch(path: Path) -> bool:
    if any(part in IGNORE_PARTS for part in path.parts):
        return False
    if path.suffix in IGNORE_SUFFIXES:
        return False
    if path.name in IGNORE_NAMES:
        return False
    return True


def frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    _, _, rest = text.partition("\n")
    block, sep, _ = rest.partition("\n---")
    if not sep:
        return {}
    data: dict[str, str] = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if key in {"name", "description"}:
            data[key] = value.strip()
    return data


def kind_for(path: str) -> str:
    if path == ".claude/settings.json":
        return "settings"
    if path.startswith(".claude/hooks/"):
        return "hook"
    if path.startswith(".claude/agents/"):
        return "agent"
    if path.startswith(".claude/skills/canvas-scan/"):
        return "canvas-scan"
    if path.startswith(".claude/skills/canvas-execute/"):
        return "canvas-execute"
    if path.startswith(".claude/skills/canvas-bootstrap/"):
        return "canvas-bootstrap"
    if path.startswith(".claude/skills/canvas-skip/"):
        return "canvas-skip"
    if path.startswith(".claude/skills/canvas-"):
        return "course-skill"
    if path.startswith(".claude/skills/kiro") or path.startswith(".claude/skills/new-feature") or path.startswith(".claude/skills/validate"):
        return "kiro-skill"
    if path.startswith(".claude/skills/"):
        return "other-skill"
    return "other"


def suggested_batches(kind: str) -> list[str]:
    table = {
        "settings": ["B2", "B7"],
        "hook": ["B2", "B7"],
        "agent": ["B7"],
        "canvas-bootstrap": ["B3"],
        "canvas-scan": ["B4"],
        "canvas-execute": ["B5"],
        "canvas-skip": ["B5"],
        "course-skill": ["B8"],
        "kiro-skill": ["manual-review"],
        "other-skill": ["manual-review"],
    }
    return table.get(kind, ["manual-review"])


def sync_note(kind: str) -> str:
    notes = {
        "settings": "Review hook/plugin registration changes; update Codex hook plan only if behavior changed.",
        "hook": "Compare guard behavior; update Codex hook parity or advanced hook batch.",
        "agent": "Review reviewer/subagent behavior; map public-safe parts to Codex reviewer plan.",
        "canvas-bootstrap": "Update Codex bootstrap batch requirements and .agents bootstrap skill.",
        "canvas-scan": "Update Codex scan behavior, fixtures, and scan acceptance checks.",
        "canvas-execute": "Update Codex execute behavior, fixtures, report, ledger, and approval checks.",
        "canvas-skip": "Update conservative skip behavior and execute fallback checks.",
        "course-skill": "Do not copy private playbook. Extract only public framework patterns into bootstrap/onboarding docs.",
        "kiro-skill": "Keep separate from Canvas Pilot unless the user asks to sync Kiro workflow into Codex.",
        "other-skill": "Manual review required before adding a Codex batch.",
    }
    return notes.get(kind, "Manual review required.")


def snapshot() -> dict[str, Any]:
    items: dict[str, Any] = {}
    for path in iter_files():
        path_rel = rel(path)
        text = path.read_text(encoding="utf-8", errors="ignore")
        items[path_rel] = {
            "sha256": sha256(path),
            "size": path.stat().st_size,
            "kind": kind_for(path_rel),
            "frontmatter": frontmatter(text),
            "private_marker_seen": bool(PRIVATE_RE.search(text)),
        }
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "items": items,
    }


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def diff(old: dict[str, Any] | None, new: dict[str, Any]) -> dict[str, list[str]]:
    old_items = (old or {}).get("items", {})
    new_items = new.get("items", {})
    old_keys = set(old_items)
    new_keys = set(new_items)
    added = sorted(new_keys - old_keys)
    removed = sorted(old_keys - new_keys)
    modified = sorted(
        key for key in old_keys & new_keys
        if old_items[key].get("sha256") != new_items[key].get("sha256")
    )
    return {"added": added, "modified": modified, "removed": removed}


def render_report(changes: dict[str, list[str]], new: dict[str, Any], baseline_path: Path) -> str:
    today = dt.date.today().isoformat()
    lines: list[str] = [
        "# CC -> Codex Sync Plan",
        "",
        f"Date: {today}",
        f"Baseline: `{baseline_path.relative_to(ROOT).as_posix()}`",
        "",
        "## Summary",
        "",
    ]
    total = sum(len(v) for v in changes.values())
    lines.append(f"- Changed files: {total}")
    for group in ["added", "modified", "removed"]:
        lines.append(f"- {group}: {len(changes[group])}")
    lines.extend(["", "## Changes", ""])

    if total == 0:
        lines.append("No Claude Code driver changes detected against the current baseline.")
    for group in ["added", "modified", "removed"]:
        if not changes[group]:
            continue
        lines.append(f"### {group.title()}")
        lines.append("")
        for path in changes[group]:
            meta = new.get("items", {}).get(path, {})
            kind = meta.get("kind") or kind_for(path)
            batches = ", ".join(suggested_batches(kind))
            private = "yes" if meta.get("private_marker_seen") else "no"
            lines.append(f"- `{path}`")
            lines.append(f"  - kind: `{kind}`")
            lines.append(f"  - suggested Codex batch: {batches}")
            lines.append(f"  - private marker seen: {private}")
            lines.append(f"  - note: {sync_note(kind)}")
        lines.append("")

    lines.extend([
        "## Recommended Plan",
        "",
        "1. Update `docs/CANVAS_PILOT_CLAUDE_FUNCTIONS.md` if the CC public behavior changed.",
        "2. Update `docs/CODEX_PARITY_MATRIX.md` only for public-safe behavior changes.",
        "3. Add or adjust the next Codex batch in `docs/CODEX_BATCHES.md` if the change is not already covered.",
        "4. Run the relevant `python scripts\\codex_check.py --batch <BATCH>` command.",
        "5. After the Codex side is synchronized and verified, run this script with `--update-baseline`.",
        "",
        "## Safety Rules",
        "",
        "- Do not copy private course playbooks from `.claude/skills/canvas-*` into Codex.",
        "- Do not write real course IDs, assignment IDs, instructor names, emails, or private URLs into Codex docs.",
        "- Treat `.claude/` as read-only during this sync pass.",
        "- Prefer adding a Codex batch over making direct untracked parity edits.",
    ])
    return "\n".join(lines) + "\n"


def write_report(text: str) -> Path:
    out_dir = ROOT / "runs" / "codex" / dt.date.today().isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "CC_SYNC_PLAN.md"
    path.write_text(text, encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a CC-to-Codex sync plan without editing .claude.")
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE), help="ignored local baseline JSON path")
    parser.add_argument("--update-baseline", action="store_true", help="save current CC snapshot as the new baseline")
    parser.add_argument("--fail-on-changes", action="store_true", help="exit 1 when changes are detected")
    args = parser.parse_args()

    baseline_path = Path(args.baseline)
    if not baseline_path.is_absolute():
        baseline_path = ROOT / baseline_path
    current = snapshot()
    previous = load_json(baseline_path)
    changes = diff(previous, current)
    report = render_report(changes, current, baseline_path)
    report_path = write_report(report)

    if args.update_baseline:
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")

    total = sum(len(v) for v in changes.values())
    print(f"Wrote {report_path.relative_to(ROOT).as_posix()}")
    print(f"Changed files: {total}")
    if args.update_baseline:
        print(f"Updated {baseline_path.relative_to(ROOT).as_posix()}")
    if args.fail_on_changes and total:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
