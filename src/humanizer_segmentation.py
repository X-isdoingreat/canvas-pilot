"""Shared sentence-segmentation primitives for humanizer pipeline.

Extracted from .claude/skills/canvas-humanizer/SKILL.md §5a so canvas-humanizer
and canvas-humanizer-loop use bit-identical splitter behavior — load-bearing for
canvas-humanizer-loop's structural-drift check (paragraph segment_count stable
across iterations).
"""

from __future__ import annotations

import re


_ABBREVS = [
    "Mr.", "Mrs.", "Ms.", "Dr.", "Prof.",
    "Inc.", "Ltd.", "St.", "Jr.", "Sr.",
    "vs.", "e.g.", "i.e.", "etc.", "Co.",
    "U.S.", "U.K.",
]


def split_sentences(text: str) -> list[str]:
    """Conservative sentence splitter: handles common abbreviations, decimals, ellipses.

    Behavior contract — match canvas-humanizer SKILL.md §5a exactly:
    - Protect abbreviations + numeric decimals + ellipses with NUL-byte substitution
    - Split on .!? followed by whitespace + capital letter / quote
    - Return list of trimmed non-empty sentences
    """
    protected = text
    for ab in _ABBREVS:
        protected = protected.replace(ab, ab.replace(".", "\x00"))
    protected = re.sub(r"(\d)\.(\d)", lambda m: m.group(1) + "\x00" + m.group(2), protected)
    protected = protected.replace("...", "\x00\x00\x00")
    parts = re.split(r'(?<=[.!?])\s+(?=[A-Z"\'])', protected)
    parts = [p.replace("\x00\x00\x00", "...").replace("\x00", ".") for p in parts]
    return [p.strip() for p in parts if p.strip()]


def segment_paragraph(paragraph_text: str, doc_paragraph_index: int) -> list[dict]:
    """Split a paragraph into per-sentence metadata records.

    Returns a list of dicts with the §5b schema fields canvas-humanizer-loop
    needs for canonical (doc_paragraph_index, intra_para_index) tuple ID.
    """
    sentences = split_sentences(paragraph_text)
    out = []
    for i, sent in enumerate(sentences):
        out.append({
            "doc_paragraph_index": doc_paragraph_index,
            "intra_para_index": i,
            "text": sent,
            "word_count": len(re.findall(r"[\w'-]+", sent)),
        })
    return out


def paragraph_segment_counts(paragraphs: list[str]) -> dict[int, int]:
    """Return {doc_paragraph_index: segment_count} — used by the loop's
    structural-drift check across iterations."""
    return {i: len(split_sentences(p)) for i, p in enumerate(paragraphs)}
