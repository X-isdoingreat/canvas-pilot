---
name: canvas-setup
description: Use this skill on a fresh Canvas Pilot install when the student has never configured the project before. Trigger phrases include "set me up", "set up canvas pilot", "install canvas pilot", "/canvas-setup", "first time", "i'm new". Also auto-invoked by `canvas-scan` §0 when `.env` is missing or `CANVAS_BASE` is empty, and by the SessionStart hook when it detects an unconfigured repo. Walks the student through a deterministic N-step first-run flow — Canvas URL → silent install → silent config → browser login → course selection — then dispatches `canvas-bootstrap` to design per-course skills. The student answers ~2 domain questions and logs into Canvas once; everything else is silent CC action.
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
  - Skill
  - WebSearch
  - WebFetch
---

# canvas-setup (first-run configurator)

This skill **replaces** the old "Helping the student configure" prose section in `CLAUDE.md`. The prose was a set of negative rules ("never say pip install") that CC had to apply on top of free-form judgment. This skill is the positive version: a fixed N-step script. Every step specifies (a) what CC does silently, (b) what CC says to the student, (c) what CC waits for. CC walks the script; CC does not improvise.

## Why this skill exists (read this before editing)

The friend test (2026-05-02) found 12 setup-related UX bugs, all rooted in the same behavior: CC was reading framework docs (`SETUP.md`, `.env.example` comments, error tables) and parroting them at the student as a tutorial. Friend was told to `pip install` herself, edit `.env` herself, navigate Canvas back-office herself — even though CC has Bash/Edit/Write tools to do all of it. See `.claude/plans/public-setup-ux-bugs.md` for the full incident list.

The fix is **not** more prose rules in CLAUDE.md. The fix is making first-run a fixed sequence the SKILL.md mechanism enforces: CC dispatches this skill, walks the steps, returns. The student's only legitimate actions are answering domain questions (Canvas URL, which courses) and logging into Canvas once in a popup browser. Every other "step" the friend ever did manually (cp .env.example .env, pip install, edit env vars, run setup.py) is now CC's silent work.

## Hard rules CC follows the entire way through this skill

**The student's only legitimate actions during this skill**:
1. Answering questions CC asks about their own situation (Canvas URL, which courses).
2. Logging into Canvas once in a browser window CC pops up.

**Anything else is CC's job.** If CC catches itself about to write a sentence telling the student to "open .env", "run pip install", "go to Canvas → Account → Settings → Approved Integrations", "copy this command into your terminal", "edit courses.yaml" — that is the bug this skill exists to prevent. Stop, do it with `Bash`/`Edit`/`Write`, and tell the student "我刚做了 X" / "I just did X" instead.

**Internal vocabulary the student never sees**: `pip`, `playwright`, `chromium`, `cookie`, `token`, `probe`, `SSO`, `Duo`, `.env`, `courses.yaml`, `SECRETS.md`, `__PROJECT_ROOT__`, `${CLAUDE_PROJECT_DIR}`, `runs/...`, `.cookies/...`, any Canvas API field name, any course/user/file `_id`. These are fine in CC's internal reasoning; they are forbidden in user-facing output.

**One question per turn**: each user-facing message ends with at most one question. Multi-question turns are a bug.

**Slow operations get one ETA + parsed progress**: any Bash command that may take >30s runs with `run_in_background=true`, gets one upfront time estimate covering the whole bundle (e.g. "等我装下浏览器组件，3-10 分钟看你网速"), and gets monitored with progress reported as numbers ("下载到 30 MB / 165 MB, ~1 Mbps, 还要 5 分钟"). Never repeat-emit "继续等" with no new information.

**Multi-command operations bundle into one Bash call**: `pip install playwright && python -m playwright install chromium` runs as ONE command, not two separate "等一下" turns. Use `&&` so failures stop the chain.

---

## What you do

### Step 1 — Open with value, ask consent

CC's silent action: none yet.

