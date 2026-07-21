---
name: canvas-execute
description: This skill should be used when executing an already-scanned Canvas plan after the user has approved it. Invoked after `canvas-scan` wrote `runs/<today>/plan.json` and the user replied with approval like "批准全部", "approve all", "做 1, 3, 5", "只做 urgent", "第 N 项 defer", "cancel". Parses the approval, updates plan.json with per-item decisions, dispatches approved items to course-specific sub-skills (canvas-ics33 / canvas-reading-annotation / canvas-essay / canvas-inside / canvas-zybooks / canvas-generic / canvas-skip), writes skipped+deferred result.json for non-approved items, then produces REPORT.md and syncs the final_drafts/ folder.
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - WebFetch
  - Skill
  - TodoWrite
---

# canvas-execute (approval-gated dispatch)

Dispatcher for the Canvas auto-homework system. This skill is the **execute** half of the scan/execute split — it runs only after `canvas-scan` has produced a plan and the user has explicitly approved some subset of it.

## The contract with canvas-scan

- `canvas-scan` wrote `runs/<today>/plan.json` with every pending item at `user_decision: null`.
- The user reviewed the plan (printed as a markdown table in the previous turn) and replied with an approval spec.
- Claude (the outer orchestrator) parsed the user's reply and invoked this skill, passing the approval interpretation as an argument or as context.

**This skill's job**: apply the approval to plan.json, dispatch the approved items, record the non-approved ones as deferred, finalize.

**If `plan.json` doesn't exist or is >24h old → STOP and tell the user to run `/canvas-scan` first.** Do not invent a plan, do not dispatch anything, do not guess.

The highest spec is [`canvas_scan.md`](../../../canvas_scan.md) §7 (batch execution after approval). Read it if unsure.

## Hook guardrails (what gates execute)

All 7 hooks apply during execute:

| # | Hook | Effect |
|---|---|---|
| 1 | SessionStart `inject-context.py` | Injects pending list at turn 0. Informational. |
| 2 | PostToolUse(Write/Edit on result.json) `check-result-schema.py` | Every result.json you write must have valid `status` (`draft_ready`/`submitted`/`skipped`/`error`). Bad schema → exit 2. |
| 3 | PostToolUse(Bash) `check-bash-output.py` | Validates pytest / coverage / git output when sub-skills run them. |
| 4 | PreToolUse(Bash) `check-presubmit-audit.py` | Blocks `cv.submit_files` / `upload_submission_file` / `submit_quiz` unless `<work>/verification.log` exists and is all PASS. |
| 5 | PostToolUse(Write/Edit on result.json) `check-spec-grounding.py` | For draft_ready/submitted, if `spec.md` mentions external refs but `references/` is empty → exit 2. |
| 6 | PostToolUse(Write/Edit on result.json) `check-identifier-grounding.py` | For .py/.pdf drafts, every suspicious Python identifier must be grounded in spec/refs/builtins. |
| 7 | Stop hook `check-router-complete.py` | **Gated by `runs/<today>/.scan_in_progress` marker.** While the marker exists, every item in `assignments.json` must have a `result.json` before Stop passes. |

**Critical**: hook 7 is the one that keeps execute honest. Without it, a session could dispatch 3 of 5 approved items and then drift off. With it, you cannot stop until every assignment in assignments.json has a result.json — either written by a sub-skill (for approved+executed) or written by this skill as `status: skipped` with `deferred_to_next_run: true` (for non-approved or skipped-at-approval-time).

## Working directory assumption

The working directory is the project root (the folder you cloned this repo into; Claude Code sets cwd automatically on session start). Python helpers under `src/`, config under `.env` and `courses.yaml`.

## What you do

### 0. Precondition check

```bash
TODAY=$(date +%Y-%m-%d)
test -f "runs/$TODAY/plan.json" || { echo "NO_PLAN"; exit 1; }
test -f "runs/$TODAY/assignments.json" || { echo "NO_ASSIGNMENTS"; exit 1; }
```

If either is missing: tell the user "No plan.json for today. Run `/canvas-scan` first to generate a plan, review it, then come back." Stop. Do NOT run scan inline — that's the router's job and would defeat the approval gate.

Then check plan.json freshness:

```python
import json, datetime as dt
plan = json.loads(open(f"runs/{today}/plan.json", encoding="utf-8").read())
expires = dt.datetime.fromisoformat(plan["expires_at"])
now = dt.datetime.now(expires.tzinfo)
if now > expires:
    print("PLAN_EXPIRED")
    # tell user: "Plan is stale (>24h). Re-run /canvas-scan before executing."
```

If expired: STOP. Tell user to rerun `/canvas-scan`.

### 1. Handle stale marker from a prior crashed session

Before activating your own marker, check for an orphan marker from a past session:

```bash
if [ -f "runs/<past-date>/.scan_in_progress" ]; then ...
```

Glob `runs/*/.scan_in_progress`. For each match whose date is **not today**:
- Read that day's `assignments.json`
- For any assignment lacking a `result.json`, write `{status: "skipped", notes: "session crashed before this item was processed", deferred_to_next_run: true}` so the next `/canvas-scan` re-proposes it
- Delete the orphan marker

This keeps Stop hook from being permanently wedged by a past crash.

### 2. Activate today's marker (with session id)

The marker file's **contents** are the creating session's id, not just a touch. The Stop hook (`check-router-complete.py`) reads the marker contents and compares to its own event's `session_id` — if they don't match, the hook treats this as "another session's marker, not mine" and passes through. This is what lets a debug-only session (in the same project, never called canvas-execute) stop cleanly while another session is mid-execute.

CC must extract the current session id from the env / hook event / transcript path and write it into the marker:

```python
import os, uuid
from pathlib import Path
import datetime as dt

today = dt.date.today().isoformat()
marker = Path(f"runs/{today}/.scan_in_progress")
marker.parent.mkdir(parents=True, exist_ok=True)

# Determine session_id. CC has its own session_id available in the runtime
# environment — check CLAUDE_SESSION_ID env var first, fall back to extracting
# from the transcript filename ($CLAUDE_TRANSCRIPT_PATH or the conversation
# transcript path), and as a last resort generate a uuid (this still works:
# the hook only requires "marker contents == event.session_id"; if execute
# stamped a uuid that doesn't match the runtime session id, the hook treats
# the session as not-the-owner and passes through, which is safe — you just
# lose the gate for this run, but no data loss).
session_id = (
    os.environ.get("CLAUDE_SESSION_ID")
    or os.environ.get("CC_SESSION_ID")
    or str(uuid.uuid4())  # safe fallback
)
marker.write_text(session_id, encoding="utf-8")
```

Practical note for CC: at execute time, read the most reliable session id source you have — typically the transcript path filename matches the session uuid. If you can't determine the current session id deterministically, use uuid4 as fallback; this still implements "this session vs other sessions" correctly within this single execute run.

This arms the Stop hook. **Every assignment in `runs/$TODAY/assignments.json` must now have a matching `result.json` before this session can stop** — for sessions whose `session_id` matches the marker contents. Other sessions in the same project pass through.

### 3. Parse user's approval + update plan.json

Read the user's approval spec. It was either:
- Passed as an argument when Claude invoked this skill (e.g. `"approve all"`, `"只做 urgent"`, `"做 1, 3, 5"`)
- Or visible in the preceding conversation turn

Recognize these patterns (Chinese + English):

| User says | Interpretation |
|---|---|
| 批准全部 / 全部批准 / approve all / all / 全部做 | every item → `approve` |
| 只做 urgent / urgent only / 只做紧急 | items with `bucket: urgent` → `approve`, rest → `defer` |
| 做 1, 3, 5 / 做 1 3 5 / approve 1 3 5 | listed indices → `approve`, rest → `defer` |
| 做 1-4 / 1 到 4 | index range → `approve`, rest → `defer` |
| 第 N 项 用 canvas-X / swap N to canvas-X | item N gets `swap:canvas-X`, still approved but with different skill |
| 第 N 项 defer / 跳过 N / skip N | item N → `defer` |
| cancel / 取消 / 全部取消 | every item → `defer` (nothing dispatched, all written as skipped+deferred) |
| 未明示 (e.g. user says "做 1, 3" silent on 2,4,5) | 2, 4, 5 → `defer` (safer than auto-executing) |

**Ambiguous or unparseable input → STOP and ask the user once more.** Do not guess. Example ambiguous input: "做前面几个" (how many is "前面"?). Answer: "请明确一下 —— 做第 1、2、3 项吗？" and wait.

Update plan.json atomically:

