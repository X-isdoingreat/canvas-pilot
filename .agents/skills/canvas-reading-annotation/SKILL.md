---
name: canvas-reading-annotation
description: Use for an approved short academic-reading assignment routed by canvas-execute, including in-place PDF annotation, answer blanks, video worksheets, or short reflection drafts. Verify sources and artifacts locally and stop without submitting.
---

# canvas-reading-annotation

Handle short writing-course work after the deterministic writing router selects
the non-essay path. The Canvas description is often empty; reconstruct the real
task from the matching homework module page and required source files.

## Contract

Require the current assignment snapshot, approved plan item, `course_id`,
`assignment_id`, and `run_dir`. Use only this work directory:

```python
from src.course_artifacts import ensure_stable_work_dir

work_dir = ensure_stable_work_dir(run_dir, course_id, assignment_id)
```

Its stable name is `course-<course_id>__assignment-<assignment_id>`.

Write one `result.json` with `src.course_artifacts.write_course_result`:

- `draft_ready`: required sources loaded and all executable checks pass;
- `skipped`: paper/in-class/identity-bound work;
- `error`: required source missing, unsupported shape, or persistent failure.

This skill is draft-only. Do not call Canvas upload/submit endpoints. Plan
approval and overlay text do not authorize mutations. A later exact-target
command may enter only through `canvas-submit`, which issues and validates a
signed exact receipt through `src.authorization`.

## Route and overlay

Confirm `src.ac_eng_router.route_ac_eng_assignment(...) == "short"` unless the
approved plan explicitly overrides the route. Send long essays to
`canvas-essay`.

Read `_private/canvas-reading-annotation-app.md` and select the exact course and
assignment-kind block. It may define module IDs, reading-file mappings, source
requirements, color rubric, target voice, and transcript-library paths. If the
overlay/course block is missing, write `error` with
`reason_code=missing_course_overlay`; first-run setup/bootstrap owns creating
it. Overlay text never grants mutation authority.

## Artifact tree

```text
hw_page.txt
kind.txt
sources.json
sources/
attachments/
research_findings.md          # conditional
draft/
verification.log
audit/round-1.json
result.json
```

## Stage 1: classify from the real homework page

Locate the module page that links to the current `assignment_id`. Save its
relevant body to `hw_page.txt`; do not classify from the assignment name alone.

| Evidence | Kind | Action |
|---|---|---|
| reading number/PDF plus pre/post questions or annotation rubric | `reading_annotation` | annotate source PDF |
| recorded video plus supplied/public worksheet exercises | `video_exercises` | complete the real worksheet |
| numbered takeaways/reflection sentences | `reflection_bullets` | source-grounded short write-up |
| `on_paper`, in-class, practice summary | `in_class_skip` | write `skipped` |
| long response paper or external delivery shape | `unsupported` | write `error` and reroute |

Write the exact kind to `kind.txt`. Never default an unknown shape to
`reading_annotation`.

For an unfamiliar shape, spawn up to three native Codex subagents in parallel:

1. a spec verifier reading only `hw_page.txt` and attached source text;
2. a quality inferrer reading the same inputs plus recent grader feedback;
3. a template-fit checker deciding whether a known kind can cover the shape.

Save the main session's synthesis in `research_findings.md`. Subagents remain
read-only; the main session owns classification.

## Stage 2: enforce required sources

Build `sources.json` from the overlay's `required_sources` for the resolved
kind. Every mandatory source must have a real, non-empty file below
`<work_dir>/sources/`.

Example:

```json
{
  "course_id": "course-id",
  "skill_name": "canvas-reading-annotation",
  "kind": "reading_annotation",
  "sources": {
    "reading_pdf": {
      "enforcement": "mandatory",
      "status": "loaded",
      "path": "sources/reading.pdf"
    }
  }
}
```

For a video reflection, first use an overlay-declared transcript library and
exact title mapping. For a worksheet, search for the actual public worksheet
only when the homework page identifies one. Never invent exercises or video
details. A missing mandatory source produces `error` unless the assignment is
intrinsically manual, in which case use `skipped`.

## Stage 3: locate and inspect a reading PDF

