# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pre-submit verification for the writing course's reading-annotation drafts.

Enforces the instructor's stated rubric (Wk4 HW page body, extracted 2026-04-21):
  "highlighting & margin notes in at least two colors, one for vocab ... another
   color for content. Color-code: if you highlight vocab in green, make the
   definition font green. Margin notes for content are expected for each
   paragraph. Both lines completely filled for each answer."

Returns a dict { "all_passed", "failures", "checks", "log_text" }. Callers
(canvas-reading-annotation skill §8.5) must block the draft when all_passed is False.

Not for production rendering — this file is read-only diagnostics.
"""
from __future__ import annotations

import colorsys
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import fitz


# Color scheme defined in SKILL.md §6.1 — keep in sync.
VOCAB_HIGHLIGHT = (0.55, 0.95, 0.55)
VOCAB_DEF_TEXT = (0.0, 0.45, 0.0)
CONTENT_HIGHLIGHT = (1.0, 0.72, 0.82)
CONTENT_NOTE_TEXT = (0.75, 0.10, 0.45)


def _rgb_int_to_tuple(col: int) -> tuple[float, float, float]:
    r = ((col >> 16) & 0xFF) / 255.0
    g = ((col >> 8) & 0xFF) / 255.0
    b = (col & 0xFF) / 255.0
    return (r, g, b)


def _hue_degrees(rgb: tuple[float, float, float]) -> float:
    h, _, _ = colorsys.rgb_to_hsv(*rgb)
    return h * 360.0


def _same_color_family(a: tuple[float, float, float], b: tuple[float, float, float]) -> bool:
    """Two RGBs are in the same family if (a) their values are within ±0.08
    element-wise OR (b) their HSV hue delta is ≤30° and both are colorful
    (saturation > 0.15)."""
    if all(abs(x - y) <= 0.08 for x, y in zip(a, b)):
        return True
    _, sa, _ = colorsys.rgb_to_hsv(*a)
    _, sb, _ = colorsys.rgb_to_hsv(*b)
    if sa < 0.15 or sb < 0.15:
        return False
    delta = abs(_hue_degrees(a) - _hue_degrees(b))
    delta = min(delta, 360.0 - delta)
    return delta <= 30.0


def _paragraph_count(original_pdf: Path) -> int:
    """Count numbered paragraphs in the original reading (regex on a standalone
    digit line). Readings use this exact pattern."""
    doc = fitz.open(str(original_pdf))
    text = "\n\n".join(p.get_text() for p in doc)
    doc.close()
    nums = re.findall(r"(?m)^\s*(\d{1,2})\s*\n", text)
    return len(nums)


def _find_blanks(page: fitz.Page) -> list[tuple[int, float, float]]:
    """Return (y, x_min, x_max) per underscore line, per SKILL.md §6.4."""
    by_y: dict[int, list[fitz.Rect]] = defaultdict(list)
    for r in page.search_for("_"):
        by_y[round(r.y0)].append(r)
    return sorted(
        (y, min(r.x0 for r in rs), max(r.x1 for r in rs))
        for y, rs in by_y.items()
    )


def _blue_answer_spans(page: fitz.Page) -> list[tuple[float, float, float, str]]:
    """Return (y, x0, x1, text) for every blue-ish answer span on the page.
    Blue is our student-answer color; NYT hyperlink blue (5,99,193) is filtered."""
    out: list[tuple[float, float, float, str]] = []
    d = page.get_text("dict")
    for block in d.get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                rgb = _rgb_int_to_tuple(span.get("color", 0))
                # Dark blue (answers), but not the NYT link blue (0.02,0.39,0.76)
                if rgb[2] > 0.5 and rgb[0] < 0.2 and rgb[1] < 0.4:
                    # Filter NYT link blue
                    if abs(rgb[0] - 0.02) < 0.02 and abs(rgb[1] - 0.39) < 0.05:
                        continue
                    bb = span.get("bbox", [0, 0, 0, 0])
                    text = span.get("text", "").strip()
                    if text:
                        out.append((bb[1], bb[0], bb[2], text))
    return out


def _text_spans_matching(page: fitz.Page, target_rgb: tuple[float, float, float],
                          size: float, tolerance: float = 0.1) -> list[dict]:
    """Find text spans whose color is close to target_rgb at approximately size."""
    out: list[dict] = []
    d = page.get_text("dict")
    for block in d.get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                rgb = _rgb_int_to_tuple(span.get("color", 0))
                if not all(abs(a - b) <= tolerance for a, b in zip(rgb, target_rgb)):
                    continue
                s = span.get("size", 0)
                if abs(s - size) > 1.0:
                    continue
                text = span.get("text", "").strip()
                if text:
                    out.append({"text": text, "size": s, "color": rgb,
                                "bbox": span.get("bbox")})
    return out


def _highlight_annots(page: fitz.Page) -> list[tuple[tuple[float, float, float], fitz.Rect]]:
    """Return (stroke_rgb, rect) for every Highlight annotation."""
    out = []
    for a in page.annots() or []:
        if a.type[0] != 8:  # 8 = Highlight
            continue
        cols = a.colors or {}
        stroke = cols.get("stroke") or []
        if len(stroke) == 3:
            out.append((tuple(stroke), a.rect))
    return out


def _sticky_icon_count(page: fitz.Page) -> int:
    """Count `Text` (type 0 — sticky note) annotations. Must be zero."""
    return sum(1 for a in (page.annots() or []) if a.type[0] == 0)


def verify_ac_eng_draft(draft_pdf: Path, original_reading_pdf: Path) -> dict[str, Any]:
    draft = fitz.open(str(draft_pdf))
    orig = fitz.open(str(original_reading_pdf))
    checks: dict[str, dict] = {}
    failures: list[str] = []

    # --- page_count_unchanged ---
    passed = draft.page_count == orig.page_count
    checks["page_count_unchanged"] = {
        "pass": passed,
        "draft_pages": draft.page_count,
        "original_pages": orig.page_count,
    }
    if not passed:
        failures.append(
            f"page_count: draft has {draft.page_count} pages, "
            f"original has {orig.page_count} — no appended pages allowed"
        )

    # --- line_fill ---
    fill_pcts: list[float] = []
    too_short: list[tuple[int, float, float]] = []
    for pi in range(draft.page_count):
        page = draft[pi]
        blanks = _find_blanks(page)
        blue_spans = _blue_answer_spans(page)
        for (y, bx0, bx1) in blanks:
            line_w = bx1 - bx0
            if line_w < 50:
                continue  # Not a real answer line
            # Find blue spans near this y (within 6pt)
            matching = [s for s in blue_spans if abs(s[0] - y) < 8 or abs(s[0] - (y - 12)) < 8]
            if not matching:
                too_short.append((pi, y, 0.0))
                fill_pcts.append(0.0)
                continue
            total_w = sum((s[2] - s[1]) for s in matching)
            pct = total_w / line_w
            fill_pcts.append(pct)
            if pct < 0.85:
                too_short.append((pi, y, pct))
    avg = sum(fill_pcts) / len(fill_pcts) if fill_pcts else 0.0
    min_pct = min(fill_pcts) if fill_pcts else 0.0
    passed = bool(fill_pcts) and min_pct >= 0.85 and avg >= 0.92
    checks["line_fill"] = {
        "pass": passed,
        "avg": round(avg, 3),
        "min": round(min_pct, 3),
        "lines_measured": len(fill_pcts),
        "too_short": [(pi, round(y, 1), round(pct, 3)) for pi, y, pct in too_short],
    }
    if not passed:
        failures.append(
            f"line_fill: avg={avg:.1%} min={min_pct:.1%} — "
            f"{len(too_short)} lines below 85% fill"
        )

    # --- margin_note_density ---
    para_count = _paragraph_count(original_reading_pdf)
    note_count = 0
    for pi in range(draft.page_count):
        page = draft[pi]
        note_count += len(_text_spans_matching(page, CONTENT_NOTE_TEXT, 7.5))
    ratio = note_count / para_count if para_count else 0.0
    passed = ratio >= 1.0
    checks["margin_note_density"] = {
        "pass": passed,
        "note_count": note_count,
        "paragraph_count": para_count,
        "ratio": round(ratio, 3),
    }
    if not passed:
        failures.append(
            f"margin_note_density: {note_count} notes for {para_count} "
            f"paragraphs — need one per paragraph"
        )

    # --- color_family_consistency ---
    # Aggregate all highlight colors across pages
    all_hi: list[tuple[tuple[float, float, float], fitz.Rect, int]] = []
    for pi in range(draft.page_count):
        for stroke, rect in _highlight_annots(draft[pi]):
            all_hi.append((stroke, rect, pi))
    # Group unique highlight colors
    unique_hi_colors = {tuple(round(c, 2) for c in h[0]) for h in all_hi}
    # Find vocab def text (any family) and content note text (any family)
    # For the v6.1 scheme vocab should be green, content should be pink
    vocab_hi_ok = any(_same_color_family(h, VOCAB_HIGHLIGHT) for h in unique_hi_colors)
    content_hi_ok = any(_same_color_family(h, CONTENT_HIGHLIGHT) for h in unique_hi_colors)
    # Definition/note text presence
    vocab_defs = []
    content_notes = []
    for pi in range(draft.page_count):
        vocab_defs += _text_spans_matching(draft[pi], VOCAB_DEF_TEXT, 6.5)
        content_notes += _text_spans_matching(draft[pi], CONTENT_NOTE_TEXT, 7.5)
    vocab_def_ok = len(vocab_defs) >= 5
    content_note_ok = len(content_notes) >= 1
    passed = vocab_hi_ok and content_hi_ok and vocab_def_ok and content_note_ok
    checks["color_family_consistency"] = {
        "pass": passed,
        "unique_highlight_colors": sorted(unique_hi_colors),
        "vocab_highlight_present": vocab_hi_ok,
        "content_highlight_present": content_hi_ok,
        "vocab_def_spans": len(vocab_defs),
        "content_note_spans": len(content_notes),
    }
    if not passed:
        reasons = []
        if not vocab_hi_ok:
            reasons.append("no green vocab highlights")
        if not content_hi_ok:
            reasons.append("no pink content highlights")
        if not vocab_def_ok:
            reasons.append(f"only {len(vocab_defs)} green 6.5pt def spans (need ≥5)")
        if not content_note_ok:
            reasons.append("no pink 7.5pt content notes")
        failures.append("color_family: " + "; ".join(reasons))

    # --- no_vocab_content_overlap ---
    overlaps: list[tuple[int, fitz.Rect, fitz.Rect]] = []
    for pi in range(draft.page_count):
        page_hi = _highlight_annots(draft[pi])
        vocab_rects = [r for c, r in page_hi if _same_color_family(c, VOCAB_HIGHLIGHT)]
        content_rects = [r for c, r in page_hi if _same_color_family(c, CONTENT_HIGHLIGHT)]
        for vr in vocab_rects:
            for cr in content_rects:
                # PyMuPDF highlight rects include leading — adjacent lines
                # naturally share ~2pt × width of bounding noise. A real
                # single-char overlap at 10pt would be ≥100 sq-pt, so set
                # threshold at 50 sq-pt to filter the noise.
                if (vr & cr).get_area() > 50.0:
                    overlaps.append((pi, vr, cr))
    passed = not overlaps
    checks["no_vocab_content_overlap"] = {
        "pass": passed,
        "overlap_count": len(overlaps),
    }
    if not passed:
        failures.append(f"no_vocab_content_overlap: {len(overlaps)} overlaps found")

    # --- no_sticky_icons ---
    sticky = sum(_sticky_icon_count(draft[pi]) for pi in range(draft.page_count))
    passed = sticky == 0
    checks["no_sticky_icons"] = {"pass": passed, "count": sticky}
    if not passed:
        failures.append(
            f"no_sticky_icons: {sticky} add_text_annot sticky notes found "
            "— forbidden per SKILL.md §6.3"
        )

    draft.close()
    orig.close()

    all_passed = not failures
    log_lines = [
        f"writing-course verification report",
        f"  draft: {draft_pdf}",
        f"  original: {original_reading_pdf}",
        f"  all_passed: {all_passed}",
        "",
    ]
    for name, result in checks.items():
        mark = "PASS" if result.get("pass") else "FAIL"
        log_lines.append(f"[{mark}] {name}")
        for k, v in result.items():
            if k == "pass":
                continue
            log_lines.append(f"    {k}: {v}")
    if failures:
        log_lines += ["", "FAILURES:"]
        log_lines += [f"  - {f}" for f in failures]
    return {
        "all_passed": all_passed,
        "failures": failures,
        "checks": checks,
        "log_text": "\n".join(log_lines),
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("usage: python -m src.ac_eng_verify <draft_pdf> <original_reading_pdf>")
        sys.exit(2)
    report = verify_ac_eng_draft(Path(sys.argv[1]), Path(sys.argv[2]))
    print(report["log_text"])
    sys.exit(0 if report["all_passed"] else 1)
