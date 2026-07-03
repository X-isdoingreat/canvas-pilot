# Codex Acceptance Checks

Acceptance checks prove the new Codex sidecar artifacts exist and express the intended behavior.

Run from repo root in PowerShell.

## A1 Codex driver plan exists

Command:

```powershell
Test-Path -LiteralPath "docs\CODEX_DRIVER_PLAN.md"
Select-String -Path "docs\CODEX_DRIVER_PLAN.md" -Pattern "sidecar|Phase 1|Phase 2|Non-Goals"
```

Pass:
- `Test-Path` returns `True`.
- `Select-String` finds all key terms.

## A2 Task ledger is structured

Command:

```powershell
Select-String -Path "docs\CODEX_TASKS.md" -Pattern "files:|done_when:|acceptance:|regression:"
```

Pass:
- Output contains each required field type.

## A3 Acceptance doc is command-backed

Command:

```powershell
Select-String -Path "docs\CODEX_ACCEPTANCE.md" -Pattern "Command:|Pass:|A1|A8"
```

Pass:
- Output contains command/pass sections and checks spanning docs and skills.

## A4 Regression doc is command-backed

Command:

```powershell
Select-String -Path "docs\CODEX_REGRESSION.md" -Pattern "Command:|Pass:|R1|R4"
```

Pass:
- Output contains command/pass sections and checks spanning driver boundary and Python syntax.

## A5 Test protocol exists

Command:

```powershell
Test-Path -LiteralPath "docs\CODEX_TEST_PROTOCOL.md"
Select-String -Path "docs\CODEX_TEST_PROTOCOL.md" -Pattern "Run acceptance|Run regression|Write report"
```

Pass:
- Protocol exists and states the loop.

## A6 Run state schema exists

Command:

```powershell
Test-Path -LiteralPath "docs\RUN_STATE_SCHEMA.md"
Select-String -Path "docs\RUN_STATE_SCHEMA.md" -Pattern "plan.json|assignments.json|result.json|_processed.json|REPORT.md"
```

Pass:
- Schema doc exists and names all shared state surfaces.

## A7 Public/private boundary exists

Command:

```powershell
Test-Path -LiteralPath "docs\PUBLIC_PRIVATE_BOUNDARY.md"
Select-String -Path "docs\PUBLIC_PRIVATE_BOUNDARY.md" -Pattern "Public-safe|Private-only|upstream|origin"
```

Pass:
- Boundary doc exists and has public/private sections.

## A8 Codex skill frontmatter exists

Command:

```powershell
Select-String -Path ".agents\skills\canvas-scan\SKILL.md",".agents\skills\canvas-execute\SKILL.md",".agents\skills\canvas-skip\SKILL.md" -Pattern "^name:|^description:"
```

Pass:
- Each skill has `name` and `description` in frontmatter.

## A9 Scan skill stops after planning

Command:

```powershell
Select-String -Path ".agents\skills\canvas-scan\SKILL.md" -Pattern "MUST NOT execute|STOP|plan.json|assignments.json"
```

Pass:
- Scan skill explicitly forbids execution and names plan outputs.

## A10 Execute skill requires approval

Command:

```powershell
Select-String -Path ".agents\skills\canvas-execute\SKILL.md" -Pattern "explicit approval|result.json|REPORT.md|Do not submit"
```

Pass:
- Execute skill requires approval, result files, report, and no submission by default.

## A11 Skip skill writes skipped result

Command:

```powershell
Select-String -Path ".agents\skills\canvas-skip\SKILL.md" -Pattern "status.*skipped|todo.md|result.json|No automation"
```

Pass:
- Skip skill documents skipped result behavior.

## A12 Codex hooks plan exists

Command:

```powershell
Test-Path -LiteralPath "docs\CODEX_HOOKS_PLAN.md"
Select-String -Path "docs\CODEX_HOOKS_PLAN.md" -Pattern "codex_hooks|hooks.json|SessionStart|PreToolUse|PostToolUse|Stop|one command hook per event"
```

Pass:
- Hooks plan exists and names official constraints plus the one-hook-per-event design.

## A13 Hook event fixtures exist

Command:

