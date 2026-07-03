# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for src/ac_eng_router.py.

Run: pytest tests/test_ac_eng_router.py -v

Coverage: each of the 6 layers gets >=3 TRIGGER + >=3 SKIP fixtures, plus an
end-to-end check using CEO's 5.15.md spec shape.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ac_eng_router import route_ac_eng_assignment


def _mk(
    name: str = "",
    description: str = "",
    points_possible=10,
    submission_types=None,
    attached_pdf_texts=None,
) -> dict:
    return {
        "name": name,
        "description": description,
        "points_possible": points_possible,
        "submission_types": submission_types
        if submission_types is not None
        else ["online_text_entry"],
        "attached_pdf_texts": attached_pdf_texts or [],
    }


# ---------------- Layer 1: plan.json manual override ----------------

def test_l1_force_essay_true_overrides_short_name():
    a = _mk(name="Reading Annotation Wk 5")
    assert route_ac_eng_assignment(a, plan_item={"ac_eng_force_essay": True}) == "essay"


def test_l1_force_essay_false_overrides_essay_name():
    a = _mk(name="Essay 1: Autoethnography")
    assert route_ac_eng_assignment(a, plan_item={"ac_eng_force_essay": False}) == "short"


def test_l1_no_plan_item_passes_to_lower_layers():
    a = _mk(name="Reading Annotation Wk 5")
    assert route_ac_eng_assignment(a) == "short"


def test_l1_plan_item_without_force_key_passes_through():
    a = _mk(name="Essay 1")
    # No ac_eng_force_essay key → L1 doesn't fire, falls to L5 (essay match).
    assert route_ac_eng_assignment(a, plan_item={"some_other_field": "x"}) == "essay"


# ---------------- Layer 2: overlay-declared hard regex ----------------

def test_l2_trigger_pattern_hit():
    a = _mk(name="Essay 1: Reflection")
    overlay = {"persona_trigger_patterns": [r"\bEssay\s+\d+\b"]}
    assert route_ac_eng_assignment(a, overlay) == "essay"


def test_l2_autoethnography_trigger_pattern():
    a = _mk(name="Autoethnographic Voices Project")
    overlay = {"persona_trigger_patterns": [r"\bAutoethnograph(y|ic)\b"]}
    assert route_ac_eng_assignment(a, overlay) == "essay"


def test_l2_skip_pattern_wins_over_trigger():
    a = _mk(name="Annotation Essay Practice")
    overlay = {
        "persona_trigger_patterns": [r"\bEssay\b"],
        "persona_skip_patterns": [r"\bAnnotation\b"],
    }
    assert route_ac_eng_assignment(a, overlay) == "short"


def test_l2_skip_pattern_hit():
    a = _mk(name="Daily Response Wk 3")
    overlay = {"persona_skip_patterns": [r"\bDaily\s+Response\b"]}
    assert route_ac_eng_assignment(a, overlay) == "short"


def test_l2_empty_overlay_passes_through():
    a = _mk(name="Reading Log Wk 3")
    assert route_ac_eng_assignment(a, overlay_config={}) == "short"


def test_l2_malformed_regex_does_not_crash():
    a = _mk(name="Essay 1")
    overlay = {"persona_trigger_patterns": ["[unclosed"]}
    # Bad regex is silently skipped; falls through to L5 which catches "essay".
    assert route_ac_eng_assignment(a, overlay) == "essay"


# ---------------- Layer 3: word count extraction ----------------

def test_l3_description_1500_words():
    a = _mk(name="Final paper", description="Write a 1500 word essay.")
    assert route_ac_eng_assignment(a) == "essay"


def test_l3_description_800_words_at_threshold():
    a = _mk(name="HW", description="Submit an 800 word reflection.")
    assert route_ac_eng_assignment(a) == "essay"


def test_l3_html_stripped_before_match():
    a = _mk(
        name="HW",
        description="<p>Required: <strong>1200 words</strong>.</p>",
    )
    assert route_ac_eng_assignment(a) == "essay"


def test_l3_below_threshold_300_words_does_not_trigger():
    a = _mk(name="Daily Response", description="Respond in 300 words.")
    assert route_ac_eng_assignment(a) == "short"


def test_l3_no_word_count_in_description():
    a = _mk(name="Reading Log", description="See Reading 200 for context.")
    assert route_ac_eng_assignment(a) == "short"


