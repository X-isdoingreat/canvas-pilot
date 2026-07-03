# Codex Hook Test Design

This document designs the future hook test suite. It does not require hooks to exist yet.

## Test Harness Shape

Future command pattern:

```powershell
Get-Content fixtures\event.json | python .codex\hooks\post_tool_guard.py
```

Each hook test should assert:

- exit code
- stdout JSON shape when applicable
- stderr message when exit code 2 is used
- no unhandled traceback
- no modification of `.claude/`

## Planned Tests

### H1 SessionStart adds context

Input:
- `SessionStart` fixture with `source=startup`.

Pass:
- returns extra context mentioning Codex sidecar and scan/approval/execute boundary.

### H2 PreToolUse blocks unsafe upstream push

Input:
- `PreToolUse` Bash fixture with `git push upstream main`.

Pass:
- denies permission with a public/private boundary reason.

### H3 PreToolUse allows harmless command

Input:
- `PreToolUse` Bash fixture with `python -m src.router --dry-run`.

Pass:
- exits 0 with no deny decision.

### H4 PostToolUse blocks invalid result

Input:
- event indicating a result file was written.
- test fixture writes invalid `runs/test/bad/result.json`.

Pass:
- blocks and explains schema failure.

### H5 Stop continues incomplete execute session

Input:
- `.scan_in_progress` marker exists.
- `assignments.json` lists one item.
- matching result file is missing.

Pass:
- Stop returns block/continue reason.

### H6 Stop releases non-execute session

Input:
- no `.scan_in_progress` marker.

Pass:
- exits 0 / continues normally.

### H7 Hook internal error fails open

Input:
- malformed or missing expected fields.

Pass:
- exits 0 and writes `.codex/hooks/hook-errors.log`.

