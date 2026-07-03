---
name: cc-sync-runner
description: "Use when Claude Code changed and Codex should create a replacement CC-to-Codex plan and any needed public-safe Codex skill/batch drafts. Default behavior is planning-production: generate the raw sync plan, run independent subagent audits, then write a corrected plan, capability gaps, proposed batches, verification targets, and new skill specs/skeletons when a missing Codex capability requires a skill. Do not stop at saying the raw plan is wrong. Only implement runtime behavior, claim batches, or update baseline when the user explicitly asks to execute the approved plan, continue roadmap, auto next step, or run until blocked."
---

# CC Sync Runner

Produce a corrected CC-to-Codex plan and the next public-safe Codex skill/batch
drafts. Implementation is a separate explicit mode. Do not copy `.claude/`
files into Codex. Treat `.claude/` as read-only.

The default output is not a critique. It is a replacement planning package that
answers:

- What Claude Code currently has.
- What Codex already covers.
- What Codex lacks.
- Which gaps are public-safe, private-only, redacted, or manual-review.
- What verification scripts/tests must exist before any implementation is
  considered done.
- Which new Codex skills or skill skeletons must be created.

## Market Pattern

Use the standard builder loop:

1. Durable rules in `AGENTS.md`.
2. Repeatable workflow in this skill.
3. Long-horizon state in `docs/CODEX_BATCHES.md`.
4. Machine checks in `scripts/codex_check.py`.
5. Stop hooks and reports to prevent early finish.
6. Optional `codex exec` automation later, after local runs are stable.

This is not "one giant prompt". It is a bounded planning-production loop:

```text
raw sync plan -> subagent audits -> capability gap ledger
              -> replacement sync plan -> new skill specs/skeletons
              -> proposed batches/checks -> final plan audit -> stop
```

## Modes

### Planning Mode

Default mode for requests like "sync CC to Codex", "run CC sync", "review
CC_SYNC_PLAN", "rewrite the plan", "what does Codex lack", "create the missing
Codex skill", or "make a plan".

Planning Mode must not:

- claim a batch
- edit `docs/CODEX_BATCHES.md` status
- implement runtime behavior
- update the CC baseline
- touch `.claude/`

It may write or refresh planning artifacts under `runs/codex/<today>/`, such as:

- `CC_SYNC_PLAN.md`
- `REVISED_CC_SYNC_PLAN.md`
- `CAPABILITY_GAPS.md`
- `PROPOSED_BATCHES.md`
- `NEW_SKILL_SPECS.md`
- `CC_SYNC_REVIEW.md` as an appendix only, not the main output

It may also create public-safe Codex skill skeletons under `.agents/skills/**`
when the plan's primary conclusion is "Codex needs a new skill". These
skeletons must be generic, redacted, and guarded with TODO/sentinel language if
they are not execution-ready. Creating a skeleton is planning output; filling it
with live runtime implementation is Execute Approved Plan Mode.

If the user asks to "fix the plan", "rewrite the plan", "create the missing
skill", or "make the skill better at planning", change only Codex-side planning
scripts, tests, docs, public-safe `.agents/skills/**` skeletons, or this skill,
and stop after verification.

### Execute Approved Plan Mode

Use this mode only when the user explicitly says "execute the approved plan",
"implement the plan", "run the sync plan", or equivalent.

Run only batches directly suggested by `CC_SYNC_PLAN.md`. When those batches
pass and the CC baseline is updated, stop.

### Roadmap Until Blocked Mode

Use this mode when the user says "continue", "auto next step", "until blocked",
"keep going", or asks why the runner did not automatically continue.

After diff sync is complete, continue with the next available roadmap batch:

1. If a batch is `in_progress`, continue it.
2. Else choose the first `status: next`.
3. Else promote the earliest eligible `status: later` batch to `next`, then
   claim it.
4. Run the same check/fix/report loop.
5. Repeat until a hard stop condition occurs or no eligible batch remains.

Do not skip batch order. B4 comes before B5, B5 before B6, etc.

## Required Reading

Read only what is needed:

- `docs/CODEX_CC_SYNC_WORKFLOW.md`
- `docs/CODEX_MASTER_PLAN.md`
- `docs/CODEX_BATCHES.md`
- `docs/CODEX_SELF_RUN_REQUIREMENTS.md`
- `runs/codex/<today>/CC_SYNC_PLAN.md` after generating it

## Workflow

### 1. Generate the raw sync plan

Run:

```powershell
python scripts\codex_cc_sync_plan.py
```

Then read:

```text
runs/codex/<today>/CC_SYNC_PLAN.md
```

If changed files is `0` in Planning Mode, report that no CC drift was detected
against the accepted baseline and stop after the final audit gate.

If changed files is `0` in Roadmap Until Blocked Mode, continue to the next
available roadmap batch instead of stopping.

### 2. Run independent subagent audits

