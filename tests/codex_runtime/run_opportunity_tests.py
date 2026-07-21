# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / ".agents" / "skills" / "canvas-skill-opportunity" / "SKILL.md"
SCHEMA = ROOT / "docs" / "RUN_STATE_SCHEMA.md"


def read_skill() -> str:
    assert SKILL.exists(), f"missing {SKILL}"
    return SKILL.read_text(encoding="utf-8")


def read_schema() -> str:
    assert SCHEMA.exists(), f"missing {SCHEMA}"
    return SCHEMA.read_text(encoding="utf-8")


def assert_pattern(text: str, pattern: str, label: str) -> None:
    assert re.search(pattern, text, re.IGNORECASE | re.MULTILINE | re.DOTALL), label


def assert_absent(text: str, needle: str, label: str) -> None:
    assert needle.lower() not in text.lower(), label


def test_agent_judgment_not_deterministic_scoring() -> None:
    text = read_skill()
    assert_pattern(text, r"^name:\s*canvas-skill-opportunity", "frontmatter name")
    assert_pattern(text, r"decision_method.*agent_judgment|Agent judgment protocol", "Agent judgment")
    assert_pattern(text, r"bucket_recurring", "factual recurring discovery")
    assert_pattern(text, r"is_course_active", "active-course facts")
    assert_pattern(text, r"min_freq=3", "recurrence threshold")
    assert_absent(text, "rank_skill_opportunities", "deterministic rank helper must not choose")
    assert_absent(text, "skillability_score", "no skillability score field")
    assert_absent(text, "grade_leverage_score", "no grade leverage score field")


def test_real_spec_evidence_contract() -> None:
    text = read_skill()
    assert_pattern(text, r"list_assignments_for_opportunity", "submission-free assignment list")
    assert_pattern(text, r"get_assignment_spec_for_opportunity", "safe real-spec helper")
    for required in ["description", "rubric", "attachment", "module", "source pointers"]:
        assert_pattern(text, re.escape(required), f"real-spec source: {required}")
    assert_pattern(text, r"at least two instances|enough representative assignments", "representative samples")
    assert_pattern(text, r"Do not infer.*course name.*assignment title.*submission_types", "no metadata-only type inference")
    assert_pattern(text, r"response pattern", "stable response pattern")
    assert_pattern(text, r"submission` object.*project.*away", "embedded submission projection")
    assert_pattern(text, r"insufficient_evidence", "unknown evidence outcome")


def test_broad_task_fit_golden_cases() -> None:
    text = read_skill()
    assert_pattern(text, r"Canvas-submittable code of any length.*even without supplied tests", "long code without tests stays strong")
    assert_pattern(text, r"formal (?:regression verifier|tests).*not required|Formal tests.*not an eligibility gate", "formal verifier not required")
    assert_pattern(text, r"Word, Excel, or PDF accounting/business", "Word accounting stays strong")
    assert_pattern(text, r"Twenty independent annotations.*10-20 words.*strong", "20 short annotations stay strong")
    assert_pattern(text, r"main or central continuous prose unit.*200 words or more.*demoter", "continuous 200+ prose demotion")
    assert_pattern(text, r"not a mechanical universal\s+hard gate", "200 is not a hard gate")
    assert_pattern(text, r"ancillary prose in a code, accounting", "ancillary prose does not misclassify")
    assert_pattern(text, r"external-site interaction, live performance.*unsupported", "external/live unsupported")


def test_pre_and_post_submit_review_are_separate() -> None:
    text = read_skill()
    assert_pattern(text, r"### Pre-submit review", "pre-submit review layer")
    assert_pattern(text, r"### Post-submit feedback and retry", "post-submit layer")
    for required in [
        "allowed_attempts",
        "results appear before the next attempt",
        "total-score visibility",
        "item-correctness visibility",
        "correct-answer visibility",
        "own-answer visibility",
        "scoring policy",
        "question reuse versus randomization",
        "evidence confidence",
    ]:
        assert_pattern(text, re.escape(required), f"quiz feedback fact: {required}")
    assert_pattern(
        text,
        r"Two or more\s+attempts.*useful feedback.*before retry.*keep_highest.*strongly\s+promotes",
        "two-attempt feedback quiz promotion",
    )


def test_classification_never_consumes_attempt_or_work() -> None:
    text = read_skill()
    attempt_helper = "start_quiz" "_submission"
    assert_absent(text, attempt_helper, "must not reference attempt-start helper")
    assert_pattern(text, r"Never start or consume a quiz attempt", "no attempt consumption")
    assert_pattern(text, r"Never solve, draft, answer, upload, submit", "no work or submission")
    assert_pattern(text, r"Never launch an attempt to discover", "no probe attempt")
    assert_pattern(text, r"Never call `canvas-scan`, `canvas-execute`", "no scan or execute")


