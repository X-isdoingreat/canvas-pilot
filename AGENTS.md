# Codex Entry — canvas-pilot

> Repo-level Codex instructions for this project.
>
> This file was migrated from:
> - `~/.claude/CLAUDE.md` (global working rules; on Windows resolves to `%USERPROFILE%\.claude\CLAUDE.md`)
> - `CLAUDE.md` (repo-specific Claude Code entry)
> - `CLAUDE.local.md` (currently empty)
>
> **Privacy rule:** repo-level Codex guidance must not contain personal identity, school identity, emails, real course IDs, instructor names, or other per-user/per-quarter details. Keep those in private local/global Claude config or `SECRETS.md`.

---

## 0. Current Plan

Codex support is a sidecar driver, not a replacement for the existing Claude Code driver.

1. Keep `.claude/` production behavior unchanged.
2. Build Codex support beside it through `AGENTS.md`, `.codex/`, `.agents/skills/`, and/or `plugins/`.
3. Do not refactor shared logic until the Codex path has run successfully several times.
4. Manually sync only the small protocol surface:
   - run state schema: `plan.json`, `assignments.json`, `result.json`, `_processed.json`
   - flow rules: scan stops, execute needs approval, every item needs result.json, report is the user-facing closeout
   - public/private boundary rules

Codex should be Codex-native. Claude Code should remain Claude-native.

---

## 1. Open Questions / Ambiguities

These are unresolved and should be clarified before large changes:

1. **Public safety of `AGENTS.md`:** keep this file free of personal identity, real school/course identifiers, emails, instructor names, and incident-specific private details. If such data appears, remove it immediately and move it to private local/global config or `SECRETS.md`.
2. **Codex hook location:** Codex supports hooks, but exact repo-local config shape should be verified against the current Codex version before wiring `.codex/hooks.json` or `.codex/config.toml`.
3. **Skill packaging:** Codex repo skills are read from `.agents/skills`; plugins can package skills under `plugins/<name>/skills`. We need to choose whether v0 is plain repo skills or a local plugin.
4. **Migration depth:** v0 should probably migrate only `canvas-scan`, `canvas-execute`, and `canvas-skip`; private course skills should stay Claude-only until the sidecar path is proven.
5. **Hook parity:** Claude hooks are already production-tested. Codex hooks should initially duplicate only basic guards, not claim full parity.
6. **Upstream safety:** if `AGENTS.md` is committed, ensure public-leak protection catches it before any `git push upstream`.
7. **Codex user install path:** decide whether external users install a plugin, clone repo skills, or just rely on `AGENTS.md` plus commands.
8. **Shared docs:** decide whether to create `docs/CANVAS_PILOT_CONTRACT.md`, `docs/RUN_STATE_SCHEMA.md`, and `docs/PUBLIC_PRIVATE_BOUNDARY.md`, or keep v0 guidance only here.

If any of these affects a code or architecture change, stop and ask the user before editing.

---

## 2. Global Working Discipline

Precision is more important than speed. Understanding is more important than execution.

For any operation that could break behavior, leak private content, or change architecture, state:

- In progress: the action
- Expected: the concrete result
- If correct: the next step
- If wrong: the recovery step

Then execute and compare the result with the expectation.

Rules:

- Distinguish "I think" from "I verified".
- Say "I am not sure" rather than inventing certainty.
- If the user's intent is ambiguous, ask before doing large work.
- Read code before editing it.
- Code is the source of truth; docs may be stale.
- If reality surprises you, stop and debug the assumption, not the symptom.
- After changing code, check whether docs need to be updated.
- On Windows, do not use `~`; expand to a full path (e.g., `%USERPROFILE%\...` or `C:\Users\<your-username>\...`).

Local/private identity context belongs in user-level Codex/Claude config, not in this repo file. If a task needs real user identity, course IDs, instructor names, or emails, read `SECRETS.md` privately and do not copy those values into generic docs, skills, or public-facing files.

---

## 3. Product Documentation Pattern

Each product repo maintains:

| File | Role | When to update |
|---|---|---|
| `_private/decisions/north-star.md` | who it is for, stance, future candidates, mechanism + decisions | functional or architectural change / quarterly review |
| `北极星方针.md` | ⚠️ STALE 2026-05-14 (双仓时期), redirects to north-star.md | superseded — historical reference only |
| `产品实现逻辑.md` | ⚠️ STALE 2026-05-14 (origin/upstream era), redirects to north-star.md | superseded — historical reference only |
| `MM.DD.md` | current point-in-time state | around commits; delete when stale |

For this repo, also read:

- `Claude Code-Codex 生态.md` for the Claude/Codex driver map.
- `canvas-skill.md` for project history and troubleshooting.
- `IMPLEMENTATION.md` for current implementation state.
- `ARCHITECTURE.md` for component flow.
- `SECRETS.md` for per-user/per-quarter identifiers. It is gitignored and private.

---

## 4. Driver Boundary

This repo currently has a production Claude Code driver.

Do not modify these unless the user explicitly asks:

- `.claude/settings.json`
- `.claude/hooks/*`
- `.claude/skills/*`
- `.claude/agents/*`
- `CLAUDE.md`

Codex work should initially stay in:

- `AGENTS.md`
- `.codex/`
- `.agents/skills/`
- `plugins/`
- Codex-specific docs

Do not try to unify the drivers early. Duplication is acceptable in v0 if it prevents pollution of the working Claude path.

