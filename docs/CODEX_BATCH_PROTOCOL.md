# Codex Batch Protocol

This is the self-run protocol for Codex parity work.

## Core Rule

Codex must work on exactly one batch at a time.

The batch ledger is the source of truth. Do not rely on conversation memory to
decide what is next.

## Batch Loop

1. Read `AGENTS.md`.
2. Read `docs/CODEX_MASTER_PLAN.md`.
3. Read `docs/CODEX_BATCHES.md`.
4. Find the only batch with `status: in_progress`.
5. If none exists, choose the first `status: next` batch and mark it `in_progress`.
6. Read that batch's `allowed_files`, `acceptance`, `regression`, `done_when`, and `report`.
7. Edit only files listed in `allowed_files`.
8. Run the listed acceptance checks.
9. Run the listed regression checks.
10. Write a report under `runs/codex/<YYYY-MM-DD>/PARITY_<batch>.md`.
11. If all required checks pass, update:
   - `docs/CODEX_PARITY_MATRIX.md`
   - `docs/CODEX_BATCHES.md`
12. If a check fails, mark the batch `blocked` and stop.

## Batch Claim Rule

Claiming a batch is a real edit:

```text
status: next -> status: in_progress
```

Do this before changing implementation files. The Stop hook uses this marker to
decide whether Codex is allowed to stop.

## Allowed Files Rule

Allowed files are a hard boundary. If a needed edit falls outside the batch:

1. Stop editing.
2. Write the reason in the report.
3. Ask the user whether to expand the batch.

Do not silently widen the batch.

## Report Rule

Every batch report must include:

- batch id and status
- files changed
- acceptance checks run
- regression checks run
- failures or warnings
- whether `.claude/` or `CLAUDE.md` changed
- next batch recommendation

The report is not decoration. It is the artifact the Stop hook and future
Codex sessions use to understand what happened.

## Stop Hook Contract

The Codex Stop hook checks:

- no batch is left `in_progress` without a report
- no batch is marked `done` while its parity IDs are unfinished
- execute-mode sessions are not missing `result.json`
- reports mention the required acceptance and regression check IDs

If a batch is still incomplete, the Stop hook tells Codex exactly what to do next.

## Post Tool Guard Contract

When a batch is `in_progress`, the PostToolUse guard may compare changed files against that batch's `allowed_files`.

If a file outside the allowed set changes, Codex must stop and ask for direction.

## Failure Policy

If a check fails:

1. Do not mark the batch done.
2. Keep or change the batch to `blocked`.
3. Record the exact command and failure in the report.
4. Fix only if the fix stays inside `allowed_files`.
5. Otherwise ask for direction.

## Long-Run Policy

If a batch is too large for one session, Codex should split it before editing
implementation files. The split belongs in `docs/CODEX_BATCHES.md`, not only in
the chat.
