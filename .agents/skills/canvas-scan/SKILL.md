---
name: canvas-scan
description: Scan Canvas for pending assignments, write the daily assignments snapshot and approval plan, render a student-facing due table, and stop without executing assignments. Use when the user asks to scan Canvas, check what is due, build a plan, or start homework planning. If routes are empty, hand off to canvas-bootstrap and stop.
---

# Canvas Scan

Scan is proposal only. It finds pending work, writes a plan, shows the student
what is due, and stops. It must not execute assignments.

## Contract

- Read `courses.yaml`.
- If routes are empty or all commented out, invoke `canvas-bootstrap` and stop.
- Run an auth probe before planning.
- Run the router dry-run.
- Produce or refresh `runs/<today>/assignments.json`.
- Produce or refresh `runs/<today>/plan.json`.
- Render a student-readable plan grouped by due window.
- MUST NOT execute assignments.
- MUST NOT call course-specific playbooks.
- MUST NOT write per-assignment `result.json`.
- MUST NOT write `REPORT.md`.
- MUST NOT create `.scan_in_progress`.
- STOP after showing the plan and ask the user for explicit approval.

## Step 0: First-Run Route Check

Read `courses.yaml` before scanning:

```python
import yaml
from pathlib import Path

cfg = yaml.safe_load(Path("courses.yaml").read_text(encoding="utf-8")) or {}
routes = cfg.get("routes") or {}
```

If `routes` is empty, `None`, or effectively all commented out, do not scan.
Hand off to `canvas-bootstrap` with this intent:

```text
routes are empty; set up public-safe per-course Codex skills first
```

After bootstrap returns, stop. Do not continue into auth probe or dry-run in
the same turn.

## Step 1: Auth Probe

Run:

```powershell
python -m src.canvas_client --probe
```

If this fails, stop and give a specific repair step:

| Symptom | Meaning | Tell the user |
|---|---|---|
| `401` or invalid token | token expired or wrong | refresh `CANVAS_TOKEN` in `.env` |
| session expired | cookie auth expired | rerun `python -m src.canvas_login --auto` |
| missing `.env` | setup incomplete | copy `.env.example` to `.env` and choose token or cookie auth |
| connection or timeout | network issue | retry after network/Canvas works |
| other traceback | unknown | show the traceback and ask for direction |

Do not write `plan.json` when auth probe fails.

## Step 2: Router Dry-Run

Run:

```powershell
python -m src.router --dry-run
```

This writes:

```text
runs/<today>/assignments.json
```

Read that file before summarizing. Each item is expected to include:

- `course_id`
- `course_name`
- `assignment_id`
- `name`
- `due_at`
- `skill` or proposed route skill
- `submission_types`
- `points_possible`

If the pending list is empty, tell the user there is no pending work in the
configured window and stop. No `plan.json` is required for an empty scan.

## Step 3: Deduplicate Already-Handled Work

Filter pending items through two layers:

1. Same-day work directories: if `runs/<today>/<work_dir>/result.json` exists
   with status `draft_ready`, `submitted`, or `skipped`, skip it.
2. Cross-day ledger: read `runs/_processed.json`; if
   `<course_id>:<assignment_id>` has a terminal status and was completed close
   enough to the due date, skip it.

Exception:

- if ledger entry has `deferred_to_next_run: true`, include it again so the
  student can decide on the next scan.

## Step 4: Live Submission State And Buckets

For every item that survives dedup, check live Canvas submission state when
available:

```python
get_submission(course_id, assignment_id)
```

Store a normalized `live_state`:

- `unsubmitted`
- `submitted`
- `graded`
- `pending_review`
- `unknown`

If a single live-state lookup fails, use `unknown` for that item and continue.

Compute `hours_left` from `due_at` and bucket:

| Bucket | Rule |
|---|---|
| `overdue` | `hours_left <= 0` and live state is not submitted/graded |
| `urgent` | `0 < hours_left <= 72` |
| `soon` | `72 < hours_left <= 168` |
| `later` | `hours_left > 168` |
| `unknown` | missing or unparsable due date |

## Step 5: Write Plan Atomically

Write `runs/<today>/plan.json` atomically by writing a `.tmp` file and then
using `os.replace`.

Plan shape:

```json
{
  "generated_at": "<ISO local time>",
  "expires_at": "<ISO local time + 24h>",
  "items": [
    {
      "index": 1,
      "bucket": "urgent",
      "course_id": 123,
      "course_name": "Example Course",
      "assignment_id": 456,
      "assignment_name": "Example Assignment",
      "due_at": "2026-05-01T23:59:00Z",
      "hours_left": 18.5,
      "live_state": "unsubmitted",
      "proposed_skill": "canvas-example",
      "user_decision": null
    }
  ]
}
```

Sort by bucket priority:

```text
overdue -> urgent -> soon -> later -> unknown
```

Then sort by `hours_left` ascending inside each bucket.

## Step 6: Render Student-Facing Table

Render two fixed sections:

- Due within 3 days
- Due within 7 days

If the user's request contains Chinese text, use Chinese headings:

- `三天内 due`
- `七天内 due`

Columns:

- `#`
- course
- assignment
- due
- submitted

Use `live_state` for the submitted column:

- submitted/graded/pending_review -> done
- unsubmitted -> no
- unknown -> ?

Do not show internal file paths, `plan.json`, proposed skill names, bucket
emojis, expiry language, or implementation details. End with one simple
approval prompt:

```text
Reply all, numbers like 1,3, or skip.
```

## Step 7: Stop

After rendering the table, stop.

Do not:

- call `canvas-execute`
- call any course-specific skill
- write `result.json`
- write `REPORT.md`
- create `.scan_in_progress`
- submit anything

The user's next message is the approval boundary. `canvas-execute` owns all
dispatch behavior.

## Real Source Of Truth Rule

Canvas assignment names and descriptions are routing hints, not full specs.
Scan should not infer assignment requirements or write drafts. Per-course
skills handle real spec lookup later.

