---
name: canvas-execute
description: Use after canvas-scan wrote a current plan and the student selected items. Records approval, hands approved work sequentially to native Codex course skills, validates results, updates ledger/report/delivery, and finalizes the marker. Canvas submission and quiz mutations require separate scoped authorization.
---

# Canvas Execute

Execute is the action half of the scan/execute boundary. It reads an existing
student-reviewed plan; it never scans, invents, expands, or silently repairs a
missing plan.

Plan approval authorizes local assignment work for the selected items only. It
does **not** authorize a Canvas upload/submission or a quiz
start/answer/complete action. Those mutations require a separate scoped
authorization receipt validated and consumed by the shared runtime.

## Hard rules

- Do not run `canvas-scan` inline or regenerate `plan.json` from Canvas.
- Do not execute unapproved items.
- Do not execute an item whose final `user_decision` is not `approve` or a
  valid `swap:canvas-*`.
- Do not expand a vague approval. Ambiguity stops before any plan write, marker,
  dispatch, or mutation.
- Do not do course work inside this dispatcher. Use sequential native Codex
  skill handoffs.
- Do not invent a route alias, draft path, verification result, result status,
  submission, score, or quiz diagnostic.
- A TODO, sentinel, skeleton, empty template, outline-only file, or placeholder
  is never `draft_ready`.
- Every assignment snapshot item must have one valid canonical `result.json`
  before finalization.
- Keep `.claude/` read-only. Do not use the frozen Claude Skill tool or Claude
  session variables as active runtime mechanisms.
- Do not submit to Canvas from plan approval.

## Phase 0: Preconditions and integrity

Before parsing approval, require:

1. `runs/<today>/plan.json` exists and parses as an object.
2. `runs/<today>/assignments.json` exists and parses as a list.
3. `generated_at` and `expires_at` are valid timezone-aware timestamps and the
   plan has not expired.
4. Plan indices are unique, contiguous, and 1-based.
5. Every plan item maps one-to-one to exactly one snapshot item by course and
   assignment identity; there are no extra or duplicate identities.
6. Each `proposed_skill` is the canonical `canvas-*` value produced by the
   shared route resolver.
7. The current conversation contains an explicit approval expression for this
   plan. Old approval from a prior plan or turn is not reusable.

If anything is missing, stale, malformed, or inconsistent, stop and tell the
student to run `canvas-scan` again. Do not “fix” the plan by fetching Canvas and
do not dispatch anything.

Call `src.run_state.validate_plan_assignments(plan, assignments,
run_dir=run_dir, require_current=True)` for these checks. Do not maintain a
second timestamp, identity, skill-name, or status validator in this skill.

After applying the complete decision set, compute
`src.run_state.plan_digest(updated_plan)`. Store that digest in the marker so a
resumed run cannot silently switch identities, skills, timestamps, or approval
decisions.

## Phase 1: Deterministic approval grammar

Normalize Unicode whitespace, Chinese punctuation, and case, but do not remove
unknown words and do not mine arbitrary numbers from prose. Match the whole
approval expression against one of these forms:

Call `src.approval.parse_approval(user_text, plan)` for the actual parse and
`src.approval.apply_approval_to_plan` for the complete decision set. The table
below is the user-facing contract and regression oracle; it is not permission
to rebuild an ad-hoc natural-language parser inside the agent.

| Exact form | Decision |
|---|---|
| `all`, `approve all`, `全部`, `全部做` | approve every item |
| bare `1,3` or `1 3`, and `approve 1,3` / `做 1,3` | approve exactly the listed indices; defer the rest |
| `1-4`, `approve 1-4`, `1 到 4` | approve the inclusive range; defer the rest |
| `urgent only`, `只做 urgent`, `只做紧急` | approve only items whose bucket is `urgent`; defer the rest |
| `skip`, `cancel`, `取消`, `全部取消` | defer every item; dispatch nothing |
| `skip 2` or `defer 2` / `跳过 2` | defer that item; other items require an explicit approve selector in the same expression or remain deferred |
| `swap 2 to canvas-x` / `第 2 项用 canvas-x` | approve item 2 with `swap:canvas-x`; all unspecified items remain deferred |