```powershell
Test-Path -LiteralPath "docs\CODEX_HOOK_EVENT_FIXTURES.md"
Select-String -Path "docs\CODEX_HOOK_EVENT_FIXTURES.md" -Pattern "SessionStart Input|PreToolUse Bash Input|PostToolUse apply_patch Input|Stop Input|Expected"
```

Pass:
- Fixture doc exists and covers all planned v0 event types.

## A14 Hook test design exists

Command:

```powershell
Test-Path -LiteralPath "docs\CODEX_HOOK_TESTS.md"
Select-String -Path "docs\CODEX_HOOK_TESTS.md" -Pattern "H1 SessionStart|H2 PreToolUse|H4 PostToolUse|H5 Stop|H7 Hook internal error"
```

Pass:
- Test design exists and covers pass, block, stop, and fail-open behavior.

## A15 Driver plan has hook design/implementation split

Command:

```powershell
Select-String -Path "docs\CODEX_DRIVER_PLAN.md" -Pattern "Phase 3A|Phase 3B|Verified official constraints|Design choice"
```

Pass:
- Driver plan separates design from implementation and records design choices.

## A16 Parity matrix exists

Command:

```powershell
Test-Path -LiteralPath "docs\CODEX_PARITY_MATRIX.md"
Select-String -Path "docs\CODEX_PARITY_MATRIX.md" -Pattern "P08|P09|P10|P15|done|todo"
```

Pass:
- Matrix exists and tracks B2 parity IDs.

## A17 Batch queue and protocol exist

Command:

```powershell
Test-Path -LiteralPath "docs\CODEX_BATCHES.md"
Test-Path -LiteralPath "docs\CODEX_BATCH_PROTOCOL.md"
Select-String -Path "docs\CODEX_BATCHES.md" -Pattern "B2 Runtime Hooks|status: in_progress|allowed_files|done_when"
Select-String -Path "docs\CODEX_BATCH_PROTOCOL.md" -Pattern "exactly one batch|Stop Hook Contract|Post Tool Guard Contract"
```

Pass:
- Batch queue and protocol exist and define B2.

## A18 Codex hook config exists

Command:

```powershell
Test-Path -LiteralPath ".codex\config.toml"
Test-Path -LiteralPath ".codex\hooks.json"
Select-String -Path ".codex\config.toml" -Pattern "codex_hooks"
Select-String -Path ".codex\hooks.json" -Pattern "SessionStart|PreToolUse|PostToolUse|Stop"
```

Pass:
- Codex config and hooks registration exist.

## H1-H8 Hook tests pass

Command:

```powershell
python tests/codex_hooks/run_hook_tests.py
```

Pass:
- Exit code 0 and every H-test prints `PASS`.

## A19 Master plan exists

Command:

```powershell
Test-Path -LiteralPath "docs\CODEX_MASTER_PLAN.md"
Select-String -Path "docs\CODEX_MASTER_PLAN.md" -Pattern "file-driven|Execution Loop|Stop Hook Rule|Skill Strategy|Batch Roadmap|Done Definition"
```

Pass:
- Master plan exists.
- It names the execution loop, Stop hook, skills, batch roadmap, and done definition.

## A20 Batch queue is split after B2

Command:

```powershell
Select-String -Path "docs\CODEX_BATCHES.md" -Pattern "B3 Bootstrap Runtime Behavior|B4 Scan Runtime Behavior|B5 Execute Runtime Behavior|B6 Runtime Fixture Suite|B7 Advanced Hook Parity|B8 First-Student Onboarding|B9 Plugin Packaging|B10 Codex Exec"
```

Pass:
- Output contains every planned post-B2 batch.

## A21 Parity matrix tracks remaining Codex work

Command:

```powershell
Select-String -Path "docs\CODEX_PARITY_MATRIX.md" -Pattern "P19|P20|P21|P22|P23|P24|P25|P26|P27|P28|P29"
```

Pass:
- Output contains P19-P29.

## A22 Batch protocol has self-run guardrails

Command:

```powershell
Select-String -Path "docs\CODEX_BATCH_PROTOCOL.md" -Pattern "Batch Claim Rule|Allowed Files Rule|Report Rule|Failure Policy|Long-Run Policy"
```

Pass:
- Protocol includes the claim, file boundary, report, failure, and long-run split rules.
