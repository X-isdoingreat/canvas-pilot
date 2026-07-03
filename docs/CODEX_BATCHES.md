# Codex Batches

Only one batch may be `in_progress` at a time.

Status values:

- `done`
- `next`
- `in_progress`
- `blocked`
- `later`

---

## B1 Docs + Skill Skeletons

status: done
parity_ids: P01, P02, P03, P04, P05, P06, P07

allowed_files:
- AGENTS.md
- docs/CODEX_DRIVER_PLAN.md
- docs/CODEX_TASKS.md
- docs/CODEX_ACCEPTANCE.md
- docs/CODEX_REGRESSION.md
- docs/CODEX_TEST_PROTOCOL.md
- docs/RUN_STATE_SCHEMA.md
- docs/PUBLIC_PRIVATE_BOUNDARY.md
- docs/CODEX_HOOKS_PLAN.md
- docs/CODEX_HOOK_EVENT_FIXTURES.md
- docs/CODEX_HOOK_TESTS.md
- .agents/skills/**
- runs/codex/**

acceptance:
- A1-A15

regression:
- R1
- R2
- R4
- R6
- R7

done_when:
- docs and skill skeletons exist
- acceptance checks pass
- report exists under `runs/codex/`

---

## B2 Runtime Hooks

status: done
parity_ids: P08, P09, P10, P11, P12, P13, P14, P15

allowed_files:
- docs/CODEX_PARITY_MATRIX.md
- docs/CODEX_BATCHES.md
- docs/CODEX_BATCH_PROTOCOL.md
- docs/CODEX_ACCEPTANCE.md
- docs/CODEX_REGRESSION.md
- docs/CODEX_HOOKS_PLAN.md
- docs/CODEX_HOOK_TESTS.md
- .codex/config.toml
- .codex/hooks.json
- .codex/hooks/**
- scripts/codex_check.ps1
- tests/codex_hooks/**
- runs/codex/**

acceptance:
- A16
- A17
- A18
- H1
- H2
- H3
- H4
- H5
- H6
- H7
- H8

regression:
- R1
- R2
- R4
- R8
- R9

done_when:
- `.codex/config.toml` enables `codex_hooks`
- `.codex/hooks.json` registers one command hook per event
- hook tests H1-H8 pass
- `scripts/codex_check.ps1 -Batch B2` exits 0
- `runs/codex/<date>/PARITY_B2.md` exists
- parity matrix marks P08-P15 done
- this batch status is changed to `done`

---

## B3 Scan/Execute Runtime Behavior

status: later
parity_ids: replaced-by-B4-B5

note:
- Superseded by B3/B4/B5 split below. Keep this section for history only.

allowed_files:
- n/a

acceptance:
- n/a

regression:
- n/a

done_when:
- n/a

---

## B3 Bootstrap Runtime Behavior

status: done
parity_ids: P19, P20

allowed_files:
- docs/CODEX_MASTER_PLAN.md
- docs/CODEX_BATCHES.md
- docs/CODEX_TASKS.md
- docs/CODEX_ACCEPTANCE.md
- docs/CODEX_REGRESSION.md
- docs/CODEX_PARITY_MATRIX.md
- scripts/codex_check.py
- .agents/skills/**
- tests/codex_bootstrap/**
- runs/codex/**

acceptance:
- A19
- A20
- A21
- A22

regression:
- R1
- R2
- R4
- R10

done_when:
- `.agents/skills/canvas-bootstrap/SKILL.md` exists
- bootstrap skill documents route-empty first-run behavior
- bootstrap skill writes only `.agents/skills/**` and public-safe routes/config
- skeleton sentinel prevents execution before student fills TODOs
- fake bootstrap fixtures prove cross-course bundling is rejected

---

## B4 Scan Runtime Behavior

status: done
parity_ids: P21, P22

allowed_files:
- .agents/skills/canvas-scan/SKILL.md
- tests/codex_runtime/**
- scripts/codex_check.py
- docs/CODEX_ACCEPTANCE.md
- docs/CODEX_REGRESSION.md
- docs/CODEX_PARITY_MATRIX.md
- docs/CODEX_BATCHES.md
- runs/codex/**

acceptance:
- future

regression:
- R1
- R2
- R4

done_when:
- fake scan fixture writes `assignments.json`
- fake scan fixture writes `plan.json`
- scan output does not execute or write `result.json`
- empty route fixture hands off to bootstrap

---

## B5 Execute Runtime Behavior

status: done
parity_ids: P23, P24, P25

allowed_files:
- .agents/skills/canvas-execute/SKILL.md
- .agents/skills/canvas-skip/SKILL.md
- tests/codex_runtime/**
- scripts/codex_check.py
- docs/CODEX_ACCEPTANCE.md
- docs/CODEX_REGRESSION.md
- docs/CODEX_PARITY_MATRIX.md
- docs/CODEX_BATCHES.md
- runs/codex/**

acceptance:
- future

regression:
- R1
- R2
- R4

done_when:
- approval parser handles all/index list/range/urgent/defer/cancel
- approved fake item gets `result.json`
- unapproved fake item gets skipped/deferred `result.json`
- `REPORT.md` is generated
- no unapproved item is dispatched

---

## B6 Runtime Fixture Suite

status: done
parity_ids: P26

allowed_files:
- tests/codex_runtime/**
- scripts/codex_check.py
- docs/CODEX_ACCEPTANCE.md
- docs/CODEX_REGRESSION.md
- docs/CODEX_BATCHES.md
- runs/codex/**

acceptance:
- future

regression:
- R1
- R2
- R4

done_when:
- fake Canvas data covers API-token-like and cookie-like auth modes
- fixture suite can run without network
- fixture suite proves scan/execute boundary

---

## B7 Advanced Hook Parity

status: done
parity_ids: P17, P18

allowed_files:
- .codex/hooks/**
- tests/codex_hooks/**
- scripts/codex_check.py
- docs/CODEX_HOOKS_PLAN.md
- docs/CODEX_HOOK_TESTS.md
- docs/CODEX_PARITY_MATRIX.md
- docs/CODEX_BATCHES.md
- runs/codex/**

acceptance:
- future

regression:
- R1
- R2
- R4
- R8

done_when:
- spec grounding hook has positive and negative tests
- identifier grounding hook has positive and negative tests
- pre-submit gate requires verification evidence
- reviewer skill/subagent plan exists or is explicitly deferred

---

## B8 First-Student Onboarding

status: done
parity_ids: P27

allowed_files:
- docs/**
- .agents/skills/**
- tests/codex_runtime/**
- scripts/codex_check.py
- runs/codex/**

acceptance:
- future

regression:
- R1
- R2
- R4

done_when:
- API-token setup path is documented and checkable
- cookie setup path is documented and checkable
- unsupported quiz/cookie paths fail closed into skip/manual handling
- onboarding does not require private course IDs

---

## B9 Plugin Packaging

status: done
parity_ids: P28

allowed_files:
- plugins/**
- docs/**
- tests/codex_runtime/**
- scripts/codex_check.py
- runs/codex/**

acceptance:
- future

regression:
- R1
- R2

done_when:
- Codex plugin manifest exists
- packaged skills match repo skills or drift is checked
- plugin install instructions are public-safe

---

## B10 Codex Exec / CI Automation

status: done
parity_ids: P29

allowed_files:
- .github/**
- docs/**
- scripts/**
- tests/**
- runs/codex/**

acceptance:
- future

regression:
- R1
- R2
- R4

done_when:
- non-interactive command is documented
- CI runner uses least privilege
- automation never uses committed auth or private cookies

---

## B11 Sync Planner Hardening And Critical Parity Gates

status: done
parity_ids: P30, P31, P32, P33, P34, P35, P36, P37

allowed_files:
- .agents/skills/cc-sync-execute-loop/**
- .agents/skills/cc-sync-runner/SKILL.md
- .agents/skills/canvas-setup/SKILL.md
- scripts/codex_cc_sync_plan.py
- scripts/codex_check.py
- tests/codex_runtime/**
- tests/codex_hooks/**
- tests/codex_bootstrap/**
- docs/CODEX_CC_SYNC_WORKFLOW.md
- docs/CODEX_PARITY_MATRIX.md
- docs/CODEX_BATCHES.md
- runs/codex/2026-05-07/**

forbidden_files:
- .claude/**
- CLAUDE.md
- runs/codex/cc_sync_baseline.json
- SECRETS.md
- courses.yaml
- src/canvas_submit_origin.py
- private course skill bodies copied into .agents/**

acceptance:
- B11-A1 reviewed sync plan schema includes source, surface, public_sync, codex_status, verification_target, and new_skill_needed fields.
- B11-A2 supporting runtime/test files referenced by changed Claude skills/hooks are surfaced as supporting-runtime.
- B11-A3 path-based private-only rules override regex private-marker results.
- B11-A4 canvas-setup is classified as setup/onboarding and has a public-safe Codex skill skeleton.
- B11-A5 runner-script guard parity is either implemented with fixtures or documented as a Codex hook-model gap with a failing/blocked check.
- B11-A6 private quiz/live-action behavior is classified no-sync and Codex fail-closed/manual behavior has fixture coverage.
- B11-A7 current-git, untracked, and baseline-drift sources are distinguished in sync output.
- B11-A8 checker/test preflight compiles planner and fixture runners before batch-specific assertions.
- B11-A9 cc-sync-execute-loop validates as a skill, documents one-shot and same-dialog loop modes, and its lock helper supports status/claim/heartbeat/release commands.

regression:
- R1
- R2
- R4
- R8
- existing B4 scan checks still pass
- existing B5 execute checks still pass
- existing B7 advanced hook checks still pass
- existing B8 onboarding checks still pass

done_when:
- `python scripts/codex_check.py --batch B11` exists and exits 0
- `runs/codex/<date>/PARITY_B11.md` exists
- `runs/codex/<date>/REVISED_CC_SYNC_PLAN.md` is generated by the reviewed planner path
- `.agents/skills/canvas-setup/SKILL.md` remains public-safe and guarded until execution-ready
- `.agents/skills/cc-sync-execute-loop/SKILL.md` remains public-safe and guarded by a lock helper
- no `.claude/**` files are modified
- `runs/codex/cc_sync_baseline.json` is unchanged unless the user explicitly approves baseline update after B11 passes

---

## B12 Setup Runtime Parity

status: done
parity_ids: P38, P39

allowed_files:
- .agents/skills/canvas-setup/SKILL.md
- scripts/codex_check.py
- tests/codex_runtime/**
- docs/CODEX_BATCHES.md
- docs/CODEX_PARITY_MATRIX.md
- runs/codex/2026-05-07/**

forbidden_files:
- .claude/**
- CLAUDE.md
- SECRETS.md
- courses.yaml
- .env
- .cookies/**
- runs/codex/cc_sync_baseline.json

acceptance:
- B12-A1 setup skill is execution-ready and no longer has `PLANNED_SKILL_SKELETON v1`.
- B12-A2 setup state matrix covers missing `.env`, incomplete Canvas config, empty routes, and complete config.
- B12-A3 setup skill routes auth-complete-but-empty-routes state to `canvas-bootstrap`.
- B12-A4 setup skill stops before `canvas-scan`, `canvas-execute`, assignments scan, result writing, report writing, or submission.
- B12-A5 student-facing contract does not tell the student to edit `.env`, run shell commands, or inspect internal config files.
- B12-A6 setup fixture tests are offline and contain no private course IDs, emails, instructor names, or private URLs.

regression:
- R1
- R2
- R4
- existing B4 scan checks still pass
- existing B8 onboarding checks still pass

done_when:
- `python scripts/codex_check.py --batch B12` exists and exits 0
- `runs/codex/<date>/PARITY_B12.md` exists
- `.agents/skills/canvas-setup/SKILL.md` is public-safe and execution-ready
- no `.claude/**` files are modified
- `runs/codex/cc_sync_baseline.json` is unchanged unless the user explicitly approves baseline update after all sync batches pass

---

## B13 Guard Parity

status: done
parity_ids: P40, P41, P42, P43

allowed_files:
- .codex/hooks/**
- tests/codex_hooks/**
- scripts/codex_check.py
- docs/CODEX_BATCHES.md
- docs/CODEX_PARITY_MATRIX.md
- runs/codex/2026-05-07/**

forbidden_files:
- .claude/**
- CLAUDE.md
- SECRETS.md
- courses.yaml
- runs/codex/cc_sync_baseline.json
- private course skill bodies copied into .agents/**

acceptance:
- B13-A1 post-tool guard blocks ad-hoc runner scripts under `runs/**`.
- B13-A2 post-tool guard allows normal non-runner artifacts under `runs/**`.
- B13-A3 stop guard treats execute markers with a different session owner as non-blocking.
- B13-A4 stop guard blocks matching-session execute markers with missing or invalid results.
- B13-A5 pre-tool guard blocks private/live quiz submit or complete actions without using public Codex automation.
- B13-A6 generic submit/upload commands still require `verification.log` with PASS and no FAIL.

regression:
- R1
- R2
- R4
- R8
- existing B7 advanced hook checks still pass

done_when:
- `python scripts/codex_check.py --batch B13` exists and exits 0
- `runs/codex/<date>/PARITY_B13.md` exists
- no `.claude/**` files are modified
- `runs/codex/cc_sync_baseline.json` is unchanged unless the user explicitly approves baseline update after all sync batches pass

---

## B14 Bootstrap UX Refresh

status: done
parity_ids: P44, P45

allowed_files:
- .agents/skills/canvas-bootstrap/SKILL.md
- tests/codex_bootstrap/**
- scripts/codex_check.py
- docs/CODEX_BATCHES.md
- docs/CODEX_PARITY_MATRIX.md
- runs/codex/2026-05-07/**

forbidden_files:
- .claude/**
- CLAUDE.md
- SECRETS.md
- courses.yaml
- runs/codex/cc_sync_baseline.json
- private course skill bodies copied into .agents/**

acceptance:
- B14-A1 bootstrap decision table uses main, likely-real, and noise buckets.
- B14-A2 noise courses are hidden from default mapping unless the user asks to show them.
- B14-A3 likely-real courses are visible but labeled as lower-confidence until recurring patterns appear.
- B14-A4 cross-course bundling remains rejected.
- B14-A5 generated skeleton sentinel remains enforced.

regression:
- R1
- R2
- R4
- existing B3 bootstrap checks still pass

done_when:
- `python scripts/codex_check.py --batch B14` exists and exits 0
- `runs/codex/<date>/PARITY_B14.md` exists
- no `.claude/**` files are modified
- `runs/codex/cc_sync_baseline.json` is unchanged unless the user explicitly approves baseline update after all sync batches pass

---

## B15 Plugin Packaging Reality Check

status: done
parity_ids: P46, P47

allowed_files:
- plugins/**
- scripts/codex_plugin_check.py
- tests/codex_runtime/run_plugin_tests.py
- scripts/codex_check.py
- docs/CODEX_BATCHES.md
- docs/CODEX_PARITY_MATRIX.md
- runs/codex/2026-05-07/**

forbidden_files:
- .claude/**
- CLAUDE.md
- SECRETS.md
- courses.yaml
- runs/codex/cc_sync_baseline.json
- private course skill bodies copied into plugins/**

acceptance:
- B15-A1 plugin packaging mode is explicitly documented as manifest-only.
- B15-A2 plugin manifest declares every public-safe repo skill that should ship in the sidecar.
- B15-A3 plugin drift check verifies every declared skill has a repo skill.
- B15-A4 plugin drift check rejects undeclared required public-safe skills.
- B15-A5 plugin tests cover setup and execute-loop skills.

regression:
- R1
- R2
- existing B9 plugin checks still pass

done_when:
- `python scripts/codex_check.py --batch B15` exists and exits 0
- `runs/codex/<date>/PARITY_B15.md` exists
- no `.claude/**` files are modified
- `runs/codex/cc_sync_baseline.json` is unchanged unless the user explicitly approves baseline update after all sync batches pass