```python
import json, os
plan_path = Path(f"runs/{today}/plan.json")
plan = json.loads(plan_path.read_text(encoding="utf-8"))
for item in plan["items"]:
    item["user_decision"] = determine_decision(item)  # "approve" | "defer" | "swap:canvas-X"
tmp = plan_path.with_suffix(".json.tmp")
tmp.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
os.replace(tmp, plan_path)
```

### 4. Dispatch approved items — one at a time, in order

For each item in plan.json where `user_decision == "approve"` or starts with `"swap:"`, process sequentially (plan.json items are already sorted by bucket priority then by `hours_left`, so earliest-due-first).

For each item:

1. Determine which sub-skill to invoke:
   - `user_decision == "swap:canvas-X"` → `canvas-X` (user explicit override wins)
   - `user_decision == "approve"` → resolve the Skill name from `proposed_skill`. `proposed_skill` may be a short `courses.yaml` route value OR already a `canvas-*` Skill name; map it to the Skill to invoke:

     | route value (`proposed_skill`) | Skill to invoke |
     |---|---|
     | `quiz` | `canvas-inside` |
     | `code_py` | `canvas-ics33` |
     | `ac_english` | `canvas-reading-annotation` (or `canvas-essay` via the sub-router below) |
     | `zybooks` | `canvas-zybooks` |
     | `mixed_unsupported` | `canvas-skip` |

     A `proposed_skill` already in `canvas-*` form (e.g. the LDB filter rewrites quiz items to `canvas-skip`) maps to itself.
   - **Writing-course sub-routing**: if the resolved skill is `canvas-reading-annotation`, run the deterministic router to decide between the short-form handler (`canvas-reading-annotation`, unchanged) and the long-essay handler (`canvas-essay`). This is a pure-Python utility — 0 LLM calls, regex + numeric comparison + Canvas API field queries.
     ```python
     if proposed_skill == "canvas-reading-annotation":
         import re, yaml
         from pathlib import Path
         from src.ac_eng_router import route_ac_eng_assignment
         from src import canvas_client as cv

         # Pull the overlay's persona_trigger_patterns / persona_skip_patterns yaml block
         overlay_path = Path("_private/canvas-essay-app.md")
         overlay_config = {}
         if overlay_path.exists():
             text = overlay_path.read_text(encoding="utf-8")
             m = re.search(r"```yaml\s*\n(persona_trigger_patterns:.*?)\n```",
                           text, re.DOTALL)
             if m:
                 overlay_config = yaml.safe_load(m.group(1)) or {}

         # Look up the full assignment dict (router needs name, description,
         # points_possible, submission_types, attached_pdf_texts).
         full = next(
             (a for a in assignments_json if str(a.get("id")) == str(item["assignment_id"])),
             None,
         )
         if full is None:
             full = cv.get_assignment(item["course_id"], item["assignment_id"])

         sub = route_ac_eng_assignment(full, overlay_config, plan_item=item)
         if sub == "essay":
             proposed_skill = "canvas-essay"
         # else keep canvas-reading-annotation for short-form path
     ```
     If `_private/canvas-essay-app.md` does not exist, `overlay_config` stays empty — the router still works (skips Layer 2, relies on Layers 3-6). The router never raises; on any malformed regex in the overlay it logs and falls through.

2. **TodoWrite**: add the assignment as a todo, mark `in_progress`.

3. **Invoke via the Skill tool**. Pass a brief context line:
   > "Work on `<assignment_name>` (course `<course_name>`). Work dir: `runs/<today>/<work_dir>`. See `assignments.json` and `plan.json` for full item details."

4. Sub-skill runs → writes its own `result.json` → returns.

5. Read the `result.json`. Mark todo `completed` (or keep in_progress with error note if `status: error`).

6. Update `runs/_processed.json` ledger (atomic write via `.tmp` + `os.replace`):
   ```python
   ledger[f"{course_id}:{assignment_id}"] = {
       "status": sub_result["status"],
       "course_name": item["course_name"],
       "assignment_name": item["assignment_name"],
       "due_at": item["due_at"],
       "completed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
       "draft_path": sub_result.get("draft_path"),
       "notes": sub_result.get("notes"),
       "deferred_to_next_run": False,
   }
   ```

7. Continue to the next approved item.

Run items **sequentially** (not in parallel) — Canvas writes can race, and sequential logs are easier to debug.

**If the Skill tool reports the target sub-skill is not discoverable**, STOP and print a clear error ("sub-skill `canvas-X` not found; CC was likely launched from the wrong directory"). Do NOT try to do the work inline.

