# Reading Annotation Pattern Example

This is a fake public-safe example. It does not describe a real course,
student, school, instructor, assignment, reading, or Canvas instance.

## Course Snapshot

```json
{
  "course_id": 100002,
  "course_name": "Writing Course B",
  "assignment_pattern": "weekly reading annotation",
  "default_workflow": "reading-annotation workflow"
}
```

## What Canvas Usually Shows

Canvas gives the weekly homework title, a due date, and a module link. The real
work is defined by a reading PDF and a rubric page in the module.

Example Canvas signal:

```text
Assignment: Week 5 Reading Notes
Due: 2026-09-19 12:30
Submission type: online upload
Description: Complete the reading worksheet and submit the annotated PDF.
```

## Recurring Pattern The Workflow Remembers

- The weekly module contains a reading PDF and a worksheet PDF.
- The workflow downloads both referenced files into `references/`.
- The output is an annotated PDF plus a filled worksheet draft.
- The student reviews the draft and adjusts tone manually before upload.
- Default result is `draft_ready`; the student reviews and uploads manually.

## What Persists Week To Week

| Remembered pattern | Changes each week |
|---|---|
| Where the reading and worksheet live | Week number, due date, and current module files |
| Expected annotated-PDF and worksheet shape | Current reading, prompts, and page count |
| Verification checklist | Current required annotations and review notes |
| Default approval/submission boundary | Which items the student approves this run |

## Approval Plan Shape

```json
{
  "generated_at": "2026-09-17T09:00:00-07:00",
  "expires_at": "2026-09-18T09:00:00-07:00",
  "items": [
    {
      "index": 2,
      "bucket": "urgent",
      "course_id": 100002,
      "course_name": "Writing Course B",
      "assignment_id": 200002,
      "assignment_name": "Week 5 Reading Notes",
      "due_at": "2026-09-19T12:30:00Z",
      "hours_left": 51.5,
      "live_state": "unsubmitted",
      "proposed_skill": "canvas-reading-annotation",
      "user_decision": null
    }
  ]
}
```

Why this matched: Canvas showed a `Week N` reading-notes item; the remembered
course pattern says the module contains the reading PDF and worksheet.

## Verification Checklist

- Reading PDF and worksheet PDF were found in the module.
- Annotated output has the same page count as the input PDF.
- Worksheet blanks are filled without overlapping nearby text.
- Notes and highlights are present where the fake rubric asks for them.
- `result.json` includes `status: draft_ready` and a local `draft_path`.
