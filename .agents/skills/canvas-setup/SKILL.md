---
name: canvas-setup
description: Public-safe Codex setup workflow for first-run Canvas Pilot configuration. Use when .env is missing, Canvas host/auth settings are incomplete, routes are empty, canvas-scan cannot proceed because setup state is missing, or the user asks to set up Canvas Pilot. Detect setup state, collect only minimal user-facing inputs, write local config through tools when safe, verify auth with project probes, hand off to canvas-bootstrap for route creation, and stop before scanning or executing assignments.
---

# Canvas Setup

Prepare Canvas Pilot for later `canvas-scan`. This skill is a setup workflow,
not a course playbook and not an assignment runner.

## Boundary

- Do not scan assignments.
- Do not execute assignments.
- Do not submit, upload, answer quizzes, or call live assignment actions.
- Do not write `assignments.json`, `plan.json`, `result.json`, or `REPORT.md`.
- Do not write course-specific playbooks.
- Do not copy private IDs, real course names, instructor names, emails, or
  private URLs into generated docs or skills.
- Keep `.claude/` read-only.

## Setup State Matrix

Classify the repo before doing anything else:

| State | Signals | Action | Stop condition |
|---|---|---|---|
| missing-env | `.env` missing | Ask for generic Canvas host and preferred auth path; create local config through tools when values are provided. | Stop after config write or when input is needed. |
| incomplete-canvas-config | `.env` exists but Canvas base/auth fields are incomplete | Ask only for the missing domain-level value or auth choice; update local config through tools. | Stop after config write or when input is needed. |
| auth-configured-empty-routes | auth config exists and `courses.yaml` has no usable routes | Verify auth probe if available, then hand off to `canvas-bootstrap`. | Stop after bootstrap handoff. |
| complete | Canvas base/auth and routes are present | Report that setup is complete and the next user action is `canvas-scan`. | Stop without scanning. |

Use existing project conventions for config names. Prefer generic labels such
as Canvas host, base URL, auth mode, API token path, and cookie path. Do not
invent private course identifiers.

## Student-Facing Contract

Ask the student only domain questions:

- Canvas host, expressed as a generic school Canvas URL.
- Whether they want an API-token path or a browser/cookie path when both are
  supported.
- Confirmation that browser login or token entry is complete.

Do not tell the student to edit `.env`, run shell commands, inspect internal config files, or find route files. Codex should perform local file edits and safe setup commands when the needed values are available.

In user-facing text, say what value is needed and why. Do not mention internal
file names unless the user explicitly asks for implementation details.

## Workflow

1. Read `AGENTS.md`.
2. Inspect setup state using local files only:
   - `.env`
   - `courses.yaml`
   - any public-safe sample config or documented project probe
3. Classify the state with the setup matrix.
4. If required values are missing, ask the user for only those values and stop.
5. If values are available, update local config with the smallest needed edit.
6. If a project auth probe exists, run it in probe mode only.
7. If auth is configured but routes are empty, invoke `canvas-bootstrap`.
8. If setup is complete, stop and tell the user to run `canvas-scan`.

## Safe Tooling

Use probe commands only when they are already present in the project docs or
scripts. Probe commands may validate auth or config shape, but must not scan
assignments, submit work, upload files, answer quizzes, or create run results.

If a probe fails because credentials are missing or expired, report the missing
setup state and stop.

## Outputs

Allowed outputs:

- local config edits when the user provides the needed values
- a setup status message
- a handoff to `canvas-bootstrap`

Forbidden outputs:

- `assignments.json`
- `plan.json`
- `result.json`
- `REPORT.md`
- course-specific skill bodies
- live Canvas submissions or quiz attempts

## Verification Targets

`python scripts\codex_check.py --batch B12` must prove:

- missing `.env` routes to setup
- incomplete Canvas config routes to setup
- auth configured with empty routes routes to `canvas-bootstrap`
- complete setup stops before scan and names `canvas-scan` only as the next
  user action
- student-facing instructions avoid manual `.env` editing and shell commands
- fixture tests are offline and contain no private identifiers