Before trusting `CC_SYNC_PLAN.md`, launch separate read-only subagents for the
critical review surfaces below. These reviewers must not edit files, execute
Canvas workflows, update baseline, or claim batches.

Treat every sync plan as a large change by default. Do not wait for the diff to
"look big". A single new skill, hook registration, setup/onboarding change,
submission path change, quiz/live-action change, or result schema change can
shift the whole driver contract.

Run them in parallel when possible:

| Review | Purpose | Required output |
|---|---|---|
| Diff Auditor | Compare `CC_SYNC_PLAN.md` against `git status`, `git diff`, untracked files, and baseline drift. | Missing files, false positives, and whether each item is current-git / untracked / baseline-drift. |
| Privacy Auditor | Check every planned sync item against `AGENTS.md` public/private rules and `check-public-leak.py` private-only paths. | `public_sync: yes / no / redacted / manual-review` plus rationale. |
| Parity Mapper | Convert each Claude change into "Claude has X; Codex has/does not have X". | Capability gaps, existing Codex coverage, and suggested verification target. |
| Final Plan Auditor | Review the merged plan for contradictions, stale batch references, and unsupported assumptions. | Blockers that must be resolved before execution mode. |

Trust but merge: do not blindly paste subagent output. The main agent owns the
final plan and must resolve conflicts explicitly.

### Critical Change Triggers

If any trigger below appears, mark the sync plan `critical` and give that item
extra scrutiny in every reviewer prompt:

- added, removed, or renamed `.claude/skills/**`
- added, removed, or renamed `.claude/hooks/**`
- `.claude/settings.json` hook registration changes
- `canvas-setup`, onboarding, auth, `.env`, cookie, or token flow changes
- scan/approval/execute boundary changes
- `result.json`, `plan.json`, `assignments.json`, or `_processed.json` schema
  changes
- submission/upload/live Canvas action changes
- quiz automation, quiz pacing, quiz event, retake, or anti-bypass changes
- new supporting runtime code referenced by `.claude` skills or hooks
- public/private leak guard changes

For critical plans:

- Always run the Final Plan Auditor; never skip it.
- Ask reviewers to identify one thing the raw plan is most likely to have
  missed.
- Require at least one explicit "do not sync to public Codex" decision when
  private-only or live-action behavior is present.
- If a new skill is added, create a capability record for the skill itself,
  its trigger path, its user-facing boundary, and its Codex equivalent or
  deliberate non-goal.

### 3. Produce the replacement plan and capability gaps

Create a replacement plan, not just an error report. The raw
`CC_SYNC_PLAN.md` becomes evidence; the authoritative planning output is the
reviewed replacement plan.

Required outputs in Planning Mode:

| Artifact | Purpose |
|---|---|
| `REVISED_CC_SYNC_PLAN.md` | The corrected plan to use instead of the raw plan. |
| `CAPABILITY_GAPS.md` | One record per Claude capability / Codex gap. |
| `PROPOSED_BATCHES.md` | Concrete proposed batches and checks. |
| `NEW_SKILL_SPECS.md` | New Codex skills needed, their trigger rules, and skeleton status. |
| public-safe `.agents/skills/<name>/SKILL.md` skeletons | Create when the plan calls for a new Codex skill and a redacted skeleton is safe. |

`CC_SYNC_REVIEW.md` may exist, but it is supporting evidence only. Do not make
it the main deliverable.

Each capability record must include:

Each record must include:

```text
Capability:
Evidence:
Source: current-git | untracked | baseline-drift | generated-plan
Surface: claude-driver | supporting-runtime | codex-side | private-only
Codex status: covered | missing | partial | not-planned
Public sync: yes | no | redacted | manual-review
Suggested action:
Suggested batch:
Verification target:
New skill needed: yes | no
Confidence: high | medium | low
```

Important rules:

- Do not treat `private marker seen: no` as public-safe. Path-based privacy
  rules override regex marker checks.
- Include supporting runtime changes when Claude skills/hooks rely on them
  (`src/`, `scripts/`, and tests referenced by `.claude`).
- Distinguish current worktree changes from baseline drift.
- If a suggested batch is already `done`, explain whether the existing checks
  actually cover the new capability. If not, propose a new batch or reopen the
  batch explicitly.
- If `New skill needed: yes`, create either a public-safe skill skeleton under
  `.agents/skills/**` or a `NEW_SKILL_SPECS.md` entry explaining why skeleton
  creation is blocked.

### 3a. New skill skeleton rules

When creating a public-safe Codex skill skeleton:

- Write under `.agents/skills/<skill-name>/SKILL.md`.
- Use only generic placeholders, never private course IDs, real URLs,
  instructor names, emails, identity, or incident specifics.
- Include frontmatter with `name` and `description`.
- Include a guard if unfinished:

```text
<!-- PLANNED_SKILL_SKELETON v1 -->
```

- State trigger conditions, inputs, boundaries, outputs, verification targets,
  and non-goals.
