---
name: canvas-bootstrap
description: Use after the student selects one Canvas skill-opportunity candidate, or when they explicitly redesign one route. It validates the real recurring workflow, creates one public-safe Codex course skill plus a private local overlay, calibrates it when authorized, and writes a route only after the viability gate passes.
---

# Canvas Bootstrap

Turn one student-selected recurring pattern into a durable Codex course skill.
This is a detective and authoring workflow, not a pending-work scanner and not a
submission workflow.

Bootstrap is intentionally scope-first: one selected candidate, one course, one
route per invocation. The student may run it again for another pattern later.

## Entry contract

Normal first-run entry requires all of the following:

1. Canvas authentication has already been verified by `canvas-setup`.
2. `canvas-skill-opportunity` wrote the private local
   `runs/<today>/skill-opportunities.json` and companion Markdown report.
3. The student explicitly selected one numbered candidate in a later turn.

The opportunity report is evidence, not authorization. A ranking does not
authorize skill creation by itself, does not approve any pending assignment,
and grants no upload, submission, or quiz-mutation authority.

A manual redesign request may target one existing route without a fresh
opportunity report, but Bootstrap must still run the same current-evidence and
viability checks and must ask before replacing a working skill or private
overlay.

If invoked with no selected candidate and no explicit redesign target, stop and
ask for the candidate number. Do not choose the top-ranked item for the student.

## Outputs and privacy split

On a successful run, Bootstrap may create or update exactly these local
surfaces:

- `.agents/skills/canvas-<safe-name>/SKILL.md` — tracked, public-safe workflow
  instructions with no private course facts;
- `_private/canvas-<safe-name>-app.md` — gitignored local overlay containing the
  real course mapping, source locations, material pointers, measured checks,
  calibration state, and user preferences;
- `courses.yaml` — local route configuration, updated atomically only after the
  skill is ready.

Keep `.claude/` read-only. It may be inspected as frozen behavioral history when
needed for parity analysis, but no content from private legacy playbooks may be
copied into the public Codex skill.
Do not write `.claude`.

Private identity, institution, real course and assignment identifiers, teaching
staff details, private URLs, feedback text, prior answers, and exact grades stay
in gitignored local state. Chat uses the opportunity number and a neutral alias.

## Hard boundaries

- Do not scan all pending work or create `plan.json`.
- Do not call `canvas-scan` or `canvas-execute` from Bootstrap.
- Do not start, answer, or complete a quiz attempt.
- Do not upload or submit anything.
- Do not create a route before student selection and the viability gate both
  pass.
- Do not mark a skeleton, TODO file, empty document, sentinel, placeholder, or
  template-only output as `draft_ready`.
- Do not infer the real spec from assignment name or description alone.
- Do not turn recurrence, points, or opportunity tier into a grade promise.

## Phase 1: Resolve the selected opportunity

Read the current private opportunity report and resolve the student's number
exactly. Verify against current read-only Canvas metadata that:

- the candidate still belongs to one course;
- its representative pattern still exists;
- the course is active (`is_course_active(..., grace_days=7)`; ended courses
  outside that grace period are ineligible);
- the candidate has not already been superseded by a working route;
- its opportunity evidence was based on representative real specifications,
  not names or metadata alone.

Reject cross-course combinations. If the student selected several patterns
from the same course, proceed only when they share one repeatable workflow and
one verification model; otherwise ask them to select one.

If the candidate disappeared or materially changed, do not silently substitute
another. Explain the drift and return to `canvas-skill-opportunity` for a fresh
report.

The full-course fingerprint triage belongs to `canvas-skill-opportunity`, not
Bootstrap: it may use `bucket_recurring(..., min_freq=3)` and divide evidence
into `main`, `likely-real`, and `noise` groups, with noise hidden by default and
too-little-history candidates labeled lower-confidence. Bootstrap consumes the
student-selected report entry and must not turn empty routes into a second,
competing ranking pass.

## Phase 2: Re-investigate the real workflow

Opportunity analysis is intentionally lightweight. Bootstrap must re-read the
chosen pattern deeply before authoring anything.

Sample at least two representative assignments when available, including the
most recent and one older instance. For each sample, follow every relevant
pointer from the Canvas description to the actual source of truth:

- assignment attachments;
- course front page and syllabus pointers;
- module pages and linked files;
- external specification pages;
- rubric or grading criteria;
- submission/delivery format.

