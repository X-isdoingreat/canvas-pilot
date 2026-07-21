# Run State Schema

This document records the mechanical state contract enforced by the Codex
runtime. The frozen Claude path may remain compatible, but `src/run_state.py`
is the executable source of truth.

## `runs/<today>/skill-opportunities.json`

Purpose:
- Private first-run qualitative judgment of recurring assignment patterns that
  may be worth turning into durable course skills.

Expected candidate shape:

```json
{
  "generated_at": "2026-07-16T12:00:00-07:00",
  "scope": "read-only real-spec opportunity judgment",
  "decision_method": "agent_judgment",
  "grade_prediction": false,
  "candidates": [
    {
      "index": 1,
      "course_id": "local-only",
      "course_name": "local-only",
      "pattern": "Weekly task <N>",
      "tier": "best_first_skill",
      "recurrence_count": 4,
      "scheduled_future_count": 3,
      "scheduled_points_total": 30,
      "existing_route": null,
      "spec_evidence": {
        "sampled_assignment_ids": ["local-only"],
        "source_locations": ["local-only"],
        "stable_response_pattern": true,
        "task_family": "objective_quiz",
        "primary_deliverable": "Canvas quiz answers",
        "central_continuous_prose_words": 0,
        "independent_response_units": true,
        "inputs_reachable": true,
        "canvas_delivery_complete": true
      },
      "pre_submit_review": ["independent solve", "source cross-check"],
      "post_submit_policy": {
        "allowed_attempts": 2,
        "results_before_retry": true,
        "total_score_visible": true,
        "item_correctness_visible": true,
        "correct_answers_visible": null,
        "own_answers_visible": null,
        "feedback_timing": "immediate",
        "scoring_policy": "keep_highest",
        "question_reuse": "unknown",
        "evidence_confidence": "declared"
      },
      "reasons": ["..."],
      "demoters": [],
      "unknowns": ["question reuse"]
    }
  ]
}
```

Rules:
- `canvas-skill-opportunity` writes it together with
  `skill-opportunities.md`; `canvas-bootstrap` reads it only after the user
  selects a numbered candidate.
- It is not `plan.json`, does not describe pending work, and grants no approval
  to create a skill, execute work, upload, or submit.
- `tier` is one of `best_first_skill`, `good_candidate`, `later_candidate`,
  `assist_only`, `unsupported`, or `insufficient_evidence`.
- The Agent decides the qualitative tier from representative real specs,
  response shape, delivery completeness, repeatability, pre-submit review, and
  post-submit feedback/retry evidence. Recurrence, known future work/points,
  and likely time saved break ties; they are not deterministic scores.
- Missing facts use `null` or `unknown`. The report must not contain raw prior
  answers, answer IDs, exact grades or scores, feedback text, or raw submission
  payloads.
- The report may contain real local course identifiers because `runs/` is
  gitignored. Chat output must use numbered aliases instead of pasting the
  private table.

## `runs/<today>/scan.json`

Purpose:
- Complete enriched read-only scan evidence from configured Canvas routes.

Rules:
- It contains timezone-aware generation time, final `items`, and
  `course_errors`/completeness signals.
- `assignments.json` is materialized from the final item list, not from a
  partial probe or a second independent fetch.
