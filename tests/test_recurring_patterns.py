# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for src/recurring_patterns.py.

Run: pytest tests/test_recurring_patterns.py -v

Fixture data mirrors the shape of Canvas list_assignments() output. The
end-to-end tests cover four typical course archetypes:

  - two-pattern code course (problem sets + projects)
  - mixed-pattern document course (twice-weekly scans + many one-offs)
  - single-pattern quiz course (weekly quizzes + a few one-offs)
  - empty course (no assignments yet)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import datetime as dt

from src.recurring_patterns import (
    Pattern,
    bucket_recurring,
    is_course_active,
    looks_like_real_course,
    normalize,
)


# ---------- normalize() ----------

def test_normalize_bare_digit():
    assert normalize("Set 3 Problem 4") == "Set <N> Problem <N>"

def test_normalize_no_space_digits():
    assert normalize("Tue Wk5 HW Scan") == "Tue Wk<N> HW Scan"

def test_normalize_section_in_phrase():
    assert normalize("Quiz on Section 17 reading and lecture") \
        == "Quiz on Section <N> reading and lecture"

def test_normalize_range():
    assert normalize("Attendance/Participation Wks 1-5") \
        == "Attendance/Participation Wks <N>"

def test_normalize_em_dash_range():
    assert normalize("Reading 3–5") == "Reading <N>"

def test_normalize_roman_numeral():
    assert normalize("Project II") == "Project <N>"
    assert normalize("Module IV homework") == "Module <N> homework"

def test_normalize_single_letter_not_roman():
    # "I" alone shouldn't be replaced — too aggressive, would eat pronouns
    assert normalize("What I learned this week") == "What I learned this week"

def test_normalize_collapses_whitespace():
    assert normalize("Set  3   Problem  4") == "Set <N> Problem <N>"

def test_normalize_no_digits_passthrough():
    assert normalize("Final Paper") == "Final Paper"
    assert normalize("Academic Honesty Contract") == "Academic Honesty Contract"


# ---------- bucket_recurring() ----------

def _items(*specs):
    """Build a list of fake assignment dicts. Each spec is (name, submission_types)."""
    return [{"name": n, "submission_types": list(st)} for n, st in specs]


def test_bucket_groups_by_normalized_name():
    items = _items(
        ("Set 1 Problem 1", ["online_upload"]),
        ("Set 1 Problem 2", ["online_upload"]),
        ("Set 2 Problem 1", ["online_upload"]),
    )
    patterns, tail = bucket_recurring(items, min_freq=3)
    assert len(patterns) == 1
    assert patterns[0].norm_name == "Set <N> Problem <N>"
    assert patterns[0].count == 3
    assert tail == 0


def test_bucket_separates_different_submission_types():
    """Same name shape but different submission_types must NOT merge."""
    items = _items(
        ("Quiz 1", ["online_quiz"]),
        ("Quiz 2", ["online_quiz"]),
        ("Quiz 3", ["online_quiz"]),
        ("Quiz 4", ["online_upload"]),
    )
    patterns, tail = bucket_recurring(items, min_freq=3)
    assert len(patterns) == 1
    assert patterns[0].submission_types == ("online_quiz",)
    assert patterns[0].count == 3
    assert tail == 1  # the online_upload one falls below threshold


def test_bucket_below_threshold_goes_to_tail():
    items = _items(
        ("Set 1 Problem 1", ["online_upload"]),
        ("Set 1 Problem 2", ["online_upload"]),  # only 2 — sub-threshold
        ("Final Exam", ["on_paper"]),
        ("Attendance", ["none"]),
    )
    patterns, tail = bucket_recurring(items, min_freq=3)
    assert patterns == []
    assert tail == 4


def test_bucket_sorted_by_count_descending():
    items = _items(
        ("Foo 1", ["online_upload"]),
        ("Foo 2", ["online_upload"]),
        ("Foo 3", ["online_upload"]),
        ("Bar 1", ["online_quiz"]),
        ("Bar 2", ["online_quiz"]),
        ("Bar 3", ["online_quiz"]),
        ("Bar 4", ["online_quiz"]),
        ("Bar 5", ["online_quiz"]),
    )
    patterns, _ = bucket_recurring(items, min_freq=3)
    assert [p.count for p in patterns] == [5, 3]
    assert patterns[0].norm_name == "Bar <N>"


def test_bucket_examples_capped_at_3():
    items = _items(*[(f"Item {i}", ["online_upload"]) for i in range(1, 11)])
    patterns, _ = bucket_recurring(items, min_freq=3)
    assert len(patterns) == 1
    assert len(patterns[0].examples) == 3


def test_bucket_handles_missing_submission_types():
    items = [
        {"name": "X 1"},
        {"name": "X 2"},
        {"name": "X 3"},
    ]
    patterns, tail = bucket_recurring(items, min_freq=3)
    assert len(patterns) == 1
    assert patterns[0].submission_types == ()
    assert tail == 0


