# SPDX-License-Identifier: AGPL-3.0-or-later
"""Port a Claude course skill to a Codex skill (.claude/skills -> .agents/skills).

Mechanical transform that preserves all hard-won logic:
  1. Strip Claude-only frontmatter keys (`allowed-tools:`, `tools:` + their
     indented list items). Keep `name`, `description`, anything else.
  2. Insert a single "Codex port note" right after the frontmatter that
     translates every Claude-ism uniformly (ad-hoc parallel subagents,
     pre-submit-reviewer toml, cross-skill invocation, tool names, hooks,
     overlay path).
  3. Body is copied verbatim — the pipeline logic is driver-agnostic.

Why a port note instead of rewriting the body: the subagent spawn idiom
`Agent(subagent_type="general-purpose")` maps 1:1 to Codex ad-hoc parallel
subagents (verified 2026-06-14), so the body's meaning carries; the note
removes ambiguity without risking the logic.

Usage:
  python scripts/port_skill_to_codex.py <skill-name> [<skill-name> ...]
  python scripts/port_skill_to_codex.py --all
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / ".claude" / "skills"
DST = ROOT / ".agents" / "skills"

HOMEWORK_SKILLS = [
    "canvas-ics33",
    "canvas-inside",
    "canvas-zybooks",
    "canvas-essay",
    "canvas-reading-annotation",
    "canvas-generic",
    "canvas-humanizer",
    "canvas-humanizer-loop",
    "canvas-humanizer-surgical",
    "canvas-awkward-syntax",
]

DROP_KEYS = ("allowed-tools:", "tools:")


def port_note(name: str) -> str:
    return f"""> **Codex port note** — auto-ported from `.claude/skills/{name}/SKILL.md` (2026-06-14).
> Read the Claude-isms below through this lens; the pipeline logic is unchanged and driver-agnostic:
> - **Subagents**: any `Agent(subagent_type="general-purpose")` / "spawn ... via the Agent tool" =
>   Codex **ad-hoc parallel subagents** — spawn them in parallel with the inline role prompts as written,
>   wait for all, collect results (verified working; `agents.max_threads` default 6, raise if you need more).
> - **`pre-submit-reviewer`** = the predefined Codex subagent `.codex/agents/pre-submit-reviewer.toml`.
> - **Cross-skill calls** ("via the Skill tool", invoke `canvas-humanizer`, hand off to `canvas-bootstrap`)
>   = invoke the Codex skill of the same name under `.agents/skills/`.
> - **Tool names** (Read/Write/Edit/Bash/Glob/Grep/WebFetch) = use Codex's equivalent native tools.
> - **Hooks** named (PreToolUse/PostToolUse/Stop guards) are enforced by `.codex/hooks/`; see
>   `docs/CODEX_HOOK_PARITY.md` for current coverage/gaps.
> - **Overlay** `_private/canvas-*-app.md` path is unchanged (gitignored, driver-agnostic).
> - **`src/*.py`** primitives are shared as-is (driver-agnostic).
"""


def strip_frontmatter_tool_keys(fm_lines: list[str]) -> list[str]:
    """Drop `allowed-tools:` / `tools:` keys and their indented list items."""
    out: list[str] = []
    skipping = False
    for line in fm_lines:
        stripped = line.strip()
        if any(stripped.startswith(k) for k in DROP_KEYS):
            skipping = True
            continue
        if skipping:
            # indented list item or continuation -> still part of the dropped key
            if line.startswith((" ", "\t")) or stripped.startswith("- "):
                continue
            skipping = False
        out.append(line)
    return out


def port(name: str) -> str:
    src = SRC / name / "SKILL.md"
    if not src.exists():
        return f"SKIP {name}: source not found at {src.relative_to(ROOT)}"
    text = src.read_text(encoding="utf-8")
    lines = text.splitlines()

    # Frontmatter: first block delimited by --- ... ---
    if lines and lines[0].strip() == "---":
        end = None
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                end = i
                break
        if end is None:
            return f"SKIP {name}: unterminated frontmatter"
        fm = lines[1:end]
        body = lines[end + 1:]
    else:
        return f"SKIP {name}: no frontmatter"

    fm = strip_frontmatter_tool_keys(fm)
    new = ["---", *fm, "---", "", port_note(name).rstrip(), "", *body]
    out_path = DST / name / "SKILL.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(new) + "\n", encoding="utf-8")
    return f"OK   {name}: {len(body)} body lines -> {out_path.relative_to(ROOT)}"


def main(argv: list[str]) -> int:
    targets = HOMEWORK_SKILLS if (not argv or argv[0] == "--all") else argv
    for t in targets:
        print(port(t))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
