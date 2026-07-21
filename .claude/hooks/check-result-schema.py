# SPDX-License-Identifier: AGPL-3.0-or-later
"""PostToolUse(Write|Edit) hook: validate runs/.../result.json schema.

If Claude is writing a file that looks like a result.json under runs/,
validate it against the canonical schema. Other writes pass through.

Schema rules:
- valid JSON object
- status field required, must be in {draft_ready, submitted, skipped, error}
- if status == draft_ready, draft_path must be present and the file must exist
- if status == submitted, draft_path or submitted_at should be present
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import (  # noqa: E402
    block,
    matches_result_json,
    passthrough,
    read_event,
    safe_main,
    validate_result_schema,
)


@safe_main
def main():
    event = read_event()
    if not event:
        passthrough()

    tool_name = event.get("tool_name")
    if tool_name not in ("Write", "Edit"):
        passthrough()

    tool_input = event.get("tool_input") or {}
    file_path = tool_input.get("file_path")

    if not matches_result_json(file_path):
        passthrough()

    # For Write: full content is in tool_input.content
    # For Edit: we'd need to read from disk after the edit. Since this is
    # PostToolUse, the file is already updated, so we read it from disk.
    if tool_name == "Write":
        content = tool_input.get("content", "")
    else:
        try:
            content = Path(file_path).read_text(encoding="utf-8")
        except Exception as e:
            block(
                f"hook check-result-schema: cannot read {file_path} after edit: {e}"
            )
            return

    ok, err = validate_result_schema(content, Path(file_path))
    if not ok:
        block(
            f"hook check-result-schema: {file_path}\n"
            f"  → {err}\n"
            f"  Fix this result.json before continuing. The router needs every assignment "
            f"to have a valid result.json with a recognized status."
        )
    passthrough(f"hook check-result-schema: {file_path} OK")


if __name__ == "__main__":
    main()