### 5. Pause when session is running tight — report clearly and ask

Claude judges its own context budget. If roughly less than ~15 turns of capacity remain AND there are still approved items left to dispatch, **break out of the loop** instead of trying to squeeze in another heavy item. Half-finished work is worse than deferred work.

To pause cleanly (Stop hook requires every `assignments.json` item to have a `result.json`):

1. For each remaining undispatched approved item, write a placeholder `result.json`:
   ```json
   {
     "assignment_id": ...,
     "course_id": ...,
     "status": "skipped",
     "notes": "paused mid-run — awaiting user decision (continue or defer)",
     "deferred_to_next_run": true
   }
   ```
   Also update `_processed.json` ledger with `deferred_to_next_run: true`. This satisfies the Stop hook.

2. **Print a clear status to the user**, in this shape:

   ```
   做完了：
   - #1 Quiz on Section 5 — draft_ready (runs/.../quiz_s5.json)
   - #2 Quiz on Section 6 — draft_ready (runs/.../quiz_s6.json)

   还没做（session 快满了）：
   - #3 Set 3 Problem 1
   - #4 Set 3 Problem 2
   - #7 Tue Wk5 HW Scan

   要继续做吗？
   - 回 "继续" → 我接着跑 #3，撑到哪算哪
   - 回 "defer" / "算了" / 不回 → 剩下的保持 deferred，下次 /canvas-scan 自动重现
   ```

3. End your turn. Do NOT proceed to §6 finalize yet — wait for the user's next reply.