- Do not copy `.claude/skills/**` bodies.
- Do not include live Canvas submit/quiz behavior unless explicitly approved in
  a later execution mode and proven public-safe.

### 4. Classify impacted batches

Use the generated plan's `suggested Codex batch` lines.

Typical mapping:

| CC change kind | Codex batch |
|---|---|
| `canvas-bootstrap` | B3 |
| `canvas-scan` | B4 |
| `canvas-execute` / `canvas-skip` | B5 |
| hooks / settings / agents | B7 |
| course-specific private skills | B8 public framework extraction only |
| Kiro skills | manual review unless explicitly requested |

In Planning Mode, do not claim a batch. Only recommend one of:

- existing batch covers it
- reopen existing batch
- create new batch
- private-only/no public Codex sync
- manual review required

In Execute Approved Plan Mode, choose the earliest impacted non-done batch.
Work one batch at a time.

If no impacted batch exists and Roadmap Until Blocked Mode is active, choose
the next roadmap batch from `docs/CODEX_BATCHES.md`.

### 5. Final plan audit gate

Before ending Planning Mode, run or simulate a final audit pass:

1. Confirm every `.claude` change is represented.
2. Confirm every supporting runtime/test change is either represented or
   explicitly out of scope.
3. Confirm private-only content is not recommended for public Codex copying.
4. Confirm every public-safe gap has a verification target.
5. Confirm stale `done` batches are not used as proof unless their current
   checks cover the new behavior.
6. Confirm no baseline update is recommended before verification passes.
7. Confirm the main output is a replacement plan / skill draft, not only a list
   of raw-plan defects.
8. Confirm every `New skill needed: yes` item has either a skeleton or a clear
   blocked reason.

If any item fails, mark it as a blocker in the plan instead of smoothing over
it.

Planning Mode ends here.

### 6. Claim the batch

Only in Execute Approved Plan Mode.

Edit `docs/CODEX_BATCHES.md`:

```text
status: next -> status: in_progress
```

Only claim one batch. If another batch is already `in_progress`, continue that
one instead of claiming a new batch.

### 7. Run the batch check first

Only in Execute Approved Plan Mode.

Run:

```powershell
python scripts\codex_check.py --batch B<N>
```

Treat the first failing assertion as the next concrete task. Do not invent a
parallel plan when the checker already named the missing file or pattern.

### 8. Fix, rerun, repeat

Only in Execute Approved Plan Mode.

Loop:

1. Read the failure.
2. Confirm the needed edit is inside the batch's `allowed_files`.
3. Edit the smallest needed Codex-side file.
4. Rerun `python scripts\codex_check.py --batch B<N>`.

Continue until the check passes or a hard stop condition occurs.

## Hard Stop Conditions

Stop and ask the user instead of continuing if:

- the fix requires editing `.claude/` or `CLAUDE.md`
- the fix requires copying private course playbooks into Codex
- the fix requires real course IDs, assignment IDs, private URLs, emails, or names
- the needed edit is outside the active batch's `allowed_files`
- live Canvas submission or quiz action would be needed
- the checker fails for an environment/dependency issue unrelated to the batch
- two repair attempts fail on the same assertion without new evidence

## Reports

Planning Mode reports are planning artifacts only. They must summarize:

- subagent audit findings
- capability gaps
- public/private classification
- proposed batches
- proposed verification targets
- blockers before execution

They must not mark a batch done or update baseline.

Execution reports apply only in Execute Approved Plan Mode.

When the batch passes, write:

```text
runs/codex/<today>/PARITY_B<N>.md
```

Include:

- scope
- changed files
- acceptance results
- regression results
- warnings
- whether `.claude/` was touched
- next batch recommendation

Then update:

- `docs/CODEX_BATCHES.md`: `in_progress -> done`
- `docs/CODEX_PARITY_MATRIX.md`: related parity IDs to `done` or `partial`
- `docs/CODEX_TASKS.md`: related tasks complete, if applicable
- If Roadmap Until Blocked Mode is active, mark the next eligible roadmap batch
  `next` after the completed batch.

### Baseline update

Only after all diff-impacted batches pass, run:

```powershell
python scripts\codex_cc_sync_plan.py --update-baseline
```

Never update the baseline before Codex side parity is checked. In Roadmap Until
Blocked Mode, baseline update closes the CC diff portion; roadmap continuation
may continue after baseline update.

## "One Breath" Rule

This rule applies only in Execute Approved Plan Mode and Roadmap Until Blocked
Mode. It does not apply to Planning Mode.

Within one active batch, keep going until one of these is true:

- `python scripts\codex_check.py --batch B<N>` passes
- a hard stop condition occurs
- the user interrupts or redirects

Do not stop merely because a plan was written. The plan is only the start of
the loop.

In Roadmap Until Blocked Mode, after a batch passes, continue to the next batch
unless a hard stop condition applies.
