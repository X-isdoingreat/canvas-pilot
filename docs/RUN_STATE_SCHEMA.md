# Run State Schema

This document records the shared state files both Claude Code and Codex drivers must respect.

## `runs/<today>/assignments.json`

Purpose:
- Snapshot of Canvas assignments selected by the scanner.

Expected shape:

```json
[
  {
    "course_id": 12345,
    "course_name": "Course Name",
    "assignment_id": 67890,
    "name": "Assignment Name",
    "due_at": "2026-04-29T23:59:00Z",
    "submission_types": ["online_upload"],
    "points_possible": 10,
    "skill": "manual_skip"
  }
]
```

Rules:
- It is produced by scan.
- It is read by execute and stop/finalize guards.
- It must not be used as approval by itself.

## `runs/<today>/plan.json`

Purpose:
- User-reviewable plan produced by scan.

Rules:
- Scan writes it.
- Execute reads it.
- Every item starts unapproved.
- User approval must be explicit before execute dispatches work.

## `runs/<today>/<slug>/result.json`

Purpose:
- Per-assignment completion contract.

Required fields:

```json
{
  "status": "draft_ready"
}
```

Valid `status` values:

- `draft_ready`
- `submitted`
- `skipped`
- `error`

Rules:
- `draft_ready` must include an existing `draft_path`.
- `submitted` must include `draft_path` or `submitted_at`.
- `skipped` must include explanatory notes when possible.
- Every assignment in `assignments.json` must eventually have a valid `result.json` before finalize/stop.

## `runs/_processed.json`

Purpose:
- Cross-day ledger to avoid repeating completed work.

Rules:
- Drivers may read it to summarize history.
- Writes must preserve existing entries.
- Public examples must not include real course IDs.

## `runs/<today>/REPORT.md`

Purpose:
- User-facing closeout.

Rules:
- Must list what happened during execute.
- Must include urgent due-soon items at the top when applicable.
- Must separate verified facts from judgment calls.

## `final_drafts/`

Purpose:
- User-facing delivery folder for final drafts.

Rules:
- Drafts copied here remain gitignored.
- Public examples should use generic names only.