4. On the user's next turn:
   - **"继续"** / **"接着做"** / **"yes"** → go back to §4 and dispatch the next undispatched item. Each successful sub-skill completion **overwrites** the placeholder `result.json` with a real one. Repeat §5 pause-check as you go.
   - **"defer"** / **"算了"** / **"跳过"** / silence / anything not a clear continue → jump to §6 finalize. Placeholder `result.json` files stay as the final state (they're already correctly marked `deferred_to_next_run: true`).

**Rule of thumb on when to pause**: if the next item's `proposed_skill` is `canvas-ics33` (heavy, ~20 turns) or `canvas-generic` (heavy, ~25-30 turns — investigation + 3 sub-agent reviews) and your context window is >60% consumed → pause. If it's `canvas-inside` or `canvas-skip` (light, ~10 or ~1 turns) → probably fine to attempt one more. Trust your judgment; erring toward pausing is safer than runaway.

### 6. Finalize — write any remaining deferred, REPORT.md, final_drafts/ sync, rm marker

Reach this section via one of two paths:
- **Happy path**: §4 loop completed all approved items.
- **Defer path**: user replied "defer" / "算了" / silence after §5's pause+ask.

Steps:

1. **Write deferred `result.json` for items not yet written**. These are items where:
   - `user_decision == "defer"` (explicitly declined at approval time) — if their `result.json` doesn't already exist
   - `user_decision == null` (user silent on this index at approval time) — same
   - Placeholder-paused items from §5 — already written, skip
   Use: `{status: "skipped", notes: "user declined at plan review" / "not approved this run", deferred_to_next_run: true}`

2. **Update `runs/_processed.json` ledger** for every item processed this run (dispatched or deferred).

3. **Write `runs/<today>/REPORT.md`** (see §7 for urgent banner + §8 for layout).

4. **Sync `final_drafts/` folder** for any `draft_ready`/`submitted` items (see §9).

5. **Remove marker**: `rm "runs/$TODAY/.scan_in_progress"`. Pair with §2's `touch`. If this step is skipped, the next session in this directory is gated.

### 7. Urgent banner at top of REPORT.md

Compute urgency for EVERY item in `assignments.json` (whether approved, deferred, or already done):

```python
import json, datetime as dt
from pathlib import Path

now = dt.datetime.now(dt.timezone.utc)
ledger = json.loads(Path("runs/_processed.json").read_text(encoding="utf-8"))
todays = json.loads(Path(f"runs/{today}/assignments.json").read_text(encoding="utf-8"))

urgent = []
for item in todays:
    key = f"{item['course_id']}:{item['assignment_id']}"
    led = ledger.get(key, {})

    # Canvas is source of truth for "is it submitted"
    try:
        sub = cv.get_submission(item["course_id"], item["assignment_id"])
        live_state = sub.get("workflow_state")
    except Exception:
        live_state = "?"

    if live_state in ("submitted", "graded"):
        continue  # done, skip from urgent banner

    due = dt.datetime.fromisoformat(item["due_at"].replace("Z", "+00:00"))
    hours_left = (due - now).total_seconds() / 3600
    if hours_left <= 24:
        # Prefer friendly name if the overlay set one (plan.json carried it through from scan)
        course_display = item.get("course_friendly_name") or item["course_name"]
        urgent.append({
            "course": course_display[:25],
            "name": item["name"][:50],
            "hours_left": round(hours_left, 1),
            "state": live_state if hours_left > 0 else "OVERDUE",
            "ledger_state": led.get("status"),
            "draft": led.get("draft_path"),
            "skill": item["skill"],
        })
```

The same friendly-name preference applies to the error block (§7.5), the success summary, and the final_drafts/ folder structure — wherever a course label is rendered for the student, `course_friendly_name` (when present in plan.json/result.json) takes precedence over `course_name`. The framework name (e.g. `canvas-ics33`) is the dispatch key and is unaffected.

Format banner:

```markdown
# 🔥 URGENT — N item(s) due within 24h, not submitted

- [canvas-ics33] <Code Course> Spring 2026 | Set 3 Problem 1 | due in 14h | state=unsubmitted | draft: runs/.../set3p1.py
- [canvas-reading-annotation] <Writing Course> S26     | Tue Wk5 HW Scan | OVERDUE 3h ago | state=OVERDUE | ledger=draft_ready

Upload the draft, mark 'skip on purpose', or handle it. This banner reappears every run until resolved.

---
```

If no urgent items:

```markdown
# ✅ No urgent items in next 24h

---
```

The banner is ALWAYS the first block of REPORT.md. The CEO opens the file and sees status immediately.

### 7.5. Errors get hand-holding, not just notes

For every item where this run wrote `result.json` with `status: "error"`, REPORT.md gets a **debug-help block** right below the urgent banner. The student sees a concrete next-step list, not just `notes: "..."`.

Iterate `runs/<today>/*/result.json`, collect the ones with `status == "error"`, and for each render:

```markdown
## ⚠️ Errors this run — N item(s) need fixing

### {assignment_name}  ({course_name})

- skill: `canvas-{name}` → `.claude/skills/canvas-{name}/SKILL.md`
- error notes: {result.json notes verbatim}

**Debug checklist** (open the SKILL.md and tick through):

- [ ] `<!-- UNFILLED_SKELETON v1 -->` sentinel still present? Remove it after you fill the 4 TODOs.
- [ ] Frontmatter `name:` matches the directory name (`canvas-{name}`)?
- [ ] Frontmatter `allowed-tools:` includes everything the skill uses (Bash / Read / Write / Edit / WebFetch)?
- [ ] §1 TODO answered (where does the real spec live)?
- [ ] §2 TODO answered (how does this skill produce a draft)?
- [ ] §3 TODO answered (how do you verify the draft before submitting)?
- [ ] §4 result.json — does the skill actually write `runs/<today>/<dir>/result.json`?
- [ ] If `notes` mentions a specific file path or API call: does that path exist? does the API call work standalone (`python -c "from src import canvas_client; ..."`)?

After fixing, re-run `/canvas-scan` — the assignment will reappear in the plan (deferred items re-enter on next scan).

---
```

If multiple errors, list them all under one `## ⚠️ Errors this run` heading. If zero errors, skip this section entirely (don't render an empty heading).

This block exists because raw `error notes` is hostile to a first-time student — they get "X failed" and don't know whether the problem is their SKILL.md, the framework, or Canvas. The checklist gives them a 30-second sanity scan + a specific re-run command.

### 7.6. Next step block at the bottom of REPORT.md

Same principle as canvas-scan §5b: data without recommendation is a bug. After all status sections, REPORT.md ends with a `## Next step` block giving ONE concrete suggested action.

The suggestion adapts to what actually happened this run:

- **Errors present**: "先看 errors 里的 [first error's assignment name]，根据 debug checklist 检查 SKILL.md 是不是还有 TODO 没填。修完再 `/canvas-scan` 重跑。" / English equivalent.
- **Skipped present (manual courses), no errors**: "[N] 项是手动课，去 Canvas 自己交：<list assignment names>." / English equivalent.
- **Done items only, no errors / skipped**: "草稿在 `runs/<today>/`，审完手动上传到 Canvas (or your skill's submission flow)." / English equivalent.
- **Mix**: pick the highest-priority single action — errors first, then skipped, then done.

Render exactly one `## Next step` block. Single sentence preferred; multiple bullets allowed only when there are multiple distinct actions of equal urgency. Keep the language matched to the rest of REPORT.md (Chinese if the run was triggered by a Chinese-language scan, English otherwise — same sniff rule as canvas-scan §5b).

### 8. Sync final_drafts/ folder

For every item from this run whose final `status` is `draft_ready` or `submitted` and has a `draft_path`:

1. Map course → subfolder:

   | skill / course pattern | subfolder |
   |---|---|
   | `code_py` / the code course | `final_drafts/CODE/` |
   | `zybooks` / the zyBooks math course | `final_drafts/ZYBOOKS/` |
   | `ac_english` / the writing course | `final_drafts/WRITING/` |
   | `quiz` / the quiz course | `final_drafts/QUIZ/` |
   | anything else | `final_drafts/_other/` |

2. Derive filename: strip course prefix from assignment name, `_` for spaces, keep extension.

3. Copy:

   ```python
   import shutil
   from pathlib import Path
   dest_dir = Path("final_drafts") / subfolder
   dest_dir.mkdir(parents=True, exist_ok=True)
   shutil.copy2(draft_path, dest_dir / short_name)
   ```

4. Rewrite `final_drafts/README.txt` entirely:
   - One line per file: `filename    STATUS (due DATE)`
   - STATUS = `✅ 已交 Canvas` / `⏳ 待上传` / `🔧 待答题`
   - Rescans the final_drafts/ tree + cross-refs `_processed.json` for status

The final_drafts/ folder is the CEO's easy-find drop zone for anything to upload. Skip this and drafts rot unseen.

(The `.scan_in_progress` marker is removed in §6 step 5 as the final step of finalize, not in a separate numbered section.)

**Crash-path fallback**: if dispatch crashed mid-run (sub-skill threw, Canvas API died, etc.) and you're recovering in a follow-up turn before marker removal: make sure every item in assignments.json has a `result.json` (write `status: skipped, notes: "execute crashed at this item", deferred_to_next_run: true` for unfinished ones). Then §6 step 5 removes marker. Then report the crash to the user with specifics.

## What you MUST NOT do

- Do NOT dispatch an item whose `user_decision` isn't in `{approve, swap:*}`. "Not approved" means "not approved". Silent over-execution is the exact failure mode we're preventing.
- Do NOT scan Canvas or regenerate plan.json from scratch. If plan.json is missing or stale, hand back to `/canvas-scan`.
- Do NOT try to rush the last approved item when context is tight. Pause (§5), report clearly, ask. Half-finished work is worse than deferred work — deferred items cleanly reappear on the next `/canvas-scan`.
- Do NOT fabricate `draft_path` or `status` in the ledger. If a sub-skill returned `error`, record `error` — don't round up to `draft_ready`.
- Do NOT submit anything to Canvas without standing authorization. Per `SECRETS.md`, the standing auto-submit authorizations are limited (the quiz course under `CANVAS_QUIZ_AUTORUN=1`, the code course under its own explicit flag). Everything else is draft-only; upload is the user's call.
- Do NOT forget to remove the marker. The single biggest lesson from 2026-04-21 was "don't leave the Stop gate wedged open".

## Relationship to the old monolithic canvas-router

The old `canvas-router` used to do scan + dispatch + finalize all in one skill. It was split because a single SKILL.md's "stop and wait for approval" instruction was too easy to drift past. The split makes the approval gate a filesystem boundary (`plan.json` on disk between two Skill invocations) instead of a prose boundary (a paragraph in a SKILL.md).

Earlier versions of this (`canvas-execute`) skill also had a "pre-dispatch session-budget guard" that estimated total turns before dispatching and refused if >60. That was over-engineered: it fired *after* the user had already approved, creating a frustrating "batched, then blocked" loop. The real mechanism now (§5 mid-run pause-and-ask) is simpler: just do them one at a time, stop when it feels tight, report clearly, ask whether to continue.

Whenever you're tempted to "just also do the scan inline if plan.json is missing", remember: that temptation IS the bug. Hand back to the user, let them run `/canvas-scan`, start fresh with a real plan.
