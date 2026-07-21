# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "plugins" / "canvas-pilot-codex" / ".codex-plugin" / "plugin.json"


def test_manifest() -> None:
    assert MANIFEST.exists()
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert data["name"] == "canvas-pilot-codex"
    assert "version" in data
    assert "skills" in data


def test_required_skills_declared() -> None:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    declared = set(data["skills"])
    for name in ["canvas-bootstrap", "canvas-setup", "canvas-skill-opportunity", "canvas-scan", "canvas-execute", "canvas-skip", "cc-sync-runner", "cc-sync-execute-loop"]:
        assert f"skills/{name}" in declared


def test_manifest_only_mode() -> None:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert "manifest-only" in data["description"].lower()
    readme = (ROOT / "plugins" / "canvas-pilot-codex" / "README.md").read_text(encoding="utf-8")
    assert "manifest-only" in readme
    assert ".agents/skills/**" in readme


def test_drift_check() -> None:
    cp = subprocess.run([sys.executable, "scripts/codex_plugin_check.py"], cwd=ROOT, text=True)
    assert cp.returncode == 0


def main() -> int:
    tests = [test_manifest, test_required_skills_declared, test_manifest_only_mode, test_drift_check]
    failures: list[str] = []
    for test in tests:
        try:
            test()
            print(f"PASS {test.__name__}")
        except Exception as exc:
            failures.append(f"{test.__name__}: {exc}")
            print(f"FAIL {test.__name__}: {exc}")
    if failures:
        print("\nFailures:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
