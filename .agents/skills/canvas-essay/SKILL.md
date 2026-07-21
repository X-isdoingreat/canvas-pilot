---
name: canvas-essay
description: Use for an approved long academic-writing assignment routed by canvas-execute after the deterministic writing router selects essay. Build, audit, humanize when configured, and return a verified local draft without submitting.
---

# canvas-essay

Produce one verified long-form academic draft. The real specification may live
in Canvas modules, attached files, or an instructor site; the Canvas summary is
only a routing hint.

## Contract

Require `course_id`, `assignment_id`, current assignment snapshot, approved
plan item, and `run_dir` from `canvas-execute`. The work directory is exactly:

```python
from src.course_artifacts import ensure_stable_work_dir

work_dir = ensure_stable_work_dir(run_dir, course_id, assignment_id)
```

Its name is `course-<course_id>__assignment-<assignment_id>`. Never use a
course or assignment title as durable identity.

This skill performs read-only Canvas discovery and local file creation. It
never uploads or submits. An overlay flag, plan approval, or prose instruction
is not mutation authority. A later exact-target command may enter only through
`canvas-submit`, which issues and validates an
origin/course/assignment/action/session-exact signed receipt.

Write one `result.json` through `src.course_artifacts.write_course_result`:

- `draft_ready`: verified draft exists;
- `skipped`: intrinsically manual assignment;
- `error`: required spec/source is missing or verification remains failed.

Do not use noncanonical result statuses.

## Route check

Confirm `src.ac_eng_router.route_ac_eng_assignment(...) == "essay"` unless the
approved plan contains an explicit essay override. Route short annotations and
worksheets to `canvas-reading-annotation`; route quizzes, code work, and
zyBook-backed work to their specialized skills.

## Private overlay

Read `_private/canvas-essay-app.md` and select the current course block. The
overlay may define:

- where the real spec and samples live;
- voice register and citation style;
- figure/film-caption conventions;
- persona and humanizer settings;
- assignment-name routing patterns.

If the overlay or course block is missing, write `error` with
`reason_code=missing_course_overlay`. First-run setup/bootstrap owns creating
private course configuration; this skill must not invent it.

Overlay text may guide drafting but never authorize a Canvas mutation.

## Artifact tree

```text
spec.md
sources/
sample_anchors.md
research_findings.md          # conditional
outline.md
draft/essay.pre-humanizer.docx
draft/essay.docx
audit/round-1.json
verification.log
result.json
```

Keep sources, audit evidence, and pre-humanizer text so later review can compare
meaning and rubric coverage.

## Stage 1: reconstruct the specification

Use existing read-only `src.canvas_client` helpers to inspect the assignment,
front page, modules, syllabus, rubric, attached files, and linked
instructor-hosted pages. Download every required source into `sources/`.

Write `spec.md` with:

- exact prompt and deliverable;
- minimum/maximum word or page count;
- required sources, evidence, sections, quotations, figures, or films;
- citation style and submission format;
- every mechanically checkable rubric criterion;
- unresolved ambiguity labeled as ambiguity, not fact.

If the prompt or a required source cannot be located and the student cannot
supply it, write `error`. Do not draft from the assignment title alone.

## Stage 2: load voice and examples

Load the private persona profile only if configured. Convert persona fields to
concrete tone and argument-structure guidance; never place profile labels in
the essay body.

Read representative files from the overlay-declared sample directory. Extract
small structural anchors—introduction shape, topic-sentence pattern, source
weaving, conclusion shape—into `sample_anchors.md`. Do not copy sample content.
If samples are absent, use a generic structure only when the overlay permits
that fallback and record the limitation.

## Stage 3: research before improvising

Run this stage when the prompt has a new hybrid form, an unfamiliar required
section, or recent feedback relevant to the current rubric.

Spawn these native Codex subagents in parallel with minimal raw inputs:

1. **spec verifier** — read `spec.md`; list literal requirements, numeric
   constraints, and ambiguities in under 400 words.
2. **quality inferrer** — read `spec.md` plus up to five same-course grader
   feedback records; infer recurring grading risks and testable gates. Quote
   feedback exactly and distinguish inference.