Lists and ranges may be combined only with unambiguous separators, for example
`1,3-5`. Expand them deterministically, reject reversed ranges, and reject any
index not present in the current plan. Deduplicate repeated indices.

An optional compound expression may contain one approve selector followed by
targeted `defer N` or `swap N to canvas-x` clauses separated by semicolons.
A targeted defer may narrow an explicit broad selector, so
`approve all; defer 2` means approve all except item 2. Reject a direct contradiction such as
`approve 1; defer 1` rather than guessing which instruction was later intent.

The following are ambiguous and must trigger one concise clarification without
writing anything:

- `do the important ones` / `做重要的`;
- `do the first few`;
- bare `defer` (no target);
- `swap 1/2` (no target skill and unclear indices);
- `cancel 2` (use `defer 2` for a targeted decision);
- `approve 1; defer 1`, or another direct conflict not covered by the documented
  broad-selector/targeted-defer precedence;
- a skill swap that is not a discoverable canonical `canvas-*` skill after
  shared resolver validation.

Silence never means approval. A list such as bare `1,3` approves only 1 and 3;
all other indices become `defer`.

After a successful parse, set every item to exactly one of:

- `approve`
- `defer`
- `swap:canvas-<canonical-name>`

Write the complete decision set to a temporary plan, validate it, then commit
with `os.replace`. No decision may remain null once execute begins.
Prefer `src.run_state.write_plan`/atomic helpers so the same validator used by
the hooks protects the write.

## Phase 2: Marker ownership and crash recovery

Use `runs/<today>/.scan_in_progress` as an execute-owned marker. The marker is a
JSON object, not an empty touch file:

```json
{
  "session_id": "<current Codex thread/session identifier>",
  "owner_kind": "codex",
  "created_at": "<ISO time>",
  "plan_digest": "<validated digest>"
}
```

Resolve the identifier with
`src.authorization.current_authorization_session()`. In current Codex this is
normally `CODEX_THREAD_ID`; the helper supports `CODEX_SESSION_ID` only as a
runtime compatibility fallback. Do not read Claude variables, invent a UUID,
or stamp a marker the Stop guard cannot associate with this session. If the
shared helper returns no reliable identifier, fail closed before creating the
marker or dispatching.

Before creating today's marker, inspect existing markers:

- **past-date marker**: validate that day's snapshot, write canonical
  skipped/deferred error-recovery results for unfinished items, update its
  ledger/report, then remove only that recovered marker;
- **today, same session and same plan digest**: resume by reconciling existing
  valid results and continuing the recorded decisions;
- **today, different owner**: do not steal or delete it; report that another
  execute session owns the run and stop;
- **malformed marker or digest mismatch**: do not dispatch; retain it for
  inspection and report the mismatch.

Create today's marker atomically only after approval was parsed, plan decisions
were committed, and the final plan digest was computed. Use
`src.run_state.validate_execute_marker` on resume and before finalization. While
the marker exists, the Stop guard requires a canonical result for every
snapshot item and recomputes the digest against `plan.json`.

Immediately after creating or resuming the owned marker, and **before reading,
reconciling, or dispatching any assignment result**, run the shared preparation
gate:

```powershell
python -m src.run_state prepare-results --run-dir runs/<today>
```

`prepare-results` validates the marker owner and final plan, recoverably moves
each approved item's pre-existing `result.json` into its deterministic
`result-history/` path, and stamps `results_prepared_at`,
`results_archive_count`, and the exact `prepared_approved_result_keys` list into
the marker. It is
idempotent after that stamp: a resume must call it again, but it must never
manually move or reuse a result around this gate. If the command fails, do not
dispatch or reconcile anything; retain the marker and report the exact error.
The shared run validator and Stop guard require that prepared key list to match
the current plan exactly. Because each approved slot was empty when the marker
was stamped, any approved `result.json` accepted afterward must have been
written by the current execute; an error or draft from a previous run is never
current-run evidence. Deferred results are not archived by this gate.

## Phase 3: Resolve the dispatch skill

For each approved item in plan order:

1. `approve` uses the canonical `proposed_skill` already written by scan.
2. `swap:canvas-x` is validated through
   `src.routes.resolve_skill(route, assignment)` and must resolve to a
   discoverable canonical Codex skill.
3. Use the shared resolver's result exactly. Do not maintain an inline mapping
   for legacy names such as old quiz/code/writing aliases.
4. When a shared deterministic sub-router is documented for a task family,
   call that shared runtime helper and consume its canonical `canvas-*` result;
   do not recreate its heuristics in prose.

If the target skill is missing or still contains `UNFILLED_SKELETON`, write a
canonical `error` result for the item, defer all not-yet-run items, and proceed
to safe closeout. Never perform the homework inline as a fallback.

## Phase 4: Separate local-work approval from mutation authority

Before every handoff, construct execution context with local drafting enabled
and Canvas mutation disabled by default.

The approval recorded in `plan.json` is never an authorization receipt. The
following actions require a separate receipt validated and consumed by the
shared runtime immediately before the exact action:

- upload an assignment file;
- submit an assignment or submission comment that changes Canvas state;
- start a quiz attempt;
- answer/save a quiz question;
- complete/submit a quiz attempt;
- take a retake or any additional attempt.

The receipt must be scoped to the exact local user, course, assignment, action
set, and validity window, and must be single-use or consumption-tracked. A
standing environment flag, route value, plan approval, skill prose, or prior
conversation statement is not a substitute. Execute must pass only a receipt
that the shared runtime has already validated for this item and action.
Use `src.authorization.require_mutation_authorization` at the mutation boundary;
do not validate signatures or scope in skill prose.

Without a valid receipt:

- ordinary course skills produce verified local drafts only;
- upload/submission branches remain disabled;
- a quiz skill that cannot even read questions without starting an attempt
  fails closed with `skipped` or `error` and a clear authorization next step;
- no start/answer/complete call is made.

Even when a receipt exists, the course skill must pass its verification gate
before the shared runtime consumes it. Never infer mutation authority from the
words `all`, `1,3`, `urgent only`, or a swap.

## Phase 5: Sequential native Codex skill handoff

Process approved items one at a time, earliest plan item first. Do not run
course skills in parallel because Canvas writes, shared artifacts, and result
ledgers can race.

For each item:

1. derive the work directory with the shared run-state identity helper using
   `course-<course_id>__assignment-<assignment_id>`; consume a validated
   snapshot `work_dir` when present and never derive it from mutable names;
2. create the work directory and pass the exact item identity, assignment name,
   course display name, snapshot path, plan path, work directory, draft-only
   default, and validated mutation receipt (if any);
3. perform a **native Codex skill handoff** to the resolved
   `.agents/skills/<canonical-name>/SKILL.md` and follow that skill's contract;
4. do not shell-launch a model, use a Claude-specific tool, or copy the target
   skill's homework logic into execute;
5. wait for the handoff to return before starting the next item;
6. read and validate the exact work directory's `result.json`.

The course skill owns spec discovery, drafting, substantive verification, and
its result write. Execute owns dispatch order, canonical validation, ledger,
report, delivery sync, and marker lifecycle.

## Phase 6: Canonical per-item result

Accept only these exact statuses:

- `draft_ready`
- `submitted`
- `skipped`
- `error`

Reject legacy or invented statuses such as `graded` and `already_submitted`.

Validation rules:

- `draft_ready` requires an existing, non-empty, substantive `draft_path` and an
  all-PASS `verification.log`;
- `submitted` requires `draft_path` or a verified `submitted_at`, plus the
  consumed authorization receipt reference and verification evidence;
- `skipped` requires explanatory `notes` and should identify whether it is
  retryable/manual;
- `error` requires concrete notes and must not claim a draft;
- no placeholder/sentinel artifact can satisfy a draft path.

