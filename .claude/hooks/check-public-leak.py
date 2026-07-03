# SPDX-License-Identifier: AGPL-3.0-or-later
"""PreToolUse(Bash) hook for single-repo mode.

This project ships under one anonymous public repo (X-isdoingreat/Canvas_pilot).
Anything tracked in git is destined for the public mirror, so any school
identity marker in a tracked file's diff is a leak. This hook
fires on `git add`, `git commit`, `git push` and blocks the operation
when a forbidden literal appears in any new line of any non-gitignored
file's diff.

Historical: this hook used to enforce a two-repo split (origin private /
upstream public) and carry a PRIVATE_ONLY_PATHS list of files that must
never reach upstream. After 2026-05-14 the project repointed to one
anonymous repo with a gitignored `_private/` overlay, so the
PRIVATE_ONLY_PATHS layer collapsed into plain `.gitignore` and this hook
became a single-stage keyword guard.

Patterns are masked with regex char-class tricks so the source of this
file does not itself trigger the gate its compiled regex enforces. The
literal sensitive substrings never appear in this source.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import ROOT, block, passthrough, read_event, safe_main  # noqa: E402


# Forbidden literals that must not enter any tracked file's diff.
# Each pattern uses a regex char-class so the source text below does
# NOT contain a substring matching its compiled regex — preventing the
# hook from blocking its own source.
STATIC_FORBIDDEN = [
    r"\b[U]CI\b",
    r"\b[x]ianzh",
    r"\b[X]ianzhi\b",
    r"\b[S]triedter\b",
    r"\b[A]c\s+[E]ng\s+\d+\w?\b",
    # Broader course-code shapes: the code-dept prefix + space/underscore +
    # number ("ICS_NN"), the bare [I]NTL prefix, and the writing-course code as
    # "[A]C [E]NG" (spaced) or "[A]C_[E]NG_<digit>" (underscored). Example
    # literals char-classed so neither this source NOR the push_public_snapshot
    # audit (which ships + scans this file) self-triggers. Crafted to PASS
    # framework identifiers (see whitelist note below): the code prefix needs a
    # space/underscore before the digit (so "ics33" passes); the writing code
    # needs a SPACE or an underscore FOLLOWED BY A DIGIT (so "ac_eng_router" /
    # "ac_english" pass).
    r"\b[I]CS[ _]\d",
    r"\b[I]NTL\b",
    r"\b[A]C [E]NG|\b[A]C_[E]NG_\d",
    r"[献]之",
    r"canvas\.eee\.[u]ci\.edu",
    r"\.eee\.[u]ci",
    r"[x]ianzhh2@[u]ci",
    r"[t]ao\.for\.luv",
    # Note: per-course skill names (canvas-ics33, canvas-reading-annotation,
    # canvas-zybooks, canvas-inside) AND the writing-course routing/util
    # identifiers (ac_eng_router, ac_eng_verify, ac_english,
    # route_ac_eng_assignment, ACEnglishSkill) are framework-level identifiers
    # that ship to fork users; they are intentionally NOT matched by the
    # course-code patterns above (no separator before the digit / a letter
    # after ENG), and not listed in STATIC_FORBIDDEN.
    # School-email domain
    r"@[u]ci\.edu",
    # Anti-deflection vocabulary — keywords that shouldn't appear in tracked
    # files. Each pattern char-classed so this source doesn't trigger itself.
    r"\b[f]orensic\b",
    r"\b[a]nti.?detection\b",
    r"\b[d]etection\s+[e]vasion\b",
    r"\b[e]vasion\b",
    # Note: \bfingerprint\b previously banned, removed 2026-05-15 — overloaded
    # technical term (course / file / TLS fingerprint protection are all
    # legitimate uses). More specific patterns above cover the bad cases.
    r"\b[a]dmin.{0,10}analytics\b",
    r"[p]age_view\s+shape",
    r"\b[p]recursor\s+[p]age_view\b",
]


def _course_id_patterns() -> list[str]:
    """Pull real course IDs from `_private/courses.yaml`. If missing,
    log a warning and return empty list (rather than silently dropping
    the check, so the user notices)."""
    out: list[str] = []
    # courses.yaml lives at repo root (gitignored); older layout had it under
    # _private/. Check root first, then fall back, so the course-id guard
    # actually loads IDs instead of silently no-opping.
    p = ROOT / "courses.yaml"
    if not p.exists():
        p = ROOT / "_private" / "courses.yaml"
    if not p.exists():
        log = ROOT / ".claude" / "hooks" / "hook-errors.log"
        try:
            log.parent.mkdir(parents=True, exist_ok=True)
            with open(log, "a", encoding="utf-8") as f:
                f.write(
                    "[check-public-leak] _private/courses.yaml missing — "
                    "course-id patterns not loaded. The keyword scan still runs.\n"
                )
        except OSError:
            pass
        return out
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return out
    in_routes = False
    for line in text.splitlines():
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        if line.rstrip() == "routes:":
            in_routes = True
            continue
        if in_routes:
            if not line.startswith(" "):
                in_routes = False
                continue
            m = re.match(r"^\s{2}(\d{4,15}):\s*$", line)
            if m:
                out.append(rf"\b{re.escape(m.group(1))}\b")
    return out


def _git(args: list[str]) -> str:
    """Run a git command, return stdout. Empty string on any failure."""
    try:
        r = subprocess.run(
            ["git", *args],
            cwd=str(ROOT),
            capture_output=True,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    if r.returncode != 0:
        return ""
    return r.stdout.decode("utf-8", errors="replace")


def _parse_added_lines_per_file(diff: str) -> dict[str, list[str]]:
    """Parse a `git diff` output into {filepath: [lines added (without '+')]}.
    Only content lines starting with '+' are kept; '+++ b/...' headers and
    '++' diff context markers are excluded."""
    by_file: dict[str, list[str]] = {}
    current: str | None = None
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            parts = line.split(" b/", 1)
            current = parts[1] if len(parts) > 1 else None
            if current:
                by_file.setdefault(current, [])
            continue
        if current is None:
            continue
        if line.startswith("+++ "):
            continue
        if line.startswith("+") and not line.startswith("++"):
            by_file[current].append(line[1:])
    return by_file


def _scan(text: str, patterns: list[str]) -> list[str]:
    hits: list[str] = []
    seen: set[str] = set()
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m and m.group(0) not in seen:
            hits.append(m.group(0))
            seen.add(m.group(0))
            if len(hits) >= 3:
                break
    return hits


def _diff_for_command(cmdl: str) -> str:
    """Return the relevant diff text given the git operation type."""
    if "git commit" in cmdl:
        # `--cached` shows what's about to be committed.
        # If `-a` / `--all` is passed, commit also sweeps tracked changes
        # so widen the scope to all tracked diff vs HEAD.
        if " -a " in f" {cmdl} " or cmdl.endswith(" -a") or " --all" in cmdl:
            return _git(["diff", "HEAD"])
        return _git(["diff", "--cached"])
    if "git push" in cmdl:
        # Diff the commits that would be pushed (upstream..HEAD).
        # Falls back to full HEAD diff if no upstream is set.
        out = _git(["log", "@{u}..HEAD", "-p"])
        if out:
            return out
        return _git(["diff", "HEAD"])
    if "git add" in cmdl:
        return _git(["diff", "HEAD"])
    return ""


@safe_main
def main() -> None:
    event = read_event()
    if not event:
        passthrough()
    if event.get("tool_name") != "Bash":
        passthrough()

    cmd = (event.get("tool_input") or {}).get("command", "") or ""
    cmdl = cmd.lower()

    if not any(p in cmdl for p in ("git add", "git commit", "git push")):
        passthrough()

    diff = _diff_for_command(cmdl)
    if not diff.strip():
        passthrough()

    patterns = STATIC_FORBIDDEN + _course_id_patterns()
    by_file = _parse_added_lines_per_file(diff)

    leaks: list[tuple[str, list[str]]] = []
    for path, added in by_file.items():
        if not added:
            continue
        # Defensive: gitignored paths shouldn't appear in diff at all, but
        # if they somehow do, skip them. _private/ and sources/ are the
        # only gitignored top-level directories we expect.
        if path.startswith("_private/") or path.startswith("sources/"):
            continue
        hits = _scan("\n".join(added), patterns)
        if hits:
            leaks.append((path, hits))

    if leaks:
        op = (
            "git push" if "git push" in cmdl
            else "git commit" if "git commit" in cmdl
            else "git add"
        )
        lines = [
            f"hook check-public-leak: BLOCKED `{op}` — would commit private",
            "markers to a tracked file in the single-repo public release.",
            "Anything tracked is destined for the X-isdoingreat/Canvas_pilot",
            "GitHub mirror; identity / school / course-id literals must not",
            "appear in a tracked file's diff.",
            "",
            "Files + offending markers (max 3 per file shown):",
        ]
        for path, hits in leaks:
            lines.append(f"  {path}:")
            for h in hits:
                lines.append(f"    -> {h!r}")
        lines += [
            "",
            "Fix options:",
            "  (a) Move the content into _private/ (which is gitignored).",
            "  (b) Rewrite the diff to use generic placeholders",
            "      (e.g. <your-canvas-host>, <course_id>, school-agnostic phrasing).",
            "  (c) If you are SURE this commit is acceptable and want to",
            "      bypass once, comment out this matcher in .claude/settings.json",
            "      for this Bash call. Don't make a habit.",
        ]
        block("\n".join(lines))

    passthrough()


if __name__ == "__main__":
    main()
