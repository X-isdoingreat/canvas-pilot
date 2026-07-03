# CC To Codex Sync Workflow

Use this workflow after the Claude Code driver changes and you want Codex to
plan the matching sidecar work.

## Purpose

The sync flow is intentionally plan-first:

```text
Claude Code changes
  -> snapshot .claude file fingerprints
  -> compare with last accepted baseline
  -> write runs/codex/<date>/CC_SYNC_PLAN.md
  -> update Codex batches/parity/docs
  -> run the relevant codex_check batch
  -> update baseline after verification
```

It does not copy `.claude/` files into Codex. That boundary protects the
working Claude driver and prevents private course details from entering public
Codex docs.

## Commands

Preferred interactive path:

```text
Use $cc-sync-runner to sync CC changes into Codex.
```

Generate a sync plan:

```powershell
python scripts\codex_cc_sync_plan.py
```

Generate a plan and fail the command when CC changed:

```powershell
python scripts\codex_cc_sync_plan.py --fail-on-changes
```

Accept the current CC state as the new local baseline after Codex is synced:

```powershell
python scripts\codex_cc_sync_plan.py --update-baseline
```

The baseline is local and ignored:

```text
runs/codex/cc_sync_baseline.json
```

## What The Script Watches

- `.claude/settings.json`
- `.claude/hooks/**`
- `.claude/skills/**`
- `.claude/agents/**`

The script records file path, kind, size, hash, and limited frontmatter. It does
not quote skill bodies into tracked Codex docs.

## How To Use The Generated Plan

Open:

```text
runs/codex/<date>/CC_SYNC_PLAN.md
```

For each changed file:

1. Decide whether the change affects public Codex behavior.
2. If yes, update `docs/CANVAS_PILOT_CLAUDE_FUNCTIONS.md` in public-safe terms.
3. Map the change to `docs/CODEX_PARITY_MATRIX.md`.
4. If needed, create or update a Codex batch in `docs/CODEX_BATCHES.md`.
5. Run the matching check:
   ```powershell
   python scripts\codex_check.py --batch B3
   ```
6. When the Codex side passes, accept the new baseline:
   ```powershell
   python scripts\codex_cc_sync_plan.py --update-baseline
   ```

The `$cc-sync-runner` skill performs this loop interactively: generate plan,
choose the earliest impacted batch, run `codex_check`, fix failures inside the
batch's allowed file scope, write the report, mark done, then update the local
baseline.

If the user asks to continue the Codex roadmap, `$cc-sync-runner` switches to
Roadmap Until Blocked mode: after sync is clean, it promotes the next eligible
batch, runs its check/fix/report loop, and repeats until a hard stop condition.

## Batch Mapping

| CC change kind | Typical Codex batch |
|---|---|
| `canvas-bootstrap` | B3 |
| `canvas-scan` | B4 |
| `canvas-execute` / `canvas-skip` | B5 |
| hook changes | B7 |
| reviewer/subagent changes | B7 |
| course-specific private skills | B8 only for public framework extraction |
| Kiro workflow skills | manual review, separate from Canvas Pilot |

## Continue Roadmap Mode

Use when the user says:

```text
continue roadmap
auto next step
until blocked
keep going after sync
```

Rules:

1. Finish any CC diff sync first.
2. If `CC_SYNC_PLAN.md` has no changes, pick the next batch from
   `docs/CODEX_BATCHES.md`.
3. If no batch is `next`, promote the earliest eligible `later` batch.
4. Run `python scripts\codex_check.py --batch B<N>`.
5. Fix failures only inside that batch's `allowed_files`.
6. Write `PARITY_B<N>.md`.
7. Mark the batch done and repeat.

Stop on the same hard stop conditions as normal sync.

## Safety Rules

- Treat `.claude/` as read-only during sync planning.
- Do not copy private course playbooks into `.agents/skills`.
- Do not write real course IDs, assignment IDs, instructor names, emails, or
  private URLs into tracked Codex docs.
- Do not mark the local baseline updated until the relevant Codex check passes.