- A fatal or partial scan must not manufacture an approvable `plan.json`.
- Scan never creates `.scan_in_progress`, dispatches work, or mutates Canvas.

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
    "skill": "canvas-generic",
    "work_dir": "course-12345__assignment-67890"
  }
]
```

Rules:
- It is produced by scan.
- It is read by execute and stop/finalize guards.
- It must not be used as approval by itself.
- Every identity is unique and maps one-to-one to a plan item. `skill` is a
  discoverable canonical `canvas-*` route.
- `work_dir` is derived only from stable IDs as
  `course-<course_id>__assignment-<assignment_id>`; mutable names are never
  filesystem identity.

## `runs/<today>/plan.json`

Purpose:
- User-reviewable plan produced by scan.

Rules:
- Scan writes it.
- Execute reads it.
- `generated_at` and `expires_at` are timezone-aware and ordered; execute
  rejects an expired plan.
- Item `index` values are unique, contiguous, ordered, positive, and 1-based.
- Each item carries the exact course/assignment identity and canonical
  `proposed_skill` matching `assignments.json`.
- Every `user_decision` starts `null`. Before marker creation execute atomically
  commits a complete set of exactly `approve`, `defer`, or
  `swap:canvas-<canonical-name>`.
- Plan approval authorizes local work only. It never authorizes Canvas POST/PUT,
  upload, quiz start/answer/complete, or retake.

## `runs/<today>/course-<course_id>__assignment-<assignment_id>/result.json`

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
- `draft_ready` must include an existing, non-empty substantive `draft_path`.
  Text artifacts may not contain unresolved placeholder/sentinel tokens. The
  associated `verification.log` must contain at least one `PASS` and no `FAIL`.
- A new `submitted` result requires a real `submitted_at`,
  `authorization_receipt_id`, `authorization_consumed: true`, and metadata with
  Canvas workflow state plus `readback_verified: true`. The receipt usage
  ledger must show a matching terminal action.
- Read-only discovery of an existing submission uses canonical
  `status: submitted` with `reason_code: already_submitted`; it must not claim
  this run consumed a receipt.
- `graded` is Canvas metadata, not a canonical status. `already_submitted` is a
  reason code, not a status.
- `skipped` and `error` require concrete notes. A deferred item uses
  `deferred_to_next_run: true` so scan can re-propose it.
- A submitted Classic Quiz additionally requires numeric (non-boolean)
  `kept_score`, `points_possible`, `attempts_used`, and `allowed_attempts`; a
  supported scoring policy; at least four independent agent passes or a
  verbatim degraded-method override; and claimed `human_ness_diagnostics`.
- Every assignment in `assignments.json` must eventually have a valid `result.json` before finalize/stop.

## `runs/<today>/.scan_in_progress`

Purpose:
- Execute ownership, plan binding, crash recovery, and prevention of stale
  stable-work-directory results.

Required base shape:

```json
{
  "session_id": "<current Codex thread/session>",
  "owner_kind": "codex",
  "created_at": "2026-07-18T12:00:00Z",
  "plan_digest": "<64 lowercase hex characters>"
}
```

Before reading, reconciling, or dispatching any approved result, execute calls
`python -m src.run_state prepare-results --run-dir runs/<today>`. It archives
each approved item's old result to
`result-history/pre-<first-20-hex-of-plan-digest>.json`, then atomically adds:

```json
{
  "results_prepared_at": "2026-07-18T12:00:01Z",
  "results_archive_count": 1,
  "prepared_approved_result_keys": [
    "course-12345__assignment-67890"
  ]
}
```

Rules:
- Prepared keys must equal the current plan's approved/swap items exactly and
  in plan order. Deferred result slots are not archived.
- Preparation is idempotent after the marker stamp and recovers a crash where
  an archive move completed before the stamp. If archive and current result
  both exist before the stamp, it fails closed without overwriting either.
- This proof is structural and intentionally does not use filesystem mtimes.
- Finalize validates every result, ledger, owner, digest, and prepared key set,
  then removes only its own marker as the last filesystem action.

## `runs/_processed.json`

Purpose:
- Cross-day ledger to avoid repeating completed work.

Rules:
- Drivers may read it to summarize history.
- Writes must preserve existing entries.
- Deferred/error entries may set `deferred_to_next_run: true`; scan must not
  deduplicate them as completed work.
- A submitted entry may retain a non-secret receipt ID/reference and read-back
  facts, but never the signing key, signature, raw receipt, or verbatim private
  authority text.
- Public examples must not include real course IDs.

## Private mutation authorization state

Interactive exact-target mutation writes `mutation_authority.json` and
`mutation_authorization.json` below the stable assignment work directory. The
local signing key and global receipt-usage ledger live under gitignored private
state. These artifacts bind one origin, Codex session, target, action set,
authority digest, and expiry. They are validated and consumption-tracked at
every Canvas write boundary; terminal consumption prevents replay. Public
examples may describe the schema but must never contain a real signature,
signing key, session identifier, or verbatim authority message.

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

