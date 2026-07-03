---
name: canvas-cron
description: Install / inspect / pause / change / delete Canvas Pilot cron instances via Windows Task Scheduler. The skill is a **course-agnostic interactive builder** — it lists the student's courses from courses.yaml, asks which course they want a cron for, which action template (email reminder vs autonomous submit), when (schedule), and which template-specific knobs to tune. Autonomous templates require the student to type `授权` to authorize auto-submit. Then walks 5 install gates end-to-end (yaml + render XML → schtasks /create → dry-run classifier → force-fire 60s OS trigger proof → enable schedule). Cookie health is checked at real fire time (not in dry-run); if Canvas session is dead the cron sends a wake-up email instead of silently launching Chromium. Triggered by "装个 cron" / "加个 cron" / "改 cron 时间" / "停掉 cron" / "看 cron 状态" / "删掉 cron" / "install a cron" / "set up a cron" / "/canvas-cron". The skill **zero-hardcodes** course names, template names, instance names, course IDs — every enumeration comes from the CLI's list-courses / list-templates / list output, computed at runtime.
allowed-tools: Bash, PowerShell, Read, AskUserQuestion
---

# canvas-cron — interactive Canvas-cron builder

This skill is the user-facing control plane for `scripts/canvas_cron.py` + the
action-template framework. The student never edits `_private/cron_instances.yaml`
by hand, never copies CLI snippets, never picks routine names from memory.

**The skill is course-agnostic by design.** It never names a specific course,
template, or instance in its source text. All such names come from the CLI's
runtime output (list-courses / list-templates / list) and are surfaced via
AskUserQuestion options.

## §0 — preflight: discover what's available

Run three readonly Bash commands. Memo-ize the parsed outputs for later steps:

```bash
python scripts/canvas_cron.py list-courses
python scripts/canvas_cron.py list-templates
python scripts/canvas_cron.py list
```

If any command fails with `ModuleNotFoundError` or the framework files
(`scripts/canvas_cron.py`, `scripts/cron_base.py`, `scripts/cron_registry.py`)
don't exist, **stop and tell the student**:

> canvas-cron framework not installed in this repo. Ask CEO to deploy the
> canvas-cron MVP plan.

If `list-courses` returns "(no courses ...)", tell the student to run
canvas-setup first. If `list-templates` returns "(no templates ...)", the
framework was installed incomplete — ask CEO.

## §1 — parse student intent

Match the student's prose against one of:

| Student says (any language, paraphrased) | Intent |
|---|---|
| 装个 cron / 加个 cron / install / set up / create | `install` (new instance) |
| 改 cron 时间 / change schedule / 改时间 | `change_schedule` |
| 停掉 / 暂停 / disable / pause | `disable` |
| 启用 / enable / 开启 | `enable` |
| 删掉 / 移除 / delete / remove / uninstall | `delete` |
| 看状态 / list / status / what's running | `status` |

For non-install intents, you need an `instance_name`. If the student named it
in their prose, match against the `list` output. If ambiguous or unnamed,
use AskUserQuestion with options dynamically built from the `list` output:

```
question: "Which cron instance?"
options: [
  {label: "<instance_name_1> (<template_1>, course=<course_id_1>)", description: "..."},
  ...
]
```

For non-install intents, run the corresponding CLI command and stop:

- `disable` → `python scripts/canvas_cron.py disable <name>`
- `enable` → `python scripts/canvas_cron.py enable <name>`
- `delete` → `python scripts/canvas_cron.py delete <name>`
- `status` → `python scripts/canvas_cron.py status [<name>]`
- `change_schedule` → continue to §4 (skip course/template/params choice),
  then call `register <name>` instead of `create <name>` at §7.

For `install`, continue to §2.

## §2 — (install only) choose course

Use AskUserQuestion with options dynamically generated from the `list-courses`
preflight output. **Never write a real course name in the question text** —
labels come from the CLI output:

```
question: "Which course is this cron for?"
options:
  - label: "All courses"
    description: "scan every course in courses.yaml (cross-cutting reminder)"
    → course_id = "all"
  - label: "<courses[0].name> (<courses[0].course_id>)"
    description: "skill=<courses[0].skill>"
  - label: "<courses[1].name> (<courses[1].course_id>)"
    description: "skill=<courses[1].skill>"
  - ...
```

Capture the chosen `course_id` for later. The special value `"all"` is only
supported by templates whose code handles it (currently `email_pending_reminder`).
If the student picks "All courses" and §3 chooses a template that does NOT
support all-courses (e.g. `autonomous_submit_pending` — autonomous templates
need a single concrete course_id for the CC prompt), warn and force re-pick
of either course or template.

## §3 — (install only) choose template

Use AskUserQuestion with options from `list-templates`:

```
question: "What should this cron do when it fires?"
options:
  - label: "<templates[0].name>"
    description: "<templates[0].kind>: <templates[0].description>"
  - label: "<templates[1].name>"
    description: "<templates[1].kind>: <templates[1].description>"
  - ...
```

Capture the chosen `template_name` and its `kind` (email / autonomous) for
later branching at §6.

## §4 — (install or change_schedule) choose schedule

Three sub-questions via AskUserQuestion (one at a time, or one multi-question
call — your choice). Defaults sensible to email or autonomous kind:

1. **Cadence**: every N days. Defaults: email kind → 1 (daily), autonomous → 2.
2. **Time**: HH:MM in 24h local PT. Defaults: email → "09:00", autonomous → "19:00".
3. **Start date**: YYYY-MM-DD. Default: tomorrow's date in PT.

Use natural ranges in the option labels: "every 1 day (daily)", "every 2 days",
"every 7 days (weekly)", etc.

## §5 — (install only) choose template params

Read the chosen template's `param_schema` from the §0 `list-templates` output.
For each `ParamSpec`, use AskUserQuestion with the `prompt` field as question
text and the `default` shown as the recommended option. Coerce the answer to
the spec's `type` (int / str / bool).

If the student says "use defaults" up-front, skip all per-param questions and
use spec defaults across the board.

## §6 — (install only, kind=autonomous) 授权 keyword

If `kind == "autonomous"`, show this exact prose:

> **This cron template will spawn a fresh Claude Code session that runs
> `/canvas-execute` and may submit to Canvas without manual approval each
> time it fires.**
>
> Type `授权` or `authorize` to proceed. Anything else aborts (nothing
> written, nothing registered).

Read the reply. If it doesn't equal `授权` or `authorize` (case-insensitive,
trimmed), abort with:

> No authorization received. Nothing was created. Stopping.

For `kind == "email"`, skip §6 (no auto-submit means no authorization needed).

## §7 — install: G1-G5 install gates

Generate an `instance_name`. Suggest a default like
`<template_short>_<course_id>` (e.g. `<template_kind>_<course_id>`) and ask
the student via AskUserQuestion if they want to keep or rename. Names must
match `^[a-zA-Z0-9_]+$` (used as yaml key + Task Scheduler suffix).

Run via Bash:

```bash
python scripts/canvas_cron.py create <instance_name> \
    --template <template_name> \
    --course <course_id> \
    --days <N> --time <HH:MM> --start <YYYY-MM-DD> \
    --param key1=value1 --param key2=value2 \
    --recipient <email_from_secrets_or_AskUserQuestion> \
    [--authorized]      # ONLY if §6 passed
```

Expected stdout:
```
→ G1a: writing yaml entry for <name>
→ G1b: rendering scripts/cron_templates/_generated/<name>.task.xml
→ G2: schtasks /create /tn 'CanvasCron_<name>'
✅ G2: task 'CanvasCron_<name>' registered (disabled).
   Schedule: every <N> day(s) at <HH:MM> PT, starting <YYYY-MM-DD>
```

If exit non-zero or the `✅` line is missing, stop, print the captured
stderr, and tell the student. Possible recovery: yaml entry may have been
written before schtasks failed — `register <name>` can retry.

Next, dry-run classifier (G3):

```bash
python scripts/canvas_cron.py fire <instance_name> --dry-run
```