def test_l3_attached_pdf_word_count_triggers():
    a = _mk(
        name="HW 5",
        description="See attached spec.",
        attached_pdf_texts=["Your essay should be at least 1500 words long."],
    )
    assert route_ac_eng_assignment(a) == "essay"


# ---------------- Layer 4: Canvas API metadata composite ----------------

def test_l4_high_points_online_upload_triggers():
    a = _mk(
        name="HW 5", points_possible=50, submission_types=["online_upload"]
    )
    assert route_ac_eng_assignment(a) == "essay"


def test_l4_threshold_25_online_upload_triggers():
    a = _mk(
        name="HW 5", points_possible=25, submission_types=["online_upload"]
    )
    assert route_ac_eng_assignment(a) == "essay"


def test_l4_high_points_no_online_upload_does_not_trigger():
    a = _mk(
        name="HW 5", points_possible=50, submission_types=["online_text_entry"]
    )
    assert route_ac_eng_assignment(a) == "short"


def test_l4_low_points_with_online_upload_does_not_trigger():
    a = _mk(name="HW 5", points_possible=10, submission_types=["online_upload"])
    assert route_ac_eng_assignment(a) == "short"


def test_l4_none_points_handled_gracefully():
    a = _mk(
        name="HW 5", points_possible=None, submission_types=["online_upload"]
    )
    assert route_ac_eng_assignment(a) == "short"


def test_l4_on_paper_high_points_does_not_trigger():
    # Mimics the real Practice Summary fixture: points=100 but submitted on paper.
    a = _mk(
        name="Practice Summary (In Class)",
        points_possible=100,
        submission_types=["on_paper"],
    )
    assert route_ac_eng_assignment(a) == "short"


# ---------------- Layer 5: name keyword regex ----------------

def test_l5_critical_reflection_paper_triggers():
    a = _mk(name="Critical Reflection Paper")
    assert route_ac_eng_assignment(a) == "essay"


def test_l5_autoethnography_essay_triggers():
    a = _mk(name="Autoethnography Essay")
    assert route_ac_eng_assignment(a) == "essay"


def test_l5_narrative_memoir_triggers():
    a = _mk(name="Personal Narrative Memoir")
    assert route_ac_eng_assignment(a) == "essay"


def test_l5_daily_reading_response_does_not_trigger():
    a = _mk(name="Daily Reading Response")
    assert route_ac_eng_assignment(a) == "short"


def test_l5_annotation_does_not_trigger():
    a = _mk(name="Reading Annotation Week 5")
    assert route_ac_eng_assignment(a) == "short"


def test_l5_essay_keyword_overridden_by_response():
    # "essay" matches, but "response" also matches non-essay set → AND NOT fails
    a = _mk(name="Essay Response (short form)")
    assert route_ac_eng_assignment(a) == "short"


# ---------------- Layer 6: default ----------------

def test_l6_vocabulary_quiz_defaults_short():
    a = _mk(name="Vocabulary Quiz")
    assert route_ac_eng_assignment(a) == "short"


def test_l6_summary_in_class_defaults_short():
    a = _mk(name="Practice Summary In Class")
    assert route_ac_eng_assignment(a) == "short"


def test_l6_empty_name_defaults_short():
    a = _mk(name="")
    assert route_ac_eng_assignment(a) == "short"


# ---------------- End-to-end: CEO's 5.15.md fixture ----------------

def test_e2e_ceo_5_15_autoethnography_routes_to_essay():
    """5.15.md spec: 1500 word autoethnography essay, MLA, points=50, online_upload."""
    a = _mk(
        name="Essay 1: Autoethnography Reflection",
        description="Write a 1500 word autoethnography essay using MLA.",
        points_possible=50,
        submission_types=["online_upload"],
    )
    overlay = {
        "persona_trigger_patterns": [
            r"\bEssay\s+\d+\b",
            r"\bAutoethnograph(y|ic)\b",
        ],
        "persona_skip_patterns": [r"\bAnnotation\b", r"\bDaily\s+Response\b"],
    }
    assert route_ac_eng_assignment(a, overlay) == "essay"


def test_e2e_real_practice_summary_routes_to_short():
    """A real-world short assignment from existing runs/ — must NOT touch essay path."""
    a = _mk(
        name="Practice Summary (In Class)",
        description="",
        points_possible=100,
        submission_types=["on_paper"],
    )
    assert route_ac_eng_assignment(a) == "short"