---

## 5. TWO REPOS: Never Leak Private Content Into Public Mirror

This project has two remotes:

| Remote | Visibility | Contains |
|---|---|---|
| `origin` | private | full project: private skills, course IDs, private operating values, incident logs |
| `upstream` | public | framework only: generic Canvas client, scan/execute pattern, login flow |

Public-safe candidates:

- generic `src/*.py`
- generic setup docs
- generic framework skills only after review
- public-safe README / examples

Never public:

- `.claude/skills/canvas-ics33/`
- `.claude/skills/canvas-reading-annotation/`
- `.claude/skills/canvas-inside/`
- `.claude/skills/canvas-zybooks/`
- `SECRETS.md`
- `courses.yaml` with real course IDs
- real school/course names, instructor names, section numbers, emails, incident specifics
- `北极星方针.md`
- `产品实现逻辑.md`
- `Claude Code-Codex 生态.md`
- `.kiro/`
- `.claude/skills/kiro-*`

Before any commit or push, ask:

> If this commit lands on `upstream/main` and gets indexed, does it expose private homework automation tied to a real user's identity?

If yes or unsure, keep it origin-only.

---

## 6. Core Product Rule: Canvas Description Is Usually Not The Spec

Canvas `assignment.name` and `assignment.description` are routing hints, not the real assignment spec.

Before doing unfamiliar work, inspect the true source:

- code courses: course front page -> external instructor site -> schedule -> project/exercise spec
- document courses: modules -> homework page -> files/readings
- quizzes: Canvas quiz API plus module readings / study notes
- zyBooks-style assignments: Canvas description table may identify assigned exercises, but zyBooks payload metadata is not instructor truth
- attached PDF / GradeScope work: download/read the actual file; GradeScope is usually the delivery endpoint, not the spec source

Rule:

1. Read Canvas description, but treat it as a hint.
2. Pull course front page, modules, syllabus body, attached files, links, and external tools as needed.
3. Follow the hint to the real source.
4. Put concrete IDs and private URLs in `SECRETS.md`, not in public docs or generic skills.

This is a core product value. Do not guess a spec from a thin Canvas description.

---

## 7. Canvas Workflow Rules

The workflow boundary is structural:

1. `canvas-scan` scans Canvas, writes `runs/<today>/plan.json` and `runs/<today>/assignments.json`, renders a plan, then stops.
2. The user reviews the plan and explicitly approves work.
3. `canvas-execute` reads the approved plan, dispatches approved items, writes one `result.json` per assignment, creates `REPORT.md`, and syncs `final_drafts/`.

Codex must preserve the same boundary:

- Do not execute assignments during scan.
- Do not execute without user approval.
- Do not bypass per-course playbooks by doing work directly in a router.
- Every assignment must end with a valid `result.json`.
- `REPORT.md` is the closeout surface for the user.

Default behavior is draft production, not submission. Do not submit to Canvas without explicit authorization documented for that exact workflow.

---

## 8. Operating Values

1. **Recurring > one-shot.** Prioritize workflows that repeat every week.
2. **Skeleton without answers is not done.** Rendering placeholders is not a completed draft.
3. **`submitted` does not mean correct.** It only means Canvas received an attempt; correctness is unknown until graded.
4. **Spec -> numeric constraints -> real measurement.** Count pages, sentences, imports, functions, examples, etc. Do not rely on vibes.
5. **Hard deadlines need a loud banner.** Due <=24h items that are not submitted/graded must appear at the top of `REPORT.md`.
6. **Honesty over confidence.** Separate verified facts from judgment calls in `result.json` and status reports.

---

## 9. Critical Do-Nots

- Do not submit drafts to Canvas without explicit authorization.
- Do not write overly polished document-course outputs when the required voice is B1-B2 international student style.
- Do not commit `.env`, `runs/`, `SECRETS.md`, `.cookies/`, `final_drafts/`, or draft artifacts.
- Do not hardcode course IDs, file IDs, instructor names, section numbers, or emails in generic skills.
- Do not push private product docs or private course automation to `upstream`.
- Do not modify `.claude/` while building Codex support unless the user explicitly asks.
- Do not treat AGENTS.md as enough to enforce safety; hooks/guards still need testing.

---

## 10. Windows / Python Pitfalls

- Windows console encoding can corrupt math/Chinese output. Configure UTF-8 explicitly in scripts that print such text.
- In Git Bash, `$CLAUDE_PROJECT_DIR` can be path-mangled. Use absolute Windows paths in hook config.
- Local Python is 3.11; avoid newer features unless verified.
- PyMuPDF font names can be non-obvious; `hebo` is Helvetica-Bold.
- For zyBooks auth, JWT lives in localStorage, not cookies.

---

## 11. Fresh Session Checklist

When Codex starts in this repo:

1. Read this `AGENTS.md`.
2. Read `Claude Code-Codex 生态.md` §8 for the dual-driver decision.
3. If doing product or implementation work, read `_private/decisions/north-star.md` (the consolidated post-2026-05-14 source of truth). `北极星方针.md` / `产品实现逻辑.md` / `IMPLEMENTATION.md` / `ARCHITECTURE.md` are STALE — see their header warnings.
5. If touching Canvas course behavior, read `SECRETS.md` privately.
6. Check `git status --short` before edits.
7. Keep `.claude/` unchanged unless explicitly asked.
