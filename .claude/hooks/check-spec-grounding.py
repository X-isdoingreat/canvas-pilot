# SPDX-License-Identifier: AGPL-3.0-or-later
"""PostToolUse(Write|Edit) hook: spec-grounding check.

When a result.json is written with status='draft_ready' or 'submitted' for
a code/theory problem, verify that all external references the spec mentions
have been fetched into <work>/references/.

The failure pattern this catches: a spec that says "the implementation of
binary_search from our conversation about Searching" — if the student
invents variable names instead of fetching the actual lecture's code,
the draft's identifiers won't match what the grader's autograder or
rubric expects. The fix is always cheap (one WebFetch); inventing is a zero.

Trigger conditions (all must hold):
1. tool_name in {Write, Edit}
2. file_path matches runs/<date>/<work>/result.json
3. result.json loads and status in {draft_ready, submitted}
4. A <work>/spec.md exists

If all hold, parse spec.md for reference phrases. For each detected reference,
require a matching file in <work>/references/. If any reference is ungrounded,
exit 2 and tell Claude to WebFetch the missing artifact.

This hook is the "soft" sibling of check-identifier-grounding.py — this one
catches missing reference files; that one catches identifiers in the draft
that have no upstream source even when references/ has content.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import block, passthrough, read_event, safe_main, matches_result_json, ROOT  # noqa: E402


# Reference-mention patterns common across instructor-site-style courses.
# Each entry: (compiled regex, lambda(match) -> human-readable description).
REFERENCE_PATTERNS = [
    # "from our conversation about Searching" / "from our lecture on X"
    (re.compile(
        r"\bfrom\s+our\s+(conversation|lecture|discussion|notes)\s+(about|on)\s+([A-Z][A-Za-z0-9_ ]+)",
        re.IGNORECASE),
     lambda m: f"lecture/notes on {m.group(3).strip()}"),
    # "the provided implementation of binary_search"
    (re.compile(
        r"\bthe\s+provided\s+(implementation|code|function|class|module)\s+of\s+(\w+)",
        re.IGNORECASE),
     lambda m: f"provided {m.group(1)} of {m.group(2)}"),
    # "as (shown|presented|written) in (class|the lecture)"
    (re.compile(
        r"\b(shown|presented|written|discussed|given)\s+in\s+(class|the\s+lecture|the\s+notes)",
        re.IGNORECASE),
     lambda m: f"lecture material ({m.group(1)} in {m.group(2)})"),
    # "the X (function|class|code) (we|that we) (wrote|saw|discussed|built)"
    (re.compile(
        r"\bthe\s+(\w+)\s+(function|class|code|implementation)\s+(we|that\s+we)\s+(wrote|saw|discussed|built|covered)",
        re.IGNORECASE),
     lambda m: f"'{m.group(1)}' {m.group(2)} from lecture"),
]


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

    status = data.get("status")
    if status not in ("draft_ready", "submitted"):
        passthrough("grounding check: status not draft_ready/submitted, skip")

    work_dir = rj.parent
    spec_path = work_dir / "spec.md"
    if not spec_path.exists():
        passthrough("grounding check: no spec.md, not a code/theory problem")

    spec_text = spec_path.read_text(encoding="utf-8", errors="ignore")

    # Collect all reference hits
    references = []
    for pattern, describe in REFERENCE_PATTERNS:
        for m in pattern.finditer(spec_text):
            references.append((m.group(0), describe(m)))

    if not references:
        passthrough("grounding check: no external references in spec")

    refs_dir = work_dir / "references"
    has_any_ref_file = refs_dir.exists() and any(refs_dir.iterdir())

    if not has_any_ref_file:
        lines = [
            "hook check-spec-grounding: SPEC REFERENCES NOT FETCHED.",
            "",
            f"Spec at {spec_path.relative_to(ROOT)} mentions external sources that must be",
            f"fetched before a draft can be marked {status!r}. Found {len(references)} reference(s):",
            "",
        ]
        for raw, desc in references[:10]:
            lines.append(f"  - {desc}")
            lines.append(f"      matched text: \"{raw.strip()[:120]}\"")
        lines.append("")
        lines.append(
            "→ WebFetch each referenced source and save the fetched text to "
            f"{refs_dir.relative_to(ROOT).as_posix()}/<name>.md (or .py, .html). "
            "Then re-verify your draft uses identifiers/code from the actual "
            "source, not invented ones. Re-write result.json after fixing."
        )
        lines.append("")
        lines.append(
            "This check exists because invented identifiers / signatures that "
            "don't match the upstream source are the most common visible-to-grader "
            "code-course failure mode. WebFetch is free; inventing is a zero."
        )
        block("\n".join(lines))

    passthrough(f"grounding check: {len(references)} refs detected, references/ has content, OK")


if __name__ == "__main__":
    main()
