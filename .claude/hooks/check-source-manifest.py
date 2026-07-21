# SPDX-License-Identifier: AGPL-3.0-or-later
"""PostToolUse(Write|Edit) hook: required-source manifest gate.

Second-line defense behind each skill's Stage 0.5. When a result.json is
written with status draft_ready/submitted, verify that every *mandatory*
source declared in the skill's overlay §0 manifest (for this course + kind)
was actually loaded into <work>/sources/, as attested by <work>/sources.json.

The PRIMARY defense is Stage 0.5 in the SKILL.md: it stops before generating
a draft when a mandatory source can't be fetched. This hook catches the case
where that stop was skipped and a draft got announced anyway — so "did we
read the spec/samples/transcripts this course always needs" stops depending
on memory and becomes a gate that can't be forgotten across skills.

Trigger conditions (all must hold):
1. tool_name in {Write, Edit}
2. file_path matches runs/<date>/<work>/result.json
3. result.json loads and status in {draft_ready, submitted}
4. A <work>/sources.json receipt exists

Non-breaking by design: if there is no <work>/sources.json, or the overlay
declares no mandatory manifest for this (skill, course, kind), the hook passes
through. Overlays that haven't been given a §0 yet are unaffected — this lets
the manifest roll out skill-by-skill without breaking the others.

Sibling of check-spec-grounding.py: that one enforces references the spec
*happens to mention*; this one enforces the standing sources the course
*always* needs even when the assignment description never mentions them.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import (  # noqa: E402
    block,
    passthrough,
    read_event,
    safe_main,
    matches_result_json,
    load_required_sources,
)


# Trust model (read before changing the strictness here): this gate's adversary
# is a forgetful/lazy future session, NOT a malicious one (project threat model
# is OSINT-only; the agent works FOR the student). So we require *evidence on
# disk* rather than trusting a self-reported "loaded" string — but we don't try
# to make ack quotes cryptographically unforgeable. The bar is "you cannot pass
# by merely typing loaded in JSON; you must have produced the artifact."

def _source_present(work_dir: Path, entry: dict) -> bool:
    """A 'loaded' source counts as truly present only if its declared `path`
    points to a non-empty file (or a non-empty directory) on disk. This is the
    '凭物不凭自报' check — parity with check-spec-grounding.py which inspects
    references/ for real files rather than trusting a flag (red-team H1)."""
    if not isinstance(entry, dict):
        return False
    rel = entry.get("path")
    if not rel:
        return False
    p = Path(rel)
    if not p.is_absolute():
        p = work_dir / rel
    try:
        if not p.exists():
            return False
        if p.is_dir():
            return any(p.iterdir())
        return p.stat().st_size > 0
    except Exception:
        return False


def _load_acks(work_dir: Path) -> set:
    """Source ids the user explicitly authorized skipping, from
    <work>/.sources_ack. Each line is a JSON object
    {source_id, action, quote}. action must be 'skip' and quote must be a
    verbatim user authorization (>=10 chars, matching the quiz
    degraded_method_user_consent bar in _lib._validate_quiz_submitted_schema)."""
    ack = work_dir / ".sources_ack"
    out: set = set()
    if not ack.exists():
        return out
    try:
        text = ack.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if obj.get("action") == "skip" and len(str(obj.get("quote", "")).strip()) >= 10:
            sid = obj.get("source_id")
            if sid:
                out.add(sid)
    return out


@safe_main
def main():
    event = read_event()
    if not event:
        passthrough()
    if event.get("tool_name") not in ("Write", "Edit"):
        passthrough()

    tool_input = event.get("tool_input") or {}
    file_path = tool_input.get("file_path", "")
    if not matches_result_json(file_path):
        passthrough()

    rj = Path(file_path)
    if not rj.exists():
        passthrough()
    rj = rj.resolve()

    try:
        data = json.loads(rj.read_text(encoding="utf-8"))
    except Exception:
        passthrough()

    if data.get("status") not in ("draft_ready", "submitted"):
        passthrough("manifest check: status not draft_ready/submitted, skip")

    work_dir = rj.parent
    receipt_path = work_dir / "sources.json"
    if not receipt_path.exists():
        # No Stage 0.5 receipt — can't locate the manifest. Mirrors
        # check-spec-grounding's "no spec.md" passthrough. Non-breaking.
        passthrough("manifest check: no sources.json receipt, skip")

    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except Exception:
        block(
            "hook check-source-manifest: <work>/sources.json is not valid JSON.\n"
            "Rewrite it as "
            "{course_id, skill_name, kind, sources:{<id>:{enforcement,status,path}}}."
        )

    course_id = receipt.get("course_id")
    skill_name = receipt.get("skill_name")
    kind = receipt.get("kind")
    receipt_sources = receipt.get("sources")
    if not isinstance(receipt_sources, dict):
        receipt_sources = {}

    if not skill_name or kind is None:
        block(
            "hook check-source-manifest: sources.json is missing required "
            "top-level fields (need course_id, skill_name, kind). The hook needs "
            "skill_name + course_id to locate the overlay §0 manifest and kind to "
            "filter it. Rewrite the receipt with all four top-level keys."
        )

    required = load_required_sources(skill_name, course_id, kind)
    mandatory = [
        s for s in required
        if s.get("enforcement", "mandatory") == "mandatory"
    ]
    if not mandatory:
        passthrough("manifest check: no mandatory sources for this kind, OK")

    acked = _load_acks(work_dir)

    problems = []
    for src in mandatory:
        sid = src.get("id")
        entry = receipt_sources.get(sid) if sid else None
        status = (entry or {}).get("status")
        if status == "loaded":
            if _source_present(work_dir, entry):
                continue
            # claims loaded but nothing on disk — the H1 bypass
            problems.append((src, "loaded-but-no-file-on-disk"))
            continue
        if status == "soft_stop_acked" and sid in acked:
            continue
        problems.append((src, status))

    if not problems:
        passthrough(
            f"manifest check: {len(mandatory)} mandatory source(s) all loaded/acked, OK"
        )

    lines = [
        "hook check-source-manifest: MANDATORY SOURCES NOT LOADED.",
        "",
        f"Skill {skill_name!r} / course {course_id} / kind {kind!r} declares "
        f"mandatory required-sources in its overlay §0 that were NOT loaded into "
        f"{work_dir.name}/sources/ before this draft was announced "
        f"{data.get('status')!r}:",
        "",
    ]
    for src, status in problems[:10]:
        sid = src.get("id")
        what = src.get("what", "")
        loc = src.get("location", "")
        cur = status or "absent from sources.json"
        lines.append(f"  - {sid}  [{cur}]")
        if what:
            lines.append(f"      what: {what}")
        if loc:
            lines.append(f"      location: {loc}")
    lines.append("")
    lines.append(
        "→ Run Stage 0.5: fetch each missing mandatory source into "
        f"{work_dir.name}/sources/ and set its status to 'loaded' in sources.json. "
        "If a source genuinely cannot be fetched, soft-stop and ASK THE USER; once "
        "they authorize skipping it, record their verbatim words in "
        f"{work_dir.name}/.sources_ack as a line "
        '{"source_id":"<id>","action":"skip","quote":"<user words>"} and set that '
        "source's status to 'soft_stop_acked'. Do NOT fabricate content from "
        "general knowledge — that is the exact failure this gate prevents."
    )
    block("\n".join(lines))


if __name__ == "__main__":
    main()