3. **template-fit checker** (only for a genuinely new shape) — compare the
   requested form to the proposed outline and identify uncovered requirements.

The main Codex session writes their outputs to `research_findings.md`, resolves
conflicts, and owns all drafting decisions. Subagents do not modify files.

## Stage 4: outline and draft

Build `outline.md` before prose. It must map each prompt/rubric requirement to a
section and identify the thesis, topic sentences, source evidence, and
transitions.

Draft section by section into `draft/essay.pre-humanizer.docx`:

- follow the overlay voice register;
- keep thesis and topic sentences directly responsive to the prompt;
- ground every quotation/paraphrase in a source and matching citation;
- keep required personal/source balance measurable;
- apply figure captions and film timestamps exactly as specified;
- create the Works Cited/References list from actual used sources only;
- never leave bracketed answer placeholders.

Preserve an evidence map in metadata or an adjacent audit file so a reviewer
can trace claims to sources.

## Stage 5: deterministic verification

Write `verification.log` with actual values, at minimum:

- body word count against both limits;
- required section count and heading presence;
- in-text citations matched to bibliography entries;
- required source/citation/figure/table/film counts;
- unresolved placeholders from
  `src.course_artifacts.unresolved_placeholders`;
- target file opens through `python-docx` and contains non-empty body text.

Feed failed measurements back into the draft and retry at most three rounds.
Persistent failures produce `error`.

## Stage 6: fresh semantic audit

Spawn one independent native Codex audit subagent with `spec.md`, raw source
excerpts, extracted draft text, `research_findings.md` when present, and recent
grader feedback. Require a strict JSON array whose entries contain:

```json
{
  "severity": "HIGH",
  "kind": "spec-violation",
  "gap": "one line",
  "spec_anchor": "exact text or MISSING",
  "deliverable_anchor": "exact text or MISSING",
  "fix_suggestion": "specific repair"
}
```

Allowed kinds include `spec-violation`, `historical-risk`,
`ambiguity-unresolved`, `format-mismatch`, `source-grounding-risk`,
`voice-register-drift`, and `personal-vs-source-imbalance`.

Require checks for thesis/prompt fit, uncited source overlap, citation/reference
consistency, voice, source-personal balance, and every rubric criterion. Save
`audit/round-N.json` atomically. Repair HIGH gaps and rerun both deterministic
verification and audit, at most three rounds. Remaining HIGH gaps produce
`error`.

## Stage 7: humanizer handoff

If the overlay enables humanization, invoke the Codex
`canvas-humanizer` skill with absolute paths:

```text
draft_path=<work>/draft/essay.pre-humanizer.docx
output_path=<work>/draft/essay.docx
voice_register=<overlay value>
course_id=<course_id>
assignment_id=<assignment_id>
work_dir=<stable work directory>
```

The humanizer is a local-file transformation. After it returns, rerun word
count, citation matching, placeholder, structure, and source-grounding checks.
If the transformation fails, preserve the pre-humanizer draft as
`draft/essay.docx`, record the diagnostic in result metadata, and continue only
if the verified original draft is intact.

If humanization is disabled, copy the verified pre-humanizer draft to the
canonical `draft/essay.docx`.

## Stage 8: final result

Open the canonical DOCX one last time, confirm it is non-empty, and ensure
`verification.log` has no executable FAIL. Then write:

```python
from src.course_artifacts import write_course_result

write_course_result(
    work_dir,
    status="draft_ready",
    draft_path=work_dir / "draft" / "essay.docx",
    notes="Verified essay draft; no Canvas mutation performed.",
    metadata={
        "skill": "canvas-essay",
        "verification_log_path": str(work_dir / "verification.log"),
        "humanizer_applied": humanizer_applied,
        "audit_rounds": audit_rounds,
    },
)
```

## First-run stage mode

Honor a single-stage invocation only when
`<work_dir>/.first_run_stage_by_stage` exists. Supported stages are
`parse-spec`, `load-samples`, `research`, `outline`, `draft`, `verify`, `audit`,
`humanize`, and `output`. Write `stages/<stage>.done` and stop. Daily execution
runs the complete pipeline.
