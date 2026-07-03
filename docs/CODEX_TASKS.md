# Codex Tasks

Status key:

- `[ ]` not started
- `[~]` in progress
- `[x]` complete and verified

Each task must list files, done criteria, acceptance checks, and regression checks.

---

## Phase 1: Documentation and Self-Check Harness

- [x] T1 Add Codex driver plan
  - files: `docs/CODEX_DRIVER_PLAN.md`
  - done_when: plan defines sidecar architecture, phases, non-goals, and current scope
  - acceptance: A1
  - regression: R1, R2

- [x] T2 Add task ledger
  - files: `docs/CODEX_TASKS.md`
  - done_when: every task has files, done_when, acceptance, and regression fields
  - acceptance: A2
  - regression: R1, R2

- [x] T3 Add acceptance checks
  - files: `docs/CODEX_ACCEPTANCE.md`
  - done_when: acceptance checks are command-backed and cover AGENTS, docs, and skill skeletons
  - acceptance: A3
  - regression: R1, R2

- [x] T4 Add regression checks
  - files: `docs/CODEX_REGRESSION.md`
  - done_when: regression checks protect Claude driver, public safety, Python syntax, and expected file scope
  - acceptance: A4
  - regression: R1, R2, R3, R4

- [x] T5 Add test protocol
  - files: `docs/CODEX_TEST_PROTOCOL.md`
  - done_when: protocol states how to run and record checks before marking tasks complete
  - acceptance: A5
  - regression: R1, R2

- [x] T6 Add run state schema
  - files: `docs/RUN_STATE_SCHEMA.md`
  - done_when: plan, assignment, result, ledger, and report contracts are documented
  - acceptance: A6
  - regression: R2

- [x] T7 Add public/private boundary doc
  - files: `docs/PUBLIC_PRIVATE_BOUNDARY.md`
  - done_when: public-safe and private-only categories are documented without personal identifiers
  - acceptance: A7
  - regression: R2

## Phase 2: Codex Skill Skeletons

- [x] T8 Add `canvas-scan` Codex skill skeleton
  - files: `.agents/skills/canvas-scan/SKILL.md`
  - done_when: skill has valid frontmatter and clearly stops after plan output
  - acceptance: A8, A9
  - regression: R1, R2

- [x] T9 Add `canvas-execute` Codex skill skeleton
  - files: `.agents/skills/canvas-execute/SKILL.md`
  - done_when: skill requires explicit approval and one result.json per item
  - acceptance: A8, A10
  - regression: R1, R2

- [x] T10 Add `canvas-skip` Codex skill skeleton
  - files: `.agents/skills/canvas-skip/SKILL.md`
  - done_when: skill documents skipped result behavior without private course specifics
  - acceptance: A8, A11
  - regression: R1, R2

## Phase 3A: Codex Hook Design

- [x] T11 Add Codex hooks plan
  - files: `docs/CODEX_HOOKS_PLAN.md`
  - done_when: plan documents official constraints, event map, output strategy, and v0 guard scope
  - acceptance: A12
  - regression: R1, R2

- [x] T12 Add hook event fixtures
  - files: `docs/CODEX_HOOK_EVENT_FIXTURES.md`
  - done_when: fixtures cover SessionStart, PreToolUse, PostToolUse, and Stop input/output shapes
  - acceptance: A13
  - regression: R1, R2

- [x] T13 Add hook test design
  - files: `docs/CODEX_HOOK_TESTS.md`
  - done_when: test design covers context injection, command deny/pass, result schema, stop guard, and fail-open behavior
  - acceptance: A14
  - regression: R1, R2, R4

- [x] T14 Update driver plan with Phase 3A/3B split
  - files: `docs/CODEX_DRIVER_PLAN.md`
  - done_when: plan separates hook design from hook implementation
  - acceptance: A15
  - regression: R1, R2

## Phase 3B: Codex Hook Implementation

- [x] T15 Add Codex hook configuration
  - files: `.codex/hooks.json`
  - done_when: current Codex hook config format is verified and registered without duplicate same-event command hooks
  - acceptance: future
  - regression: R1, R2

- [x] T16 Add Codex hook wrappers
  - files: `.codex/hooks/*.py`
  - done_when: wrappers parse Codex events, fail open on internal errors, and pass future hook tests
  - acceptance: future
  - regression: R1, R2, R4

## Phase 4: Master Self-Run Design

- [x] T17 Add Codex master plan
  - files: `docs/CODEX_MASTER_PLAN.md`
  - done_when: plan defines the file-driven control plane, batch loop, Stop hook rule, skill strategy, student runtime sequence, and roadmap
  - acceptance: A19
  - regression: R1, R2

- [x] T18 Expand batch queue into small executable slices
  - files: `docs/CODEX_BATCHES.md`
  - done_when: B3-B10 are split by bootstrap, scan, execute, fixtures, hook parity, onboarding, packaging, and automation
  - acceptance: A20
  - regression: R1, R2

- [x] T19 Extend parity matrix for the post-B2 roadmap
  - files: `docs/CODEX_PARITY_MATRIX.md`
  - done_when: P19-P29 map the remaining Claude capabilities into Codex targets
  - acceptance: A21
  - regression: R1, R2

- [x] T20 Extend batch protocol with self-run enforcement rules
  - files: `docs/CODEX_BATCH_PROTOCOL.md`
  - done_when: protocol includes claim, allowed-files, report, stop-hook, failure, and long-run split rules
  - acceptance: A22
  - regression: R1, R2
