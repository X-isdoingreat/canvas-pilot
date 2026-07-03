# SPDX-License-Identifier: AGPL-3.0-or-later
"""Aggregate REPORT.md from skill results."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable


STATUS_ICONS = {
    "draft_ready": "OK",
    "submitted": "SUBMITTED",
    "skipped": "SKIP",
    "error": "ERROR",
}


def write_report(run_dir: Path, results: list[dict]) -> Path:
    by_status: dict[str, list[dict]] = {}
    for r in results:
        by_status.setdefault(r.get("status", "error"), []).append(r)

    lines = [f"# Canvas Run Report - {run_dir.name}", ""]
    lines.append(f"Total: {len(results)} assignments processed")
    lines.append("")

    order = ["submitted", "draft_ready", "skipped", "error"]
    for status in order:
        items = by_status.get(status, [])
        if not items:
            continue
        lines.append(f"## {STATUS_ICONS.get(status, status)} ({len(items)})")
        for r in items:
            it = r.get("item", {})
            line = f"- **{it.get('course_name','?')}** / {it.get('name','?')}"
            if it.get("due_at"):
                line += f"  (due {it['due_at']})"
            lines.append(line)
            if r.get("draft_path"):
                lines.append(f"  - draft: `{r['draft_path']}`")
            if r.get("notes"):
                lines.append(f"  - notes: {r['notes']}")
            if r.get("message"):
                lines.append(f"  - message: {r['message']}")
        lines.append("")

    out = run_dir / "REPORT.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out
