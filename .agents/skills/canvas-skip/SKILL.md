---
name: canvas-skip
description: Mark an unsupported or deferred Canvas assignment as skipped by writing a result.json and optional todo.md entry. No automation.
---

# Canvas Skip

Use this skill when an assignment is unsupported, deferred, manually handled, or outside the current Codex sidecar scope.

## Contract

- No automation.
- Do not solve the assignment.
- Do not submit anything.
- Write a `result.json` with `status` set to `skipped`.
- Include clear notes explaining why it was skipped.
- If useful, append a human-facing item to `runs/<today>/todo.md`.

## Result Shape

Use this pattern:

```json
{
  "status": "skipped",
  "notes": "Deferred or unsupported in Codex sidecar v0."
}
```

## Closeout

Report the skip honestly to the user and include any manual next step.

