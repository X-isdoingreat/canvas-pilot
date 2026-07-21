# SPDX-License-Identifier: AGPL-3.0-or-later
"""Integration smoke test: replicate the canvas-execute SKILL.md dispatch
snippet that loads the overlay yaml block, then run the router against
realistic assignment fixtures.

Run: pytest tests/test_ac_eng_router_integration.py -v

These complement the unit tests in test_ac_eng_router.py — those verify
each layer in isolation; this verifies the overlay-load + parse + dispatch
chain that canvas-execute actually performs in production.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.ac_eng_router import route_ac_eng_assignment


def _load_overlay_config() -> dict:
    """Mirror exactly what canvas-execute SKILL.md §4 step 1 does."""
    overlay_path = ROOT / "_private" / "canvas-essay-app.md"
    overlay_config: dict = {}
    if overlay_path.exists():
        text = overlay_path.read_text(encoding="utf-8")
        m = re.search(
            r"```yaml\s*\n(persona_trigger_patterns:.*?)\n```", text, re.DOTALL
        )
        if m:
            overlay_config = yaml.safe_load(m.group(1)) or {}
    return overlay_config


def test_overlay_yaml_block_parses():
    """The overlay's first yaml block must produce non-empty trigger + skip lists."""
    cfg = _load_overlay_config()
    if not (ROOT / "_private" / "canvas-essay-app.md").exists():
        # Overlay not yet authored on this machine — skip the integration test.
        return
    assert "persona_trigger_patterns" in cfg, f"missing trigger key: {cfg}"
    assert "persona_skip_patterns" in cfg, f"missing skip key: {cfg}"
    assert len(cfg["persona_trigger_patterns"]) >= 3
    assert len(cfg["persona_skip_patterns"]) >= 3


def test_e2e_ceo_5_15_autoethnography_with_real_overlay():
    """The 5.15.md autoethnography spec routed against the actual deployed
    overlay must land on `essay` (not `short`)."""
    cfg = _load_overlay_config()
    fixture = {
        "name": "Essay 1: Autoethnography Reflection",
        "description": "Write a 1500 word autoethnography essay in MLA format.",
        "points_possible": 50,
        "submission_types": ["online_upload"],
    }
    assert route_ac_eng_assignment(fixture, cfg, plan_item={}) == "essay"


def test_e2e_practice_summary_with_real_overlay():
    """The existing Practice Summary (In Class) assignment routed against the
    real overlay must land on `short` — overlay's skip patterns include
    'Practice Summary' so Layer 2 should fire."""
    cfg = _load_overlay_config()
    fixture = {
        "name": "Practice Summary (In Class)",
        "description": "",
        "points_possible": 100,
        "submission_types": ["on_paper"],
    }
    assert route_ac_eng_assignment(fixture, cfg, plan_item={}) == "short"


def test_e2e_annotation_with_real_overlay():
    """A short reading-annotation assignment routed against the real overlay
    must land on `short` (overlay's skip list includes 'Annotation')."""
    cfg = _load_overlay_config()
    fixture = {
        "name": "Tue Wk5 HW Annotation",
        "description": "Annotate Reading 4 (Lule) with margin notes.",
        "points_possible": 10,
        "submission_types": ["online_upload"],
    }
    assert route_ac_eng_assignment(fixture, cfg, plan_item={}) == "short"


def test_e2e_manual_override_force_essay():
    """plan.json `ac_eng_force_essay: true` must override every other layer."""
    cfg = _load_overlay_config()
    fixture = {
        "name": "Random Quiz",
        "description": "",
        "points_possible": 5,
        "submission_types": ["online_text_entry"],
    }
    assert (
        route_ac_eng_assignment(
            fixture, cfg, plan_item={"ac_eng_force_essay": True}
        )
        == "essay"
    )
