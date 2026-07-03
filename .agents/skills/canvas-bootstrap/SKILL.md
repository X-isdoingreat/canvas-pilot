---
name: canvas-bootstrap
description: Set up Canvas Pilot in Codex for the first time, add a course route, or redesign a public-safe per-course Codex skill. Trigger when routes in courses.yaml are empty, when the user says to add/design/modify a Canvas course skill, or when canvas-scan cannot route assignments. Surveys recurring assignment patterns, asks the student to name skills, writes guarded .agents/skills/canvas-<name>/SKILL.md skeletons, and updates public-safe route config without copying Claude private course playbooks.
---

# Canvas Bootstrap

Use this skill to stand up public-safe Codex course skills. Treat `.claude/`
as read-only. Do not write `.claude`. Do not copy private Claude course
playbooks.

## Contract

- Entry points:
  - Manual: the user asks to set up Canvas Pilot, add a course, design a skill,
    or modify a skill.
  - Auto: `canvas-scan` detects `courses.yaml` routes are empty and hands off
    to this skill.
- Outputs:
  - `.agents/skills/canvas-<student-name>/SKILL.md`
  - a route entry mapping the course to `canvas-<student-name>`
- Non-goal:
  - Never write solving logic.
  - Never submit to Canvas.
  - Never include private course IDs, private URLs, instructor names, emails,
    or private Claude skill bodies in generic Codex docs.

## Step 1: Build Course Fingerprints

Read `courses.yaml`. If `routes` is empty or all entries are commented out,
use the Canvas client to inspect active courses. If routes exist, inspect the
configured courses too so a student can refresh or redesign later.

Use the project helpers when available:

```python
from src import canvas_client as cv
from src.recurring_patterns import bucket_recurring, is_course_active
```

For each candidate course:

1. Skip ended courses with a 7-day grace period.
2. Skip courses with zero assignments.
3. Call `bucket_recurring(items, min_freq=3)`.
4. Store:
   - course name
   - course identifier, kept local only
   - configured skill if present
   - recurring `patterns`
   - sub-threshold count
   - total assignment count

This fingerprint is factual measurement only. Do not label a course as code,
quiz, writing, or PDF based on vibes.

## Step 2: Render A Student Decision Table

Split the fingerprints:

- `main`: courses with at least one recurring pattern.
- `likely-real`: active courses with assignments but no recurring pattern yet.
- `noise`: inactive, empty, sandbox, orientation, training, demo, or otherwise
  low-signal courses.

Number continuously:

- Main numbers point to individual patterns.
- Likely-real numbers point to whole courses.
- Noise courses are hidden from default mapping unless the user explicitly asks
  to show them.

Show configured courses as already configured and do not make them eligible for
renaming in the same pass unless the user explicitly asks to redesign.

Use a compact whitespace table, not a pipe table. Keep internal words like
`submission_types`, API, endpoint, and list_modules out of the student-facing
text. Say "I looked around the course" rather than naming API calls.

Render three sections:

1. `main`: likely recurring work, numbered by pattern.
2. `likely-real`: real courses with too little history for recurring patterns,
   numbered by course and labeled lower-confidence.
3. `noise`: hidden by default with only a count; reveal only if the student
   asks to inspect ignored courses.

The table must teach the student how to name a skill without recommending a
name as the answer. Example lines may use made-up names only to demonstrate
format.

## Step 3: Parse Student Mapping

Accept mapping lines:

```text
1,2 -> pyhw
3 -> globalquiz
```

Normalize:

- separators: comma, space, plus, ampersand, and common Chinese separators
- arrows: `->` and equivalent arrow text
- skill name: strip a leading `canvas-`; Codex adds it back

Resolve every number through the lookup table.

Hard reject cross-course bundling:

- one mapping must refer to exactly one course
- one skill maps to one course
- if selected numbers span different courses, reject the line and ask the user
  to split it

Soft warn partial coverage:

- if the user selected only some patterns from a main course, say that
  unselected patterns will fall back to skip/manual handling unless they create
  another skill
- never auto-create extra skills

Likely-real course numbers mean the whole course, so there is no
partial-pattern warning for likely-real course mappings.

## Step 4: Design Dialogue Per Accepted Mapping

Walk one mapping at a time. Do not interleave courses.

Ask in plain language and save the student's answers into the generated
skeleton:

1. Where the assignment instructions live.
2. What verification checks prove a draft is done.
3. The student's normal workflow for this kind of assignment.
4. Verification execution is auto-filled: run checks and save
   `verification.log`.
5. Whether the student wants a polish/review step.
6. `result.json` is auto-filled.

Rules:

- If the student says they do not know, propose exactly one workflow or check
  set and ask for approval.
- Verification checks must produce numbers or yes/no outputs, not feelings.
- Do not write the assignment content in the skill.
- Do not auto-polish future work; prompt the student first.

## Step 5: Write Guarded Codex Skeleton

Write to:

```text
.agents/skills/canvas-<name>/SKILL.md
```

Do not write `.claude/skills`.

Generated skeleton frontmatter:

```yaml
---
name: canvas-<name>
description: Handles the selected Canvas assignment patterns for one course.
---
```

The first body line must be:

```text
<!-- UNFILLED_SKELETON v1 -->
```

Include this guard:

```text
> **STOP if you are Codex reading this from canvas-execute dispatch.**
> This generated skeleton is not ready until the student has completed the
> design dialogue. Write result.json with status="error" and
> deferred_to_next_run=true, then stop.
```

When and only when the six design sections are actually filled and approved,
remove the `UNFILLED_SKELETON` sentinel before saving the final skeleton.

Generated body must contain:

- course-at-a-glance fingerprint summary
- selected patterns or folded-course summary
- instruction location
- verification checks
- student workflow
- verification run step writing `verification.log`
- polish/review step
- `result.json` schema with status `draft_ready`, `skipped`, or `error`

## Step 6: Update Routes

Update the public-safe route config atomically:

1. Read `courses.yaml`.
2. Coerce `routes: null` to `{}`.
3. Add one route per generated skill.
4. Preserve existing routes.
5. Write to a temporary file.
6. Replace with `os.replace`.

If the public repo must avoid real course identifiers, keep generated examples
and docs generic. Real route values are local user config.

## Failure Modes

| Failure | Behavior |
|---|---|
| Canvas auth probe fails | Stop and tell the user to fix auth. |
| No active course has assignments | Stop and tell the user to rerun later. |
| Student input is ambiguous | Ask once; second failure stops bootstrap. |
| Cross-course mapping | Reject and ask for split mappings. |
| Existing Codex skill has sentinel | Safe to overwrite after confirmation. |
| Existing Codex skill has no sentinel | Ask before overwrite; default no. |

## Required Boundaries

- Do not copy `.claude/skills/canvas-*` playbooks into Codex.
- Do not copy private IDs or private URLs into `.agents/skills`.
- Do not write `.claude`.
- Do not execute assignments.
- Do not call `canvas-execute`.
- Do not submit anything.

