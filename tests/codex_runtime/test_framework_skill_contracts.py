# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = ROOT / ".agents" / "skills"


def skill(name: str) -> str:
    path = SKILL_ROOT / name / "SKILL.md"
    assert path.exists(), f"missing framework skill: {path}"
    return path.read_text(encoding="utf-8")


def has(text: str, pattern: str, label: str) -> None:
    assert re.search(pattern, text, re.IGNORECASE | re.MULTILINE | re.DOTALL), label


def test_setup_is_friendly_resumable_and_stops_at_opportunity() -> None:
    text = skill("canvas-setup")
    has(text, r"Which school do you use Canvas through\?", "school-first setup")
    has(text, r"one domain question per turn", "one-question UX")
    has(text, r"Resume from observed state", "state-based recovery")
    has(text, r"preserve.*token mode", "token recovery preservation")
    has(text, r"canvas-skill-opportunity", "opportunity handoff")
    has(text, r"student's choice comes before.*canvas-bootstrap", "choice boundary")
    has(text, r"Do not scan assignments", "setup cannot scan")
    has(text, r"Do not submit, upload, or answer quizzes", "setup cannot mutate")
    has(text, r"Do not write `assignments\.json`, `plan\.json`, `result\.json`, or `REPORT\.md`", "no run artifacts")


def test_bootstrap_has_selection_viability_authoring_and_calibration() -> None:
    text = skill("canvas-bootstrap")
    has(text, r"student explicitly selected one numbered candidate", "selection required")
    has(text, r"sample at least two representative assignments", "representative samples")
    has(text, r"three-part reachability check", "real-source reachability")
    has(text, r"native Codex subagents", "native reviewers")
    has(text, r"Rubric coverage reviewer", "rubric review")
    has(text, r"Verification designer", "verification design")
    has(text, r"Feasibility simulator", "feasibility simulation")
    has(text, r"All six conditions must be true", "viability gate")
    has(text, r"do not write a ready route", "failed gate cannot route")
    has(text, r"UNFILLED_SKELETON", "guarded scaffold")
    has(text, r"sentinel can never count as `draft_ready`", "sentinel not a draft")
    has(text, r"public-safe.*private local overlay", "public/private split")
    has(text, r"first_run_calibration_done", "calibration state")
    for category in ("one_off", "recurring_pattern", "workflow_change"):
        assert category in text
    has(text, r"explicit draft consent", "calibration consent")
    has(text, r"src\.routes\.resolve_skill", "shared resolver")
    has(text, r"Do not write `?\.claude", "frozen driver")


def test_scan_uses_one_enriched_process_and_atomic_hard_stop() -> None:
    text = skill("canvas-scan")
    has(text, r"python -m src\.router --scan-json", "enriched scan command")
    has(text, r"src\.scan_service", "shared scan service")
    has(text, r"exactly one interactive scan command", "single process")
    has(text, r"Do not restore the old interactive sequence", "old path rejected")
    has(text, r"non-empty `course_errors`.*incomplete scan", "partial scan fails loudly")
    has(text, r"stop without replacing the prior approval plan", "no partial plan")
    has(text, r"Unsupported delivery types.*canvas-skip", "unsupported fail closed")
    has(text, r"Same-day result", "same-day dedup")
    has(text, r"course-<course_id>__assignment-<assignment_id>", "stable work dir")
    has(text, r"never recompute.*mutable.*names", "no name-derived work dir")
    has(text, r"Cross-day ledger", "ledger dedup")
    has(text, r"deferred_to_next_run", "deferred re-entry")
    has(text, r"materialize `runs/<today>/assignments\.json` from the final", "fresh snapshot")
    has(text, r"plan\.json", "approval plan")
    has(text, r"\.tmp.*os\.replace", "atomic state")
    has(text, r"Every `user_decision` starts `null`", "unapproved by default")
    has(text, r"Reply all, numbers like 1,3, or skip", "simple approval prompt")
    has(text, r"MUST NOT create `\.scan_in_progress`", "scan has no marker")
    has(text, r"Hard stop", "architectural stop")
    has(text, r"src\.routes\.resolve_skill", "canonical route resolver")