Expected: stdout contains `=== <instance_name> done ===` near the end. Dry-run
**skips the cookie probe** (no 5s probe latency); cookies are only enforced at
real OS-trigger fire time. If classifier crashes (Python traceback), task is
registered but disabled — print last 30 lines of `runs/_<name>_log.txt`, ask
whether to leave the task disabled (safe) or `delete` it.

Next, force-fire OS chain (G4, ~60s):

```bash
python scripts/canvas_cron.py fire <instance_name> --os-trigger
```

Tell the student up front:

> Force-firing the registered task once via Task Scheduler to prove the OS
> trigger chain works. This takes about 60 seconds. If the cookie is
> currently dead, the cron will send a wake-up email; otherwise (autonomous)
> the CC session keeps running in the background up to its execution time
> limit and emails the result.

Expected: `LastTaskResult` is `0` / `0x0` / `0x41301` (running). Anything else
= G4 failed; leave task disabled and surface the error.

Finally, enable (G5):

```bash
python scripts/canvas_cron.py enable <instance_name>
```

Tell the student:

> ✅ Install complete. Instance `<name>` is enabled. Next fire: <next_run from
> stdout>. If the Canvas cookie is dead at fire time, you'll get a wake-up
> email instead of a silent failure.

## §8 — change_schedule re-register flow

After §4 customize, run `python scripts/canvas_cron.py register <name>`
(re-renders XML + re-creates task from existing yaml). The CLI keeps the
existing yaml entry (only schedule fields change if §4 captured new values
— for v1 the simplest path is: tell the student to `delete` and re-create
to change schedule, then implement true in-place edit in v2).

For v1 of this skill, treat `change_schedule` as **delete + recreate**:

```bash
python scripts/canvas_cron.py delete <name>
# ...then run install §2-§7 starting from §2 (course already known, can
# pre-fill); skip §3 (template already known); §4 captures the new schedule.
```

## Error-recovery cheatsheet

| Symptom | Cause | Recovery |
|---|---|---|
| `ModuleNotFoundError: scripts.cron_base` | framework not installed | Ask CEO to deploy canvas-cron MVP |
| `instance not found: <name>` | typo or yaml entry missing | Run `list`, suggest closest match |
| `template not found: <name>` | template module deleted / typo | Run `list-templates` |
| `duplicate: instance ... already covers (course=..., schedule=...)` | another instance has same combo | `delete` the other or pick different time |
| G2 schtasks /create exit 1 | task with same name + different config exists | The CLI does `/delete /f` first; if still failing, check `schtasks /query` |
| G3 classifier crash | bug in template or Canvas API error | Inspect `runs/_<name>_log.txt`; leave task disabled |
| G4 LastTaskResult = 0x1 | action exited code 1 | Check `runs/_<name>_log.txt` for traceback |
| G4 LastTaskResult = 0x41301 | autonomous CC session still running — OK | Wait for result email |
| Enable fails | task missing or action path broken | `delete` + reinstall |
| User got cookie-expired email | cron tried to fire but Canvas session dead | Run `python -m src.canvas_login` to refresh; next cron will retry |

## Hard rules

- **Never** name a real course, template, or instance in the skill's question
  text or example output. All such names come from CLI runtime output.
- **Never** write a new template file or edit `scripts/cron_template_*.py`.
  Templates are framework code. To add a new kind of cron behavior, ask CEO.
- **Never** call `schtasks /change /enable` or `/disable` directly. Use
  `canvas_cron.py enable` / `disable` which route through PowerShell cmdlets
  (avoids password prompt on Win11 22H2+).
- **Never** force-fire `--os-trigger` outside §7 install or explicit student
  request. It's a real Task Scheduler trigger that for autonomous templates
  may actually submit homework.
- **Stop at any failed gate.** Don't advance G(n+1) if G(n) didn't print its
  expected success marker. Print the missing proof and explain.
- **Cookie probe is dry-run-exempt.** The skill should NOT expect a cookie
  check failure in `fire --dry-run` output — that gate is intentionally
  skipped in dry-run mode. Cookie state is enforced at the first real OS
  trigger; if cookies are dead, the user gets a wake-up email instead.
