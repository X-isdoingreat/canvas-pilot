---
name: canvas-skill-opportunity
description: Use after first-run Canvas setup or when the user asks which recurring Canvas work should become the first durable course skill. Inspect representative real specifications and Canvas feedback policy, make a qualitative Agent judgment, write a private opportunity report, and stop for the user's choice.
---

# Canvas Skill Opportunity

Choose the best **first durable workflow**, not merely the easiest-looking
assignment. This is an Agent judgment protocol. Deterministic code may discover
recurrence and project private data, but it must not decide the recommendation.

## Contract

- Enter after `canvas-setup` verifies authentication and finds no ready routes,
  or when the user explicitly asks for skill opportunities.
- Write only:
  - `runs/<today>/skill-opportunities.json`
  - `runs/<today>/skill-opportunities.md`
- Keep `.claude/` read-only.
- Never start or consume a quiz attempt merely to classify it.
- Never solve, draft, answer, upload, submit, create a route, or create a skill.
- Never call `canvas-scan`, `canvas-execute`, or a course-solving skill.
- Stop for one numbered user choice. Selection authorizes only the later
  `canvas-bootstrap` design check; it does not authorize assignment submission.

## 1. Establish The Read-Only Boundary

Read `AGENTS.md`, `courses.yaml`, and setup state. Verify Canvas authentication
if it has not been verified in this session. Before inspecting course data, say:

```text
I will read recurring assignment instructions and Canvas feedback settings to
recommend one reusable workflow. I will not do work, start an attempt, upload,
submit, or create a skill.
```

Before writing, verify `runs/` is gitignored. Stop if it is not.

## 2. Discover Recurrence As Fact

Use the existing factual helpers:

```python
from src import canvas_client as cv
from src.opportunity_evidence import derive_quiz_feedback_capabilities
from src.recurring_patterns import bucket_recurring, is_course_active
```

For each active course, call `cv.list_assignments_for_opportunity(course_id)`
once, apply the existing 7-day term grace period, and call
`bucket_recurring(items, min_freq=3)`. The dedicated list helper excludes
student submission state. Retain the assignment IDs belonging to each returned
bucket, future occurrence count, known future points, and current route
coverage. These are evidence and later tie-breakers, not a verdict.

Do not infer task family, response length, or suitability from course name,
assignment title, or `submission_types` alone. A Canvas upload may be code, a
Word accounting worksheet, or a long essay; discovery cannot tell which.

## 3. Inspect Representative Real Specifications

For each plausible recurring bucket, use
`cv.get_assignment_spec_for_opportunity(course_id, assignment_id)` to read
enough representative assignments to establish whether the **response
pattern** repeats. This helper returns an allowlisted real-spec projection and
does not request a submission include:

1. Read the full assignment description and rubric.
2. Inspect attachment metadata and read required attached Word, Excel, PDF,
   starter-code, data, or template files when accessible.
3. Follow relevant module pages, Canvas pages, and instructor/source pointers
   to the real specification. Do not treat a thin Canvas description as the
   specification.
4. Compare at least two instances when two exist. Read additional instances
   when their required deliverables disagree. If stability still cannot be
   established, use `insufficient_evidence`.

Do not replace this helper with generic `get_assignment`, which requests an
embedded `submission` object. If another source unexpectedly embeds student
state, project it away before the Agent inspects or stores the specification.

Record derived facts, IDs, and source locations in the private report; do not
copy full bodies, rubric text, or attachment contents into it. Never read or
retain a student's prior answer content for task classification.

Extract these facts:

- actual task family and primary deliverable
- stable response pattern and whether the required inputs are reachable
- Canvas-native or file-upload delivery path
- number and independence of response units
- estimated length and role of the **main continuous prose unit**
- required live, physical, group, proctored, or unsupported external work
- plausible pre-submit checks
- post-submit feedback and retry policy, with evidence confidence

## 4. Apply Broad Task-Fit Priors

Treat the following as strong first-skill candidates when their response
pattern repeats and their inputs and Canvas delivery path are reachable:

- Canvas-submittable code of any length, even without supplied tests
- mostly objective Canvas quizzes: choice, true/false, matching, numeric, and
  other objectively checkable items
