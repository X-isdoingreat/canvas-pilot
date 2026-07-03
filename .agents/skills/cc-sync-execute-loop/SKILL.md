---
name: cc-sync-execute-loop
description: Execute approved CC-to-Codex sync work in a guarded loop. Use when the user explicitly asks Codex to execute, continue, auto-continue, wake every 10 minutes, or run until blocked from an already reviewed CC_SYNC_PLAN.md / REVISED_CC_SYNC_PLAN.md. Do not use for raw plan review or capability-gap analysis; use cc-sync-runner for that planning/review surface first.
---

# CC Sync Execute Loop

Run the execution side of the CC-to-Codex workflow. This skill owns the loop,
lock, heartbeat, plan-state update, and bounded execution cycle. It does not
audit raw Claude Code drift; `$cc-sync-runner` owns review/planning.

## Boundary

- Consume reviewed and approved plan artifacts; do not create the sync plan from
  scratch unless the user explicitly redirects to planning.
- Treat `CC_SYNC_PLAN.md` / `REVISED_CC_SYNC_PLAN.md` as durable state.
  Conversation context is helpful but not authoritative.
- Preserve scan -> approval -> execute boundaries. Do not execute unapproved
  work.
- Keep `.claude/` and `CLAUDE.md` read-only.
- Do not copy private course playbooks, real course IDs, private URLs,
  instructor names, emails, or identity details into Codex artifacts.
- Do not submit to Canvas, answer quizzes, upload files, push upstream, or run
  live external actions from this skill.

## Relationship To cc-sync-runner

Use `$cc-sync-runner` for:

- generating `runs/codex/<today>/CC_SYNC_PLAN.md`
- reviewing raw sync plans
- writing `REVISED_CC_SYNC_PLAN.md`, `CAPABILITY_GAPS.md`,
  `PROPOSED_BATCHES.md`, and `NEW_SKILL_SPECS.md`
- deciding public/private sync classification

Use `$cc-sync-execute-loop` only after the user approves the reviewed plan or
approved batch.

If approval or reviewed plan evidence is missing, write a blocker in the loop
state and stop. Do not silently fall back into planning.

## Plan Lookup

Prefer artifacts in this order:

1. `runs/codex/<today>/REVISED_CC_SYNC_PLAN.md`
2. `runs/codex/<today>/CC_SYNC_PLAN.md`
3. `docs/CODEX_BATCHES.md` only when the user explicitly requested roadmap
   continuation rather than CC drift execution

Always read `AGENTS.md` before executing a cycle.

## Loop Modes

### One-Shot Tick

Default mode. Run exactly one guarded cycle, update the plan state, release the
lock, and report.

Use this mode when an external scheduler invokes Codex every 10 minutes.

### Same-Dialog Persistent Loop

Use only when the user explicitly asks for a loop, wake every 10 minutes, keep
going, auto-continue, or run until blocked.

After each successful cycle:

1. Release the lock.
2. Report the next scheduled wake time.
3. Run `Start-Sleep -Seconds 600`.
4. Start the next cycle in the same conversation.

The 10-minute delay starts after the previous cycle finishes. If a cycle takes
longer than 10 minutes, do not overlap it with another cycle.

## Lock Helper

Use the bundled script for lock and heartbeat state:

```powershell
python .agents\skills\cc-sync-execute-loop\scripts\cc_sync_loop_lock.py claim --root . --ttl-minutes 30
python .agents\skills\cc-sync-execute-loop\scripts\cc_sync_loop_lock.py heartbeat --root .
python .agents\skills\cc-sync-execute-loop\scripts\cc_sync_loop_lock.py release --root .
python .agents\skills\cc-sync-execute-loop\scripts\cc_sync_loop_lock.py status --root .
```

The lock file is `.codex/cc-sync-execute-loop.lock.json`.

If `claim` reports a fresh active lock:

- in one-shot mode, stop and report that another cycle is active
- in same-dialog loop mode, sleep 10 minutes and retry

If the lock is stale, the script claims a new cycle and records the recovered
lock in `recovered_from`.

Heartbeat before and after long checks, tests, or edits.

## Loop State Block

Keep or create this block near the top of the active plan artifact:

```markdown
<!-- CC_SYNC_EXECUTE_LOOP_STATE v1 -->
## Execute Loop State

- status: idle | active | blocked | sleeping | complete
- mode: one-shot | same-dialog-loop
- active_batch: none | B<N>
- active_step: short text
- last_completed_step: short text
- next_step: short text
- approval_source: user-message | plan | none
- lock_owner: cycle id or none
- updated_at: ISO-8601 timestamp
- blocker: none or concrete blocker
<!-- /CC_SYNC_EXECUTE_LOOP_STATE -->
```

Update this block after every material action. If the active plan lacks the
block, add it before making execution edits.

## Cycle

For each cycle:

1. Read `AGENTS.md`.
2. Read the active plan artifact using the lookup order above.
3. Confirm explicit execution approval.
4. Claim the lock.
5. Update loop state to `active`.
6. Determine the next bounded execution unit.
7. Execute that unit.
8. Run the relevant verification.
9. Update loop state with completed work, next step, and blockers.
10. Release the lock.
11. In same-dialog loop mode, sleep 10 minutes unless blocked or complete.

## Next Unit Selection

Choose the next unit in this order:

1. Continue the single batch already marked `in_progress` in
   `docs/CODEX_BATCHES.md`.
2. If no batch is in progress, claim the earliest approved batch named by the
   reviewed plan.
3. If roadmap continuation was explicitly requested, choose the earliest
   eligible `status: next` batch.
4. If no approved unit exists, mark the loop `blocked` with
   `approval_source: none` and stop.

Claim only one batch. Do not skip batch order.

## Execution Unit

Within one cycle, prefer one concrete repair loop:

1. Run `python scripts\codex_check.py --batch B<N>`.
2. If it passes, write the batch report and mark the batch done.
3. If it fails, read the first actionable assertion.
4. Confirm the needed edit is inside the batch's allowed files.
5. Make the smallest Codex-side edit.
6. Rerun the same batch check.
7. Update loop state.

If the user explicitly requested "run until blocked", the cycle may continue
within the same active batch until the batch passes or a hard stop occurs. Do
not continue into a second batch without an explicit roadmap/loop instruction.

## Reports

When a batch passes, write:

```text
runs/codex/<today>/PARITY_B<N>.md
```

Include:

- scope
- changed files
- check results
- warnings
- whether `.claude/` was touched
- next batch recommendation

Then update public-safe Codex tracking docs named by the approved plan, such as
`docs/CODEX_BATCHES.md` and `docs/CODEX_PARITY_MATRIX.md`.

Do not update the CC baseline unless the reviewed plan explicitly approved it
and all impacted checks pass.

## Hard Stops

Stop, update loop state to `blocked`, release the lock, and report if:

- execution approval is missing or ambiguous
- the active plan has not been reviewed
- the next edit would touch `.claude/` or `CLAUDE.md`
- the next edit needs private course details or live user identity
- the next action would submit, upload, answer a quiz, push upstream, or call a
  live Canvas endpoint
- the needed edit is outside the active batch's allowed files
- `codex_check.py` fails for an environment problem unrelated to the batch
- the same assertion fails twice after a repair without new evidence
- the user interrupts or redirects the loop