def test_safe_observed_feedback_projection() -> None:
    text = read_skill()
    assert_pattern(text, r"derive_quiz_feedback_capabilities", "pure quiz-policy interpreter")
    assert_pattern(
        text,
        r"get_submission_feedback_observation_for_opportunity",
        "safe observed-submission projector",
    )
    assert_pattern(text, r"minimal Boolean/enum projection", "minimal derived projection")
    assert_pattern(text, r"observed.*declared.*inferred.*unknown", "evidence confidence levels")
    for prohibited in [
        "raw prior answers",
        "answer IDs",
        "exact grades or scores",
        "feedback text",
        "submission payloads",
    ]:
        assert_pattern(text, re.escape(prohibited), f"prohibit retaining {prohibited}")
    assert_pattern(text, r"If no safe projector exists.*leave the capability `unknown`", "unknown is fail-closed")
    assert_pattern(
        text,
        r"record_present.*does \*\*not\*\* prove.*view its contents",
        "response record is not answer visibility",
    )


def test_qualitative_tiers_and_tie_breakers() -> None:
    text = read_skill()
    for tier in [
        "best_first_skill",
        "good_candidate",
        "later_candidate",
        "assist_only",
        "unsupported",
        "insufficient_evidence",
    ]:
        assert_pattern(text, rf"`{tier}`", f"qualitative tier {tier}")
    assert_pattern(text, r"recurrence, scheduled future count, known\s+future points, and likely time saved.*break ties", "value tie-breakers")
    assert_pattern(text, r"Do not invent a 0-100", "no fake precision")


def test_private_report_and_user_choice_boundary() -> None:
    text = read_skill()
    assert_pattern(text, r"runs/<today>/skill-opportunities\.json", "private JSON report")
    assert_pattern(text, r"runs/<today>/skill-opportunities\.md", "private Markdown report")
    assert_pattern(text, r"verify `runs/` is gitignored", "gitignore privacy gate")
    assert_pattern(text, r"post_submit_policy", "feedback policy in report schema")
    assert_pattern(text, r"Course 1 / Pattern 1", "sanitized chat alias")
    assert_pattern(text, r"never paste the private table", "no private table in chat")
    assert_pattern(text, r"Which number should Canvas Pilot", "single user choice prompt")
    assert_pattern(text, r"Do not invoke `canvas-bootstrap` in the same turn", "stop before bootstrap")
    assert_pattern(text, r"choice never authorizes solving or submission", "selection is not submission authority")


def test_run_state_schema_matches_qualitative_contract() -> None:
    text = read_schema()
    assert_pattern(text, r'"decision_method":\s*"agent_judgment"', "Agent judgment schema")
    assert_pattern(text, r'"tier":\s*"best_first_skill"', "qualitative tier schema")
    assert_pattern(text, r'"spec_evidence"', "real-spec evidence schema")
    assert_pattern(text, r'"post_submit_policy"', "feedback policy schema")
    assert_absent(text, '"skillability_score"', "no deterministic skillability field")
    assert_absent(text, '"grade_leverage_score"', "no deterministic leverage field")


def test_failure_modes_fail_closed() -> None:
    text = read_skill()
    assert_pattern(text, r"Representative real spec is inaccessible.*insufficient_evidence", "missing spec failure")
    assert_pattern(text, r"Feedback facts are incomplete.*`unknown`", "unknown feedback failure")
    assert_pattern(text, r"Safe historical projection is unavailable.*Do not read a raw submission payload", "unsafe history failure")
    assert_pattern(text, r"Required external/live/physical/group/proctored step exists.*`unsupported`", "unsupported delivery failure")
    assert_pattern(text, r"No eligible first skill", "no eligible outcome")


def main() -> int:
    tests = [
        test_agent_judgment_not_deterministic_scoring,
        test_real_spec_evidence_contract,
        test_broad_task_fit_golden_cases,
        test_pre_and_post_submit_review_are_separate,
        test_classification_never_consumes_attempt_or_work,
        test_safe_observed_feedback_projection,
        test_qualitative_tiers_and_tie_breakers,
        test_private_report_and_user_choice_boundary,
        test_run_state_schema_matches_qualitative_contract,
        test_failure_modes_fail_closed,
    ]
    failures: list[str] = []
    for test in tests:
        try:
            test()
            print(f"PASS {test.__name__}")
        except Exception as exc:
            failures.append(f"{test.__name__}: {exc}")
            print(f"FAIL {test.__name__}: {exc}")
    if failures:
        print("\nFailures:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
