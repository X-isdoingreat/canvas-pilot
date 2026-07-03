# Codex Test Protocol

This protocol is the self-checking loop for Codex driver work.

## Loop

1. Pick tasks from `docs/CODEX_TASKS.md`.
2. Make only the files listed by those tasks.
3. Run acceptance checks from `docs/CODEX_ACCEPTANCE.md`.
4. Run regression checks from `docs/CODEX_REGRESSION.md`.
5. Write report output under `runs/codex/<YYYY-MM-DD>/REPORT.md`.
6. Mark tasks complete only after checks pass.

## Report Requirements

Each report must include:

- Scope
- Changed files
- Acceptance results with evidence
- Regression results with evidence
- Open issues
- Whether `.claude/` was touched

## Failure Rule

If any acceptance or regression check fails:

1. Do not mark tasks complete.
2. Record the failed check and evidence in the report.
3. Fix or ask for direction before continuing to the next phase.

## Current Phase

Current phase covers:

- Phase 1 documentation/self-check harness
- Phase 2 minimal Codex repo skill skeletons

Hook implementation and plugin packaging are future phases.
