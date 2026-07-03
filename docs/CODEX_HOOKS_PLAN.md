# Codex Hooks Plan

This document designs the Codex hook layer before any hook code is written.

## Official Constraints

Verified from the current Codex docs on 2026-04-29:

- Hooks require `[features] codex_hooks = true`.
- Codex can load repo-local hooks from `<repo>/.codex/hooks.json` or `<repo>/.codex/config.toml`.
- If multiple matching hooks exist, they all run.
- Multiple matching command hooks for one event are launched concurrently.
- `SessionStart` plain stdout can become extra context.
- `PreToolUse` can intercept some tools but is a guardrail, not a complete enforcement boundary.
- `PostToolUse` can provide feedback after tool execution.
- `Stop` can make Codex continue by returning a blocking decision or exit code 2.

## Design Rules

1. Prefer `.codex/hooks.json` over inline TOML for this repo.
2. Register exactly one command hook per event in v0.
3. Put sequential checks inside the hook script, not in multiple concurrent hook registrations.
4. Every hook must fail open on internal exceptions and log to `.codex/hooks/hook-errors.log`.
5. Hook scripts must parse Codex event JSON, not Claude Code event JSON.
6. Hooks must not import from `.claude/hooks`.
7. Hooks must not modify `.claude/`.
8. Hooks must not contain private identity or real course identifiers.

## Event Map

| Codex event | v0 script | Purpose |
|---|---|---|
| `SessionStart` | `.codex/hooks/session_start.py` | Add pending/driver context |
| `PreToolUse` | `.codex/hooks/pre_tool_guard.py` | Guard dangerous commands and public leaks |
| `PostToolUse` | `.codex/hooks/post_tool_guard.py` | Validate `result.json` after writes |
| `Stop` | `.codex/hooks/stop_guard.py` | Continue if execute-mode work is incomplete |

## Output Strategy

| Event | Pass | Block / continue |
|---|---|---|
| `SessionStart` | stdout plain text or JSON context | pass unless script itself fails |
| `PreToolUse` | exit 0 no output | JSON deny decision or exit 2 |
| `PostToolUse` | exit 0 no output | JSON block decision or exit 2 |
| `Stop` | JSON `{ "continue": true }` | JSON block decision or exit 2 |

## v0 Guard Scope

Implement only:

- session context summary
- obvious dangerous command guard
- public/private leak guard for Codex-side files
- `result.json` schema validation
- execute marker / missing result stop guard

Do not implement yet:

- full private course pre-submit gate
- spec grounding
- identifier grounding
- bash output coverage/backdate policy
- private course-specific behavior

