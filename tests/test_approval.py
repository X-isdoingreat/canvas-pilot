from __future__ import annotations

import datetime as dt

import pytest

from src.approval import apply_approval_to_plan, parse_approval


@pytest.fixture
def plan():
    now = dt.datetime.now(dt.timezone.utc)
    return {
        "generated_at": (now - dt.timedelta(minutes=1)).isoformat(),
        "expires_at": (now + dt.timedelta(hours=1)).isoformat(),
        "items": [
            {"index": 1, "bucket": "urgent", "user_decision": None},
            {"index": 2, "bucket": "urgent", "user_decision": None},
            {"index": 3, "bucket": "soon", "user_decision": None},
            {"index": 4, "bucket": "soon", "user_decision": None},
        ]
    }


@pytest.mark.parametrize("text", ["all", "approve all", "execute all", "全部", "全部做"])
def test_all_forms(text, plan) -> None:
    parsed = parse_approval(text, plan)
    assert parsed.approved_indices == (1, 2, 3, 4)
    assert parsed.grants_canvas_mutation is False


@pytest.mark.parametrize(
    ("text", "expected"),
    [("1,3", (1, 3)), ("approve 1, 3", (1, 3)), ("2-4", (2, 3, 4)), ("approve 1-2,4", (1, 2, 4))],
)
def test_lists_and_ranges(text, expected, plan) -> None:
    assert parse_approval(text, plan).approved_indices == expected


@pytest.mark.parametrize("text", ["urgent", "urgent only"])
def test_urgent_only(text, plan) -> None:
    parsed = parse_approval(text, plan)
    assert parsed.approved_indices == (1, 2)
    assert parsed.deferred_indices == (3, 4)


@pytest.mark.parametrize("text", ["cancel", "skip", "cancel all"])
def test_cancel_defers_everything(text, plan) -> None:
    parsed = parse_approval(text, plan)
    assert parsed.kind == "cancel"
    assert parsed.deferred_indices == (1, 2, 3, 4)


def test_defer_and_swap(plan) -> None:
    assert parse_approval("defer 2", plan).approved_indices == ()
    swapped = parse_approval("swap 2 to canvas-generic", plan)
    assert swapped.decisions[2] == "swap:canvas-generic"
    assert swapped.approved_indices == (2,)


@pytest.mark.parametrize(
    ("text", "expected", "decision"),
    [
        ("做 1，3", (1, 3), None),
        ("1 到 4", (1, 2, 3, 4), None),
        ("跳过 2", (), "defer"),
        ("第 2 项用 canvas-generic", (2,), "swap:canvas-generic"),
    ],
)
def test_documented_chinese_approval_forms(text, expected, decision, plan) -> None:
    parsed = parse_approval(text, plan)
    assert not parsed.needs_clarification
    assert parsed.approved_indices == expected
    if decision is not None:
        assert parsed.decisions[2] == decision


@pytest.mark.parametrize(
    "text",
    [
        "do important ones",
        "you decide",
        "swap 1/2",
        "sounds good",
        "5",
        "approve 1 if you think it is safe",
        "please maybe do 1 later",
        "approve 1; submit 1",
    ],
)
def test_ambiguous_or_invalid_inputs_require_clarification(text, plan) -> None:
    parsed = parse_approval(text, plan)
    assert parsed.needs_clarification
    assert parsed.decisions == {}


def test_apply_updates_plan_without_mutation_authority(plan) -> None:
    parsed = parse_approval("1,3", plan)
    updated = apply_approval_to_plan(plan, parsed)
    assert [item["user_decision"] for item in updated["items"]] == [
        "approve", "defer", "approve", "defer"
    ]
