# Codex Regression Checks

Regression checks prove the Codex sidecar work did not break or pollute existing behavior.

Run from repo root in PowerShell.

## R1 Do not touch Claude driver

Command:

```powershell
git diff --name-only -- .claude CLAUDE.md
```

Pass:
- Empty output for this Codex sidecar phase.
- If the worktree already had unrelated `.claude/` or `CLAUDE.md` changes before the Codex phase, record this as `WARN-preexisting` in the report instead of claiming it as Codex work.

Note:
- Pre-existing unrelated `.claude/skills/new-feature/` and `.claude/skills/validate/` may appear in `git status` as untracked; they are not part of this phase.

## R2 No private identity in Codex docs or skills

Command:

```powershell
Get-ChildItem -Path AGENTS.md,docs,.agents -Recurse -File |
  Where-Object { $_.FullName -notlike "*CODEX_REGRESSION.md" } |
  Select-String -Pattern "[U]CI|[x]ianzh|tao\.for|gmail|@[u]ci|胡|[献]之"
```

Pass:
- Empty output.

## R3 Expected Codex-side file scope only

Command:

```powershell
git status --short
```

Pass:
- Codex work from this phase is limited to:
  - `AGENTS.md`
  - `docs/CODEX_*.md`
  - `docs/RUN_STATE_SCHEMA.md`
  - `docs/PUBLIC_PRIVATE_BOUNDARY.md`
  - `.agents/skills/**`
  - `runs/codex/**`
- Existing unrelated modified/untracked files may remain, but must not be claimed as Codex work.

## R4 Python source still compiles

Command:

```powershell
python -m compileall src
```

Pass:
- Exit code 0.

## R5 Codex skill files are ASCII-safe except intentional project terms

Command:

```powershell
Get-ChildItem -Path ".agents\skills" -Recurse -File |
  Select-String -Pattern "[^\x00-\x7F]"
```

Pass:
- Empty output, unless a non-ASCII project term is intentionally documented in the report.

## R6 Do not create Codex runtime hooks during design-only phase

Command:

```powershell
Test-Path -LiteralPath ".codex"
```

Pass:
- Returns `False` during Phase 3A design-only work.

## R7 Hook design docs do not claim implementation is complete

Command:

```powershell
Select-String -Path "docs\CODEX_HOOKS_PLAN.md","docs\CODEX_HOOK_TESTS.md" -Pattern "implemented|production-ready|full parity"
```

Pass:
- Empty output, or only appears in a negated/non-goal statement recorded in the report.

## R8 Codex hook config uses one command hook per event

Command:

```powershell
Select-String -Path ".codex\hooks.json" -Pattern '"command":'
```

Pass:
- Exactly 4 command hooks: one for `SessionStart`, `PreToolUse`, `PostToolUse`, and `Stop`.

## R9 Batch check script passes

Command:

```powershell
python scripts/codex_check.py --batch B2
```

Pass:
- Exit code 0.

## R10 Bootstrap skeleton sentinel remains mandatory

Command:

```powershell
Select-String -Path "docs\CODEX_MASTER_PLAN.md","docs\CODEX_BATCHES.md" -Pattern "UNFILLED_SKELETON|sentinel"
```

Pass:
- The bootstrap roadmap still requires an unfilled-skeleton sentinel before a generated course skill can execute.
