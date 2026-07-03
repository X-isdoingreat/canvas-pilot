# Codex Driver Plan

## Goal

Build a Codex sidecar driver for canvas-pilot without changing the existing Claude Code production driver.

The first usable version should let a Codex user understand the workflow, discover the Codex skills, preserve the scan/approval/execute boundary, and run self-checks that prove the sidecar did not pollute the Claude path.

## Non-Goals

- Do not replace Claude Code.
- Do not refactor `.claude/`.
- Do not migrate private course-specific skills in v0.
- Do not promise full hook parity with Claude Code until it is tested.
- Do not put personal identity, real school identifiers, course IDs, instructor names, or emails in Codex repo-level docs.

## Architecture

Two drivers live in one repo:

```text
Claude Code driver
  CLAUDE.md
  .claude/settings.json
  .claude/hooks/
  .claude/skills/

Codex driver
  AGENTS.md
  .agents/skills/
  .codex/          # future hooks/config
  plugins/         # future plugin packaging
```

Shared state files:

```text
runs/<today>/plan.json
runs/<today>/assignments.json
runs/<today>/<slug>/result.json
runs/<today>/REPORT.md
runs/_processed.json
final_drafts/
```

## Phases

### Phase 1: Documentation and Self-Check Harness

Create Codex-specific planning, task, acceptance, regression, and test protocol docs.

Success:
- Codex plan exists.
- Validation sets are command-backed.
- Private identity keyword checks pass.
- `.claude/` is not touched by Codex work.

### Phase 2: Repo Skill Skeletons

Create instruction-only Codex repo skills:

```text
.agents/skills/canvas-scan/SKILL.md
.agents/skills/canvas-execute/SKILL.md
.agents/skills/canvas-skip/SKILL.md
```

Success:
- Each skill has `name` and `description` frontmatter.
- Each skill explicitly preserves scan/approval/execute boundaries.
- No private course-specific skills are migrated.

### Phase 3A: Codex Hook Design

Design Codex hooks only after Phase 1/2 pass.

Verified official constraints as of 2026-04-29:

- Hooks are behind `[features] codex_hooks = true`.
- Codex discovers hooks in `hooks.json` or inline `[hooks]` tables in `config.toml`.
- Useful repo-local locations include `<repo>/.codex/hooks.json` and `<repo>/.codex/config.toml`.
- Matching hooks from multiple files all run; multiple matching command hooks for the same event launch concurrently.
- `SessionStart` can add extra context.
- `PreToolUse` is a guardrail, not a complete enforcement boundary.
- `PostToolUse` can block/replace tool output after a tool has run.
- `Stop` can tell Codex to continue.

Official references:

- https://developers.openai.com/codex/hooks
- https://developers.openai.com/codex/skills
- https://developers.openai.com/codex/guides/agents-md

Design choice:

- Use `hooks.json`, not inline TOML, for hook registration.
- Use one command hook per event and do sequential checks inside the script.
- Do not implement hooks until the design acceptance checks pass.

Candidate config:

```text
.codex/hooks.json
.codex/hooks/session_start.py
.codex/hooks/pre_tool_guard.py
.codex/hooks/post_tool_guard.py
.codex/hooks/stop_guard.py
```

### Phase 3B: Codex Hook Implementation

Add Codex hooks after Phase 3A design passes.

Candidate files:

```text
.codex/hooks.json
.codex/hooks/session_start.py
.codex/hooks/pre_tool_guard.py
.codex/hooks/post_tool_guard.py
.codex/hooks/stop_guard.py
```

Success:
- Hooks parse Codex event shape.
- Hooks fail open on internal errors.
- Basic result schema and stop checks work.
- Claude hooks remain untouched.

### Phase 4: Optional Plugin Packaging

If repo skills work, package them as a local Codex plugin:

```text
plugins/canvas-pilot-codex/.codex-plugin/plugin.json
plugins/canvas-pilot-codex/skills/
```

Success:
- Plugin manifest points to bundled skills.
- Repo skill and plugin skill behavior are not allowed to drift silently.

## Current Scope

This implementation pass covers Phase 1 and Phase 2 only.
