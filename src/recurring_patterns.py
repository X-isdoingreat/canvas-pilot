# SPDX-License-Identifier: AGPL-3.0-or-later
"""Detect recurring assignment-name patterns in a Canvas course.

Used by canvas-bootstrap to surface the "things that repeat every week" so the
student knows what's worth automating with a per-course skill. The algorithm
is deliberately simple: normalize numbers in assignment names, bucket by
(normalized_name, submission_types), and keep the buckets that occur >= 3 times.

No classifier, no recommendation — just facts.

Also exposes `is_course_active()` so bootstrap can drop courses whose term has
already ended — students never want to install a skill on last quarter's course.
"""
from __future__ import annotations

import datetime as dt
import re
from collections import defaultdict
from typing import NamedTuple


class Pattern(NamedTuple):
    """One recurring assignment shape detected in a course."""
    norm_name: str
    submission_types: tuple[str, ...]
    count: int
    examples: tuple[str, ...]
    # Local-only identifiers let Opportunity fetch representative real specs
    # without reconstructing IDs from assignment titles.  The safe projection
    # layer still controls what may be written to reports or chat.
    assignment_ids: tuple[str, ...] = ()


def normalize(name: str) -> str:
    """Replace bare digits and Roman numerals with <N>, collapse <N> ranges."""
    s = re.sub(r'\d+', '<N>', name)
    s = re.sub(r'\b[IVX]{2,}\b', '<N>', s)
    s = re.sub(r'<N>(\s*[-–to,]+\s*<N>)+', '<N>', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def bucket_recurring(
    items: list[dict],
    min_freq: int = 3,
) -> tuple[list[Pattern], int]:
    """Group assignments into patterns and split by frequency threshold.

    Returns (patterns, sub_threshold_count):
      - patterns: clusters with count >= min_freq, sorted by count descending
      - sub_threshold_count: total assignments in clusters below the threshold
        (the "+ N one-off / sub-threshold assignments" tail)
    """
    buckets: dict[
        tuple[str, tuple[str, ...]], list[tuple[str, str | None]]
    ] = defaultdict(list)
    for a in items:
        name = a.get("name", "") or ""
        st = tuple(a.get("submission_types") or [])
        raw_id = a.get("id")
        assignment_id = str(raw_id) if raw_id not in (None, "") else None
        buckets[(normalize(name), st)].append((name, assignment_id))

    patterns: list[Pattern] = []
    sub_threshold = 0
    for (norm, st), members in buckets.items():
        if len(members) >= min_freq:
            patterns.append(Pattern(
                norm_name=norm,
                submission_types=st,
                count=len(members),
                examples=tuple(name for name, _ in members[:3]),
                assignment_ids=tuple(
                    assignment_id
                    for _, assignment_id in members
                    if assignment_id is not None
                ),
            ))
        else:
            sub_threshold += len(members)

    patterns.sort(key=lambda p: -p.count)
    return patterns, sub_threshold


def is_course_active(course: dict, grace_days: int = 7, now: dt.datetime | None = None) -> bool:
    """Has the course's term ended (with a grace window)?

    Returns True if the course's latest known end date is at or after `now - grace_days`.
    A course with no end date (perpetual orientation spaces, etc.) is treated as active.

    Looks at both `course.end_at` and `course.term.end_at`, takes the LATEST (most
    permissive) — Canvas sometimes sets one but not the other, and a course can
    legitimately extend past its term's nominal end.

    Bootstrap uses this to drop last-quarter courses that the student no longer
    wants to install a skill on.
    """
    if now is None:
        now = dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(days=grace_days)

    candidates: list[str] = []
    if course.get("end_at"):
        candidates.append(course["end_at"])
    term = course.get("term") or {}
    if term.get("end_at"):
        candidates.append(term["end_at"])

    if not candidates:
        return True  # no end date known — treat as active (e.g. perpetual spaces)

    latest = max(
        dt.datetime.fromisoformat(c.replace("Z", "+00:00"))
        for c in candidates
    )
    return latest >= cutoff


# Positive-signal heuristic for "this looks like a real coursework course".
# Used by canvas-bootstrap §2 Layer 4 to rescue real courses with 0 recurring
# patterns out of the fold (e.g. seminars where each week's assignment is unique,
# or week 1-2 of a real course before patterns have accumulated).
#
# Matches typical dept-code prefixes used by US universities:
#   "CS 101 Spring 2026"                    -> matches "CS 101"
#   "BIO SCI 99 LAB B: Methods"             -> matches "BIO SCI 99"
#   "MATH 2B Sect 1"                        -> matches "MATH 2B"
#   "ENGL 200 Section 1"                    -> matches "ENGL 200"
#   "PHYS 110A LEC C"                       -> matches "PHYS 110A"
# Misses (intentional - these stay folded):
#   "Academic Integrity Training Module"
#   "First-Year Online Orientation Space"
#   "Student Training Hub 2025-2026"
#   "Writing Center Drop-In Lab - Spring 2026"
#   "Placement Exam Holding Course"
#   "Intro to World Cultures Spring 2026" (no all-caps dept prefix)
_COURSE_CODE_PATTERN = re.compile(r"^[A-Z&]{2,}(\s[A-Z&]+)*\s\d+[A-Z]?\b")


def looks_like_real_course(course: dict, now: dt.datetime | None = None) -> bool:
    """Positive-signal heuristic: does this course look like real coursework
    even though it has no recurring assignment patterns?

    Two signals must BOTH hold:
      1. Name has a typical course-code prefix (`<DEPT> <number>`)
      2. Time has not passed `is_course_active`'s 7-day grace

    Deliberately uses NO noise blocklist. A keyword blocklist would misfire
    on real courses whose names happen to contain "lab", "training", "space",
    etc. (e.g. "Computer Science Lab Training", "Workspace Design Studio").
    Positive-only detection has only one failure mode: a real course missing
    the dept-code prefix stays folded — which the student can manually expand.
    That's preferable to silently mis-promoting noise into the main view.
    """
    name = course.get("name", "") or ""
    has_course_code = bool(_COURSE_CODE_PATTERN.match(name))
    time_ok = is_course_active(course, grace_days=7, now=now)
    return has_course_code and time_ok
