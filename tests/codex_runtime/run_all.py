# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run(path: str) -> None:
    print(f"+ {path}")
    cp = subprocess.run([sys.executable, path], cwd=ROOT, text=True)
    if cp.returncode != 0:
        raise SystemExit(cp.returncode)


def main() -> int:
    run("tests/codex_runtime/run_setup_tests.py")
    run("tests/codex_runtime/run_scan_tests.py")
    run("tests/codex_runtime/run_execute_tests.py")
    print("Codex runtime fixture suite PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
