# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from src import canvas_login


ROOT = Path(__file__).resolve().parent.parent


class FakeClient:
    def __init__(self, *, alive=True, user=None, error=None):
        self.alive = alive
        self.user = user if user is not None else {"id": 1}
        self.error = error
        self.get_self_calls = 0

    def session_alive(self, timeout_s=5):
        assert timeout_s == 5
        if self.error:
            raise self.error
        return self.alive

    def get_self(self):
        self.get_self_calls += 1
        if self.error:
            raise self.error
        return self.user


class FakeCredentials:
    def __init__(self, *, removed=True, remains=False):
        self.removed = removed
        self.remains = remains

    def forget_credentials(self):
        return self.removed

    def has_stored_credentials(self):
        return self.remains


def test_help_works_without_importing_canvas_client():
    env = os.environ.copy()
    env.pop("CANVAS_BASE", None)
    env.pop("CANVAS_TOKEN", None)
    completed = subprocess.run(
        [sys.executable, "-m", "src.canvas_login", "--help"],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert completed.returncode == 0
    assert "--auto" in completed.stdout
    assert "--probe" in completed.stdout


def test_auto_and_default_use_existing_interactive_capable_get_self():
    explicit = FakeClient()
    default = FakeClient()

    assert canvas_login.main(["--auto"], client=explicit) == canvas_login.EXIT_OK
    assert canvas_login.main([], client=default) == canvas_login.EXIT_OK
    assert explicit.get_self_calls == 1
    assert default.get_self_calls == 1


def test_probe_is_noninteractive_and_returns_actionable_auth_code(capsys):
    client = FakeClient(alive=False)

    code = canvas_login.main(["--probe"], client=client)

    assert code == canvas_login.EXIT_AUTH_REQUIRED
    assert client.get_self_calls == 0
    assert "--auto" in capsys.readouterr().err


def test_forget_does_not_require_canvas_configuration():
    credentials = FakeCredentials(removed=True, remains=False)

    code = canvas_login.main(["--forget"], credentials=credentials)

    assert code == canvas_login.EXIT_OK


def test_missing_configuration_returns_specific_code(monkeypatch, capsys):
    def fail_load():
        raise RuntimeError("CANVAS_BASE env var is required")

    monkeypatch.setattr(canvas_login, "_load_client", fail_load)

    code = canvas_login.main(["--auto"])

    assert code == canvas_login.EXIT_NOT_CONFIGURED
    assert "canvas-setup" in capsys.readouterr().err


def test_incomplete_current_user_response_fails_actionably():
    code = canvas_login.main(["--auto"], client=FakeClient(user={}))

    assert code == canvas_login.EXIT_RUNTIME_ERROR