def test_bucket_empty_input():
    patterns, tail = bucket_recurring([], min_freq=3)
    assert patterns == []
    assert tail == 0


# ---------- end-to-end: four typical course archetypes ----------

def test_e2e_two_pattern_code_course():
    """17 problem-set items + 3 projects, all online_upload."""
    items = _items(
        *[(f"Set {s} Problem {p}", ["online_upload"])
          for s in range(1, 5) for p in range(1, 5)],
        ("Set 5 Problem 1", ["online_upload"]),
        ("Project 0", ["online_upload"]),
        ("Project 1", ["online_upload"]),
        ("Project 2", ["online_upload"]),
    )
    assert len(items) == 20
    patterns, tail = bucket_recurring(items, min_freq=3)
    assert tail == 0
    assert len(patterns) == 2
    counts = sorted([p.count for p in patterns], reverse=True)
    assert counts == [17, 3]


def test_e2e_document_course_with_long_tail():
    """8 Thu HW Scan + 7 Tue HW Scan + 12 sub-threshold (mixed)."""
    items = _items(
        *[(f"Thu Wk{w} HW Scan", ["online_upload"]) for w in range(1, 9)],
        *[(f"Tue Wk{w} HW Scan", ["online_upload"]) for w in range(2, 9)],
        ("Student Info Sheet", ["online_upload"]),
        ("Academic Honesty Contract", ["online_upload"]),
        ("Final Exam (In-Class Essay)", ["on_paper"]),
        ("Attendance/Participation Wks 1-5", ["none"]),
        ("Attendance/Participation Wks 6-10", ["none"]),
        *[(f"Note Taking R{i} (At home)", ["external_tool"]) for i in range(1, 5)],
        *[(f"Response Paper Draft {i}", ["external_tool"]) for i in (1, 2)],
        ("Response Paper Final Draft", ["external_tool"]),
    )
    patterns, tail = bucket_recurring(items, min_freq=3)
    pattern_names = {p.norm_name for p in patterns}
    assert "Thu Wk<N> HW Scan" in pattern_names
    assert "Tue Wk<N> HW Scan" in pattern_names
    # The 4 Note Taking + 3 Response Paper would also clear threshold given
    # this fixture; tail is everything below 3.
    assert tail >= 3  # at least the 3 unique singletons


def test_e2e_single_pattern_quiz_course():
    """17 weekly quizzes + 3 one-off non-quiz items."""
    items = _items(
        *[(f"Quiz on Section {s} reading and lecture", ["online_quiz"])
          for s in range(1, 18)],
        ("Final Paper", ["external_tool"]),
        ("Extra Credit Evaluation", ["none"]),
        ("iClicker Lecture Attendance", ["external_tool"]),
    )
    assert len(items) == 20
    patterns, tail = bucket_recurring(items, min_freq=3)
    assert len(patterns) == 1
    assert patterns[0].count == 17
    assert patterns[0].submission_types == ("online_quiz",)
    assert tail == 3


def test_e2e_empty_course():
    """0 assignments — no patterns, no tail."""
    patterns, tail = bucket_recurring([], min_freq=3)
    assert patterns == [] and tail == 0


# ---------- is_course_active() ----------

NOW = dt.datetime(2026, 4, 30, tzinfo=dt.timezone.utc)


def test_active_no_end_date_treated_as_active():
    """Perpetual spaces (no end_at, no term.end_at) are treated as active."""
    assert is_course_active({"end_at": None, "term": {"end_at": None}}, now=NOW) is True
    assert is_course_active({}, now=NOW) is True


def test_active_term_end_in_future():
    """Term ends after now → active."""
    course = {"term": {"end_at": "2026-06-19T07:00:00Z"}}
    assert is_course_active(course, now=NOW) is True


def test_active_term_ended_outside_grace():
    """Term ended >7 days ago → not active."""
    course = {"term": {"end_at": "2026-03-27T07:00:00Z"}}  # 34 days before NOW
    assert is_course_active(course, now=NOW) is False


def test_active_term_ended_within_grace():
    """Term ended 5 days ago → still within 7-day grace, active."""
    course = {"term": {"end_at": "2026-04-25T07:00:00Z"}}  # 5 days before NOW
    assert is_course_active(course, now=NOW) is True


def test_active_uses_latest_of_course_and_term_end():
    """course.end_at is later than term.end_at → use the later one (most permissive)."""
    course = {
        "end_at": "2026-08-28T06:59:00Z",       # far future
        "term": {"end_at": "2025-09-09T07:00:00Z"},  # last year
    }
    assert is_course_active(course, now=NOW) is True


def test_active_only_course_end_set():
    """No term info but course.end_at is set."""
    assert is_course_active({"end_at": "2026-06-19T07:00:00Z"}, now=NOW) is True
    assert is_course_active({"end_at": "2025-12-01T07:00:00Z"}, now=NOW) is False


