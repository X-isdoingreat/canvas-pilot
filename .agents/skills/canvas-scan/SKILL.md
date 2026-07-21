---
name: canvas-scan
description: Use when the student asks what Canvas work is pending or wants a homework plan. It performs one enriched read-only scan, writes the atomic assignment snapshot and approval plan, renders the plan, and stops without drafting or submitting anything.
---

# Canvas Scan

Scan is proposal only. It reads current Canvas state, creates a reviewable plan,
and stops. The next user message is the architectural approval boundary.

## Hard boundary

- MUST NOT execute or draft an assignment.
- MUST NOT dispatch a course skill or `canvas-execute`.
- MUST NOT write a per-assignment `result.json` or `REPORT.md`.
- MUST NOT create `.scan_in_progress`.
- MUST NOT upload, submit, or start/answer/complete a quiz.
- MUST NOT interpret authentication as work approval.
- MUST stop after rendering the plan. Never “helpfully” begin an urgent item.

## Phase 0: Setup and route gate

Read local setup state before touching Canvas.

1. If `.env` is missing or the Canvas host/auth configuration is incomplete,
   hand off to `canvas-setup` and stop this scan when setup returns.
2. Read `courses.yaml`. Treat missing `routes`, `routes: null`, an empty mapping,
   and effectively all-commented routes as empty.
3. If routes are empty, hand off to `canvas-skill-opportunity` with this intent:

   > Inspect recurring candidates read-only, inspect representative real specs
   > and safe feedback-policy evidence, make a qualitative recommendation,
   > write the private opportunity report, and stop for the student's numbered
   > choice.

   Stop when opportunity analysis returns. Do not scan assignments and do not
   call `canvas-bootstrap` in the same turn. The student first chooses a
   candidate; a later Bootstrap invocation verifies it and creates one route.
4. Only non-empty usable routes proceed to the scan.

## Phase 1: One enriched Canvas process

Run exactly one interactive scan command:

```powershell
python -m src.router --scan-json
```

This single process owns connection/auth recovery, routed-course assignment
listing, pending-window filtering, live submission reads (`get_submission`),
due-time calculation, urgency buckets, unsupported-submission classification,
and quiz LockDown metadata checks. It reuses one Canvas/browser session.
The router delegates normalization/output safety to the shared
`src.scan_service` and route resolver; this skill consumes those outputs rather
than reimplementing their rules.

Do not restore the old interactive sequence of
`python -m src.canvas_client --probe`, `python -m src.router --dry-run`, and
separate per-item live-state calls. Those commands may remain for setup, cron,
or debugging, but they are not the student-facing scan path.

Read `runs/<today>/scan.json`; do not reconstruct the payload from terminal
prose. Expected top-level fields are:

```json
{
  "generated_at": "<ISO local time>",
  "now_utc": "<ISO UTC time>",
  "items": [],
  "course_errors": []
}
```

Each item must already include the identifiers and display fields needed by the
state protocol plus:

- canonical `skill` from `src.routes.resolve_skill(route, assignment)`;
- `live_state`;
- `hours_left`;
- `bucket`;
- supported/unsupported classification;
- LockDown result or an explicit check failure.

Scan consumes the canonical `canvas-*` name emitted by the shared route
resolver. Never embed or guess a legacy alias table in this skill.

## Phase 2: Fail loudly on an incomplete scan

Handle command-level errors before writing any approval artifact:

| Error class | Behavior |
|---|---|
| not configured | hand off to setup and stop |
| authentication | explain that Canvas needs login, offer one browser retry, then stop on failure |
| network/browser | explain the connection problem, do not retry silently more than once |
| unknown | show a short sanitized detail and stop |

Do not write or replace `assignments.json` or `plan.json` after a non-zero scan.

Treat a non-empty `course_errors` array as an incomplete scan even if the
process exited zero. Name the affected course aliases, explain that the plan
would be partial, and stop without replacing the prior approval plan. Do not
hide a failed course in a “successful” plan. A later explicit product feature
may authorize partial planning; ordinary scan does not.

Per-item live-state or LockDown lookup failures are different: the item remains
visible with `live_state: "unknown"` or an explicit check-failed field, and the
plan renders `?`. A failed safety classification must never be treated as proof
that an item is safe to mutate.

## Phase 3: Normalize and fail closed

Validate `scan.json` before deduplication:

- top level is an object and `items`/`course_errors` are lists;
- every item has one stable course/assignment identity;
- no duplicate identity appears;
- `live_state` and `bucket` are in their documented enums;
- route skill is a canonical `canvas-*` name;
- dates and numeric fields are either valid or explicitly unknown.

