---
name: canvas-setup
description: Use for first-run Canvas Pilot configuration or recovery when the Canvas host, local runtime, authentication, or route setup is incomplete. It performs the mechanical setup, verifies authentication, then hands empty-route installs to canvas-skill-opportunity and stops.
---

# Canvas Setup

Set up or repair Canvas Pilot without turning setup into a technical tutorial.
The student supplies only facts that Codex cannot discover and completes one
normal browser login when needed. Codex performs local checks, installs,
configuration edits, and verification itself.

Setup is not a scan or assignment workflow. It must never inspect pending
assignments, create a plan, draft work, start a quiz attempt, upload, or submit.

## Non-negotiable boundary

- Keep `.claude/` read-only. It is frozen legacy history, not an active setup
  surface.
- Do not scan assignments.
- Do not execute assignments.
- Do not submit, upload, or answer quizzes.
- Do not write `assignments.json`, `plan.json`, `result.json`, `REPORT.md`, or
  `.scan_in_progress`.
- Do not write `assignments.json`, `plan.json`, `result.json`, or `REPORT.md`.
- Do not create a course skill or route directly from setup.
- Successful authentication with empty routes hands off to
  `canvas-skill-opportunity`; that skill performs read-only evidence review and
  **stops for the student's numbered choice**. Only a later, separate
  `canvas-bootstrap` invocation may create one selected skill and route.
  The student's choice comes before any later `canvas-bootstrap` handoff.
- Authentication is not assignment approval. It grants no authority to start,
  answer, or complete a quiz, upload a file, or submit an assignment.
- Never copy a private identity, school, account, credential, course identifier,
  teaching-staff details, email, or private URL into a tracked file or public message.

## Student experience

Open with the value in the language the student used:

> I’ll connect Canvas, find recurring work worth automating, and show you the
> evidence before any course skill is created. Drafting and submission remain
> separate approvals. Want to start?

After consent, ask one domain question per turn. For an unconfigured install,
the first question is:

> Which school do you use Canvas through?

Ask the student only domain questions. School name first; use the Canvas login
URL only as the ambiguity fallback.

Use the answer to discover the school's official Canvas login host. Search the
public web when necessary and verify the candidate host has a Canvas/Instructure
login signature. If no single official host can be established, ask for the
Canvas login-page URL. Never guess a host from a school name. Normalize only to
the origin (`https://host`) and derive the API base from that origin.

Do not tell the student to edit `.env`, run shell commands, inspect internal config files,
install a package, find a token menu, inspect a cookie, or copy internal IDs.
Do those mechanical tasks with local tools. Keep internal
vocabulary out of ordinary student-facing messages unless the student
explicitly asks for implementation details.

Before a browser login, say that a local browser window will open and that the
student should sign in normally, including SSO/2FA. Explain that the default
stores a local browser session but does not save the username/password. Do not
ask the student to paste credentials into chat.

For an operation likely to exceed 30 seconds, give one time estimate and report
only meaningful numeric progress. Do not emit repeated “still waiting” updates
when nothing changed.

## Resume from observed state

Inspect the filesystem before asking anything. Never ask “where did we leave
off?” when the answer is local.

| Observed state | Resume action |
|---|---|
| `.env` missing or Canvas host empty | Ask school first; ask for the login URL only if official-host resolution is ambiguous. |
| Host present, runtime dependency missing | Install/repair the isolated runtime silently, then continue. |
| Browser auth configured but no usable local session | Explain the browser popup, run login/probe, and continue only on verified success. |
| Token auth already configured deliberately | Preserve the token mode and token value; probe it without advertising or rewriting it. |
| Auth probe fails as expired/unauthorized | Re-enter the matching browser or token recovery path; do not proceed to opportunity analysis. |
| Auth works, `courses.yaml` missing | Create a minimal local config with the configured pending window and `routes: {}`. |
| Auth works, routes empty/null | Hand off to `canvas-skill-opportunity`, then stop. |
| Auth works, routes non-empty | Report setup complete; name `canvas-scan` as the next user action and stop. |

If the student explicitly asks to redo setup, first ask which material fact
changed (school/host, authentication, or routes). Preserve unrelated working
configuration. Never silently replace a working configuration or delete a
browser profile.

## Deterministic workflow

### 1. Inspect, classify, and preserve

