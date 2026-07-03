# Canvas Pilot — Claude Code session instructions

This file is auto-loaded by Claude Code on every session in this project.
Keep it short. The product flow, architecture, design principles, skill
descriptions, and the core rules all live in **[README.md](./README.md)**.
That file is the single source of truth.

When you start a session here, read these README sections first:

- "The product flow" — one entry, three branches, single-cluster bootstrap,
  first-run calibration loop.
- "The 9 skills" — what each skill is and which pipeline stages it has.
- "The core rule: `assignment.description` is rarely the real spec" — the
  single most common failure mode if you skip it.
- "Agent stops at can't-do, not shouldn't-do" — when to stop, when to
  soft-stop, when not to stop.
- "Git hygiene and critical do-nots" — what not to commit, what not to
  dispatch from where.

---

## Session operational rules (Claude-Code-specific, not in README)

These are the few rules that exist *only* because Claude Code is the
runtime, not because they belong to the product flow.

1. **The SessionStart hook prints a context message when `.env` is
   missing or `CANVAS_BASE` is empty.** When you see that message,
   dispatch `canvas-setup` on the student's next message. Do not
   improvise a setup conversation. Do not read `SETUP.md` to the
   student. Do not ask them to edit files or run commands manually.
   If you find yourself writing a setup conversation outside the
   skill, stop. That is the failure mode the skill exists to prevent.

2. **`canvas-scan` produces a plan and stops. `canvas-execute`
   dispatches after the user approves.** Never dispatch per-course
   skills from `canvas-scan`. The two-skill split is the approval
   gate; collapsing it into one breaks the gate.

3. **One assignment = one work directory = one `result.json`.** The
   Stop hook refuses to release the session until every dispatched
   assignment has produced a valid `result.json`. If a run crashes,
   clean up the `.scan_in_progress` marker before stopping; the Stop
   hook will hold the session otherwise.

4. **`git add` always names specific paths.** Never `git add -A`,
   never `git add .`, never `git add -f`. `.gitignore` covers
   `.env`, `runs/`, `SECRETS.md`, `courses.yaml`, `_private/`,
   `sources/`, `.cookies/`. Trust it but verify with `git diff
   --cached` before committing.

---

## Feedback writeback (permanent)

Whenever the user gives feedback on a per-course skill's draft —
during a first-run calibration in `canvas-bootstrap` §8, OR any
subsequent review of a draft produced by `canvas-execute`'s
dispatched skills — do NOT silently apply the change and move on.
Classify the feedback first; write recurring preferences back to
the relevant overlay so the next dispatch honors them automatically.

The full categorization protocol lives at
[docs/feedback-categorization.md](./docs/feedback-categorization.md).
Both bootstrap §8 and this permanent rule reference that doc — it is
the single source of truth for the three categories (`one_off` /
`recurring_pattern` / `workflow_change`), the inline-vs-Sub-agent-D
decision, the overlay edit diff format, and the file-path resolution
including the `canvas-generic` learnings overlay slug.

**Heuristic for this permanent rule (Mode B / inline)**:

- Clearly `one_off` (typo, specific data point, this-draft-only
  phrasing) → apply silently, move on.
- Looks like `recurring_pattern` (voice, color, citation style,
  formatting) or `workflow_change` (skip stage X / always do Y first):
  apply to current draft, then at the END of the response append:
  > 顺便：'<paraphrased feedback>' 这条要不要也写进 skill 下次自动这样？
- On `yes`: propose a specific overlay edit (show the diff per the
  protocol doc), confirm, write back to
  `_private/canvas-<framework>-app.md` (or
  `_private/canvas-generic-<course_id>-<cluster_slug>.md` for
  canvas-generic clusters).
- On `no` / silence: do nothing. Do not re-ask the same kind of
  question later in this session.
- When in doubt, ask. Missing a recurring preference is worse than
  asking once.

This rule fires in every session, not just bootstrap. It is how
overlays stay current with the student's evolving preferences without
requiring a full bootstrap re-run for every nuance.

---

## Pointers

- [README.md](./README.md) — product flow, architecture, design
  principles, skill descriptions, core rules.
- [CLAUDE.local.md](./CLAUDE.local.md) — your private session notes
  (gitignored). Project-specific operator memory lives here.
- `SECRETS.md`, `courses.yaml`, `_private/canvas-*-app.md` — local
  config (all gitignored).
- `runs/<today>/REPORT.md` — latest run output.
- `docs/NORTH_STAR.md`, `docs/SKILL_DESIGN.md` — internal design docs
  (some content has been migrated into README; these files are kept
  for now but may be merged or pruned later).
