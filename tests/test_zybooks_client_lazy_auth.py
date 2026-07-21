from __future__ import annotations

import json
from pathlib import Path

import pytest

from src import zybooks_client as zb


class _Response:
    status_code = 200
    content = b"{}"

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return {"user": {"id": 42}}


def _storage(path: Path) -> None:
    session = {
        "authenticated": {
            "session": {"auth_token": "synthetic-jwt", "user_id": 42}
        }
    }
    path.write_text(
        json.dumps({"ember_simple_auth-session-5": json.dumps(session)}),
        encoding="utf-8",
    )


def test_module_import_and_symbol_access_do_not_require_local_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(zb, "LOCALSTORAGE_PATH", tmp_path / "missing.json")
    zb.clear_cached_auth()
    assert callable(zb.whoami)
    assert callable(zb.exercises_for_section)
    assert callable(zb.exercise_to_dict)
    assert "Authorization" not in zb._session.headers


def test_first_network_helper_loads_token_lazily(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = tmp_path / "storage.json"
    _storage(storage)
    monkeypatch.setattr(zb, "LOCALSTORAGE_PATH", storage)
    monkeypatch.setattr(zb._session, "get", lambda *args, **kwargs: _Response())
    zb.clear_cached_auth()

    result = zb.whoami()

    assert result["user"]["id"] == 42
    assert zb._session.headers["Authorization"] == "Bearer synthetic-jwt"


def test_missing_token_fails_at_call_time_not_import_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(zb, "LOCALSTORAGE_PATH", tmp_path / "missing.json")
    zb.clear_cached_auth()
    with pytest.raises(zb.ZybooksAuthError, match="missing"):
        zb.whoami()
