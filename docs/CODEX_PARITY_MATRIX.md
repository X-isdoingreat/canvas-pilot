# Codex Parity Matrix

This matrix tracks which Claude Code capabilities from `docs/CANVAS_PILOT_CLAUDE_FUNCTIONS.md` have a Codex sidecar equivalent.

| ID | Claude capability | Source | Codex target | Status | Acceptance | Regression |
|---|---|---|---|---|---|---|
| P01 | Codex repo entry | n/a | `AGENTS.md` | done | A1 | R2 |
| P02 | Run state schema docs | §2 | `docs/RUN_STATE_SCHEMA.md` | done | A6 | R2 |
| P03 | Public/private boundary docs | §5, §7.4 | `docs/PUBLIC_PRIVATE_BOUNDARY.md` | done | A7 | R2 |
| P04 | Scan skill skeleton | §3 | `.agents/skills/canvas-scan/SKILL.md` | done | A8, A9 | R1, R2 |
| P05 | Execute skill skeleton | §4 | `.agents/skills/canvas-execute/SKILL.md` | done | A8, A10 | R1, R2 |
| P06 | Skip skill skeleton | §6.5 | `.agents/skills/canvas-skip/SKILL.md` | done | A8, A11 | R1, R2 |
| P07 | Hook design | §7 | `docs/CODEX_HOOKS_PLAN.md` | done | A12-A15 | R1, R2, R6, R7 |
| P08 | Batch self-run protocol | §9 baseline | `docs/CODEX_BATCHES.md`, `docs/CODEX_BATCH_PROTOCOL.md` | done | A16, A17 | R1, R2 |
| P09 | Codex hook config | §1.2, §7 | `.codex/config.toml`, `.codex/hooks.json` | done | A18 | R1, R2 |
| P10 | SessionStart context hook | §7.2 | `.codex/hooks/session_start.py` | done | H1 | R1, R2, R4 |
| P11 | PreToolUse public leak guard | §7.4 | `.codex/hooks/pre_tool_guard.py` | done | H2, H3 | R1, R2, R4 |
| P12 | PostToolUse result schema guard | §7.5 | `.codex/hooks/post_tool_guard.py` | done | H4 | R1, R2, R4 |
| P13 | Stop batch / execute completion guard | §7.9 | `.codex/hooks/stop_guard.py` | done | H5, H6, H8 | R1, R2, R4 |
| P14 | Hook fail-open behavior | §7.1 | `.codex/hooks/_lib.py` | done | H7 | R1, R2, R4 |
| P15 | Hook check runner | self-check layer | `scripts/codex_check.ps1`, `tests/codex_hooks/*` | done | H1-H8 | R1, R2, R4 |
| P16 | Full private course skills | §6.1-§6.4 | none in Codex v0 | not-planned-v0 | n/a | n/a |
| P17 | Advanced grounding hooks | §7.6-§7.8 | `.codex/hooks/*` | done | `codex_check --batch B7` | R1, R2, R4 |
| P18 | Pre-submit reviewer | §8 | future Codex subagent/skill | partial | `codex_check --batch B7` | R1, R2, R4 |
| P19 | Bootstrap first-run trigger | `canvas-bootstrap` + scan §0 | `.agents/skills/canvas-bootstrap/SKILL.md` | done | `codex_check --batch B3` | R1, R2 |
| P20 | Public-safe generated course skeletons | `canvas-bootstrap` appendix | `.agents/skills/canvas-<name>/SKILL.md` template | done | `codex_check --batch B3` | R1, R2, R10 |
| P21 | Real scan behavior | scan §1-§5 | `.agents/skills/canvas-scan/SKILL.md` + fixtures | done | `codex_check --batch B4` | R1, R2, R4 |
| P22 | Scan/execute approval boundary | scan §6 | tests/codex_runtime boundary fixtures | done | `codex_check --batch B4` | R1, R2, R4 |
| P23 | Approval parser | execute §3 | `.agents/skills/canvas-execute/SKILL.md` + fixtures | done | `codex_check --batch B5` | R1, R2, R4 |
| P24 | Execute dispatch/result ledger | execute §4-§6 | Codex execute skill + fake runtime fixtures | done | `codex_check --batch B5` | R1, R2, R4 |
| P25 | REPORT and delivery closeout | execute §6-§8 | Codex execute skill + fake runtime fixtures | done | `codex_check --batch B5` | R1, R2, R4 |
| P26 | Offline runtime fixture suite | scan/execute combined | `tests/codex_runtime/**` | done | `codex_check --batch B6` | R1, R2, R4 |
| P27 | First-student API/cookie onboarding | setup/auth docs | `docs/CODEX_ONBOARDING.md` | done | `codex_check --batch B8` | R1, R2 |
| P28 | Plugin packaging | Codex distribution | `plugins/canvas-pilot-codex/**` | done | `codex_check --batch B9` | R1, R2 |
| P29 | Non-interactive automation | Codex exec / CI | `docs/CODEX_AUTOMATION.md`, `.github/workflows/codex.yml` | done | `codex_check --batch B10` | R1, R2, R4 |
| P30 | Reviewed CC sync plan schema | CC sync workflow | `scripts/codex_cc_sync_plan.py`, `runs/codex/**` | done | B11-A1 | R1, R2 |
| P31 | Supporting runtime detection | Claude skill/runtime references | `scripts/codex_cc_sync_plan.py` | done | B11-A2 | R1, R2 |
| P32 | Path-based public/private sync classification | public leak rules | sync planner privacy classification | done | B11-A3 | R2 |
| P33 | Codex setup skill skeleton | `canvas-setup` | `.agents/skills/canvas-setup/SKILL.md` | done | B11-A4 | R1, R2 |
| P34 | Runner-script guard parity target | `check-no-runner-script.py` | Codex hook fixture or documented hook-model gap | done | B11-A5 | R1, R4 |
| P35 | Private quiz/live-action fail-closed target | `canvas-inside` guardrails | Codex execute/runtime fixtures | done | B11-A6 | R1, R2, R4 |
| P36 | Source labeling for CC drift | baseline vs worktree drift | `CC_SYNC_PLAN.md` replacement schema | done | B11-A7 | R1 |
| P37 | Checker/test preflight | self-run safety | `scripts/codex_check.py` | done | B11-A8 | R1, R2, R4 |
| P38 | Public-safe setup runtime entry | `canvas-setup` | `.agents/skills/canvas-setup/SKILL.md` | done | B12-A1, B12-A3, B12-A4 | R1, R2, R4 |
| P39 | Setup state matrix fixtures | setup/onboarding states | `tests/codex_runtime/run_setup_tests.py` | done | B12-A2, B12-A5, B12-A6 | R1, R2, R4 |
| P40 | Runner-script write guard | `check-no-runner-script.py` | `.codex/hooks/post_tool_guard.py` + hook fixtures | done | B13-A1, B13-A2 | R1, R2, R4 |
| P41 | Session-scoped execute marker | `check-router-complete.py` | `.codex/hooks/stop_guard.py` + hook fixtures | done | B13-A3, B13-A4 | R1, R4 |
| P42 | Private quiz live-action fail-closed guard | `canvas-inside` guardrails | `.codex/hooks/pre_tool_guard.py` + hook fixtures | done | B13-A5 | R1, R2, R4 |
| P43 | Generic verification-before-submit guard | `check-presubmit-audit.py` | `.codex/hooks/pre_tool_guard.py` + hook fixtures | done | B13-A6 | R1, R4 |
| P44 | Bootstrap richer course triage | `canvas-bootstrap` UX | `.agents/skills/canvas-bootstrap/SKILL.md` | done | B14-A1, B14-A2, B14-A3 | R1, R2, R4 |
| P45 | Bootstrap mapping safeguards retained | `canvas-bootstrap` route design | `tests/codex_bootstrap/run_bootstrap_tests.py` | done | B14-A4, B14-A5 | R1, R2, R4 |
| P46 | Plugin packaging mode clarity | Codex plugin distribution | `plugins/canvas-pilot-codex/README.md` | done | B15-A1 | R1, R2 |
| P47 | Plugin skill manifest drift check | Codex plugin distribution | `plugins/canvas-pilot-codex/.codex-plugin/plugin.json`, `scripts/codex_plugin_check.py` | done | B15-A2, B15-A3, B15-A4, B15-A5 | R1, R2 |

Status values:

- `done`: implemented and verified for Codex sidecar scope.
- `partial`: implemented but missing planned checks.
- `todo`: planned but not implemented.
- `next`: planned next; not yet implemented or verified.
- `not-planned-v0`: explicitly out of the first Codex sidecar scope.