Unsupported delivery types (for example on-paper work or an unsupported
external tool) must be canonicalized to `canvas-skip` with a reason, never
routed as ordinary draft work. LockDown-confirmed quizzes also route to
`canvas-skip`. When LockDown status could not be checked, retain the item with a
loud caveat; the quiz skill must re-check and fail closed before any attempt.

## Phase 4: Deduplicate completed work

Use both layers:

1. **Same-day result** — derive the work directory using the shared run-state
   identity helper. Its stable shape is
   `course-<course_id>__assignment-<assignment_id>`; never recompute a directory
   from mutable course or assignment names. A valid result with terminal status
   `draft_ready`, `submitted`, or `skipped` means the item was handled today.
2. **Cross-day ledger** — read `runs/_processed.json`. Skip a matching terminal
   entry completed close enough to its due time to represent this assignment.

Exception: any ledger/result entry with `deferred_to_next_run: true` re-enters
the plan. This is how `skip`, `cancel`, an explicit defer, and crash recovery get
another approval opportunity.

Live Canvas state is defense in depth. Exclude confirmed `submitted`, `graded`,
or `pending_review` items from new work even if local state drifted. Preserve
`unknown` rather than inventing a submitted state.

## Phase 5: Use enriched buckets without refetching

Copy the single-process values; do not recompute or refetch them:

| Bucket | Meaning |
|---|---|
| `overdue` | due time passed and live state confirms not submitted |
| `urgent` | due within 72 hours, including uncertain past-due state |
| `soon` | due within 7 days after the urgent window |
| `later` | outside 7 days only when configured pending window includes it |
| `unknown` | missing/unparseable due time |

Sort by `overdue`, `urgent`, `soon`, `later`, `unknown`, then by
`hours_left` ascending with unknown last. Assign stable 1-based indices after
all filters.

## Phase 6: Write both state artifacts atomically

If no items survive, say there is no pending work in the configured window and
stop. Do not create an empty approval plan.

First materialize `runs/<today>/assignments.json` from the final normalized,
deduplicated items. This snapshot is what execute and the Stop guard share; it
must not be a stale `--dry-run` file. Include the canonical skill, identity,
name, due time, delivery types, points, URLs needed by the course skill,
enriched live state/bucket, skip reason, and a deterministic work-dir field when
the shared runtime provides one. Materialize it with
`src.run_state.stable_work_dir(run_dir, course_id, assignment_id)` so scan,
execute, finalize, and the Stop guard use the exact same ID-based directory.

Then write `runs/<today>/plan.json`:

```json
{
  "generated_at": "<ISO local time>",
  "expires_at": "<generated_at + 24 hours>",
  "items": [
    {
      "index": 1,
      "bucket": "urgent",
      "course_id": "<local-only>",
      "course_name": "<local-only>",
      "assignment_id": "<local-only>",
      "assignment_name": "Example Assignment",
      "due_at": "<ISO time>",
      "hours_left": 18.5,
      "live_state": "unsubmitted",
      "proposed_skill": "canvas-example",
      "user_decision": null
    }
  ]
}
```

Every plan item must map one-to-one to an assignments snapshot item by course
and assignment identity. Every `user_decision` starts `null`; prior decisions
must not leak into a fresh scan.

Write each JSON file to a sibling `.tmp`, parse and validate the temporary
content, then commit with `os.replace`. Commit the snapshot first and the plan
second. If either write fails, do not present an approval prompt; remove only
the temporary file and keep the last known-good artifacts.

## Phase 7: Render the student plan

Use the student's language. Always show:

- due within 3 days (including overdue at the top);
- due within 7 days;
- item index, recognizable course label, assignment name, due time, and live
  submitted state (`done`, `no`, or `?`);
- a small “manual/can't do” list for items routed to `canvas-skip`;
- one suggested starting item when at least one is draft-capable.

Prefer a private friendly course alias when configured. Do not show route
names, internal paths, plan expiry, implementation details, or bucket emojis.

End with exactly one simple approval hint:

```text
Reply all, numbers like 1,3, or skip.
```

This hint documents selection only. It does not imply submission or quiz
authority.

## Phase 8: Hard stop

After rendering, stop the turn. At this point verify:

- `assignments.json` and `plan.json` are valid and mutually consistent;
- every plan decision is null;
- no marker exists;
- no result, report, draft, upload, submission, or quiz attempt was created;
- no course skill was handed off.

The student's next message may be parsed by `canvas-execute`. Scan itself never
crosses that boundary.

## Real source-of-truth rule

Assignment names and Canvas descriptions are routing hints, not reliable full
specifications. Scan never guesses task requirements or drafts from them.
Approved course skills must follow the front page, modules, attachments, linked
pages, files, and external sources to the real specification at execution time.
