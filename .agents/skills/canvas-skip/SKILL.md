---
name: canvas-skip
description: Use when an approved Canvas plan item is manual, unsupported, explicitly deferred, or blocked by missing scoped mutation authority. It records one honest canonical skipped result and an idempotent manual todo, with no solving or Canvas mutation.
---

# Canvas Skip

`canvas-skip` is a result-producing manual handoff, not a lightweight homework
solver. It may be selected for an unsupported delivery type, confirmed
LockDown/proctored work, an in-person action, a user defer, missing required
input, or a mutation-dependent task whose scoped authorization receipt is
absent.

## Input contract

Accept the exact item context from `canvas-execute`, including:

- assignment and course identity/display labels;
- due time and student-facing URL when present;
- canonical stable ID-based work directory
  (`course-<course_id>__assignment-<assignment_id>`), never a mutable-name slug;
- the reason execute selected `canvas-skip`;
- whether the item should re-enter the next scan.

Do not rescan Canvas or infer a different assignment from names. Do not invoke
another course skill.

## Absolute no-action boundary

- Do not solve, draft, research, download private assignment content, or create a
  fake deliverable.
- Do not upload, submit, post a comment, or alter Canvas state.
- Do not start, answer/save, complete, or retake a quiz.
- Do not use browser automation to work around LockDown/proctoring.
- Do not mark anything `draft_ready` or `submitted`.
- A TODO, empty file, sentinel, skeleton, or placeholder is not a draft.

## Write an idempotent manual todo

When a human next step is useful, append or update one entry in
`runs/<today>/todo.md`. Use the assignment's stable local identity as the
deduplication key so retries do not create duplicate entries.

Include only runtime-local facts useful to the student:

- recognizable course alias and assignment title;
- due time;
- Canvas URL when available;
- why automation stopped;
- the concrete manual next step;
- whether it will reappear on the next scan.

Do not paste a long assignment description, private feedback, prior answers,
credentials, or raw API payload into the todo.

## Write the canonical result atomically

Write exactly one `<work_dir>/result.json` via a sibling temporary file and
`os.replace`:

```json
{
  "status": "skipped",
  "notes": "manual handling required: <specific reason>",
  "manual_action_required": true,
  "deferred_to_next_run": false
}
```

Set `deferred_to_next_run: true` only when the student deferred it, the required
input/authorization may arrive later, or retry is otherwise meaningful. Keep it
false for an intrinsic manual-only item that would otherwise recur forever.

The status must remain exactly `skipped`. Do not use legacy statuses and do not
claim that Canvas received anything.

Use `src.run_state.write_result` for validation plus the atomic write; do not
invent a second result validator in this skill.

After writing, parse the file back and confirm the status, notes, and boolean
fields. Return the work directory and concise manual next step to
`canvas-execute`; execute owns ledger, REPORT.md, delivery sync, and marker
cleanup.

## Authorization-specific skip

Plan approval is not Canvas mutation authority. If the item needs an upload,
submission, or quiz start/answer/complete action and the shared runtime has no
valid scoped authorization receipt, do not attempt the action. Record an honest
retryable skip explaining that the student must separately authorize that exact
mutation. Never create or infer a receipt in this skill.
