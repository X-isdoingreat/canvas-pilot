from __future__ import annotations

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / ".agents" / "skills"
CANVAS_CLIENT = ROOT / "src" / "canvas_client.py"


def _canvas_skill_texts() -> dict[Path, str]:
    return {
        path: path.read_text(encoding="utf-8")
        for path in sorted(SKILL_ROOT.glob("canvas-*/SKILL.md"))
    }


def _top_level_functions(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def test_every_canvas_client_method_named_by_a_skill_exists() -> None:
    refs: dict[str, list[str]] = {}
    for path, text in _canvas_skill_texts().items():
        for name in re.findall(r"\bcv\.([A-Za-z_][A-Za-z0-9_]*)\b", text):
            refs.setdefault(name, []).append(path.parent.name)
    public = _top_level_functions(CANVAS_CLIENT)
    missing = {name: skills for name, skills in refs.items() if name not in public}
    assert not missing, f"Canvas skills reference missing public client helpers: {missing}"


def test_every_src_module_named_by_a_canvas_skill_is_tracked_runtime_source() -> None:
    refs: dict[str, list[str]] = {}
    patterns = (
        r"python\s+-m\s+src\.([A-Za-z_][A-Za-z0-9_]*)",
        r"from\s+src\s+import\s+([A-Za-z_][A-Za-z0-9_]*)",
        r"\bsrc/([A-Za-z_][A-Za-z0-9_]*)\.py\b",
    )
    for path, text in _canvas_skill_texts().items():
        for pattern in patterns:
            for name in re.findall(pattern, text):
                refs.setdefault(name, []).append(path.parent.name)
    missing = {
        name: skills
        for name, skills in refs.items()
        if not (ROOT / "src" / f"{name}.py").is_file()
    }
    assert not missing, f"Canvas skills reference missing tracked src modules: {missing}"


def test_canvas_skills_do_not_emit_noncanonical_result_statuses() -> None:
    bad: list[str] = []
    status_pattern = re.compile(
        r"(?:\"status\"\s*:\s*\"|status\s*=\s*\")"
        r"(graded|already_submitted)\""
    )
    for path, text in _canvas_skill_texts().items():
        for match in status_pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            bad.append(f"{path.relative_to(ROOT).as_posix()}:{line}:{match.group(1)}")
    assert not bad, "Noncanonical result statuses remain:\n" + "\n".join(bad)


def test_product_framework_has_no_legacy_router_execution_entry() -> None:
    for name in ("canvas-scan", "canvas-execute"):
        text = (SKILL_ROOT / name / "SKILL.md").read_text(encoding="utf-8")
        assert "src.router --run" not in text
    router = (ROOT / "src" / "router.py").read_text(encoding="utf-8")
    assert "legacy skill dispatch is disabled" in router.lower()
