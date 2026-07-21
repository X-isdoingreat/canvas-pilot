# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared utilities for Canvas Skill hook scripts.

All hook scripts read a JSON event from stdin and exit with:
  0 = pass (Claude continues normally)
  2 = block (stderr is shown to Claude as feedback)

Anything else is treated as a non-blocking error by Claude Code.

CRITICAL SAFETY RULE: hook scripts MUST NEVER raise an unhandled exception
or exit with a non-zero non-2 code. If they do, CC may interpret it as a
block, feed the traceback back to Claude, and Claude will be stuck in a
runaway loop trying to fix something that's actually a hook bug. Wrap your
main() in @safe_main and you'll exit 0 (pass-through) on any internal error.
"""
from __future__ import annotations

import datetime as dt
import functools
import json
import os
import re
import sys
import traceback
from pathlib import Path

# Project root — hooks live in <root>/.claude/hooks/
ROOT = Path(__file__).resolve().parent.parent.parent


def read_event() -> dict:
    """Read the hook event JSON from stdin. Empty stdin → empty dict (so we
    can run scripts manually for testing without piping anything)."""
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"hook: stdin not valid JSON: {e}", file=sys.stderr)
        return {}


def block(message: str) -> None:
    """Exit 2 with a message to stderr — Claude sees this and must respond."""
    print(message, file=sys.stderr)
    sys.exit(2)


def passthrough(message: str | None = None) -> None:
    """Exit 0. Optional message goes to stdout (debug log only, Claude doesn't see it)."""
    if message:
        print(message)
    sys.exit(0)


def safe_main(fn):
    """Decorator: wrap a hook main() so that ANY internal error is caught
    and converted to a passthrough exit 0. This prevents runaway loops where
    a buggy hook script erroring out gets interpreted by CC as a block.

    The full traceback is written to a hook-errors.log file next to this
    module so we can debug after the fact without burning Claude tokens.
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except SystemExit:
            raise  # Let intentional sys.exit() through
        except BaseException as e:
            try:
                log = Path(__file__).resolve().parent / "hook-errors.log"
                with open(log, "a", encoding="utf-8") as f:
                    f.write(f"\n--- {dt.datetime.now().isoformat()} {fn.__name__} ---\n")
                    f.write(traceback.format_exc())
            except Exception:
                pass
            # Always exit 0 to avoid blocking Claude
            print(f"hook safe_main: caught {type(e).__name__}, passing through", file=sys.stderr)
            sys.exit(0)
    return wrapper


def today_dir() -> Path:
    """The runs/<today>/ directory in PT (since cron is PT-anchored)."""
    # Use system local time, which on this Windows machine is PT.
    return ROOT / "runs" / dt.date.today().isoformat()


def project_root() -> Path:
    return ROOT


def is_path_under(p: Path, parent: Path) -> bool:
    try:
        p.resolve().relative_to(parent.resolve())
        return True
    except (ValueError, FileNotFoundError):
        return False


def matches_result_json(file_path: str | None) -> bool:
    """Returns True if the given path looks like a `runs/.../result.json`,
    whether the path is relative (`runs/2026-04-09/foo/result.json`) or
    absolute (`C:/.../Canvas Skill/runs/2026-04-09/foo/result.json`)."""
    if not file_path:
        return False
    p = Path(file_path).as_posix()
    if not p.endswith("/result.json"):
        return False
    return p.startswith("runs/") or "/runs/" in p


# ---- §0 required-sources manifest ----


def overlay_path_for_skill(skill_name: str) -> Path:
    """Resolve the overlay file for one of the framework skills.

    e.g. 'essay' -> _private/canvas-essay-app.md. Generic clusters use a
    different naming scheme (canvas-generic-<course>-<slug>.md); callers that
    need those should pass overlay_path explicitly to load_required_sources.
    """
    return ROOT / "_private" / f"canvas-{skill_name}-app.md"


def _manifest_scope(text: str, course_id) -> str:
    """Text region to search for required_sources yaml block(s).

    Combines the document *preamble* (everything before the first
    ``## Course`` header — where course-AGNOSTIC manifests live, e.g. a
    transcript library shared by the one main course) with the matched
    ``## Course {id}`` block (course-SPECIFIC manifests). A different
    course's block is never included, so course A's query can't pick up
    course B's sources. If the overlay has no ``## Course`` headers at all
    (single-course overlays like essay), the whole document is the scope.
    """
    first = re.search(r"^##\s+Course\s+", text, re.MULTILINE)
    if first is None:
        return text  # no course headers: single-course overlay, whole doc
    preamble = text[:first.start()]
    if course_id in (None, ""):
        return preamble  # no course context: only the course-agnostic part
    cid = re.escape(str(course_id))
    m = re.search(rf"^##\s+Course\s+{cid}\b.*$", text, re.MULTILINE)
    if not m:
        return preamble  # this course not configured: at least the agnostic part
    start = m.end()
    nxt = re.search(r"^##\s+", text[start:], re.MULTILINE)
    block = text[start: start + nxt.start()] if nxt else text[start:]
    return preamble + "\n\n" + block


def load_required_sources(skill_name, course_id, kind, overlay_path=None) -> list[dict]:
    """Parse the §0 required-sources manifest for (skill, course, kind).

    Returns the source dicts whose ``applies_to_kinds`` includes ``kind`` (or
    that declare no ``applies_to_kinds`` / ``"*"``, meaning every kind in the
    course). Returns ``[]`` whenever the overlay, the §0 yaml block, or PyYAML
    is missing/unparseable — callers MUST treat an empty list as "no manifest
    to enforce" so overlays without a §0 yet are non-breaking.

    The §0 block is located as the first fenced ```yaml block (within the
    course's H2 section, if present) whose parsed content has a top-level
    ``required_sources:`` list.
    """
    try:
        import yaml  # type: ignore
    except Exception:
        return []
    overlay_path = Path(overlay_path) if overlay_path else overlay_path_for_skill(str(skill_name))
    if not overlay_path.exists():
        return []
    try:
        text = overlay_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []

    block_text = _manifest_scope(text, course_id)
    # Merge required_sources from EVERY yaml block in scope (preamble + course
    # block), so a course-agnostic source declared once at the top and a
    # course-specific source in the block both apply. Later blocks (the course
    # block) win on id collision. Closing fence must start its own line so a
    # literal ``` inside a quoted value can't truncate early (red-team M2);
    # `[^\n]*` tolerates an info-string after ```yaml (red-team L1).
    merged: dict = {}
    for m in re.finditer(r"```ya?ml[^\n]*\n(.*?)\n```", block_text, re.DOTALL | re.IGNORECASE):
        try:
            parsed = yaml.safe_load(m.group(1))
        except Exception:
            continue
        if isinstance(parsed, dict) and isinstance(parsed.get("required_sources"), list):
            for s in parsed["required_sources"]:
                if isinstance(s, dict) and s.get("id"):
                    merged[s["id"]] = s
    if not merged:
        return []

    out: list[dict] = []
    for s in merged.values():
        kinds = s.get("applies_to_kinds")
        if kinds in (None, [], "*") or (isinstance(kinds, list) and kind in kinds):
            out.append(s)
    return out


# ---- result.json schema ----

VALID_STATUSES = {"draft_ready", "submitted", "skipped", "error"}
REQUIRED_FIELDS = {"status"}


def validate_result_schema(content: str, file_path: Path | None = None) -> tuple[bool, str]:
    """Validate a result.json blob. Returns (ok, error_message)."""
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        return False, f"result.json is not valid JSON: {e}"

    if not isinstance(data, dict):
        return False, f"result.json must be a JSON object, got {type(data).__name__}"

    missing = REQUIRED_FIELDS - data.keys()
    if missing:
        return False, f"result.json missing required fields: {sorted(missing)}"

    status = data.get("status")
    if status not in VALID_STATUSES:
        return False, (
            f"result.json status={status!r} is not one of "
            f"{sorted(VALID_STATUSES)}. Use 'draft_ready' for finished drafts, "
            f"'submitted' for things actually uploaded to Canvas, 'skipped' for "
            f"items intentionally not done, 'error' for failures."
        )

    if status == "draft_ready":
        draft_path = data.get("draft_path")
        if not draft_path:
            return False, (
                "result.json status='draft_ready' but no draft_path field. "
                "Add draft_path pointing to the file the user should upload."
            )
        # Resolve relative to repo root
        candidate = (ROOT / draft_path) if not Path(draft_path).is_absolute() else Path(draft_path)
        if not candidate.exists():
            return False, (
                f"result.json draft_path={draft_path!r} does not exist on disk. "
                f"Either create the file or change status away from 'draft_ready'."
            )

    if status == "submitted":
        # Submitted items should also have a draft_path so the user knows what was submitted
        if not data.get("draft_path") and not data.get("submitted_at"):
            return False, (
                "result.json status='submitted' should have either draft_path or "
                "submitted_at to provide an audit trail."
            )

    # Quiz-specific schema: when kind == "quiz" and status == "submitted",
    # require structural evidence that 4-agent arbitration ran. This is the
    # second of three independent layers preventing the Section 7 bypass
    # (other two: canvas_client._require_canonical_arbitration_evidence and
    # check-router-complete.py §10 retake gate).
    if data.get("kind") == "quiz" and status == "submitted":
        ok, err = _validate_quiz_submitted_schema(data)
        if not ok:
            return False, err

    return True, ""


_QUIZ_REQUIRED_NUMERIC_FIELDS = (
    "kept_score",
    "points_possible",
    "attempts_used",
    "allowed_attempts",
)


def _validate_quiz_submitted_schema(data: dict) -> tuple[bool, str]:
    """Extra checks for result.json with kind=quiz + status=submitted."""
    for f in _QUIZ_REQUIRED_NUMERIC_FIELDS:
        v = data.get(f)
        if not isinstance(v, (int, float)):
            return False, (
                f"quiz result.json missing required numeric field {f!r}. "
                f"Required for status=submitted: kept_score, points_possible, "
                f"attempts_used, allowed_attempts. See SKILL.md §11."
            )

    policy = data.get("scoring_policy")
    if policy not in ("keep_highest", "keep_latest", "keep_average"):
        return False, (
            f"quiz result.json scoring_policy={policy!r} is not one of "
            f"keep_highest / keep_latest / keep_average. Read from "
            f"quiz_meta.json after start_quiz_submission."
        )

    # Either real 4-agent arbitration evidence (agent_passes_count >= 4)
    # OR explicit human authorization for a degraded method (verbatim user quote).
    agent_passes_count = data.get("agent_passes_count")
    consent = data.get("degraded_method_user_consent")

    has_real_arbitration = isinstance(agent_passes_count, int) and agent_passes_count >= 4
    has_user_override = isinstance(consent, str) and len(consent.strip()) >= 10

    if not has_real_arbitration and not has_user_override:
        return False, (
            "quiz result.json status='submitted' requires EITHER "
            "agent_passes_count >= 4 (proves 4-agent arbitration ran) "
            "OR degraded_method_user_consent (verbatim quote of user authorizing "
            "a degraded method, ≥10 chars). The Section 7 bypass on 2026-05-02 "
            "had neither — single-pass with self-stamped 'high' confidence "
            "produced 14/20 vs class median 19. SKILL.md §7 mandates 4-agent."
        )

    # Anti-bulk-question_viewed defense: if human_ness_diagnostics is present,
    # views_paired_with_answers must be true. Bulk-emit is the §8 "smoking gun"
    # that the bypass script triggered.
    diag = data.get("human_ness_diagnostics", {})
    if isinstance(diag, dict) and "views_paired_with_answers" in diag:
        if diag["views_paired_with_answers"] is not True:
            return False, (
                "quiz result.json human_ness_diagnostics.views_paired_with_answers "
                "is not True. SKILL.md §8 Layer 4C: question_viewed events "
                "must be paired with each answer, NOT bulk-emitted at quiz open. "
                "A burst at t=0 is the single most obvious tell on the instructor's "
                "quiz log page."
            )

    return True, ""
