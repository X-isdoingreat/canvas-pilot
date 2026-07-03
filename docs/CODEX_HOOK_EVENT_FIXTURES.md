# Codex Hook Event Fixtures

These are design fixtures for future hook tests. They document expected input and output shapes before implementation.

## SessionStart Input

```json
{
  "session_id": "test-session",
  "transcript_path": null,
  "cwd": "C:/repo",
  "hook_event_name": "SessionStart",
  "model": "gpt-test",
  "source": "startup"
}
```

Expected pass output:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "Codex sidecar driver active. Preserve scan/approval/execute boundaries."
  }
}
```

## PreToolUse Bash Input

```json
{
  "session_id": "test-session",
  "cwd": "C:/repo",
  "hook_event_name": "PreToolUse",
  "model": "gpt-test",
  "turn_id": "turn-1",
  "tool_name": "Bash",
  "tool_use_id": "tool-1",
  "tool_input": {
    "command": "git push upstream main"
  }
}
```

Expected deny output:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "Refuse upstream push until public/private boundary checks pass."
  }
}
```

## PostToolUse apply_patch Input

```json
{
  "session_id": "test-session",
  "cwd": "C:/repo",
  "hook_event_name": "PostToolUse",
  "model": "gpt-test",
  "turn_id": "turn-1",
  "tool_name": "apply_patch",
  "tool_use_id": "tool-2",
  "tool_input": {
    "command": "*** Begin Patch..."
  },
  "tool_response": {}
}
```

Expected block output when a `runs/.../result.json` schema is invalid:

```json
{
  "decision": "block",
  "reason": "Invalid result.json schema. Fix it before continuing.",
  "hookSpecificOutput": {
    "hookEventName": "PostToolUse",
    "additionalContext": "Every assignment needs a valid result.json."
  }
}
```

## Stop Input

```json
{
  "session_id": "test-session",
  "cwd": "C:/repo",
  "hook_event_name": "Stop",
  "model": "gpt-test",
  "turn_id": "turn-1",
  "stop_hook_active": false,
  "last_assistant_message": "Done."
}
```

Expected block output when execute-mode work is incomplete:

```json
{
  "decision": "block",
  "reason": "Session cannot stop: one or more approved assignments are missing result.json."
}
```

