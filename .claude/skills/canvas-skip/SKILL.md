---
name: canvas-skip
description: This skill should be used when an assignment was routed as `mixed_unsupported` (currently the zyBooks math course). Logs the assignment to the daily todo.md so the user can do it manually, and returns a `skipped` status to canvas-execute. Does no automation work.
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
---

# canvas-skip

Handler for assignments we don't currently automate (zyBooks-based math-course work).

## What you do

1. Read the assignment item passed by canvas-execute.
2. Append a section to `runs/<today>/todo.md` with:
   - Course name and assignment title
   - Due date
   - URL (`html_url`)
   - `submission_types`
   - Whether `description` mentions zyBooks (search for "zybook" case-insensitive)
   - First 400 chars of `description` as an excerpt
3. Return result:

```json
{
  "status": "skipped",
  "notes": "logged to todo.md"
}
```

## Future work

When a `browse` skill exists that can drive a headless browser to log into zyBooks, this skill becomes a router into that. For now, no automation.

## Important

- **Do NOT** try to fetch zyBooks content via Canvas API. There isn't any — it's all on zybooks.com behind their auth.
- **Do NOT** mark anything as `draft_ready` unless you actually produced a draft. `skipped` is the honest status.
