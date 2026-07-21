---
name: canvas-cron
description: Use when managing Canvas Pilot schedules: install, inspect, pause, change, delete, or safely test scheduled scans and runs. Scan-only automation has no mutation authority; autonomous Canvas work requires a signed target-exact durable receipt.
allowed-tools: Bash, PowerShell, Read, AskUserQuestion
---

# canvas-cron — Codex-native schedule control

This skill is the user-facing control plane for `scripts/canvas_cron.py` and
the discovered `scripts/cron_template_*.py` templates. Never ask the user to
edit `_private/cron_instances.yaml` or Task Scheduler directly.

Course names, IDs, instance names, and recipients are private runtime values.
Do not copy them into this skill, tracked documentation, examples, or public
output.

## 0. Read-only preflight

Run from the repository root:

```powershell
python scripts/canvas_cron.py list-courses
python scripts/canvas_cron.py list-templates
python scripts/canvas_cron.py list
```

These commands inspect configuration and Task Scheduler state; they do not
create or change a schedule. If framework imports fail, stop and report the
exact missing file or module. If no courses exist, route to `canvas-setup`.

Memoize the discovered courses, template specs, and installed instances. Build
all user-facing choices from those live results.

## 1. Interpret the requested operation

Map the user's wording to one operation:

| Intent | CLI path |
|---|---|
| create/install a schedule | continue through this workflow |
| inspect/list/status | `status [name]` |
| pause/disable | `disable <name>` |
| resume/enable | `enable <name>` |
| remove/delete | `delete <name>` |
| change schedule | delete and recreate in v1 after confirming the change |
| test without effects | `fire <name> --dry-run` |

For a non-create operation, resolve the instance from the live `list` output.
If more than one matches, ask one concise question with those live choices.
Deleting an instance removes its registered task and archives local ledger/log
state; obtain confirmation because that is a destructive schedule change.

## 2. Choose scope and template from live data

For installation, ask for the course/scope and template using only preflight
results. Template kinds have different authority:

- `scan`: starts a fresh Codex session that runs `canvas-scan` and stops at the
  approval boundary. It has no Canvas mutation receipt.
- `email`: reads Canvas and sends a reminder email. It has no Canvas mutation
  receipt, but creating the outbound-email schedule still requires the user's
  approval.
- `autonomous`: may run approved Canvas assignment or quiz mutations. It must
  have a signed durable automation receipt before YAML is written or a task is
  registered.

The `all` course scope is valid only when the selected template advertises it.
The autonomous submit template requires one concrete course. The scan template
may use `all` as its scope label because `canvas-scan` builds the full daily
snapshot.

## 3. Choose schedule and parameters

Collect:

1. cadence (`days_interval`, positive integer);
2. local Pacific time (`HH:MM`, 24-hour format);
3. start date (`YYYY-MM-DD`);
4. every parameter in the selected template's live `param_schema`;
5. recipient when the template sends email or failure alerts;
6. a safe instance name matching `^[A-Za-z0-9_]+$`.

Show the complete proposed instance before creating it: template, private
course/scope label, schedule, parameters, recipient behavior, and whether it
can mutate Canvas.

## 4. Autonomous authority receipt

Skip this section for `scan` and `email` templates.

For an autonomous template, obtain explicit authorization for all of these
exact fields in the current conversation:

- current Canvas origin;
- concrete course ID;
- template ID;
- each allowed action (for example the exact `assignment.*` and/or `quiz.*`
  actions shown by `src.authorization.MUTATION_ACTIONS`);
- receipt expiration;
- whether an immediate OS-trigger test is included.

Explain that this is durable scheduled delegation, not approval of one draft.
If any field is missing or the user does not authorize it, stop without writing
YAML, a receipt, XML, or a scheduled task.

After explicit authority is verified, record it with
`src.authorization.create_authorization_receipt` using:

- `target_type="automation_template"`;
- `target_id=<selected template ID>`;
- the exact origin and course;
- only the explicitly authorized assignment/quiz actions;
- a delegation session label tied to the instance;
- an `authority_reference` that hashes the verified user authorization;
- `synthetic_qa=False` for a durable schedule;
- output under `_private/cron_authorizations/<instance>.json`.

The signing API enforces HMAC integrity and exact action names. The interactive
install flow may record authority only after the user grants it. The scheduled
template itself must never create durable authority from its YAML, prompt, an
environment variable, or a boolean flag.

## 5. Create and register, disabled first

Run:

```powershell
python scripts/canvas_cron.py create <instance> --template <template> --course <course_id> --days <N> --time <HH:MM> --start <YYYY-MM-DD> --param key=value --recipient <recipient>
```

For an autonomous template only, append:

```powershell
--authorization-receipt _private/cron_authorizations/<instance>.json
```

Never use or recreate the removed `--authorized` boolean path. The CLI must
validate the receipt's signature, expiry, current Canvas origin, course,
template, and every delegated action before its first durable write.

Success requires both:

- YAML and task XML rendered;
- Task Scheduler registration succeeded and the task is disabled.

If any gate fails, stop. Do not enable or force-fire the task.

## 6. Side-effect-free dry run

Run:

```powershell
python scripts/canvas_cron.py fire <instance> --dry-run
```

Dry run may read configuration, signed authority, local state, and Canvas
classification data. It must not start Codex, send email, upload/submit work,
answer a quiz, acquire a persistent lock, or call Task Scheduler mutation
commands. `--dry-run` and `--os-trigger` are mutually exclusive.

For autonomous instances, dry run still validates the durable receipt. A
missing, expired, tampered, or mismatched receipt is a failed gate.

## 7. Optional OS-chain proof and enable

An OS-trigger test is a real trigger. For an autonomous instance it may submit
work. Run it only when the exact authorization in §4 included the immediate
test, or after obtaining a separate explicit confirmation:

```powershell
python scripts/canvas_cron.py fire <instance> --os-trigger
```

Accept only Task Scheduler success/running results documented by the CLI. On
failure, the CLI re-disables the task and returns non-zero. If no immediate
test is authorized, leave the task disabled and ask before enabling it.

Enable only after all applicable gates pass:

```powershell
python scripts/canvas_cron.py enable <instance>
```

`enable` revalidates autonomous authority. Report the returned task state and
next run time.

## Runtime guarantees to verify

- Fresh agent work launches through `src.codex_runner.run_codex`.
- `scan_pending` invokes only `canvas-scan` and stops before execution.
- Autonomous fire validates durable authority before the Canvas health probe
  and before starting Codex.
- The fresh Codex turn revalidates the durable receipt, uses its actual
  `CODEX_THREAD_ID`, and mints only short-lived target-exact per-item receipts
  for already delegated actions.
- Missing authority, Canvas auth/probe failure, Codex non-zero/timeout, and
  post-action verification failure all return non-zero.
- A successful process code does not claim assignment correctness; it only
  means the authorized action and readback verification completed.

## Hard rules

- Never put real course/account/recipient data in tracked files or examples.
- Never store durable receipts outside `_private/` or expose their content.
- Never let cron self-authorize or widen receipt actions/targets.
- Never give the scan template mutation authority.
- Never call Task Scheduler mutation commands during dry run.
- Never force-fire outside an explicitly authorized install/test operation.
- Never continue past a failed gate.
- Never submit to a real Canvas origin unless that exact scheduled workflow is
  explicitly authorized. Synthetic QA authority is not valid for durable cron.