A submitted quiz additionally requires numeric kept score, possible points,
attempts used and allowed attempts, a documented scoring policy, and the
required arbitration diagnostic (`agent_passes_count` at the product minimum or
the student's sufficiently specific degraded-method consent). Those diagnostics
do not replace the mutation receipt.

If a handoff returns without a result, emits malformed JSON, uses an invalid
status, or claims a missing draft, preserve its raw evidence privately and
write a canonical `error` result atomically. Do not round it up to
`draft_ready`.
Use `src.run_state.validate_result` and `write_result` for canonical validation
and atomic writes.

## Phase 7: Deferred and interrupted items

Every non-approved item and every approved item left after a controlled pause
gets an atomic placeholder result:

```json
{
  "status": "skipped",
  "notes": "not approved this run",
  "deferred_to_next_run": true
}
```

Use a more specific note for explicit defer, cancel, crash recovery, or
capacity pause. These are result placeholders only in the sense of closeout;
they never claim a draft and must re-enter the next scan.

If the context is becoming too tight for the next heavy approved item:

1. finish and validate the current item;
2. write skipped/deferred results and ledger entries for every remaining item;
3. tell the student what completed and what remains;
4. ask whether to continue or defer;
5. on a clear continue in the same owned run, overwrite each deferred placeholder
   only after its real handoff completes;
6. otherwise finalize with the deferred state.

Never stop with an assignment missing a result while the marker is owned.

## Phase 8: Atomic cross-day ledger

After every validated result, update `runs/_processed.json` immediately:

- read and preserve the whole existing object;
- key by the shared canonical assignment identity;
- record canonical status, display labels, due time, completion time, real draft
  path when any, notes, and `deferred_to_next_run`;
- for mutation results, record only a non-secret receipt reference/consumption
  fact, never secret receipt material;
- write a sibling temporary file, parse it, and commit with `os.replace`.

Never truncate unrelated historical entries. A ledger write failure stops new
dispatch; write safe results for remaining items and retain the marker until
closeout is repaired.
Use `src.run_state.merge_ledger_entry` (or its current shared equivalent), not a
read-modify-write snippet duplicated in the model.

## Phase 9: REPORT.md closeout

Write `runs/<today>/REPORT.md` atomically after every snapshot item has a valid
result and the ledger is current.

The first block is always one of:

- `🔥 URGENT` for every overdue or due-within-24-hours item whose live state is
  not confirmed submitted/graded;
- `✅ No urgent items in next 24h` when none qualify.

This urgent banner is always the first block of the report.

Immediately below the banner, include one debug-help block for all `error`
results. For each error name the assignment/course alias, canonical skill and
public Codex skill path when known, verbatim result notes, and checks for:

- an `UNFILLED_SKELETON` skeleton sentinel;
- frontmatter/directory mismatch;
- missing private overlay or real spec location;
- missing required sources;
- incomplete workflow or verification step;
- absent/invalid result path;
- a referenced helper/file that fails standalone;
- missing scoped mutation receipt when the requested action required one.

Then group all items by canonical status (`draft_ready`, `submitted`, `skipped`,
`error`). Separate **verified facts** (files, checks, live state, receipt
consumption) from **judgment calls** (recommendation, uncertainty, user choice).
Never say “submitted” merely because a draft exists.

End with exactly one `## Next step` recommendation. Priority is urgent mutation
or manual action, then first error, then skipped/manual work, then review/upload
of drafts. Keep the recommendation within the authority actually granted.

## Phase 10: Delivery sync

For each `draft_ready` or `submitted` result with a validated draft path:

1. copy the artifact into the gitignored `final_drafts/` delivery tree using a
   stable collision-safe name;
2. preserve the source artifact;
3. refresh the delivery README/status surface from the ledger;
4. label drafts as awaiting review/upload unless their canonical status is
   truly `submitted`;
5. do not copy secrets, raw receipts, private feedback, or full private overlay
   content.

An absent draft means no delivery copy. Do not create an empty stand-in.

## Phase 11: Finalize marker last

Remove the owned `.scan_in_progress` marker only after all of these are true:

1. every snapshot item has one valid canonical result;
2. all results agree with real artifacts and mutation evidence;
3. `_processed.json` is atomically current;
4. `REPORT.md` exists and begins with the urgent block;
5. delivery sync/README completed when drafts exist;
6. the current marker owner and plan digest still match this session/run.

If closeout validation fails, retain the marker, report the exact missing piece,
and repair it. Never delete another session's marker. Marker removal is the
final filesystem action of a successful execute run; only then is the marker
removed.
