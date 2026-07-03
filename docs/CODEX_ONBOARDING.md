# Codex Student Onboarding

This guide is for a new student using the Codex sidecar.

## Goal

Set up Canvas access, verify it works, then run the safe draft-only workflow:

```text
auth setup -> canvas-bootstrap -> canvas-scan -> approval -> canvas-execute
```

## Auth setup

1. Copy `.env.example` to `.env`.
2. Set:
   ```text
   CANVAS_AUTH=cookie
   CANVAS_BASE=<your Canvas base URL>
   CANVAS_WEB_BASE=<your Canvas web URL, no /api/v1>
   ```
3. Capture browser cookies:
   ```powershell
   python -m src.canvas_login --auto
   ```
4. Verify:
   ```powershell
   python -m src.canvas_client --probe
   ```

If the session expires, rerun the browser login command.

## First Run

Run bootstrap first if routes are empty:

```text
Use canvas-bootstrap to set up course skills.
```

Then scan:

```text
Use canvas-scan to check what is due.
```

Then approve specific items:

```text
approve 1,3
```

## Safety Defaults

- Draft-only by default.
- No Canvas submission by default.
- No live quiz submission by default.
- Private course IDs, assignment IDs, private URLs, names, and emails belong in
  local config, not tracked Codex docs.
