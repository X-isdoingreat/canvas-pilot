---
name: canvas-execute
description: Execute only the Canvas plan items explicitly approved by the user after canvas-scan. Parses approval, updates plan.json, dispatches approved items sequentially to Codex course skills or canvas-skip, writes result.json for every item, updates the processed ledger, writes REPORT.md with urgent and error-help sections, syncs delivery drafts, and clears the execute marker. Never executes unapproved items or submits by default.
---

# Canvas Execute

Execute is action only after approval. It must never scan, invent a plan, or
execute unapproved items.

## Preconditions

- `runs/<today>/plan.json` exists.
- `runs/<today>/assignments.json` exists.
- `plan.json` is not expired; use `expires_at`.
- The user explicitly approved work in the current conversation.

If any precondition is missing, stop and tell the user to run `canvas-scan`
first. Do not run scan inline.

## Contract

- Parse approval.
- Update `plan.json` atomically with `user_decision`.
- Arm `runs/<today>/.scan_in_progress`.
- Dispatch approved items sequentially.
- Do not dispatch unapproved items.
- For every item in `assignments.json`, ensure one valid `result.json` exists.
- Update `runs/_processed.json`.
- Write `runs/<today>/REPORT.md`.
- Sync draft-ready files into the delivery folder when applicable.
- Remove `.scan_in_progress` at finalize.
- Do not submit to Canvas by default.

## Approval Parser

Recognize:

| User says | Decision |
|---|---|
| `approve all`, `all` | every item `approve` |
| `urgent only` | urgent bucket `approve`, rest `defer` |
| `approve 1,3,5` | listed indices `approve`, rest `defer` |
| `1-4` or index range | range `approve`, rest `defer` |
| `swap 2 to canvas-x` | item 2 `swap:canvas-x` |
| `defer 2` or `skip 2` | item 2 `defer` |
| `cancel` | every item `defer` |

Ambiguous input stops and asks once. Do not guess.

Atomic update:

```python
tmp = plan_path.with_suffix(".json.tmp")
tmp.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
os.replace(tmp, plan_path)
```

## Marker And Crash Recovery

Before starting:

1. Look for old `runs/*/.scan_in_progress` markers.
2. For old markers, write skipped/deferred `result.json` for unfinished items.
3. Remove old markers.

For today's run:

```text
runs/<today>/.scan_in_progress
```

While this marker exists, Stop hook expects every assignment to have a valid
`result.json`.

## Dispatch

Process approved items one at a time in plan order.

For each item:

1. Determine skill:
   - `approve` -> `proposed_skill`
   - `swap:canvas-x` -> `canvas-x`
2. Dispatch via the Skill tool.
3. Pass assignment name, course name, work dir, and references to
   `assignments.json` / `plan.json`.
4. Read the sub-skill's `result.json`.
5. Update todo state if todo tooling is available.
6. Update `runs/_processed.json` atomically.

If the target skill is missing, write an error result and stop with a clear
message. Do not inline homework logic inside execute.

## Deferred And Unapproved Items

Every item not approved this run must get:

```json
{
  "status": "skipped",
  "notes": "not approved this run",
  "deferred_to_next_run": true
}
```

This includes:

- explicitly deferred items
- silent unapproved items
- items left after a pause
- items skipped because the session is running tight

## Pause When Tight

If context is running low and approved items remain:

1. Write skipped/deferred placeholder `result.json` for remaining items.
2. Update `_processed.json` with `deferred_to_next_run: true`.
3. Tell the user what was done and what remains.
4. Ask whether to continue or defer.

Do not try to squeeze in one more heavy item.

## REPORT.md

Write `runs/<today>/REPORT.md`.

The report must begin with an urgent banner:

- due within 24 hours and not submitted
- overdue and not submitted
- no urgent items if none exist

Then include run results grouped by status:

- `draft_ready`
- `submitted`
- `skipped`
- `error`

### Error Help Section

For every `result.json` with `status: "error"`, add a debug-help block under
the urgent banner. Include:

- assignment name
- course name
- skill name and skill path when known
- error notes verbatim
- checklist:
  - skeleton sentinel still present?
  - frontmatter name matches directory?
  - allowed tools match skill needs?
  - spec location filled?
  - draft workflow filled?
  - verification step filled?
  - result.json path exists?
  - mentioned file/API path works standalone?

Tell the user to fix the skill and rerun scan; deferred items re-enter on the
next scan.

## Delivery Sync

For `draft_ready` or `submitted` items with `draft_path`, copy the draft into
the delivery folder and refresh a README/status surface. Do not claim the user
has submitted unless the result status is actually `submitted`.

## Finalize

Before finishing:

1. Every assignment has a valid `result.json`.
2. `_processed.json` is updated.
3. `REPORT.md` exists.
4. Delivery folder is synced when drafts exist.
5. `.scan_in_progress` is removed.

## Hard Rules

- Do not scan Canvas.
- Do not regenerate `plan.json`.
- Do not execute unapproved items.
- Do not bypass missing course skills by doing homework inline.
- Do not fabricate `draft_path`, `submitted`, or `draft_ready`.
- Do not submit to Canvas by default.
- Do not copy private Claude course skills into Codex.