def test_execute_owns_dispatch_results_ledger_report_and_marker() -> None:
    text = skill("canvas-execute")
    has(text, r"plan indices are unique, contiguous, and 1-based", "plan integrity")
    has(text, r"src\.approval\.parse_approval", "shared deterministic parser")
    has(text, r"src\.run_state\.validate_plan", "shared plan validator")
    has(text, r"one-to-one.*snapshot item", "snapshot/plan identity")
    has(text, r"CODEX_SESSION_ID", "Codex marker owner")
    has(text, r"plan_digest", "marker plan ownership")
    has(text, r"different owner.*do not steal", "marker isolation")
    has(text, r"prepare-results --run-dir", "shared approved-result preparation gate")
    has(text, r"before reading,\s*reconciling, or dispatching", "preparation precedes result reuse")
    has(text, r"prepared_approved_result_keys", "prepared slots bound to current plan")
    has(text, r"src\.routes\.resolve_skill", "shared resolver")
    has(text, r"native Codex skill handoff", "native dispatch")
    has(text, r"course-<course_id>__assignment-<assignment_id>", "stable execute work dir")
    has(text, r"never derive it from mutable names", "execute avoids name slugs")
    has(text, r"one at a time", "sequential dispatch")
    has(text, r"Do not maintain an inline mapping", "no alias guessing")
    for status in ("draft_ready", "submitted", "skipped", "error"):
        assert f"`{status}`" in text
    has(text, r"Reject legacy or invented statuses", "canonical result enum")
    has(text, r"not approved this run", "deferred placeholder")
    has(text, r"Atomic cross-day ledger", "ledger closeout")
    has(text, r"src\.run_state\.merge_ledger_entry", "shared atomic ledger helper")
    has(text, r"REPORT\.md closeout", "report closeout")
    has(text, r"verified facts.*judgment calls", "honest report")
    has(text, r"Delivery sync", "draft delivery")
    has(text, r"Remove the owned `\.scan_in_progress` marker only after", "marker last")


def test_execution_approval_is_not_canvas_mutation_authority() -> None:
    bootstrap = skill("canvas-bootstrap")
    execute = skill("canvas-execute")
    skip = skill("canvas-skip")
    for text in (bootstrap, execute, skip):
        has(text, r"authorization receipt", "separate authorization receipt")
        has(text, r"start.*answer.*complete", "quiz action scope")
    has(execute, r"plan\.json.*never an authorization receipt", "plan approval separation")
    has(execute, r"shared runtime.*validated.*consumed", "runtime receipt consumption")
    has(execute, r"src\.authorization\.require_mutation_authorization", "shared receipt gate")
    has(execute, r"Without a valid receipt", "mutation fail closed")
    has(execute, r"ordinary course skills produce verified local drafts only", "draft-only default")


def test_skip_is_an_honest_atomic_manual_handoff() -> None:
    text = skill("canvas-skip")
    has(text, r"Do not solve, draft, research", "skip does no work")
    has(text, r"Do not start, answer/save, complete, or retake a quiz", "skip no quiz")
    has(text, r"Do not mark anything `draft_ready` or `submitted`", "honest status")
    has(text, r"idempotent manual todo", "todo dedup")
    has(text, r'"status"\s*:\s*"skipped"', "canonical skipped result")
    has(text, r"deferred_to_next_run", "retry semantics")
    has(text, r"os\.replace", "atomic result")
    has(text, r"src\.run_state\.write_result", "shared result writer")


def test_public_skill_text_has_no_concrete_private_identifiers() -> None:
    combined = "\n".join(
        skill(name)
        for name in (
            "canvas-setup",
            "canvas-bootstrap",
            "canvas-scan",
            "canvas-execute",
            "canvas-skip",
        )
    )
    assert not re.search(r"[\w.\-+]+@[\w.\-]+\.edu\b", combined, re.IGNORECASE)
    assert not re.search(r"\bcourse_id\s*[:=]\s*\d{4,}\b", combined, re.IGNORECASE)
    assert not re.search(r"\bassignment_id\s*[:=]\s*\d{4,}\b", combined, re.IGNORECASE)
