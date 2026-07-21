# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import datetime as dt
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.approval import parse_approval


EXECUTE = (
    ROOT / ".agents" / "skills" / "canvas-execute" / "SKILL.md"
).read_text(encoding="utf-8")


def documented(pattern: str) -> None:
    assert re.search(pattern, EXECUTE, re.IGNORECASE | re.MULTILINE | re.DOTALL)


def plan_for(buckets: dict[int, str]) -> dict[str, object]:
    now = dt.datetime.now(dt.timezone.utc)
    return {
        "generated_at": (now - dt.timedelta(minutes=1)).isoformat(),
        "expires_at": (now + dt.timedelta(hours=1)).isoformat(),
        "items": [
            {"index": index, "bucket": bucket, "user_decision": None}
            for index, bucket in sorted(buckets.items())
        ]
    }


def decisions(spec: str, buckets: dict[int, str]) -> dict[int, str]:
    parsed = parse_approval(spec, plan_for(buckets))
    assert not parsed.needs_clarification, parsed.clarification
    return parsed.decisions


def test_documented_exact_forms() -> None:
    for literal in (
        "bare `1,3`",
        "`all`",
        "`skip`",
        "`1-4`",
        "`urgent only`",
        "`swap 2 to canvas-x`",
        "`defer 2`",
        "`cancel`",
    ):
        assert literal in EXECUTE


def test_exact_approval_semantics() -> None:
    buckets = {1: "urgent", 2: "soon", 3: "urgent", 4: "later"}
    assert decisions("all", buckets) == {
        1: "approve", 2: "approve", 3: "approve", 4: "approve"
    }
    assert decisions("1,3", buckets) == {
        1: "approve", 2: "defer", 3: "approve", 4: "defer"
    }
    assert decisions("1-3", buckets) == {
        1: "approve", 2: "approve", 3: "approve", 4: "defer"
    }
    assert decisions("urgent only", buckets) == {
        1: "approve", 2: "defer", 3: "approve", 4: "defer"
    }
    assert decisions("skip", buckets) == {
        1: "defer", 2: "defer", 3: "defer", 4: "defer"
    }
    assert decisions("cancel", buckets) == {
        1: "defer", 2: "defer", 3: "defer", 4: "defer"
    }
    assert decisions("swap 2 to canvas-example", buckets) == {
        1: "defer", 2: "swap:canvas-example", 3: "defer", 4: "defer"
    }
    assert decisions("approve all; defer 2", buckets) == {
        1: "approve", 2: "defer", 3: "approve", 4: "approve"
    }


@pytest.mark.parametrize(
    "spec",
    [
        "do the important ones",
        "do the first few",
        "defer",
        "swap 1/2",
        "cancel 2",
        "approve 1; defer 1",
        "1,99",
        "4-2",
        "",
    ],
)
def test_ambiguous_or_invalid_forms_fail_closed(spec: str) -> None:
    parsed = parse_approval(
        spec,
        plan_for({1: "urgent", 2: "soon", 3: "later", 4: "later"}),
    )
    assert parsed.needs_clarification


def test_skill_explicitly_documents_ambiguity_before_writes() -> None:
    documented(r"ambiguous.*clarification.*without\s+writing anything")
    for phrase in (
        "do the important ones",
        "do the first few",
        "bare `defer`",
        "`swap 1/2`",
        "`cancel 2`",
        "`approve 1; defer 1`",
    ):
        assert phrase in EXECUTE
    documented(r"Silence never means approval")
    documented(r"Ambiguity stops before any plan write, marker,\s+dispatch, or mutation")


def test_execute_uses_the_current_codex_thread_identity() -> None:
    assert "current_authorization_session" in EXECUTE
    assert "CODEX_THREAD_ID" in EXECUTE
    assert "invent a UUID" in EXECUTE
