---
name: canvas-scan
description: This skill should be used when scanning Canvas for pending assignments and producing an approval-gated plan. Invoked manually when the user says "check canvas", "scan canvas", "what's due", "do my homework", "/canvas-scan". Reads courses.yaml, queries Canvas for assignments due in the configured pending window, buckets them by urgency, renders a plan table, writes `runs/<today>/plan.json`, and STOPS. Does NOT dispatch sub-skills — that is `canvas-execute`'s job.
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - WebFetch
  - TodoWrite
---

# canvas-scan (scan + plan)

Scanner + planner for the Canvas auto-homework system. This skill produces a **plan for user review** and then stops. Dispatch is a separate skill, `canvas-execute`, that the user invokes *after* reviewing the plan.

> **Name history**: this skill used to be called `canvas-router` (up to 2026-04-21 evening), which was misleading since it no longer routes anything — it scans and plans. Renamed to `canvas-scan` for honesty. The user-facing trigger is `/canvas-scan`; old muscle memory `/canvas-router` is no longer registered.

## Why the scan/execute split exists (must understand before editing this skill)

The highest spec is [`canvas_scan.md`](../../../canvas_scan.md) at repo root. Read it.

The 2026-04-21 runaway happened because the old monolithic `canvas-router` (this skill's predecessor) had a single SKILL.md that said "scan then dispatch". The "stop and wait for approval" step was only a *behavioral* instruction inside that SKILL.md — one more line of prose among many. Under session pressure, Claude skipped it and started dispatching 8 items, one of which used all the remaining context budget.

**Splitting into two skills makes the approval gate an architectural boundary, not a prose instruction:**

- `canvas-scan` (this file): scan → bucket → render plan → write `plan.json` → **END**.
- `canvas-execute`: reads `plan.json` → parse user's approval → dispatch approved → write REPORT.md.

Because the two skills are invoked in two separate Skill tool calls, there is a hard boundary between "agent proposes" and "agent acts". The user must explicitly say "go" (or "approve all", "做 1, 3, 5", etc.) before any sub-skill runs. The file on disk is the contract.

**This skill MUST NOT:**
- Invoke any sub-skill (`canvas-ics33`, `canvas-reading-annotation`, `canvas-inside`, `canvas-zybooks`, `canvas-skip`).
- Write any `result.json`.
- Write `REPORT.md`.
- Sync the `final_drafts/` folder.
- Create the `.scan_in_progress` marker (that's for execute).

All of those belong in `canvas-execute`.

## Hook guardrails (what still applies during scan)

7 hooks are registered in `.claude/settings.json`. During scan, most are inert:

| # | Hook | Fires during scan? |
|---|---|---|
| 1 | SessionStart `inject-context.py` | yes — injects pending list at turn 0 |
| 2 | PostToolUse(Write/Edit on result.json) `check-result-schema.py` | **never** (scan writes no result.json) |
| 3 | PostToolUse(Bash) `check-bash-output.py` | yes — validates `python -m src.canvas_client --probe` / `python -m src.router --dry-run` output |
| 4 | PreToolUse(Bash) `check-presubmit-audit.py` | never (scan doesn't submit) |
| 5 | PostToolUse(Write/Edit on result.json) `check-spec-grounding.py` | never |
| 6 | PostToolUse(Write/Edit on result.json) `check-identifier-grounding.py` | never |
| 7 | Stop hook `check-router-complete.py` | **gated by `.scan_in_progress` marker — scan does NOT create it, so Stop passes freely** |

That means a scan session can stop cleanly as soon as `plan.json` is written. If the user ctrl+Cs mid-scan, no marker was set, so the next session is also not gated. `plan.json` is idempotent (re-run overwrites), so partial scans are safe.

## Working directory assumption

This skill assumes the working directory is the project root (the folder you cloned this repo into; Claude Code sets cwd automatically on session start). The Python helpers under `src/` and the config files (`.env`, `courses.yaml`) all live there.

## What you do

### 0. First-run check — unconfigured repo dispatches canvas-setup or canvas-bootstrap

Before doing anything else, check the repo's setup state. Two distinct unconfigured states:

```python
import os, yaml
from pathlib import Path

env_ok = False
env_path = Path(".env")
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() == "CANVAS_BASE" and v.strip():
            env_ok = True
            break

cfg = yaml.safe_load(Path("courses.yaml").read_text(encoding="utf-8")) if Path("courses.yaml").exists() else {}
routes = (cfg or {}).get("routes") or {}
routes_nonempty = bool(routes)
```

**If `env_ok` is False** → fresh install, never configured. Dispatch `canvas-setup` via the Skill tool with this context:

> ".env is missing or CANVAS_BASE is empty — fresh install, student has never configured the project. Run the full first-run flow."

Do NOT proceed to §1. Do NOT print a traceback if `.env` doesn't exist. canvas-setup will return when the student is fully configured (or stops mid-flow). On its return, scan exits — student can re-trigger `scan canvas` whenever they want.

**Else if `env_ok` but `routes_nonempty` is False** → Canvas connection is configured but no per-course skills. Dispatch `canvas-bootstrap`:

> "courses.yaml.routes is empty — Canvas connection works but student needs to design per-course skills. Run the fingerprint flow."

When bootstrap returns, **stop this scan**. Tell the student:

> "Routes installed. Open each new SKILL.md and fill the TODOs. Then run `scan canvas` again to produce a plan."

**Else** (`env_ok` and `routes_nonempty`): proceed to §1 normally.

### 1. Sanity check

```bash
python -m src.canvas_client --probe
```

If this fails, STOP. Don't print the traceback. Map the failure to one of the cases below and respond in the user's language with no internal jargon, no file paths, no commands shown — same voice as `canvas-setup` SKILL.md (the student should never see `.env`, `pip`, `python -m src.*`, `cookie`, `token`, etc.).

| Symptom (from traceback / output) | CC's silent action | What CC says to the user |
|---|---|---|
| `401 Unauthorized` / `Invalid access token` (token mode) | None — needs user input. | "你的 Canvas 认证不工作了。你想我重新弹浏览器让你登一次（最简单），还是你贴一个新的 Canvas API token？" / "Your Canvas auth isn't working. Want me to re-pop the browser so you log in again (simplest), or you paste a fresh API token?" |
| `CanvasSessionExpired` (cookie mode) | The Playwright backend should already auto-relogin on 401 — if you're seeing it surface here, that auto-relogin failed. Try once more, then escalate. | "Canvas 让我重新登录。我开浏览器弹一下你登一下。" / "Canvas wants me to log in again. Popping the browser — log in like normal." Then trigger the relogin and retry the scan. |
| `FileNotFoundError: .env` / `CANVAS_TOKEN not set` | Not configured yet. **Dispatch `canvas-setup` via the Skill tool** — that skill owns the first-run flow. | (Don't say anything yourself; let canvas-setup's Step 1 opener handle it.) |
| `ConnectionError` / `Timeout` / DNS failure | Network. Don't retry silently more than once. | "连不上 Canvas。检查一下网络/VPN，好了告诉我重试。" / "Can't reach Canvas. Check your network and tell me when you want me to try again." |
| Anything else | Genuinely unexpected. Don't guess a fix. | "出了个我没见过的错。给你看一下原始信息：\n\n{traceback excerpt}\n\n你看着像什么？" / "Hit an error I don't recognize. Here's the raw output:\n\n{traceback excerpt}\n\nDoes this look like anything to you?" |

Do NOT write `plan.json` in any of these cases — there's nothing real to plan; a half-written plan would mislead. **STOP** after responding.

**Forbidden in the user-facing column** (these will leak forbidden vocab — if you find yourself drafting them, the response is wrong): `CANVAS_TOKEN`, `.env`, `python -m src.*`, `Approved Integrations`, `New Access Token`, `Settings → ...`, `Chromium`, `Playwright`, `Duo`, `Cookies`, file paths starting with `.cookies/` or `runs/` or `.claude/`. CC silently knows what those things are; the user doesn't need to.

### 2. Scan for pending

```bash
python -m src.router --dry-run
```

This writes `runs/<today>/assignments.json` with the pending list. Read it. Each item has `course_id`, `course_name`, `skill`, `assignment_id`, `name`, `due_at`, `submission_types`, `points_possible`.

If the list is empty, tell the user "no pending assignments in window", skip steps 3-6, and exit. No `plan.json` needed.

### 3. Filter what's already done

There are two layers of dedup. Use both.

**Layer A — per-day work dirs.** For each item, check whether `runs/<today>/<work_dir>/result.json` exists with `status` in `("draft_ready","submitted","skipped")`. If yes, skip — it was processed in an earlier run today. The work_dir naming convention is `<course_slug>__<assignment_slug>` (see `src/skills/base.py:slugify`).

**Layer B — cross-day ledger.** Read `runs/_processed.json` (a flat dict keyed by `<course_id>:<assignment_id>` → `{status, completed_at, draft_path, ...}`). If the assignment is in there with a terminal status AND its `completed_at` is more recent than its `due_at - 24h`, skip. This prevents re-doing assignments that were finished yesterday but are still in the 7-day window.

**Exception — deferred items re-enter the plan.** If a ledger entry has `deferred_to_next_run: true`, treat it as **NOT processed** and re-include in the plan (see §5). This is how the user's "defer 第 N 项" / "cancel" choices at plan-review stage get another chance on the next `/canvas-scan` run. Without this exception, one "defer" would permanently hide the item.

### 4. Bucket by due_at

For each remaining item, compute `hours_left = (due_at_utc - now_utc).total_seconds() / 3600`.

Assign a bucket (first match wins):

| Bucket | Rule |
|---|---|
| ⏰ OVERDUE | `hours_left <= 0` AND live Canvas `workflow_state` not in `{submitted, graded}` |
| 🔥 URGENT  | `0 < hours_left <= 72` |
| ⚠️  SOON   | `72 < hours_left <= 168` (7 days) |
| 🟢 LATER  | `hours_left > 168` |

Check live Canvas state (via `get_submission(course_id, assignment_id)` from `src.canvas_client` — returns the `/submissions/self` payload) for **every** item that survived the dedup filter. Two purposes:

1. **OVERDUE confirmation** — only treat an item as OVERDUE if `workflow_state` is not in `{submitted, graded}`. This is the existing role.
2. **Submitted column for the user-facing table** — surface live state in §5b's `已交` / `Submitted` column so ledger drift never silently misroutes a finished item into the plan. Even when the column is uniformly `未交` / `no` (the common case), the existence of the check is a health signal.

Store the raw `workflow_state` on each plan item as `live_state` (one of `unsubmitted`, `submitted`, `graded`, `pending_review`, `unknown`). If the API call fails for one item, set `live_state: "unknown"` and continue with the rest — don't abort the whole scan.

(Earlier versions of this skill also emitted an `estimated_turns` field per item for a "session budget" calculation in `canvas-execute`. That was removed — per-item turn estimates were guesses, and the budget check produced the annoying "batched then blocked" experience. `canvas-execute` now handles session capacity via the simpler §5 mid-run pause-and-ask. Don't re-add `estimated_turns`.)

### 5. Write plan.json + render plan table

#### 5a. plan.json

Write `runs/<today>/plan.json`:

```json
{
  "generated_at": "<ISO now, local PT>",
  "expires_at":   "<ISO now + 24h>",
  "items": [
    {
      "index": 1,
      "bucket": "urgent",
      "course_id": 70600,
      "course_name": "Code Course Spring 2026",
      "course_friendly_name": "Dr. Example's CS 101",
      "assignment_id": 1234567,
      "assignment_name": "Set 3 Problem 1",
      "due_at": "2026-04-25T23:59:00Z",
      "hours_left": 53.2,
      "live_state": "unsubmitted",
      "proposed_skill": "canvas-ics33",
      "user_decision": null
    }
  ]
}
```

**`course_friendly_name`**: read from the overlay (`_private/canvas-<framework>-app.md` → `## Course {course_id}` block → `course_friendly_name` field) at scan time. Null if the overlay lacks this field (older overlays / fork user never set it). Display in the plan table prefers this over `course_name` when present.

- Sort items by bucket priority (`overdue` → `urgent` → `soon` → `later`), then within each bucket by `hours_left` ascending.
- `index` is 1-based and stable for this plan.json (users will refer to items by index: "做 1, 3, 5").
- `user_decision` starts as `null`. `canvas-execute` fills it in (`approve` / `defer` / `swap:<skill>`) during the approval parse step.
- Use atomic write (write to `.tmp`, then `os.replace`) to avoid leaving a half-written plan if Python crashes.

**Note: the plan.json schema above is illustrative, not exhaustive.** In-memory items built from `cv.list_assignments()` carry the raw assignment fields including `submission_types` and `quiz_id`, which the §5a LDB filter below depends on. When constructing items don't strip these fields before the filter runs. If a future refactor changes plan.json structure, keep `submission_types` and `quiz_id` accessible at the LDB filter call site — otherwise the filter silently no-ops (its `submission_types == ["online_quiz"]` condition would always be False, and LDB quizzes would silently route to canvas-inside then break at the browser layer).

**Before writing plan.json, apply the quiz LDB filter.** For each item where `submission_types == ["online_quiz"]` and `proposed_skill == "quiz"`, fetch the full quiz object and inspect three boolean fields. If any is true, override the routing to `canvas-skip` (keep the due-based bucket so the item still appears in the main table — §5b' "Can't do" annotation block picks it up via `proposed_skill == "canvas-skip"`):

```python
for item in items:
    if item["submission_types"] == ["online_quiz"] and item["proposed_skill"] == "quiz":
        q = cv.get_quiz(item["course_id"], item["quiz_id"])
        if q.get("require_lockdown_browser") or \
           q.get("require_lockdown_browser_for_results") or \
           q.get("require_lockdown_browser_monitor"):
            item["proposed_skill"] = "canvas-skip"
            item["skip_reason"] = "🔴 Lockdown Browser — agent 物理无法 take"
            # bucket stays as-is (urgent/soon/later/overdue) so the item still
            # shows up in the due-based table; §5b' Can't-do block annotates it.
```

Lockdown Browser quizzes are intrinsic can't-do (see CLAUDE.md "Agent stops at can't-do, not shouldn't-do" — physically impossible category). Without this filter the framework would silently route an LDB quiz to canvas-inside and break at the browser layer with no graceful refusal. The check is inline — three fields, one call site, no `is_lockdown_quiz()` helper needed.

#### 5b. Plan table to user

This block is the **main student-facing surface of the whole project**. Students are the users; don't leak internals (plan.json path, `canvas-execute` scheduling, skill names, expiry hints, proposed_skill column, bucket emojis). They need three things:

1. What's pending (course + name + due)
2. What's urgent (≤3 days) vs not (3–7 days)
3. One sentence on how to pick

Render two fixed sections — both always appear, even when empty:

- **Section 1 — 三天内 due / Due within 3 days**: items with `hours_left <= 72`. OVERDUE items (`hours_left <= 0`, live state not `submitted`/`graded`) go at the top of this section with `已过期 Xh` / `overdue Xh` in the due column.
- **Section 2 — 七天内 due / Due within 7 days**: items with `72 < hours_left <= 168`.

If a section has no items, render its heading with `— 无` / `— none` inline (see templates). Do NOT omit.

Columns (5, no truncation): `#`, 课/Course, 作业/Assignment, due/Due, 已交/Submitted.

- `#` — `index` from plan.json.
- 课/Course — short label the student recognizes. **Prefer `course_friendly_name` if the overlay has set it** (renders verbatim, that's the whole point — student picked the name). Else fall back to short-form of `course_name`: drop quarter suffix (e.g. `Spring 2026`, `S26`); collapse long course names to leading department+number tokens (`<Long Course Name> Spring 2026` → `<DEPT> <NUM>`); for a new course, pick the leading department+number tokens.
- 作业/Assignment — `assignment_name` verbatim.
- due/Due — PT day-of-week + 24h time: `周一 23:59` / `Mon 23:59`. Overdue: `已过期 Xh` / `overdue Xh` where X = `abs(hours_left)` rounded.
- 已交/Submitted — derived from `live_state` set in §4. Render `已交` / `done` if `live_state` ∈ `{submitted, graded, pending_review}`, `未交` / `no` if `unsubmitted`, `?` if `unknown` (API failed). The column is almost always `未交` / `no` because already-submitted items get filtered upstream — its purpose is **defense-in-depth**: it makes ledger drift visible at a glance and reassures the student the plan reflects live Canvas state, not a stale local file.

**Language selection**: sniff the most recent user message that triggered this scan. If it contains any Han character, use the Chinese template; otherwise English. No config flag.

**Chinese template**:

```markdown
**三天内 due** — 无

**七天内 due**

| # | 课 | 作业 | due | 已交 |
|---|---|---|---|---|
| 1 | Quiz Course | Quiz on Section 5 | 周日 23:59 | 未交 |
| ... |

要做哪几项？全做回"全部"，挑几项回编号（例 "3,4"），不做回"跳过"。
```

**English template**:

```markdown
**Due within 3 days** — none

**Due within 7 days**

| # | Course | Assignment | Due | Submitted |
|---|---|---|---|---|
| 1 | Quiz Course | Quiz on Section 5 | Sun 23:59 | no |
| ... |

Which ones? Reply `all` to do everything, numbers to pick (e.g. `3,4`), or `skip` to pass.
```

When a section has rows, drop its `— 无` / `— none` marker and render the heading + table. When empty, render only the heading with the inline marker (no empty table).

#### 5b'. Recommendation block (mandatory after the tables)

The two-table render answers "what's pending" + "what's urgent". It does NOT answer "what should I do first?". Without that answer, students stare at a 5-column table not knowing how to start. Add a Recommendation block immediately after Section 2.

The block has three parts, in order:

1. **"我做不了 / Can't do"**: a small bulleted subsection listing items the framework will skip (routes to `canvas-skip`). Skip the subsection entirely if the list is empty.
2. **"建议 / Suggested"**: one sentence picking ONE item as the recommended starting point — usually the most urgent item that the framework CAN do. Frame as "try this one first, see how it goes". Reasoning is optional but helpful when the choice is non-obvious.
3. **Reply hint**: keep the existing one-line `all / 编号 / skip` prompt — it stays at the end.

**Chinese template (extended)**:

```markdown
**三天内 due** — 无

**七天内 due**

| # | 课 | 作业 | due | 已交 |
|---|---|---|---|---|
| 1 | PHYS 7A | Lab Report 5 | 周日 23:59 | 未交 |
| 2 | Writing | Tue Wk5 HW Scan | 周二 23:59 | 未交 |
| 3 | Python | Set 5 Problem 2 | 周一 08:00 | 未交 |

**我做不了**
- 1. PHYS 7A Lab Report 5 — 路由表里没有这门课的 skill，手动交

建议：先批 3（最紧急），看看效果。觉得 OK 再批 2。

要做哪几项？全做回"全部"，挑几项回编号（例 "3,4"），不做回"跳过"。
```

**English template (extended)**:

```markdown
**Due within 3 days** — none

**Due within 7 days**

| # | Course | Assignment | Due | Submitted |
|---|---|---|---|---|
| 1 | PHYS 7A | Lab Report 5 | Sun 23:59 | no |
| 2 | Writing | Tue Wk5 HW Scan | Tue 23:59 | no |
| 3 | Python | Set 5 Problem 2 | Mon 08:00 | no |

**Can't do**
- 1. PHYS 7A Lab Report 5 — no skill mapped for this course, submit manually

Suggested: try 3 first (most urgent), then come back for 2 once you see how that goes.

Which ones? Reply `all` to do everything, numbers to pick (e.g. `3,4`), or `skip` to pass.
```

Drop the `**Can't do**` subsection if it would be empty. Drop the recommendation sentence if there are zero items the framework can do (rare). The reply hint always stays.

**Do NOT add any of the following to the user-facing render** (they're internal — keep them out even if you feel the urge to be thorough):

- `plan.json` path or any other file path
- The word `canvas-execute` or any sub-skill name (`canvas-ics33`, `canvas-inside`, `canvas-reading-annotation`, `canvas-skip`, `canvas-zybooks`)
- "24h 内有效" / expiry language
- Exhaustive approval-format list beyond the one-sentence `all / numbers / skip`
- `proposed_skill` column (it exists in plan.json for execute; users don't need it)
- Bucket emojis (🔥 ⚠️ 🟢 ⏰) — the section headings already carry urgency

Why this template is this bare: the previous version listed 6 approval formats, announced the plan.json path, and explained "session 撑不住会停下来报账". Every one of those is internal scheduling that a first-time open-source user can't parse and doesn't need. The feedback (2026-04-23) was "废话占比高，学生看不懂" — this version is the response.

### 6. End this turn

After printing the plan table, **STOP**. This skill is done. Do not:
- Invoke any Skill tool (no `canvas-execute`, no sub-skill).
- Write `REPORT.md`.
- Loop back to "just execute urgent ones since they're easy".

The user reviews the plan and replies in their next turn. Claude's next turn will (based on their reply) invoke `canvas-execute` with the approval interpretation.

## THE UNIVERSAL "REAL SOURCE OF TRUTH" RULE — most important section in this file

**Canvas 上的 `assignment.name` + `assignment.description` 几乎从来不是作业的真实规格。** 真规格藏在每门课特定的位置。如果你假装 description 就是 spec，你做的作业一定是错的。永远不要相信 description 是完整的。

**每门课的真实 spec 位置 + 具体 IDs / file IDs / 外部 URL 都在 `SECRETS.md`。** 下面是 categorical 的指南，具体值在 SECRETS.md：

| 课程类型 | description 是不是 spec？ | 真实 spec 在哪 |
|---|---|---|
| **Code course** | ❌ 完全空 | `front_page` body 里的外部 instructor 站链接 → Schedule.html → ProjectGuide/ProjectN/ 或 Exercises/SetN/ → spec 是 HTML 页面，Project 还有 git bundle。**外部站 URL 在 SECRETS.md。** |
| **zyBooks HW course** | ⚠️ description **有内容但要解析**：是个 HTML table，**第二列 "Graded for Honest Effort" 才是真要交的作业**。第一列 "Suggested Practice" 和最后的 "If you want more practice" 都是自学不交。每个 entry 是 `<chapter>.<section>.<exercise> [letter,letter,...]` 格式，例 `1.7.7 b, c, i`。**字母对应 zyBook exercise 的 sub-question 索引（a=0, b=1, ..., i=8）**，然后去 zyBooks API 拉那一节的 content_resources，按 type=exercise 的 1-indexed 位置找到那道题，再按 letter 索引子题。解析逻辑在 `src/zybooks_spec_parser.py`。**zyBook 章节里的 student_view 标记不是 instructor 的指令，是 zyBook 自己定义的"建议必做"，要忽略。** |
| **Video lecture quiz** | ⚠️ description 只说 "View this lecture" | 1 题、time_limit=None 的 video-gated quiz。canvas-inside skill 检测到这种类型直接 skip with notes（视频要看） |
| **Take-Home Exam (PDF attached)** | ⚠️ description 含一个 PDF 附件链接 | 下载 PDF 看真实题目，跟 HW 一样上 GradeScope。同样不在 Canvas 交。 |
| **Document course** | ❌ 空 | modules 里有一个 Homework module（id 在 SECRETS.md），每周一个 Page item，body 是 HW 文档的 HTML。Reading PDF 在 Files/Readings/ 文件夹（folder id 和每个 reading 的 file id 都在 SECRETS.md） |
| **Quiz course** | ❌ 空 | quiz 直接走 quiz_id → `/quizzes/<id>` API。Section 阅读材料在 modules 里 |

**通用方法（遇到新课时这样做）**：
1. `assignment.description` 看一眼，但永远不要假设它就是全部
2. 同时拉 `/courses/<cid>/front_page`、`/courses/<cid>/modules`、`/courses/<cid>/syllabus_body`、attached files
3. 如果 description 含 HTML table、外部链接、提到 zyBook/GradeScope/textbook → 那是 routing hint，沿着它去找真 spec
4. 把找到的具体 IDs / URLs **写进 `SECRETS.md`**（不是 SKILL.md）。SKILL.md 只描述类型行为，SECRETS.md 存具体值。

**为什么这条这么重要**：第一夜把所有代码课作业标成 `mixed_unsupported`，因为 description 全空 — 事后才发现 front_page 里有外部站链接。第二夜把 zyBook-style HW 的章节里 162 个 question 全渲染了 — 事后才发现 Canvas description 表格的第二列才是 instructor 真指定的 ~22 道。**两次都因为相信了 description**。

## Critical lessons from prior overnight runs

1. **`assignment.description` is empty for almost every course.** Don't trust it. The real content is in modules, in linked external sites, or in Files folders. If you ever add a NEW course, the first thing to do is `cv.get(f'/courses/{cid}/front_page').get('body')` to find the external pointer, then add the discovered URL/IDs to SECRETS.md.

2. **`course.syllabus_body` is sometimes useful, sometimes empty.** Try it but don't depend on it.

3. **`/courses/<id>/files` returns 403 on some courses.** But `/courses/<id>/folders` works, and from a folder you can `/folders/<id>/files`. Folder IDs go in SECRETS.md.

4. **Canvas Quiz API for students** is non-obvious: `/quizzes/<id>/questions` returns 403. Must `start_quiz_submission` first, then `/quiz_submissions/<sid>/questions`. **Starting a submission consumes one of the allowed attempts even if you don't /complete it.** Scan doesn't start submissions — that's execute's job, and only for `canvas-inside`.

## Configuration

- `courses.yaml` — course_id → skill mapping. Edit when courses come and go.
- `.env` — `CANVAS_TOKEN`, `CANVAS_BASE`
- `runs/<today>/assignments.json` — raw pending list (written by `src.router --dry-run`)
- `runs/<today>/plan.json` — approval-gated plan (written by this skill)

## What you MUST NOT do

- Do NOT dispatch sub-skills from this skill. That's `canvas-execute`'s job. The whole point of the split is to make dispatch impossible from scan — if you feel tempted to "just also run ics33 since it's urgent", stop. That's how 2026-04-21 burned a whole session.
- Do NOT create the `.scan_in_progress` marker. Scan doesn't need it.
- Do NOT write `REPORT.md` or sync `final_drafts/`. Those happen in execute, after dispatching is done.
- Do NOT fabricate `due_at` or `workflow_state`. If Canvas API fails for an item, mark `hours_left: null` and `bucket: "unknown"` in plan.json and move on.
- Do NOT process assignments outside the 7-day window. The `pending_window_days` config in `courses.yaml` is the source of truth.
- Do NOT touch the zyBooks math course or anything routed to `mixed_unsupported` — those are proposed_skill = `canvas-skip`, meaning "log to todo.md, no automation".
