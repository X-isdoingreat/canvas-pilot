# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from src.recurring_patterns import bucket_recurring


def test_recurring_pattern_preserves_assignment_ids_without_changing_examples():
    items = [
        {
            "id": 100 + index,
            "name": f"Project {index}",
            "submission_types": ["online_upload"],
            # Unsafe student state must not be copied into Pattern.
            "submission": {"score": 999, "body": "private"},
        }
        for index in range(1, 5)
    ]

    patterns, tail = bucket_recurring(items, min_freq=3)

    assert tail == 0
    assert len(patterns) == 1
    assert patterns[0].examples == ("Project 1", "Project 2", "Project 3")
    assert patterns[0].assignment_ids == ("101", "102", "103", "104")
    assert "submission" not in patterns[0]._fields
