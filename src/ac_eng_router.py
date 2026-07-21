# SPDX-License-Identifier: AGPL-3.0-or-later
"""Deterministic 6-layer cascade for routing writing-course assignments to
either canvas-reading-annotation (short) or canvas-essay (long).

0 LLM calls. Pure regex + numeric comparison + dict queries. Unit-testable.

Cascade (short-circuit on first match):
    L1  plan.json manual override (ac_eng_force_essay: true/false)
    L2  overlay-declared regex lists (skip wins over trigger)
    L3  word count >= 500 anywhere in description or attached PDF text
    L4  points_possible >= 25 AND 'online_upload' in submission_types
    L5  name keyword regex: essay/paper/reflection/autoethnography/narrative/memoir
        AND NOT annotation/reading/quiz/daily/response/discussion
    L6  default "short"

Caller is responsible for pre-extracting PDF text into
assignment["attached_pdf_texts"] if Layer 3 should see PDF contents.
"""
from __future__ import annotations

import re
from typing import Any


_DEFAULT_ESSAY_NAME_KEYWORDS = re.compile(
    r"\b(essay|paper|reflection|autoethnography|narrative|memoir)\b",
    re.IGNORECASE,
)
_DEFAULT_NON_ESSAY_NAME_KEYWORDS = re.compile(
    r"\b(annotation|reading|quiz|daily|response|discussion)\b",
    re.IGNORECASE,
)
_WORD_COUNT_RE = re.compile(
    r"\b(\d{3,5})\s*(?:words?|word\s*count|字)\b",
    re.IGNORECASE,
)
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(s: str) -> str:
    return _HTML_TAG_RE.sub(" ", s or "")


def _max_word_count(text_blob: str) -> int:
    if not text_blob:
        return 0
    nums = [int(n) for n in _WORD_COUNT_RE.findall(text_blob)]
    return max(nums) if nums else 0


def _matches_any(patterns: list[str] | None, text: str) -> bool:
    if not text or not patterns:
        return False
    for p in patterns:
        try:
            if re.search(p, text, re.IGNORECASE):
                return True
        except re.error:
            continue
    return False


def route_ac_eng_assignment(
    assignment: dict[str, Any],
    overlay_config: dict[str, Any] | None = None,
    plan_item: dict[str, Any] | None = None,
) -> str:
    """Returns "essay" or "short". See module docstring for cascade."""
    overlay_config = overlay_config or {}

    if plan_item is not None:
        force = plan_item.get("ac_eng_force_essay")
        if force is True:
            return "essay"
        if force is False:
            return "short"

    name = assignment.get("name") or ""

    skip_pat = overlay_config.get("persona_skip_patterns") or []
    trig_pat = overlay_config.get("persona_trigger_patterns") or []
    if _matches_any(skip_pat, name):
        return "short"
    if _matches_any(trig_pat, name):
        return "essay"

    desc = _strip_html(assignment.get("description") or "")
    pdf_texts = assignment.get("attached_pdf_texts") or []
    text_blob = desc + "\n" + "\n".join(pdf_texts)
    if _max_word_count(text_blob) >= 500:
        return "essay"

    points = assignment.get("points_possible") or 0
    submission_types = assignment.get("submission_types") or []
    if (
        isinstance(points, (int, float))
        and points >= 25
        and "online_upload" in submission_types
    ):
        return "essay"

    if (
        _DEFAULT_ESSAY_NAME_KEYWORDS.search(name)
        and not _DEFAULT_NON_ESSAY_NAME_KEYWORDS.search(name)
    ):
        return "essay"

    return "short"
