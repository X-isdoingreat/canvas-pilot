# SPDX-License-Identifier: AGPL-3.0-or-later
"""Deterministic artifact helpers shared by Codex course skills.

The helpers in this module deliberately stop at local artifact and run-state
management.  They never call Canvas or any third-party learning platform.
"""
from __future__ import annotations

import html
import os
import re
import uuid
from pathlib import Path
from typing import Any, Mapping

from .run_state import stable_work_dir, write_result


_HTML_TAG = re.compile(r"<[^>]+>")
_BEHAVIORAL_RULES = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"[^.!?\n]*\b(?:do\s+not\s+use|don'?t\s+use|no)\s+"
        r"(?:ai|chatgpt|gpt-?\d?|llms?|generative\s+ai|copilot)\b[^.!?\n]*[.!?]?",
        r"[^.!?\n]*\b(?:ai|chatgpt|gpt|llm)\s+(?:is|are)\s+not\s+"
        r"(?:allowed|permitted)\b[^.!?\n]*[.!?]?",
        r"[^.!?\n]*\bno\s+collaboration\b[^.!?\n]*[.!?]?",
        r"[^.!?\n]*\bindividual\s+work\s+only\b[^.!?\n]*[.!?]?",
        r"[^.!?\n]*\b(?:your|the\s+student'?s?)\s+own\s+work\b[^.!?\n]*[.!?]?",
        r"[^.!?\n]*\bno\s+(?:online\s+help|tutors?|chegg|outside\s+resources|peer\s+help)"
        r"\b[^.!?\n]*[.!?]?",
    )
)
_PLACEHOLDER = re.compile(
    r"\[(?:answer\s+needed|placeholder|todo|insert[^\]]*)\]",
    re.IGNORECASE,
)


def ensure_stable_work_dir(
    run_dir: str | Path,
    course_id: str | int,
    assignment_id: str | int,
) -> Path:
    path = stable_work_dir(run_dir, course_id, assignment_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def atomic_write_text(path: str | Path, text: str) -> Path:
    """Atomically write UTF-8 text beside its destination."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            if text and not text.endswith("\n"):
                handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def html_to_text(value: str | None) -> str:
    """Convert small Canvas HTML fragments to normalized plain text."""

    stripped = _HTML_TAG.sub(" ", value or "")
    normalized = re.sub(r"\s+", " ", html.unescape(stripped)).strip()
    return re.sub(r"\s+([,.;:!?])", r"\1", normalized)


def redact_behavioral_rules(value: str | None) -> str:
    """Remove course-policy sentences before assignment-shape analysis.

    This mirrors the existing product boundary: course skills reason from the
    deliverable specification, while user authority and platform mutations are
    enforced separately by approval and signed-receipt modules.
    """

    text = value or ""
    for pattern in _BEHAVIORAL_RULES:
        text = pattern.sub("", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def unresolved_placeholders(text: str) -> list[str]:
    return sorted(set(match.group(0) for match in _PLACEHOLDER.finditer(text)))


def write_course_result(
    work_dir: str | Path,
    *,
    status: str,
    draft_path: str | Path | None = None,
    notes: str = "",
    metadata: Mapping[str, Any] | None = None,
    reason_code: str | None = None,
) -> Path:
    """Write a canonical course ``result.json`` through ``src.run_state``."""

    work = Path(work_dir)
    payload: dict[str, Any] = {"status": status, "notes": notes}
    if draft_path is not None:
        payload["draft_path"] = str(Path(draft_path))
    if metadata is not None:
        payload["metadata"] = dict(metadata)
    if reason_code:
        payload["reason_code"] = reason_code
    return write_result(work / "result.json", payload, root=Path.cwd())