def test_active_grace_zero():
    """grace_days=0 — no buffer."""
    course = {"term": {"end_at": "2026-04-29T07:00:00Z"}}  # 1 day before NOW
    assert is_course_active(course, grace_days=0, now=NOW) is False  # ended yesterday
    assert is_course_active(course, grace_days=7, now=NOW) is True   # within 7-day buffer


# ---------- looks_like_real_course() ----------
# Positive-signal Layer 4 heuristic. Two checks: dept-code prefix + time gate.
# No noise blocklist by design — see docstring in src/recurring_patterns.py.

FUTURE_END = "2026-06-19T07:00:00Z"
PAST_END = "2024-03-15T07:00:00Z"


def test_real_course_dept_prefix_short():
    """CS 101 — classic dept-code-+-number, future end -> real."""
    course = {"name": "CS 101 Spring 2026", "end_at": FUTURE_END}
    assert looks_like_real_course(course, now=NOW) is True


def test_real_course_dept_prefix_multi_token():
    """BIO SCI 99 — multi-token dept code -> real."""
    course = {
        "name": "BIO SCI 99 LAB B: Methods",
        "end_at": FUTURE_END,
    }
    assert looks_like_real_course(course, now=NOW) is True


def test_real_course_seminar_code():
    """UNIV 100 SEM D — generic freshman seminar with dept-code style -> real."""
    course = {"name": "UNIV 100 SEM D: Foundations", "end_at": FUTURE_END}
    assert looks_like_real_course(course, now=NOW) is True


def test_real_course_engl_dept():
    """ENGL 200 — academic English course code -> real."""
    course = {"name": "ENGL 200 Spring 2026", "end_at": FUTURE_END}
    assert looks_like_real_course(course, now=NOW) is True


def test_noise_integrity_module():
    """Generic onboarding integrity module — no dept-code prefix -> not real."""
    course = {"name": "Academic Integrity Training Module"}
    assert looks_like_real_course(course, now=NOW) is False


def test_noise_first_year_orientation():
    """First-Year Orientation — hyphenated title-case -> no dept code -> not real."""
    course = {"name": "First-Year Online Orientation Space 1"}
    assert looks_like_real_course(course, now=NOW) is False


def test_noise_student_training_hub():
    """Student Training Hub 2025-2026 — no number after dept-style token -> not real."""
    course = {"name": "Student Training Hub - 2025-2026"}
    assert looks_like_real_course(course, now=NOW) is False


def test_noise_writing_support_lab():
    """Academic Writing Support Lab — 'Academic' is single token, no dept-code shape."""
    course = {"name": "Academic Writing Support Lab - Spring 2026", "end_at": FUTURE_END}
    assert looks_like_real_course(course, now=NOW) is False


def test_noise_placement_exam():
    """Placement exam holding course — fails on time AND on no-dept-code."""
    course = {"name": "Summer 2025 Placement Exam Holding Course", "end_at": PAST_END}
    assert looks_like_real_course(course, now=NOW) is False


def test_real_course_blocked_by_time_gate():
    """CS 101 from a past term — name passes but end_at is past 7-day grace -> not real anymore."""
    course = {"name": "CS 101 Spring 2024", "end_at": PAST_END}
    assert looks_like_real_course(course, now=NOW) is False


def test_no_blocklist_lab_methods():
    """'Lab Methods Training' — no dept code -> fails. Proves we don't need a
    'training' keyword blocklist; absence of dept code is sufficient."""
    course = {"name": "Lab Methods Training", "end_at": FUTURE_END}
    assert looks_like_real_course(course, now=NOW) is False


def test_no_blocklist_workspace_design():
    """'Workspace Design Studio' — no dept code -> fails despite containing 'Workspace'."""
    course = {"name": "Workspace Design Studio", "end_at": FUTURE_END}
    assert looks_like_real_course(course, now=NOW) is False


def test_real_course_with_lab_in_name():
    """Counter-example to keyword-blocklist approach: a real course whose name
    contains 'Lab' should still pass IF it has a dept-code prefix.
    'BIO SCI 99 LAB B' has dept code -> real even with 'LAB' in name.
    This test enforces our 'positive-only, no blocklist' design choice."""
    course = {"name": "BIO SCI 99 LAB B: Methods", "end_at": FUTURE_END}
    assert looks_like_real_course(course, now=NOW) is True


def test_real_course_perpetual_no_end_date():
    """Real course with no end_at info is OK (is_course_active returns True for those)."""
    course = {"name": "MATH 2B Sect 1"}
    assert looks_like_real_course(course, now=NOW) is True


def test_title_case_no_dept_code_corner_case():
    """'Intro to Global Studies Spring 2026' — title-case, no dept code -> fails Layer 4.
    But this is fine in practice: such courses typically have recurring assignment
    patterns and get caught by Layer 3 before reaching Layer 4. Documenting expected
    behavior — folded courses are still selectable, so user can always expand."""
    course = {"name": "Intro to Global Studies Spring 2026", "end_at": FUTURE_END}
    assert looks_like_real_course(course, now=NOW) is False
