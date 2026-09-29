"""Generated .claude skills must keep the whole .agents source.

A DOTALL rewrite rule once matched from an early sentence to the file's
last line and silently dropped most of canvas-skill-opportunity.
"""
from __future__ import annotations

import pytest

from scripts.sync_claude_skills import EXCLUDED, SOURCE, translate

SKILLS = sorted(
    p.name for p in SOURCE.iterdir() if p.is_dir() and p.name not in EXCLUDED
)


@pytest.mark.parametrize("name", SKILLS)
def test_translation_keeps_every_section(name):
    source = (SOURCE / name / "SKILL.md").read_text(encoding="utf-8")
    generated = translate(source, name)
    def headings(text):
        return [line for line in text.splitlines() if line.startswith("## ")]

    # Rewrites may reword a heading but never remove one.
    assert len(headings(generated)) == len(headings(source)), name
    # Rewrites only reword targeted passages; nothing should lose a large block.
    assert len(generated) >= 0.95 * len(source), name