- quantitative math, accounting, economics, statistics, finance, and business
  work; a formal regression verifier is not required
- structured Word, Excel, or PDF accounting/business work, worksheets, tables,
  calculations, and template-driven documents
- independent short answers and short reading/writing annotations

Use response shape, not aggregate word count. Twenty independent annotations
of 10-20 words remain a strong candidate even though their combined total may
exceed 200 words. Conversely, a main or central continuous prose unit around
200 words or more is a strong default demoter for the **first** skill because
voice, coherence, and review cost compound. This is not a mechanical universal
hard gate: ancillary prose in a code, accounting, or quantitative deliverable
must not make the central task look like an essay.

Long essays, research prose, personal reflection, and creative writing usually
belong in `assist_only`. Required external-site interaction, live performance,
physical work, proctoring, or group participation is `unsupported` unless an
already-verified Canvas Pilot path can complete the whole required deliverable.

## 5. Evaluate Review In Two Separate Layers

### Pre-submit review

Identify reasonable checks without demanding an external validator:

- code: run, compile, inspect interfaces, examples, and constraints
- accounting/finance: recompute, reconcile, balance, and cross-foot
- math/statistics/economics: independent derivation, units, assumptions,
  direction, and magnitude checks
- structured documents: required-field, source, calculation, rubric, and
  format coverage
- objective questions: independent solving and source cross-checking

Formal tests improve confidence but are not an eligibility gate. Long code
without supplied tests stays strong when its specification, inputs, and Canvas
submission path are complete.

### Post-submit feedback and retry

For quizzes and other retryable work, separately establish:

- `allowed_attempts`
- whether results appear before the next attempt
- total-score visibility
- item-correctness visibility
- correct-answer visibility
- own-answer visibility
- feedback timing/window
- scoring policy (`keep_highest`, latest, average, or unknown)
- question reuse versus randomization between attempts
- evidence confidence and source

Use `derive_quiz_feedback_capabilities(quiz)` on static Canvas settings first;
it is a pure interpreter and never calls Canvas or starts an attempt. If an
already-completed sibling assignment can provide observed evidence, call only
`cv.get_submission_feedback_observation_for_opportunity(course_id,
assignment_id)`. That dedicated wrapper may inspect the existing submission
internally, but it returns only a minimal Boolean/enum projection. It must not
expose or retain raw prior answers, answer IDs, exact grades or scores,
feedback text, or submission payloads. A projected `own_response.record_present`
means only that a response record existed; it does **not** prove the student
can view its contents. Keep own-answer visibility `unknown` unless separate
safe evidence establishes it. If no safe projector exists, do not inspect the
raw record: leave the capability `unknown`.

Label feedback evidence `observed`, `declared`, `inferred`, or `unknown`.
Do not turn `declared` visibility into `observed` visibility. Two or more
attempts plus useful feedback **before retry** plus `keep_highest` strongly
promotes an otherwise suitable, mostly objective quiz. Merely allowing another
attempt without timely useful feedback does not receive the same promotion.
Never launch an attempt to discover any of these facts.

## 6. Make A Qualitative Judgment

Assign exactly one tier:

- `best_first_skill`: strongest complete, repeatable, high-fit opportunity
- `good_candidate`: suitable and reusable, but not the best first investment
- `later_candidate`: plausible, with material uncertainty or extra review cost
- `assist_only`: Agent assistance is useful, but the central deliverable should
  not be the first end-to-end skill
- `unsupported`: required delivery includes an unhandled external, live,
  physical, group, or proctored component
- `insufficient_evidence`: real specs, materials, stability, or feedback facts
  are too incomplete to judge honestly

Judge in this order:

1. unsupported or missing required inputs
2. actual task-family fit and central response shape
3. complete digital production and Canvas delivery path
4. repeatable response pattern across representative specs
5. pre-submit review and post-submit feedback/retry opportunity
6. existing route coverage

Within otherwise suitable tiers, use recurrence, scheduled future count, known
future points, and likely time saved to break ties. Missing points stay unknown.
Do not invent a 0-100 skillability score, grade-leverage score, grade prediction,
or precise probability. State evidence, uncertainties, and the reason for the
relative ordering.

## 7. Write The Private Report

Write JSON with this concrete shape:

```json
{
  "generated_at": "<ISO local time>",
  "scope": "read-only real-spec opportunity judgment",
  "decision_method": "agent_judgment",
  "grade_prediction": false,
  "candidates": [
    {
      "index": 1,
      "course_id": "<local only>",
      "course_name": "<local only>",
      "pattern": "Weekly task <N>",
      "tier": "best_first_skill",
      "recurrence_count": 8,
      "scheduled_future_count": 4,
      "scheduled_points_total": 40,
      "existing_route": null,
      "spec_evidence": {
        "sampled_assignment_ids": ["<local only>"],
        "source_locations": ["<local only>"],
        "stable_response_pattern": true,
        "task_family": "objective_quiz",
        "primary_deliverable": "Canvas quiz answers",
        "central_continuous_prose_words": 0,
        "independent_response_units": true,
        "inputs_reachable": true,
        "canvas_delivery_complete": true
      },
      "pre_submit_review": ["independent solve", "source cross-check"],
      "post_submit_policy": {
        "allowed_attempts": 2,
        "results_before_retry": true,
        "total_score_visible": true,
        "item_correctness_visible": true,
        "correct_answers_visible": null,
        "own_answers_visible": true,
        "feedback_timing": "immediate",
        "scoring_policy": "keep_highest",
        "question_reuse": "unknown",
        "evidence_confidence": "observed"
      },
      "reasons": ["..."],
      "demoters": [],
      "unknowns": ["question reuse"]
    }
  ]
}
```

Example values illustrate the schema only. Use locally observed facts. Use
`null`/`unknown` rather than guessing.

Write Markdown with a compact whitespace table, not a pipe table:

```text
#  local alias  tier  task family  recurring  future  feedback loop  strongest evidence  demoter/unknown
```

Then include:

- `Best first skill`: one candidate plus 2-4 evidence bullets, or
  `No eligible first skill` when none qualifies
- `Evidence inspected`: representative spec and source pointers
- `Why not the others`: one evidence-based reason per demoted candidate
- `Unknowns`: facts that remain unknown rather than inferred
- `Bootstrap must still verify`: materials, workflow, review steps, and handoff

The private files may contain real local names and IDs. In chat, use only
numbered aliases such as `Course 1 / Pattern 1`, link to the local Markdown
report, and never paste the private table, course names, IDs, private links, or
assignment examples.

## 8. Stop At User Choice

End with exactly one decision prompt in the user's language:

```text
Which number should Canvas Pilot turn into the first durable course skill?
```

Do not invoke `canvas-bootstrap` in the same turn. After the user selects a
number, pass that candidate and report path to Bootstrap. Bootstrap must still
verify the real materials, repeating workflow, review checks, and delivery
handoff before marking a route ready. If validation fails, offer the next saved
candidate. The choice never authorizes solving or submission.

## Failure Modes

| Failure | Required behavior |
|---|---|
| Canvas authentication fails | Stop with the exact setup repair step. |
| `runs/` is not ignored | Stop before writing private course data. |
| No bucket reaches `min_freq=3` | Report insufficient recurring evidence; do not invent a recommendation. |
| Representative real spec is inaccessible | Use `insufficient_evidence`; name the missing source. |
| Representative specs disagree | Read more samples; use `later_candidate` or `insufficient_evidence` if instability remains. |
| Feedback facts are incomplete | Keep each field `unknown`; do not award retry promotion. |
| Safe historical projection is unavailable | Do not read a raw submission payload. Use settings-only evidence. |
| Central deliverable is 200+ words of continuous prose | Default to `assist_only` or `later_candidate`, with evidence; do not apply a mechanical gate. |
| Required external/live/physical/group/proctored step exists | Use `unsupported`. |
| Every candidate is covered, unsupported, or insufficient | Write `No eligible first skill` and stop. |

## Non-Negotiable Boundaries

- Do not write `assignments.json`, `plan.json`, `result.json`, `REPORT.md`, or
  `.scan_in_progress`.
- Do not retain raw prior answers, answer IDs, exact grades or scores, feedback
  text, submission payloads, or complete assignment/rubric/file contents.
- Do not create routes or per-course skills before the user's numbered choice.
- Do not promise correctness, a grade, or score improvement.
- Do not write `.claude`.
