---
name: canvas-zybooks
description: Use for an approved zyBook-backed math or discrete assignment routed by canvas-execute. Reconstruct the exact exercise set, solve and verify a local artifact, and stop before any zyBooks, GradeScope, or Canvas mutation.
---

# canvas-zybooks

Produce a verified local draft for written homework, take-home exams, or
reading-completion evidence whose real content is backed by zyBooks.

## Contract

Require `course_id`, `assignment_id`, current assignment snapshot, approved
plan item, and `run_dir`. Create the work directory with:

```python
from src.course_artifacts import ensure_stable_work_dir

work_dir = ensure_stable_work_dir(run_dir, course_id, assignment_id)
```

The name is exactly `course-<course_id>__assignment-<assignment_id>`.

Write one canonical result through
`src.course_artifacts.write_course_result`:

- `draft_ready`: local artifact exists and checks pass;
- `skipped`: intrinsically manual or unsupported protected work;
- `error`: missing required source/authentication or persistent verification
  failure.

This skill is read-only against Canvas and zyBooks and never uploads to
GradeScope. Do not call `src.zybooks_client.post`, Canvas `POST`/`PUT`, or a
submission endpoint. A later mutation workflow needs its own explicit authority;
for Canvas that means a signed target/action/session-exact receipt validated by
`src.authorization`.

## Private overlay

Read `_private/canvas-zybooks-app.md` and select the current course block. It
may define the zyBook code, local token path, course-context primer, instructor
notation, assignment naming patterns, and render settings.

If it is missing, write `error` with `reason_code=missing_course_overlay`.
Never place a JWT, cookie, real course identifier, or instructor identity in a
tracked skill or artifact meant for public release.

## Artifact tree

```text
spec.md
references/
zybook_exercises/
research_findings.md          # conditional
solutions.md
draft/solutions.pdf
verification.log
audit/round-1.json
result.json
```

## Stage 1: classify and parse the instructor specification

Classify from real evidence:

- Canvas HTML table of graded exercises → `written_homework`;
- attached exam/problem-set PDF → `take_home_exam`;
- assigned sections without a written deliverable → `reading_completion`.

For the standard HTML table, call the existing deterministic parser:

```python
from src.zybooks_spec_parser import parse_homework_spec

exercise_refs = parse_homework_spec(assignment.get("description") or "")
```

The parser intentionally extracts only the graded column. Save exact
`chapter.section.exercise` references and requested parts to `spec.md`. For a
PDF, download the actual file and extract every question/part. If the exercise
set cannot be established, write `error` rather than guessing from the title.

## Stage 2: read exercise content

Validate local authentication with a read-only call such as
`src.zybooks_client.whoami()`. Read section exercises with
`src.zybooks_client.exercises_for_section(chapter, section)` and convert each
matching resource using `src.zybooks_client.exercise_to_dict(...)`.

Cache only the assignment-local normalized exercise text under
`zybook_exercises/`; never copy the token. Match every requested reference and
part. A missing or expired token, missing section, or unmatched exercise is an
`error` with a precise reason and no fabricated substitute.

`reading_completion` remains read-only: produce a local checklist/study record
unless a separately authorized external workflow exists. Do not mark
participation or completion here.

## Stage 3: research before improvising

Use this stage for a new table shape, proof method, notation system, or current
rubric issue seen in recent feedback. Spawn these native Codex subagents in
parallel:

1. **spec verifier** — read `spec.md` and raw exercise text; list every required
   part, hard constraint, and ambiguity.
2. **quality inferrer** — read the same material plus recent grader comments;
   infer recurring notation and reasoning risks, clearly labeling inference.
3. **template-fit checker** — only when the standard homework/exam/reading flow
   does not cover the deliverable.

Keep subagents read-only and give them raw artifacts rather than expected
answers. Save the main session's synthesis to `research_findings.md`.

## Stage 4: solve

Write `solutions.md` with one stable heading per requested exercise and part.
For every answer:

- apply the overlay course-context primer and exact notation;
- show the required reasoning and name laws when required;
- preserve problem variables and quantifiers;
- distinguish computed facts from interpretation;
- include all and only the assigned parts;
- leave no `[answer needed]`, TODO, or placeholder.

For an exam or unusual problem, independently recompute/check the answer before
rendering. Do not treat a model's agreement with itself as proof.

## Stage 5: render

Render the requested format, normally `draft/solutions.pdf`, using the
overlay-declared LaTeX/MathJax settings. Extract text from the rendered PDF and
inspect representative pages so missing glyphs, clipped formulas, blank pages,
and pagination errors are observable.

## Stage 6: deterministic verification

Write `verification.log` with actual measurements:

- expected exercise/part set equals rendered exercise/part set;
- no duplicate or missing heading;
- no unresolved placeholder from
  `src.course_artifacts.unresolved_placeholders`;
- every required law/notation marker appears where specified;
- PDF opens, has nonzero pages, and extracted text is non-empty;
- every requested reference is backed by a cached exercise source.

Repair failures and rerun at most three rounds. Persistent failures produce
`error`.

## Stage 7: fresh semantic audit

Spawn one independent native Codex subagent with `spec.md`, normalized exercise
text, extracted PDF text, `research_findings.md` when present, overlay notation
rules, and recent feedback. Require a strict JSON array with exact
`spec_anchor`, exact `deliverable_anchor`, severity, kind, gap, and concrete fix.

Require checks for missing subparts, invalid steps, notation drift, unsupported
assumptions, and render/format mismatch. Save `audit/round-N.json`. Repair HIGH
gaps and rerun deterministic checks plus audit, at most three rounds. Remaining
HIGH gaps produce `error`.

## Stage 8: finalize

Confirm the source-to-solution mapping is complete and the PDF opens. Then
write:

```python
from src.course_artifacts import write_course_result

write_course_result(
    work_dir,
    status="draft_ready",
    draft_path=work_dir / "draft" / "solutions.pdf",
    notes="Verified local zyBook-backed draft; no platform mutation performed.",
    metadata={
        "skill": "canvas-zybooks",
        "kind": kind,
        "exercise_count": len(exercise_refs),
        "verification_log_path": str(work_dir / "verification.log"),
        "delivery": "manual",
    },
)
```

Do not claim a real zyBooks or GradeScope end-to-end verification unless it was
actually run with current external access. Local fixture/parser/render tests are
not external-platform evidence.

## First-run stage mode

Honor one stage only when `<work_dir>/.first_run_stage_by_stage` exists.
Supported stages: `classify`, `parse-spec`, `fetch-exercises`, `research`,
`solve`, `render`, `verify`, `audit`, `output`. Write
`stages/<stage>.done`; normal daily execution runs all stages.