Treat the assignment title and description as routing hints. Do not assume a
thin description is complete.

For every sample, perform a three-part reachability check:

1. the real instruction source is identified;
2. every required referenced material is located;
3. each located source can actually be read or downloaded without a live
   attempt or other mutation.

Name every missing or login-locked source in one concise clarification. Never
turn a missing source into a silent “unknown.” If the student cannot provide a
required source, the viability gate fails.

Read-only quiz policy projections may be used when the opportunity involves a
quiz: allowed attempts, feedback timing, answer visibility, and scoring policy.
Never start an attempt to discover those facts; do not retain raw answers,
answer identifiers, private feedback bodies, or exact scores.

## Phase 3: Design and independent review

Draft a private workflow model containing:

- how the real spec and required inputs are found each run;
- ordered production stages;
- the concrete local deliverable or explicit manual handoff;
- measurable verification checks that write `verification.log`;
- optional polish/review behavior;
- canonical `result.json` outcomes;
- failure and retry limits;
- the intended existing base capability, when one applies.

Verification checks must return numbers or yes/no results. “Looks good,”
“follows the rubric,” and similarly subjective placeholders are not checks.

Use native Codex subagents for three bounded reviews. Run rubric-coverage and
verification-checklist review in parallel, then run the feasibility simulation
against one representative sample after their findings are incorporated:

1. **Rubric coverage reviewer** — enumerate every requirement and identify
   workflow omissions. Revise and re-review up to two times.
2. **Verification designer** — produce specific measurements and thresholds;
   add a noisy failure check for any residual uncovered requirement.
3. **Feasibility simulator** — map each workflow step to available inputs and
   concrete outputs, then map every output to a check. Revise and re-run once
   when a step, output, or check is orphaned.

These are Codex native subagent handoffs, not Claude `Agent(...)` calls and not
shell-launched model sessions. Give each reviewer only the sanitized evidence
needed for its role. Keep reviewer transcripts and private evidence out of the
tracked skill.

Categorize review findings before talking to the student:

- resolved implementation details go silently into the workflow;
- choices that change the delivered content or user experience go into one
  batched question;
- low-confidence engineering branches go into private calibration notes.

Do not dump reviewer JSON or internal workflow tables into chat.

## Phase 4: Viability gate

All six conditions must be true before a skill can become ready:

1. Real instructions have a stable, reachable location.
2. Every required input/material is reachable or has an explicit manual handoff.
3. The response workflow repeats in substance, not merely in assignment naming.
4. The deliverable can be produced locally without an unauthorized Canvas
   mutation.
5. Completion checks are measurable and can write an all-PASS-or-fail
   `verification.log`.
6. A public-safe workflow can be separated cleanly from the private local facts.

Intrinsic impossibilities such as a proctored/LockDown environment or mandatory
in-person identity action fail the gate for automation and route only to manual
handling. A source that neither Codex nor the student can obtain also fails.

When the gate fails:

- do not write a ready route;
- if a scaffold was created, retain `<!-- UNFILLED_SKELETON v1 -->` and make its
  dispatch guard return canonical `status: "error"` with
  `deferred_to_next_run: true`;
- explicitly state which gate failed;
- offer the next candidate from the saved opportunity report;
- stop without executing an assignment.

## Phase 5: One batched student decision

Ask once, in plain language, only for facts that change the delivered result:

- confirm a genuinely uncertain task-family/routing judgment, if any;
- provide an unreachable required resource, if they can;
- choose the desired voice/format or review behavior when the assignment needs
  that choice;
- approve or reject the neutral public skill name;
- choose whether to run one **local draft-only calibration** on a named real
  assignment now.

Default calibration choice is no until the student explicitly says yes. Skill
creation approval and calibration-draft approval are separate. Neither one
authorizes submission, upload, or any quiz attempt/action.

Do not ask the student to decide internal retry counts, parsing methods, file
hashes, or other engineering details. If they revise a choice, re-render the
single batch once for confirmation; do not drip questions over many turns.

## Phase 6: Write the guarded Codex skill and private overlay

The tracked skill must have valid frontmatter:

```yaml
---
name: canvas-<safe-name>
description: Handles one repeatable Canvas assignment workflow using a private local overlay and produces verified drafts only by default.
---
```

While incomplete, the first body line after frontmatter is:

```text
<!-- UNFILLED_SKELETON v1 -->
```

