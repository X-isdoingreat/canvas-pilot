# zyBooks-Backed Pattern Example

This is a fake public-safe example. It does not describe a real course,
student, school, instructor, assignment, textbook, or Canvas instance.

## Course Snapshot

```json
{
  "course_id": 100003,
  "course_name": "Math Course C",
  "assignment_pattern": "weekly problem set from an external exercise list",
  "default_workflow": "zyBooks-backed workflow"
}
```

## What Canvas Usually Shows

Canvas lists the assigned exercise references. The full problem text is fetched
from the configured external source after the student has set up local access.

Example Canvas signal:

```text
Assignment: Problem Set 4
Due: 2026-09-20 23:59
Submission type: file upload
Description: Complete the listed exercises and upload a PDF.
```

## Recurring Pattern The Workflow Remembers

- Canvas is the instructor-selected source of which exercises are due.
- The external exercise source is used only to fetch the problem text.
- The output is a PDF draft with one section per assigned exercise.
- Verification counts expected exercises, subparts, and placeholder text.
- Default result is `draft_ready`; upload is manual unless explicitly authorized.

## What Persists Week To Week

| Remembered pattern | Changes each week |
|---|---|
| Where the assigned exercise list lives | Problem-set number, due date, and selected exercises |
| Expected PDF draft shape | Current exercises, subparts, and notation needs |
| Verification checklist | Current exercise count, subpart count, and review notes |
| Default approval/submission boundary | Which items the student approves this run |

## Approval Plan Shape

```json
{
  "generated_at": "2026-09-17T09:00:00-07:00",
  "expires_at": "2026-09-18T09:00:00-07:00",
  "items": [
    {
      "index": 3,
      "bucket": "soon",
      "course_id": 100003,
      "course_name": "Math Course C",
      "assignment_id": 200003,
      "assignment_name": "Problem Set 4",
      "due_at": "2026-09-20T23:59:00Z",
      "hours_left": 86.98,
      "live_state": "unsubmitted",
      "proposed_skill": "canvas-zybooks",
      "user_decision": null
    }
  ]
}
```

Why this matched: Canvas showed a `Problem Set N` exercise list; the remembered
course pattern says Canvas selects the due exercises and the external source
provides problem text.

## Verification Checklist

- Exercise list parsed from Canvas description.
- Problem text fetched for every assigned exercise.
- PDF contains one section per assigned exercise.
- No placeholder text remains.
- `result.json` includes `status: draft_ready` and a local `draft_path`.
