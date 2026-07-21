# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import pytest

from src.routes import (
    RouteConfigError,
    normalize_route,
    normalize_routes,
    resolve_route,
    resolve_skill,
)


def _assignment(**updates):
    value = {
        "id": 10,
        "name": "Project 4",
        "description": "See the linked specification.",
        "submission_types": ["online_upload"],
        "points_possible": 20,
        "quiz_id": None,
    }
    value.update(updates)
    return value


def test_normalizes_string_shorthand_and_legacy_code_alias():
    route = normalize_route(123, "code_py")

    assert route == {
        "name": "Course 123",
        "skill": "code_py",
        "overrides": [],
    }
    assert resolve_route(route, _assignment()).skill == "canvas-ics33"
    assert resolve_skill(route, _assignment()) == "canvas-ics33"
    assert resolve_skill("code_py", _assignment()) == "canvas-ics33"


def test_normalizes_object_route_and_override_before_canonicalization():
    route = normalize_route(
        "12",
        {
            "name": "Synthetic Course",
            "skill": "canvas-generic",
            "overrides": [
                {
                    "match": {"submission_types": ["online_quiz"]},
                    "skill": "quiz",
                }
            ],
        },
    )

    decision = resolve_route(
        route,
        _assignment(submission_types=["online_quiz"], quiz_id=88),
    )

    assert decision.skill == "canvas-inside"
    assert decision.configured_skill == "quiz"


def test_writing_alias_uses_deterministic_writing_router():
    route = normalize_route(1, {"name": "Writing", "skill": "ac_english"})

    essay = resolve_route(
        route,
        _assignment(
            name="Reflection Essay",
            description="Write at least 800 words.",
            points_possible=50,
        ),
    )
    short = resolve_route(
        route,
        _assignment(name="Reading Annotation Week 4", points_possible=10),
    )

    assert essay.skill == "canvas-essay"
    assert short.skill == "canvas-reading-annotation"


@pytest.mark.parametrize(
    ("submission_types", "quiz_id", "reason"),
    [
        (["on_paper"], None, "on_paper"),
        (["external_tool"], None, "external_tool_unsupported"),
        (["online_quiz"], None, "new_quiz_or_missing_classic_quiz_id"),
        (["none"], None, "no_online_submission"),
        (["future_delivery_mode"], None, "unsupported_submission_type"),
        ([], None, "missing_submission_type"),
    ],
)
def test_unsupported_delivery_modes_fail_closed(
    submission_types, quiz_id, reason
):
    route = normalize_route(1, "canvas-generic")
    decision = resolve_route(
        route,
        _assignment(submission_types=submission_types, quiz_id=quiz_id),
    )

    assert decision.skill == "canvas-skip"
    assert decision.reason_code == reason


def test_classic_quiz_forces_canonical_quiz_skill():
    route = normalize_route(1, "canvas-generic")
    decision = resolve_route(
        route,
        _assignment(submission_types=["online_quiz"], quiz_id=45),
    )

    assert decision.skill == "canvas-inside"


def test_unknown_bare_route_alias_fails_closed_but_generated_skill_is_allowed():
    unknown = resolve_route(normalize_route(1, "mystery"), _assignment())
    generated = resolve_route(
        normalize_route(1, "canvas-synthetic-project"), _assignment()
    )

    assert unknown.skill == "canvas-skip"
    assert unknown.reason_code == "unknown_route_skill"
    assert generated.skill == "canvas-synthetic-project"


def test_invalid_route_shape_is_a_configuration_error():
    with pytest.raises(RouteConfigError):
        normalize_routes({"routes": ["canvas-generic"]})
    with pytest.raises(RouteConfigError):
        normalize_route(1, {"name": "No skill"})
