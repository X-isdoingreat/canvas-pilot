# Code Course Pattern Example

This is a fake public-safe example. It does not describe a real course,
student, school, instructor, assignment, or Canvas instance.

## Course Snapshot

```json
{
  "course_id": 100001,
  "course_name": "Code Course A",
  "assignment_pattern": "weekly programming set",
  "default_workflow": "code-course workflow"
}
```

## What Canvas Usually Shows

Canvas assignment pages for this course usually contain a short title and due
date, but not the full programming spec.

Example Canvas signal:

```text
Assignment: Set 3 Problem 1
Due: 2026-09-18 23:59
Submission type: online upload
Description: See the course site for starter files and full instructions.
```

## Recurring Pattern The Workflow Remembers

- The real spec is linked from the course front page, not copied into the
  assignment description.
- Starter files are downloaded from a public fake URL pattern:
  `https://example.invalid/code-course-a/sets/{set_number}/starter.zip`
- The expected output is a zip bundle containing only the source files listed in
  the spec.
- Verification is mechanical: run the test command, check required files, and
  confirm the bundle does not include build artifacts.
- Default result is `draft_ready`; submission requires explicit authorization.

## What Persists Week To Week

| Remembered pattern | Changes each week |
|---|---|
| Where the real spec and starter files live | Set number, due date, and current starter archive |
| Expected draft bundle shape | Required files and current problem constraints |
| Verification checklist | Current tests, required outputs, and review notes |
| Default approval/submission boundary | Which items the student approves this run |

## Approval Plan Shape

```json
{
  "generated_at": "2026-09-17T09:00:00-07:00",
  "expires_at": "2026-09-18T09:00:00-07:00",
  "items": [
    {
      "index": 1,
      "bucket": "urgent",
      "course_id": 100001,
      "course_name": "Code Course A",
      "assignment_id": 200001,
      "assignment_name": "Set 3 Problem 1",
      "due_at": "2026-09-18T23:59:00Z",
      "hours_left": 38.98,
      "live_state": "unsubmitted",
      "proposed_skill": "canvas-code-course",
      "user_decision": null
    }
  ]
}
```

Why this matched: Canvas showed a `Set N` programming item; the remembered
course pattern says the real spec and starter files live on the course site.

## Verification Checklist

- Spec URL resolved from the fake course front page.
- Starter archive downloaded into the assignment work directory.
- Required files listed in the spec are present.
- Test command exits successfully.
- Bundle contains only allowed paths.
- `result.json` includes `status: draft_ready` and a local `draft_path`.