CC says (literal pin, pick the language matching the student's first message):

> 这是 Canvas 作业自动化工具。我会扫你这学期的 Canvas，列出待交作业，每周帮你处理重复性的（阅读注释、刷题、quiz 之类），交付前给你审批。要开始吗？

> This is Canvas Pilot. I scan your Canvas, list what's pending, and each week help you draft the recurring stuff (reading annotations, quizzes, problem sets) — you review before anything gets submitted. Want to start?

CC waits for: any affirmative (yes/好/行/ok/嗯/start/开始). If the student says no or asks something else, answer their question and wait — do not advance to step 2.

### Step 2 — Get the Canvas URL

CC asks for the school, not the URL — CC will find the URL itself.

CC says:

> 你哪个学校？学校名或域名都行（比如学校的简称或 `<your-school>.edu`）。

> Which school do you go to? Name or domain works (e.g. your school's short name or `<your-school>.edu`).

CC waits for: a school identifier (name / domain / anything searchable). If the student volunteered school context in an earlier message (email domain like `name@<school>.edu`, or SSO URL like `shib.service.<school>.edu/idp/...`), CC may skip the question — extract the school silently from the prior message (base domain `<school>.edu` from email or SSO host).

CC's silent action: discover + verify the Canvas URL.

1. **WebSearch** `<school> canvas login`. From the result list, pick the first URL whose host matches Canvas-shaped patterns:
   - `canvas.<anything>.edu`
   - `<anything>.instructure.com`
   - `gocanvas.<anything>` (Stanford-style)
   - `<anything>.canvas.<anything>`

   If **none** of the WebSearch results match these patterns → skip to step 4 (fallback).

2. **WebFetch** `<candidate>` (the host root — Canvas root returns the login page or a `/login` redirect for unauthenticated users, and either way emits Canvas signature strings). The Canvas signature is any of:
   - HTML contains `Canvas by Instructure`
   - HTML contains `canvas-login` or `/login/canvas` form action
   - HTML contains `instructure` (case-insensitive)

3. If WebFetch succeeded AND signature matched → silently normalize and use:
   ```python
   import re
   host_only = re.match(r"(https?://[^/]+)", candidate).group(1).rstrip("/")
   CANVAS_WEB_BASE = host_only
   CANVAS_BASE = host_only + "/api/v1"
   ```
   Advance to Step 3. Do NOT confirm with the student — they'll see the domain in Step 6 when the browser pops up.

4. **Fallback** — triggered when WebSearch returned no Canvas-shaped candidate, OR WebFetch failed (timeout / non-200 / permission deny), OR signature didn't match.

   CC says:

   > 查不到你们学校的 Canvas 地址 — 直接给我 Canvas 登录页的网址就行（比如 `canvas.<your-school>.edu`）。

   > Couldn't find your school's Canvas — give me the Canvas login page URL directly (e.g. `canvas.<your-school>.edu`).

   When the student replies:

   **4a. If the manual input looks like an SSO URL** (host starts with `shib.` / `idp.` / `sso.` / `login.` subdomain prefix): extract the base domain (e.g. `shib.service.<school>.edu` → `<school>.edu`), re-run step 1 + step 2 once with the extracted school. If that round succeeds, use it silently and advance to Step 3. If it still fails, fall through to step 4b.

   **4b. Otherwise normalize the manual URL** as before:
   ```python
   raw = student_input.strip()
   if not raw.startswith("http"):
       raw = "https://" + raw
   host_only = re.match(r"(https?://[^/]+)", raw).group(1).rstrip("/")
   CANVAS_WEB_BASE = host_only
   CANVAS_BASE = host_only + "/api/v1"
   ```

   If the manual input doesn't match `https?://[a-z0-9.-]+` after normalization, ask once more without explaining regex: "我没认出来这是个 Canvas 网址 — 直接给我学校 Canvas 登录页那个地址就行。"

### Step 3 — Tell the student a browser will pop up

CC's silent action: none yet.

CC says (literal pin):

> 配 Canvas 连接需要一次浏览器登录——我等会儿弹一个浏览器，你像平时一样登 Canvas 就行。session 偶尔过期了浏览器会再弹一下让你重登几秒，你不需要手动找或粘任何东西。

> Setting up the Canvas connection needs a one-time browser login — I'll pop a browser, you log in like normal. If the session ever expires the browser pops up again for ~10 seconds. You don't need to find or copy anything manually.

CC waits for: any affirmative or silence (default: continue). If the student asks why / wants alternatives / is worried, answer their question briefly and continue once they're ready. Do not surface alternative auth paths — there is only one supported path.

### Step 4 — Install browser components

First check whether playwright + chromium are already installed (single Python check, not a user-visible question):

```python
import subprocess, sys
result = subprocess.run(
    [sys.executable, "-c", "import playwright; from playwright.sync_api import sync_playwright; p=sync_playwright().start(); p.chromium.launch(headless=True).close(); p.stop()"],
    capture_output=True, text=True, timeout=30
)
already_installed = result.returncode == 0
```

If `already_installed` → skip to Step 5 silently, say nothing.

If not installed → CC says (literal pin):

> 等我装下浏览器组件——3-10 分钟看你网速，第一次比较慢。我会同步进度。

> Installing the browser components — 3-10 minutes depending on your connection. I'll keep you posted.

CC then runs ONE bundled Bash command in background:

```bash
pip install playwright && python -m playwright install chromium 2>&1 | tee /tmp/canvas_setup_install.log
```

(Use `run_in_background=true`. On Windows replace `/tmp` with a project-relative tmp dir.)

CC monitors the log file every 30-60 seconds. Each time CC reports, it must extract **numbers** from the log:
- `playwright install chromium` prints `Downloading Chrome ... [progress bar] X% of YMb` — parse to "下载到 X MB / Y MB"
- divide bytes-downloaded by elapsed time → throughput in Mbps
- (Y - X) / throughput → ETA in minutes

CC says (literal pin format):

> 下载到 30 MB / 165 MB，~1 Mbps，还要 5 分钟。网慢的话再等等就行。

> 30 MB / 165 MB downloaded, ~1 Mbps, ~5 min left. Hang tight if your connection is slow.

**Suppression rule**: if CC's last status update was <2 minutes ago AND the new numbers haven't moved meaningfully (same X MB), CC stays silent. Repeat-emitting "继续等" / "still downloading" with no new info is a bug.

If install fails (non-zero exit, network error, disk full): CC reads the tail of the log, surfaces the actual error in plain language ("下载断了，看起来是网络问题——要不要再试一次？"), and waits for the student's call.

### Step 5 — Write `.env` silently

CC's silent action: write `.env` file. **Never** ask the student to do this.

```python
env_content = (
    "CANVAS_AUTH=cookie\n"
    f"CANVAS_BASE={CANVAS_BASE}\n"
    f"CANVAS_WEB_BASE={CANVAS_WEB_BASE}\n"
)
```

Use `Write` tool. Do not announce ".env written" or any filename to the student.

If a `.env` already exists (e.g. student is re-running setup): read it first; **preserve** any non-Canvas keys the student may have added; only overwrite `CANVAS_AUTH=cookie` + `CANVAS_BASE` + `CANVAS_WEB_BASE`.

**Escape hatch preservation**: if the existing `.env` has `CANVAS_AUTH=token` (the student manually configured the undocumented token escape hatch — knows what they're doing), preserve it as-is. Do not change `CANVAS_AUTH`, do not touch `CANVAS_TOKEN`, do not ask the student about it, do not surface that token mode exists. Only update `CANVAS_BASE` / `CANVAS_WEB_BASE` if they're missing or empty. This is intentional: the escape hatch is for users who already configured it deliberately; canvas-setup's job is to configure cookie mode without disturbing existing manual config.

### Step 6 — Trigger login

CC silently runs a probe that triggers the headed browser:

```bash
python -m src.canvas_client --probe
```

The probe will pop a Chromium login window (handled inside `canvas_client.py:_login_interactive`).

CC says (literal pin, **immediately before** running the probe so the student knows what's about to happen):

> 浏览器要弹出来。你照常登 Canvas，登完它自己关。

> Browser is about to pop up. Log in to Canvas like normal, it'll close itself when it's done.

CC waits for: probe to return successfully (Canvas accepted the session, cookies persisted to `.cookies/session.json`).

If probe fails because the student didn't complete login within 5 minutes: CC says "我没看到你登好——是浏览器没起来，还是中间卡住了？" and waits.

If probe fails because `playwright` import broke (rare; install was supposed to handle this): CC silently reruns the install bundle once more, then retries the probe. Don't surface the install failure to the student unless it fails twice.

### Step 7 — Write empty `courses.yaml` silently

**Note**: setup deliberately does NOT list courses or ask the student "which courses?" — that work belongs to `canvas-bootstrap`, which has a more thorough 4-layer noise filter (Layer 1 active + Layer 2 nonempty + Layer 3 recurring-pattern fold + Layer 4 looks-like-real-course rescue) plus the fingerprint table that shows assignment-pattern signals per course. Setup's job ends at "Canvas authentication works"; selection + design is bootstrap's job.

CC's silent action: use `Write` to create `courses.yaml`:

```yaml
# Generated by canvas-setup. canvas-bootstrap (next) will fill routes.
pending_window_days: 7
routes: {}
```

`routes: {}` is an empty mapping — bootstrap §1 explicitly handles this (line 38: "or every active course Canvas returns when routes is empty") by listing all active courses with the full filter pipeline.

If `courses.yaml` already exists with non-empty `routes` (re-running setup on a partially-configured project), preserve existing entries and skip this write.

If `SECRETS.md` exists, CC updates the "Active courses" table inside it (read first, replace just that section). If `SECRETS.md` doesn't exist, CC creates it from `SECRETS.example.md` (if that template exists; otherwise creates minimal).

CC says nothing about writing these files.

### Step 8 — Hand off to canvas-bootstrap

CC says (literal pin):

> 配好了 Canvas 连接。下面看你这学期有哪几门课，给每门课设计 skill——决定怎么自动化。从最简单的开始。

> Canvas connection is set up. Now let's look at your courses this term and design a skill for each — how each course should be automated. Starting with the simplest one.

CC then invokes `canvas-bootstrap` via the `Skill` tool, passing this context:

> "canvas-setup just finished — Canvas auth works, courses.yaml has empty routes ({}). This is first-run mode: list all active courses with the 3-section fingerprint render (main / likely-real / noise), let the student pick which to track AND name skills in one combined picker, write SKILL.md skeletons + populate routes."

`canvas-bootstrap` takes over from here. canvas-setup exits.

### Step 9 — End condition

When `canvas-bootstrap` returns, CC says (literal pin, three affordances):

> 配好了。
> - 想看这周要交什么 → "scan canvas"
> - 还想加更多课 / 改某门课的设计 → "设计 skill"
> - 你刚设计的 skill 在 `.claude/skills/` 下面（每门课一个文件夹），里面就是你给自己写的执行步骤，以后想改直接编辑

> All set.
> - Want to see what's due this week → "scan canvas"
> - Want to add more courses / redesign a skill later → "design a skill"
> - The skills you just designed are under `.claude/skills/` (one folder per course) — those are the playbooks you wrote for yourself; edit anytime

The three affordances cover three real first-run needs:
- (a) Get immediate value (scan now)
- (b) Half-finished bootstrap or new courses later — explicit re-entry trigger
- (c) Knowledge that SKILL.md files are the student's own product, editable

Note: this is the one place where `.claude/skills/` is named to the student. After bootstrap completes, those files are the student's playbook artifacts (not framework internal config), so the path is meaningful and editable, not jargon. This intentional break of the "internal vocabulary the student never sees" rule is per plan 2026-05-03 design.

This skill exits.

---

## Error / interruption recovery

**Student ctrl+C mid-setup, comes back later**: CC detects partial state on next session entry:
- `.env` doesn't exist → started with fresh first-run, restart at Step 1
- `.env` exists but `CANVAS_BASE` empty → restart at Step 2
- `.env` complete but no `.cookies/session.json` and `CANVAS_AUTH=cookie` → restart at Step 6 (re-trigger login)
- `.env` has `CANVAS_AUTH=token` (escape hatch — student configured manually): treat as fully authenticated; verify with a silent `python -m src.canvas_client --probe` and proceed to Step 7
- `.env` complete + auth works but `courses.yaml` missing or has `routes: {}` → restart at Step 7 (write empty routes if needed) → continue Step 8 (re-dispatch bootstrap)

CC does not ask the student "where did we leave off". CC reads the filesystem state and resumes silently from the right step.

**Student wants to redo setup from scratch**: explicit trigger phrases like "redo setup" / "重新配", or `/canvas-setup` invoked manually. CC says "你想全部重来还是只改某一步（学校换了 / 课程列表）？" and routes accordingly. **Never** silently overwrite working config.

**Student wants to uninstall**: out of scope for v1. If asked, CC explains what files are involved (`.env`, `.cookies/`, the playwright binaries) and lets the student decide what to delete.

---

## What this skill MUST NOT do

- Tell the student to run any shell command. CC has Bash; CC runs it.
- Tell the student to edit any file. CC has Edit/Write; CC writes it.
- Show the student a file path, command, environment variable name, or API field name.
- Surface alternative auth modes to the student. Cookie auth is the only supported path; the token escape hatch in `canvas_client.py` is undocumented and must not be advertised.
- Ask the student a question whose answer CC could discover by running a check.
- Pre-announce a multi-step workflow ("first I'll do X, then Y, then Z..."). Steps happen silently when their time comes.
- Mix two questions into one turn. Single domain question per message.
- Repeat status messages with no new content.
- Skip the value-statement opening (Step 1) and jump to "what's your Canvas URL". The opening is mandatory.
