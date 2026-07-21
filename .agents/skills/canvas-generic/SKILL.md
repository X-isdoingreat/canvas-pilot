---
name: canvas-generic
description: Use for an approved Canvas assignment that no specialized course skill can handle. Investigate the real specification, build and verify a local draft artifact, and stop without submitting.
---

# canvas-generic

Produce a grounded draft for one approved assignment whose route is
`canvas-generic`. This is a runtime-designed fallback, not a shortcut around a
specialized course skill.

## Contract

Require these inputs from `canvas-execute`:

- `course_id`, `assignment_id`, and the assignment snapshot from the current
  `assignments.json`;
- an approved current plan item;
- `run_dir`, normally `runs/YYYY-MM-DD`;
- the exact work directory returned by
  `src.course_artifacts.stable_work_dir(run_dir, course_id, assignment_id)`.

The directory must be named
`course-<course_id>__assignment-<assignment_id>`. Do not use course or
assignment names as filesystem identity.

Write exactly one canonical `result.json` through
`src.course_artifacts.write_course_result`:

- `draft_ready` with an existing `draft_path` after all executable checks pass;
- `skipped` only for an intrinsically manual or unsupported assignment;
- `error` when required inputs remain unavailable or checks still fail after
  their retry limit.

This skill is draft-only. Never call Canvas `POST`/`PUT`, upload, submit, start
a quiz, or complete a quiz. Execution approval is not mutation authority. A
later submission workflow must independently validate a signed, target-exact
receipt with `src.authorization.validate_authorization_receipt`.

## Stop and route elsewhere

Do not use this fallback when the shape is already supported:

- code project → `canvas-ics33`;
- Classic Quiz → `canvas-inside`;
- long essay → `canvas-essay`;
- reading annotation or short worksheet → `canvas-reading-annotation`;
- zyBook-backed work → `canvas-zybooks`.

Use `skipped` for in-person attendance, paper-only delivery, identity checks,
oral defenses, proctored/lockdown work, or another intrinsically manual step.
Do not invent content when a required source is unavailable.

## Working tree

Create this structure under the stable work directory:

```text
spec.md
references/
investigation/rubric.md
investigation/unreachable.txt
investigation/review-a.json
pipeline_design.md
draft/
verification_checklist.md
verification.log
review-c.json
result.json
```

Use `src.course_artifacts.atomic_write_text` for small text artifacts and the
atomic writers in `src.run_state` for JSON.

## Optional recurring preferences

Compute the optional learnings path with:

```python
from src.overlay_utils import canvas_generic_overlay_path
from src.recurring_patterns import normalize

cluster_norm = normalize(assignment["name"])
learnings_path = canvas_generic_overlay_path(course_id, cluster_norm)
```

If the gitignored file exists, load only user preferences such as voice,
citation style, color choices, and recurring workflow adjustments. Never reuse
an old specification, rubric, answer, or pipeline as current evidence. Missing
or empty learnings are normal and do not block the assignment.

## Stage 1: collect the real specification

Use the read-only helpers that actually exist in `src.canvas_client`:

```python
from src import canvas_client as cv
from src.course_artifacts import redact_behavioral_rules

assignment = cv.get_assignment(course_id, assignment_id)
front_page = cv.get_front_page(course_id)
modules = cv.list_modules(course_id)
syllabus = cv.get_syllabus_body(course_id)
attached_files = cv.list_assignment_files(course_id, assignment_id)
rubric = cv.get_rubric(course_id, assignment_id)
```

Treat Canvas name and description as routing hints. Follow relevant module
items, attached files, front-page links, syllabus references, and
instructor-hosted specification links. Apply `redact_behavioral_rules` before
placing external prose in the working set.

Write `spec.md` with the deliverable, due date, points, submission types,
allowed extensions, numeric constraints, source requirements, and every
located specification URL. Label unverified interpretations as inference.

Download reachable files into `references/`. Record every failed source and
the observed reason in `investigation/unreachable.txt`.

## Stage 2: locate the rubric

Search in this order:

1. `cv.get_rubric(course_id, assignment_id)`;
2. assignment and attached-file text;
3. module pages, front page, and syllabus;
4. instructor-hosted specification pages.

Render criteria and point values to `investigation/rubric.md`. If no rubric is
published, say so literally and derive only clearly testable constraints from
the specification. A missing rubric alone does not justify invented criteria.

## Stage 3: independent investigation review

Spawn one bounded native Codex subagent with only the work-directory path and
this role:

> Read `spec.md`, `investigation/rubric.md`, `references/`, and
> `investigation/unreachable.txt`. Return strict JSON with
> `deliverable_clear`, `deliverable_summary`, `rubric_found`,
> `inputs_complete`, `missing_sources`, `blocking_unreachables`, `verdict`
> (`proceed|recover|stop`), and `recovery_actions`. Do not draft the answer.

Save the response as `investigation/review-a.json`.

- `recover`: perform the named read-only recovery actions and review again;
  maximum two recovery rounds.
- `stop`: write `error` when the missing item blocks the work, otherwise write
  `skipped` for an intrinsically manual item.
- `proceed`: continue.

Do not ask the subagent to reconstruct hidden context. Give it the raw local
artifacts.

## Stage 4: classify the artifact

Write the chosen mode and evidence to `pipeline_design.md`:

| Mode | Evidence and output |
|---|---|
| `doc_prose` | essay/paragraph/word-count criteria → DOCX or requested text format |
| `pdf_annotated` | a source PDF plus highlight/note rubric → annotated source PDF |
| `pdf_typed` | math/problem-set notation → typed PDF |
| `code` | scaffold, source extension, tests, or programming rubric → source tree/archive |
| `form_answers` | enumerated short questions and text entry → `draft/submission.txt` |
| `mixed` | specification requires more than one artifact → separate named outputs |

If the evidence does not support one mode, write `error` with
`reason_code=output_mode_unclear` instead of guessing.

## Stage 5: design and generate

Turn every rubric line into a generation requirement. Preserve exact numeric,
format, notation, citation, filename, and source constraints.

- `doc_prose`: outline, draft section by section, verify sources, then invoke
  `canvas-humanizer` only when the caller requested that pass. Keep the
  pre-humanized draft for comparison.
- `pdf_annotated`: clone the source PDF, annotate in place, and preserve page
  count. Follow any color and note-density rubric exactly.
- `pdf_typed`: solve every enumerated part, show required reasoning, render,
  and extract the rendered PDF text to catch missing glyphs.
- `code`: work only in a copied scaffold under `draft/`; run the supplied tests
  and language parser. Do not silently weaken tests.
- `form_answers`: map one non-empty answer to every numbered question.
- `mixed`: run each constituent pipeline independently and verify all parts.

Use no placeholder as a completed answer. Check with
`src.course_artifacts.unresolved_placeholders`.

## Stage 6: independent checklist design

Spawn a fresh native Codex subagent. Give it `spec.md`, `rubric.md`,
`pipeline_design.md`, and the draft. Ask it for a numbered checklist in which:

- numeric constraints name a real measurement and threshold;
- structural constraints name the expected location;
- parse/render/test checks name the executable command;
- subjective criteria are explicitly marked `human_review`.

Save `verification_checklist.md`. The subagent must not alter the draft.

## Stage 7: measure and repair

Run every executable checklist item and write `verification.log` lines as:

```text
PASS | requirement | measured: value
FAIL | requirement | measured: value
SKIP | requirement | reason: human_review
```

Use real measurements: word count, PyMuPDF page/text inspection, `ast.parse`,
test exit codes, citation matching, file hashes, and explicit item counts. Feed
failed checks back into generation and retry at most three times. Persistent
failures produce `error`, never a false `draft_ready`.

## Stage 8: independent coverage review

Spawn a third fresh native Codex subagent. Give it the raw rubric, checklist,
and verification log. Require strict JSON with `coverage_gaps`,
`false_pass_risks`, `human_review_items`, and verdict
`verification_sufficient|add_checks|human_review_required`.

Run at most two add-check rounds. Preserve subjective items in result metadata
for the student to inspect.

## Stage 9: finalize

Confirm the draft exists, opens or parses, contains no unresolved placeholder,
and matches allowed extensions. Then write:

```python
from src.course_artifacts import write_course_result

write_course_result(
    work_dir,
    status="draft_ready",
    draft_path=draft_path,
    notes="Verified local draft; no Canvas mutation performed.",
    metadata={
        "skill": "canvas-generic",
        "output_mode": output_mode,
        "verification_log_path": str(verification_log),
        "human_review_items": human_review_items,
    },
)
```

## First-run stage mode

Honor stage-by-stage execution only when both the invocation names one stage
and `<work_dir>/.first_run_stage_by_stage` exists. Run only that stage, write
`stages/<stage>.done`, and stop without writing a final result until the export
stage. Normal daily execution runs the full pipeline.
