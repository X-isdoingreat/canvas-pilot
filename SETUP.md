# SETUP — first run on a fresh clone

> **Codex primary path (2026-07-16):** use the concise prompt at
> <https://canvas-pilot.likelyou.com/install>. After authentication it runs
> `canvas-skill-opportunity`, writes a private local ranking, and stops for a
> numbered choice before `canvas-bootstrap` or any pending-work scan. The
> Claude-oriented manual walkthrough below is retained as legacy developer
> reference and is not the current public onboarding path.

> **⚠️ CC: do NOT read this file's instructions back to the user.**
>
> This file is a human-only reference for developers who clone the repo and want to hand-configure it. The user-facing setup flow is driven by [.claude/skills/canvas-setup/SKILL.md](./.claude/skills/canvas-setup/SKILL.md) — that skill governs what CC says and does on first run. If you (CC) catch yourself about to tell the user "open .env and edit X" or "run pip install Y" or "go find Approved Integrations in Canvas", that is a bug — stop, and do those things yourself with your Edit / Bash / Write tools. The user has Edit-capable CC running; they should not also need to be a developer.
>
> The non-CC reader (a developer poking around) can use the walkthrough below.

---

Bootstrap walkthrough for **manual setup** (developer reference). ~10 min first run (Playwright install + browser login), ~15 sec subsequent runs.

Assumptions: [Claude Code](https://claude.com/claude-code) installed, Python 3.11+. The hook scripts under `.claude/hooks/` use only stdlib + cross-platform path handling, so macOS / Linux / Windows all work.

---

## 1. Set up cookie auth

Install Playwright + a Chromium binary (one-time, ~150 MB):

```bash
pip install playwright
python -m playwright install chromium
```

```bash
cp .env.example .env
```

Edit `.env`:

```
CANVAS_AUTH=cookie
CANVAS_BASE=https://canvas.<your-school>.edu/api/v1
CANVAS_WEB_BASE=https://canvas.<your-school>.edu
```

If your school uses a generic Canvas-cloud host, `CANVAS_BASE` looks like `https://<school>.instructure.com/api/v1` instead — check the URL bar when you're in Canvas.

That's it. **No login command.** The first `scan canvas` (§5) opens a Chromium window automatically. Log in normally — username, password, 2FA. The window closes itself once Canvas accepts the session, scan continues.

Browser auth state lives in `.cookies/playwright-profile/` (gitignored). It persists, so subsequent sessions reuse it; if Canvas ever responds 401 mid-scan the same browser pops up, you log in again, scan keeps going. There is no cookie file to manage, no schema, no command to remember.

> **Strongly recommended on first run**: use "Remember this device" / "Trust this browser" / "Don't ask again" if your 2FA page offers it. The login helper now waits up to 1 minute for Duo's "Yes, this is my device" / "Trust this browser" prompt and tries to click it automatically; if the button copy changes, click it manually. Subsequent renewals then skip the 2FA push for the trust window (typically 30 days).

If something gets wedged (mysterious login loop): `rm -rf .cookies/playwright-profile/`. Next scan triggers fresh full SSO.

## 2. Let Claude Code populate your config

```bash
cp SECRETS.example.md SECRETS.md
```

That's the only manual step. **Don't look up your course IDs by hand** — Claude Code will fill in `courses.yaml` and the `Active courses` table in `SECRETS.md` for you on first scan (§5). It runs `python -m src.canvas_client --probe`, lists your courses by name, asks which to handle, and writes the entries.

If you want to do it manually anyway, the schema is documented in `SECRETS.example.md` and `courses.yaml`.

## 3. Rewrite hardcoded paths

```bash
python setup.py
```

`setup.py` rewrites the `__PROJECT_ROOT__` placeholder in `.claude/settings.json` so hook commands point at the right files for your local clone. Idempotent — safe to re-run.

> Don't commit the resulting changes — they're machine-local. `git diff` after `setup.py` shows exactly what got rewritten.

## 4. Install Python deps

```bash
pip install requests
```

That's the only hard dependency for the framework. Add others as your own skills need them (e.g. `pyyaml` for richer YAML manipulation, `pymupdf` if a skill parses PDFs). You already installed `playwright` in §1.

## 5. Test

In Claude Code (`claude` from the repo root):

```
scan canvas
```

If `courses.yaml` is still empty (first run), CC asks which courses to handle and writes the config for you — you don't type IDs. Then `canvas-scan` produces `runs/<today>/plan.json` plus a markdown table of pending work. **It stops there — nothing is dispatched until you approve.** Reply with (`all` / `1, 3, 5` / `urgent only` / `skip`) to trigger `canvas-execute`.

If `scan canvas` doesn't trigger the skill, type `/canvas-scan` explicitly. If hooks aren't firing (no SessionStart context message at the top), re-check that `python setup.py` actually rewrote `.claude/settings.json`.

---

## Troubleshooting

**`setup.py` says "no placeholder" everywhere.** Either you already ran it, or your clone was rewritten by someone else on a different machine and they pushed the change. Check `git diff .claude/settings.json` — if the path inside isn't `__PROJECT_ROOT__` and isn't yours either, fix manually.

**Hooks don't fire.** Open `.claude/settings.json`, confirm every `command` field has your absolute path, and that the `.claude/hooks/*.py` files exist. Try `python .claude/hooks/inject-context.py` manually — if it crashes, fix the import / path issue before re-running CC.

**`CanvasSessionExpired`.** The browser login window timed out (5 min) without completing. Re-run scan and finish login this time; or `rm -rf .cookies/playwright-profile/` if the persistent profile is somehow stuck.

**`HTTPError` 401 on probe.** Shouldn't happen — the backend re-launches headed login on 401 and retries once. If it still fails, the persistent profile is wedged; remove it.

**Different OS.** The hook commands in `.claude/settings.json` use `python` (not `python3`). On macOS/Linux you may need to symlink `python` → `python3` or hand-edit settings.json. The scripts themselves are platform-independent.