Read `AGENTS.md`, `.env` if present, `courses.yaml` if present, tracked setup
examples, and the documented probe entry point. Preserve all non-Canvas keys in
`.env`. Preserve an existing deliberate token mode and token value. Treat
`routes: null` as an empty mapping.

Classify the install as one of:

1. `host_missing`
2. `runtime_missing`
3. `authentication_missing_or_expired`
4. `authenticated_empty_routes`
5. `ready`

Compatibility names used by older checks map as follows: `missing-env` and
`incomplete-canvas-config` are pre-auth states;
`auth-configured-empty-routes` is `authenticated_empty_routes`; `complete` is
`ready`. These are state labels only, not alternate workflows.

Perform only the steps needed to advance that state. A failure stops at the
state it actually reached; never announce readiness from configuration shape
alone.

### 2. Resolve and write the Canvas host

After the official login origin is verified, update only the relevant Canvas
host fields atomically. Preserve unrelated environment settings. Do not put the
school name or host into tracked docs, skills, examples, or tests.

The default authentication path is local browser/session auth. Token auth is an
advanced recovery path only when the project supports it and the student
chooses it or already configured it. Never expose a token in command output or
chat.

### 3. Prepare the local runtime

Use an isolated Python environment. A repo-local `.venv/` is acceptable only
after confirming it is gitignored. Install tracked requirements and the matching
browser component with the active interpreter; on Windows use full paths and
UTF-8 output. Bundle dependent install steps so a failed prerequisite stops the
sequence.

The interpreter-equivalent commands are:

```text
python -m pip install -r requirements.txt
python -m playwright install chromium
```

Before installing, run a bounded import-and-browser-launch check. Skip install
silently when the check passes. If installation fails, retain the real failure
in a private local log, translate it into plain language, and offer one retry.

### 4. Protect credentials and authenticate

Keep `CANVAS_REMEMBER_CREDENTIALS=false` unless the student explicitly opts in
to password autofill. For opt-in storage, continue only when the project's
credential helper reports a protected method such as DPAPI or Fernet. Base64
obfuscation is not protected storage and must never be used for a new secret.
Probe the configured method through `canvas_credentials._pick_method()`.
Never write new credentials with base64 obfuscation.

For the default browser path:

1. tell the student the browser is about to open;
2. run `python -m src.canvas_client --probe` with the isolated interpreter;
3. let the student complete normal SSO/2FA in the browser;
4. after success, use `python -m src.canvas_client --forget-credentials` to
   remove any legacy opt-in username/password record;
5. verify `has_stored_credentials()` is false;
6. probe once more and continue only if the retained local browser session still
   authenticates.

For an existing token path, run only the auth probe and preserve the token.

Classify failures without dumping a traceback:

- unauthorized/expired: recover authentication;
- login timeout: ask whether the browser failed to open or login was blocked;
- network/browser-engine failure: offer one retry after the connection works;
- unknown: show a short sanitized detail and stop for direction.

An auth probe may validate identity and connectivity only. It must not list
assignments or perform any Canvas mutation.

### 5. Create or preserve empty route configuration

If authentication works and `courses.yaml` is missing, atomically create the
minimal local configuration expected by the current router, including
`pending_window_days` and `routes: {}`. If it exists, preserve every existing
route and unrelated key. Never replace non-empty routes during recovery.

### 6. Opportunity handoff and hard stop

When authentication is verified and routes are empty, invoke
`canvas-skill-opportunity` with this intent:

> Authentication is verified and routes are empty. Inspect recurring
> candidates read-only, inspect representative real specifications and safe
> feedback-policy projections, write the private opportunity report, show only
> numbered aliases in chat, and stop for the student's choice.

After that handoff returns, **stop setup**. Do not scan pending work, do not call
`canvas-bootstrap`, and do not create a route in the same turn.

When routes are already non-empty, say setup is ready and that `canvas-scan` is
the next action. Stop without invoking scan.

## Verification checklist

Before reporting success, verify:

- the official Canvas origin was established rather than guessed;
- local configuration is syntactically valid and preserves unrelated keys;
- the active auth probe succeeded in the current process environment;
- default browser auth has no persisted username/password record;
- route configuration is either intentionally empty or already populated;
- empty routes went to `canvas-skill-opportunity`, not directly to bootstrap;
- no assignment snapshot, plan, result, report, marker, quiz attempt, upload, or
  submission was created.