The incomplete-skeleton guard must stop a dispatch, write a canonical error
result, set `deferred_to_next_run: true`, and create no draft, upload, quiz
attempt, or submission. A sentinel can never count as `draft_ready`.

The generated guard says: **STOP if you are Codex reading this from an execute
dispatch.** Until authoring finishes, write the error result with
`deferred_to_next_run=true` and stop.

The completed public-safe skill must describe, without local identifiers:

- its invocation contract from `canvas-execute`;
- loading and validating the private overlay;
- real-spec discovery rather than trusting Canvas description;
- ordered production stages;
- measurable verification and `verification.log`;
- canonical result statuses (`draft_ready`, `submitted`, `skipped`, `error`);
- `draft_ready` only for an existing substantive deliverable;
- default draft-only behavior and the separate runtime mutation-receipt rule;
- stage-by-stage calibration mode;
- failure recovery and manual handoff.

The private overlay stores current course facts, selected pattern matcher,
source locations, workflow parameters, verification thresholds, calibration
notes, and:

```text
first_run_calibration_done: false
```

Remove `UNFILLED_SKELETON` only after the viability gate passes, the batched
student decision is confirmed, every public section is filled, and the private
overlay exists and validates. Never expose private overlay content in the
tracked skill.

If a non-sentinel skill already exists at the target path, ask before replacing
it and default to preserving it. Replace only the selected course block in an
existing private overlay; preserve all unrelated blocks and user changes.

## Phase 7: Write the route atomically

Do this only for a completed, sentinel-free skill whose private overlay exists.

1. Read `courses.yaml`; coerce `routes: null` to `{}`.
2. Preserve every existing route and unrelated setting.
3. Add or update only the selected local course route.
4. Store the canonical `canvas-*` skill name expected by
   `src.routes.resolve_skill(route, assignment)`.
5. Write a sibling temporary file, validate it can be loaded, then replace the
   original with `os.replace`.

Do not embed a legacy-alias table in Bootstrap. The shared resolver used by
`src.router` owns canonical/legacy translation. New routes write canonical
names; later plan items consume the resolver's canonical name.

## Phase 8: First-run calibration (only with explicit draft consent)

Calibration is a narrow exception for one local draft; it is not daily scan or
execute. Run it only when:

- the student explicitly approved calibration on the named assignment;
- the assignment matches the selected recurring pattern;
- the real spec and materials are available;
- the task does not require a live quiz attempt or any other Canvas mutation;
- `first_run_calibration_done` is false.

Use a native Codex skill handoff to the newly created skill in stage-by-stage,
draft-only mode. Pass the exact assignment context and a private calibration
work directory derived by the shared stable identity helper
(`course-<course_id>__assignment-<assignment_id>`), never by mutable names. Run
one stage at a time, stop after each stage artifact, and let
the student review the real output. Do not use `canvas-execute`, do not create a
daily approval plan, and do not claim submission.

For substantive feedback, spawn one native Codex feedback-categorization
subagent and classify each piece as:

- `one_off` — repair only this draft;
- `recurring_pattern` — propose a private overlay change;
- `workflow_change` — propose a private workflow change.

Show recurring/workflow changes to the student before writing them. Preserve
confirmed changes incrementally. After the final verified substantive draft,
ask whether to set `first_run_calibration_done: true`. If they defer, leave it
false with a short private dissent/retry note. If any stage errors, remove the
calibration control marker, leave the flag false, report the concrete gap, and
stop.

If there is no safe matching assignment or no explicit calibration consent,
skip calibration and leave the flag false. The first later assignment approved
through `canvas-execute` can enter the equivalent calibration branch.

No placeholder, outline-only file, empty template, or sentinel output may pass
calibration or be recorded as `draft_ready`.

## Phase 9: Closeout and stop

Report:

- whether the viability gate passed;
- the neutral skill alias created or preserved;
- whether the local route was installed;
- whether calibration ran and, if so, whether it was locked in;
- any unresolved source, verification, or workflow risk;
- exactly one next action: `canvas-scan`, retry this candidate, or choose the
  next opportunity candidate.

Then stop. Never continue directly into scan or execute.

## Mutation authority reminder

Bootstrap, opportunity selection, route creation, and calibration-draft consent
never create Canvas mutation authority. Uploading/submitting and quiz
start/answer/complete actions require a separate, scoped authorization receipt
consumed by the shared runtime for the exact course, assignment, action, and
valid time window. Bootstrap must not create, infer, or consume that receipt.
