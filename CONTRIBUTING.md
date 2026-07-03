# Contributing to Canvas Pilot

Thanks for your interest. Canvas Pilot is a
[Claude Code](https://claude.com/claude-code) project: the behavior lives in
Markdown skill files under `.claude/skills/`, and the Python in `src/` is
API-primitive glue (Canvas client, PDF tooling, verifiers). Most contributions
are either (a) framework Python / hook fixes or (b) skill-prose improvements.

By participating in this project you agree to abide by its
[Code of Conduct](./CODE_OF_CONDUCT.md).

## Ground rules — read these or your PR will be rejected on sight

This repo ships under a strict public/private split.

- **Never commit personal or school-identifying data.** Course IDs, file IDs,
  instructor names, school names, emails, cookies, JWTs, real drafts — none of
  it. All of that lives in gitignored paths (`_private/`, `SECRETS.md`,
  `courses.yaml`, `.env`, `.cookies/`, `sources/`, `runs/`). A `PreToolUse`
  hook (`.claude/hooks/check-public-leak.py`) blocks commits that add known
  identity literals, but the hook is a backstop, not a license to be careless.
- **`git add` always names explicit paths.** Never `git add -A`, `git add .`,
  or `git add -f`. Verify with `git diff --cached` before committing.
- **Never edit `.gitignore` to remove a safety entry**, even "just for testing".
- **No school-specific or instructor-specific solving logic in tracked files.**
  The tracked skills are *generic frameworks*; per-school behavior belongs in a
  local `_private/canvas-<name>-app.md` overlay that never leaves your machine.

## Dev setup

```bash
git clone https://github.com/X-isdoingreat/Canvas_pilot.git
cd Canvas_pilot
python -m venv .venv
. .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium    # one-time, ~150 MB
```

Open the folder in Claude Code and say `scan canvas` to exercise the entry
flow. On a fresh checkout this dispatches `canvas-setup` (asks for your Canvas
URL, logs you in once).

## Project shape

- `.claude/skills/canvas-*/SKILL.md` — the actual behavior. Prose instructions
  to Claude, organized as pipelines (stages), not monoliths.
- `.claude/hooks/*.py` — deterministic guardrails (schema validation, approval
  gates, leak checks). These run inside Claude Code sessions.
- `src/*.py` — API primitives and verifiers. Pure-ish Python, unit-testable.
- `scripts/*.py` — cron-able helpers (reminders, autonomous submit) for Windows
  Task Scheduler / `/schedule`.
- `tests/` — these are **Codex-sidecar runners** (`run_*.py`), not pytest
  suites. Run a relevant one directly, e.g. `python tests/codex_runtime/run_all.py`.

## Tests

Run the runner for the area you touched:

```bash
python tests/codex_runtime/run_all.py        # scan / execute / router / onboarding
python tests/codex_hooks/run_hook_tests.py   # hooks
```

## Pull requests

- Keep PRs scoped to one concern.
- Describe what changes for the *student* ("the scanner now…"), not just the
  diff.
- If you touched a hook or the public/private boundary, say so explicitly and
  confirm `check-public-leak.py` still blocks the bad cases.
- By contributing, you agree your contribution is licensed under
  AGPL-3.0-or-later, the project license.

## Questions / disclosure

- General questions: open an issue, or reach the maintainer on X
  [@X_isdoingreat](https://x.com/X_isdoingreat).
- Security or accidental-leak reports: see [SECURITY.md](./SECURITY.md). Do not
  open a public issue for those.
