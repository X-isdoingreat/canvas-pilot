# Codex Self-Run Requirements

This is the complete requirement set for making Codex able to run its own
Canvas Pilot sidecar build in small verified stages.

## Goal

Codex must be able to enter the repo, find the next batch, execute only that
batch, verify it, report it, and either mark it done or block with evidence.

## Requirement Classes

| ID | Requirement | Verification |
|---|---|---|
| SR1 | There is exactly one control plane for long work | `docs/CODEX_BATCHES.md` |
| SR2 | There is one top-level architecture plan | `docs/CODEX_MASTER_PLAN.md` |
| SR3 | Every batch has `status`, `parity_ids`, `allowed_files`, `acceptance`, `regression`, `done_when`, and `report` | A23 |
| SR4 | Only one batch may be `in_progress` | A24 |
| SR5 | At most one batch may be `next` | A25 |
| SR6 | There are no duplicate batch IDs | A26 |
| SR7 | No batch uses `acceptance: future` | A27 |
| SR8 | No batch uses `report: future` or omits report | A28 |
| SR9 | `scripts/codex_check.py` must support every non-legacy batch before that batch can be executed | A29 and per-batch checks |
| SR10 | Stop hook must block an in-progress batch with no report | H8 |
| SR11 | Stop hook must block execute-mode sessions with missing `result.json` | H5 |
| SR12 | Allowed files are a hard edit boundary | protocol + PostToolUse guard |
| SR13 | Every implementation batch has offline fixtures before live Canvas use | B6 acceptance |
| SR14 | Scan and execute remain structurally split | B4/B5 acceptance |
| SR15 | No private identity enters Codex docs or skills | R2 |
| SR16 | Claude driver remains untouched by Codex batches | R1 |
| SR17 | Generated course skills must have an unfilled-skeleton sentinel | B3 acceptance |
| SR18 | Student auth paths are explicit for API token and cookie modes | B8 acceptance |
| SR19 | Submission is never default behavior | B5/B7/B8 acceptance |
| SR20 | Reports are the evidence trail for completed batches | batch protocol + A23 |
| SR21 | CC updates can generate a sync plan without copying `.claude/` into Codex | `scripts/codex_cc_sync_plan.py` + `$cc-sync-runner` |

## Batch Requirement Map

| Batch | Requirement surface | Must prove |
|---|---|---|
| B3 | bootstrap | first-run route setup, skeleton sentinel, public-safe generated skills |
| B4 | scan | auth probe, dry-run scan, plan generation, no execution |
| B5 | execute | approval parser, dispatch, result ledger, report, no unapproved work |
| B6 | runtime fixtures | offline fake Canvas suite and scan/execute boundary tests |
| B7 | advanced hooks | spec grounding, identifier grounding, pre-submit verification gate |
| B8 | onboarding | API token path, cookie path, unsupported paths fail closed |
| B9 | plugin packaging | installable Codex plugin with drift checks |
| B10 | automation | non-interactive/CI path with least privilege and no committed auth |

## Required Check Runner Shape

`scripts/codex_check.py` must eventually support:

```powershell
python scripts\codex_check.py --batch B2
python scripts\codex_check.py --batch B3
python scripts\codex_check.py --batch B4
python scripts\codex_check.py --batch B5
python scripts\codex_check.py --batch B6
python scripts\codex_check.py --batch B7
python scripts\codex_check.py --batch B8
python scripts\codex_check.py --batch B9
python scripts\codex_check.py --batch B10
```

Each batch command must:

1. Run that batch's acceptance checks.
2. Run that batch's regression checks.
3. Run privacy checks.
4. Check allowed file scope when a batch is `in_progress`.
5. Exit nonzero on failure.
6. Print a short evidence trail.

## Required Report Shape

Every `runs/codex/<date>/PARITY_<batch>.md` must include:

- batch id
- status
- scope
- changed files
- acceptance results by ID
- regression results by ID
- warnings
- blocked items
- whether `.claude/` or `CLAUDE.md` changed
- next batch recommendation

## Self-Run Ready Definition

The system is self-run ready when:

1. A23-A29 pass.
2. B3-B10 have concrete acceptance IDs, not `future`.
3. `scripts/codex_check.py --batch <id>` exists for the active batch.
4. Stop hook blocks unfinished active batches.
5. A batch can be claimed, implemented, checked, reported, and marked done
   without relying on chat memory.
