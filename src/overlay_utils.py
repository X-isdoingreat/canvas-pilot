# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared utilities for per-course skill overlays.

These helpers exist to keep deterministic computations (especially file
path resolution) consistent between write-time and read-time, across
multiple SKILL.md invocations.

The most critical helper is `cluster_filename_slug`: canvas-generic's
learnings overlay file path embeds a slug derived from a cluster
normalized name. If bootstrap-time creation and Layer 2 writeback
compute the slug differently, the writeback creates a sibling file the
next dispatch never reads and the feedback is silently lost.

Used by:
- `.claude/skills/canvas-bootstrap/SKILL.md` §4 + §7.1 (create empty
  canvas-generic learnings overlay).
- `.claude/skills/canvas-generic/SKILL.md` Stage 0 (load learnings).
- `CLAUDE.md` "Feedback writeback (permanent)" rule (write back to
  learnings overlay).
- `docs/feedback-categorization.md` (documents the slug convention).
"""

from __future__ import annotations

import re


def cluster_filename_slug(cluster_norm: str) -> str:
    """Deterministic filesystem-safe slug from a normalized cluster name.

    Input is typically the output of `src.recurring_patterns.normalize()`
    (e.g. "Tue Wk<N> HW Scan", "Project <N>", "Quiz on Section <N> reading
    and lecture"). The slug is lowercase, ASCII alphanumerics joined by
    hyphens, with `<N>` placeholders dropped.

    Examples:
        >>> cluster_filename_slug("Reading Annotation Week <N>")
        'reading-annotation-week'
        >>> cluster_filename_slug("Project <N>")
        'project'
        >>> cluster_filename_slug("Quiz on Section <N> reading and lecture")
        'quiz-on-section-reading-and-lecture'
        >>> cluster_filename_slug("")
        'cluster'
        >>> cluster_filename_slug("<N>")
        'cluster'
    """
    s = cluster_norm.lower()
    s = re.sub(r"<n>", "", s)
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "cluster"


def canvas_generic_overlay_path(course_id: int | str, cluster_norm: str) -> str:
    """Compose the canvas-generic learnings overlay path.

    Returns a project-relative path (forward slashes). Callers can pass
    this directly to pathlib.Path / Read / Write tools.

    >>> canvas_generic_overlay_path(12345, "Reading Annotation Week <N>")
    '_private/canvas-generic-12345-reading-annotation-week.md'
    """
    slug = cluster_filename_slug(cluster_norm)
    return f"_private/canvas-generic-{course_id}-{slug}.md"