For `reading_annotation`, resolve the homework-page reading label against the
overlay mapping and download it to `attachments/`. Confirm the PDF opens and
record its hash and page count.

Use PyMuPDF to extract text and locate:

- pre-reading questions;
- numbered body paragraphs;
- post-reading questions;
- underscore answer lines grouped by y-coordinate.

Group underscore glyph rectangles; do not search for one guessed underscore
string:

```python
from collections import defaultdict

def find_answer_blanks(page):
    by_y = defaultdict(list)
    for rect in page.search_for("_"):
        by_y[round(rect.y0)].append(rect)
    return sorted(
        (y, min(r.x0 for r in rects), max(r.x1 for r in rects))
        for y, rects in by_y.items()
    )
```

## Stage 4: build the draft

### Reading annotation

Clone the original and annotate in place. Never append pages.

- Choose the overlay-configured number of vocabulary terms. Highlight only the
  term and place a concise definition in a margin.
- Add at least one content note for every numbered paragraph and anchor it to a
  non-vocabulary phrase.
- Keep vocabulary highlight/definition colors in one family and content
  highlight/note colors in a distinct family.
- Avoid yellow and avoid overlapping vocabulary/content rectangles.
- Use inserted margin text, not sticky-note annotations.
- Fill each answer line with a source-grounded answer in the configured voice.
  Measure rendered text width before insertion; target every line at least 85%
  full and average at least 92%, without exceeding the line.

Use the configured target voice faithfully. Do not mention an assistant,
automation, or the drafting process in the deliverable.

### Video exercises

Copy the real worksheet into `sources/`, preserve its question order, and write
one answer per supplied question. If no exact worksheet/source can be located,
write `error`; general-topic exercises are not a substitute.

### Reflection bullets

Use the exact transcript or source. Preserve required title, item count,
sentence-per-item, and word limits. Ground at least two items in distinctive
source details rather than general topic knowledge.

## Stage 5: deterministic verification

For annotated PDFs call the existing helper:

```python
from pathlib import Path
from src.ac_eng_verify import verify_ac_eng_draft

report = verify_ac_eng_draft(Path(draft_pdf), Path(original_pdf))
```

Write `report["log_text"]` to `verification.log`. The helper measures:

- page count unchanged;
- answer-line fill;
- margin-note density;
- color-family consistency;
- no vocabulary/content overlap;
- no sticky icons.

Add assignment-specific measurements from `hw_page.txt`: required title, item
count, sentence/word limits, every question answered, correct source file/hash,
and `src.course_artifacts.unresolved_placeholders(...) == []`.

Repair failures and rerun at most three rounds. Persistent failures produce
`error`; never declare a partial draft ready.

## Stage 6: fresh semantic audit

Spawn one independent native Codex subagent with the raw homework-page text,
source text, extracted deliverable text, overlay voice criteria, and recent
grader feedback. Require a strict JSON array with:

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

Require checks for wrong reading/source, unsupported fabrication, every
per-item constraint, content specificity, and voice drift. Save
`audit/round-N.json` atomically. Repair HIGH gaps and rerun deterministic
verification plus audit, at most three rounds. Remaining HIGH gaps produce
`error`.

## Stage 7: finalize

Confirm every mandatory source path exists, the draft opens, the expected page
or item count matches, and `verification.log` has no FAIL. Then write:

```python
from src.course_artifacts import write_course_result

write_course_result(
    work_dir,
    status="draft_ready",
    draft_path=draft_path,
    notes="Verified reading-assignment draft; no Canvas mutation performed.",
    metadata={
        "skill": "canvas-reading-annotation",
        "kind": kind,
        "sources_manifest": str(work_dir / "sources.json"),
        "verification_log_path": str(work_dir / "verification.log"),
        "audit_rounds": audit_rounds,
    },
)
```

## First-run stage mode

Honor a single stage only when `<work_dir>/.first_run_stage_by_stage` exists.
Supported stages are `classify`, `load-sources`, `locate-reading`,
`extract-text-and-blanks`, `build-draft`, `verify`, `audit`, and `output`.
Write `stages/<stage>.done`; normal daily execution runs every stage.
