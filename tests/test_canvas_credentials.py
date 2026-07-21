# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for src/canvas_credentials.py.

Run: pytest tests/test_canvas_credentials.py -v

Coverage: persistence opt-in, protected-method round-trip, base64 refusal,
fail-closed cleanup, and corrupt/missing/empty reads.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import canvas_credentials


@pytest.fixture
def tmp_cred_paths(tmp_path, monkeypatch):
    """Point CRED_PATH and KEY_PATH at a tmp dir so tests don't touch the
    real .cookies/."""
    cred = tmp_path / "credentials.dat"
    key = tmp_path / "credentials.key"
    monkeypatch.setattr(canvas_credentials, "CRED_PATH", cred)
    monkeypatch.setattr(canvas_credentials, "KEY_PATH", key)
    monkeypatch.setenv("CANVAS_REMEMBER_CREDENTIALS", "true")
    monkeypatch.setattr(canvas_credentials, "_pick_method", lambda: "dpapi")
    monkeypatch.setattr(
        canvas_credentials, "_encrypt_dpapi", lambda value: value[::-1]
    )
    monkeypatch.setattr(
        canvas_credentials, "_decrypt_dpapi", lambda value: value[::-1]
    )
    return cred, key


def test_load_returns_none_when_missing(tmp_cred_paths):
    assert canvas_credentials.load_credentials() is None
    assert not canvas_credentials.has_stored_credentials()


def test_store_then_load_round_trip(tmp_cred_paths):
    assert canvas_credentials.store_credentials("fixture-user", "hunter2") is True
    assert canvas_credentials.has_stored_credentials()
    loaded = canvas_credentials.load_credentials()
    assert loaded == ("fixture-user", "hunter2")


def test_store_overwrites_prior(tmp_cred_paths):
    canvas_credentials.store_credentials("u1", "p1")
    canvas_credentials.store_credentials("u2", "p2")
    assert canvas_credentials.load_credentials() == ("u2", "p2")


def test_store_empty_inputs_noop(tmp_cred_paths):
    assert canvas_credentials.store_credentials("", "p") is False
    assert canvas_credentials.store_credentials("u", "") is False
    assert not canvas_credentials.has_stored_credentials()


def test_persistence_is_disabled_without_explicit_opt_in(tmp_cred_paths, monkeypatch):
    monkeypatch.delenv("CANVAS_REMEMBER_CREDENTIALS", raising=False)
    assert canvas_credentials.remember_credentials_enabled() is False
    assert canvas_credentials.store_credentials("u", "p") is False
    assert not canvas_credentials.has_stored_credentials()


def test_disabled_persistence_does_not_load_legacy_record(
    tmp_cred_paths, monkeypatch
):
    canvas_credentials.store_credentials("u", "p")
    assert canvas_credentials.has_stored_credentials()
    monkeypatch.setenv("CANVAS_REMEMBER_CREDENTIALS", "false")
    assert canvas_credentials.load_credentials() is None
    assert canvas_credentials.has_stored_credentials()


def test_forget_removes_file_returns_true(tmp_cred_paths):
    canvas_credentials.store_credentials("u", "p")
    assert canvas_credentials.forget_credentials() is True
    assert not canvas_credentials.has_stored_credentials()
    assert canvas_credentials.load_credentials() is None


def test_forget_returns_false_when_nothing_to_forget(tmp_cred_paths):
    assert canvas_credentials.forget_credentials() is False


def test_forget_raises_when_file_cannot_be_deleted(tmp_cred_paths, monkeypatch):
    cred, _ = tmp_cred_paths
    canvas_credentials.store_credentials("u", "p")
    original_unlink = Path.unlink

    def fail_target(path: Path, *args, **kwargs):
        if path == cred:
            raise PermissionError("locked fixture")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_target)
    with pytest.raises(
        canvas_credentials.CredentialStorageError, match="locked fixture"
    ):
        canvas_credentials.forget_credentials()
    assert cred.exists()


def test_load_returns_none_on_corrupt_file(tmp_cred_paths):
    cred, _ = tmp_cred_paths
    cred.parent.mkdir(parents=True, exist_ok=True)
    cred.write_text("not valid json {{{", encoding="utf-8")
    assert canvas_credentials.load_credentials() is None


def test_load_returns_none_on_wrong_version(tmp_cred_paths):
    cred, _ = tmp_cred_paths
    cred.parent.mkdir(parents=True, exist_ok=True)
    cred.write_text(
        json.dumps({"version": 99, "method": "base64", "payload": ""}),
        encoding="utf-8",
    )
    assert canvas_credentials.load_credentials() is None


def test_load_refuses_legacy_base64_record(tmp_cred_paths):
    cred, _ = tmp_cred_paths
    cred.parent.mkdir(parents=True, exist_ok=True)
    cred.write_text(
        json.dumps({"version": 1, "method": "base64", "payload": "unused"}),
        encoding="utf-8",
    )
    assert canvas_credentials.load_credentials() is None


def test_base64_fallback_is_refused(tmp_cred_paths, monkeypatch):
    monkeypatch.setattr(canvas_credentials, "_pick_method", lambda: "base64")
    with pytest.raises(
        canvas_credentials.CredentialStorageError, match="base64 is refused"
    ):
        canvas_credentials.store_credentials("u", "p")
    assert not canvas_credentials.has_stored_credentials()


def test_fernet_path_creates_key_file(tmp_cred_paths, monkeypatch):
    """If Fernet is available, exercising that path should create the key
    file. Skip if cryptography isn't installed (rare; it's a transitive
    dep of most projects)."""
    pytest.importorskip("cryptography")
    monkeypatch.setattr(canvas_credentials, "_pick_method", lambda: "fernet")
    canvas_credentials.store_credentials("u", "p")
    _, key = tmp_cred_paths
    assert key.exists()
    assert canvas_credentials.load_credentials() == ("u", "p")


def test_forget_also_removes_fernet_key(tmp_cred_paths, monkeypatch):
    pytest.importorskip("cryptography")
    monkeypatch.setattr(canvas_credentials, "_pick_method", lambda: "fernet")
    canvas_credentials.store_credentials("u", "p")
    _, key = tmp_cred_paths
    assert key.exists()
    canvas_credentials.forget_credentials()
    assert not key.exists()


def test_pick_method_prefers_dpapi_when_available(monkeypatch):
    """On Windows with pywin32, _pick_method should return 'dpapi'.
    Verified via direct import attempt; skip on platforms without it."""
    try:
        import win32crypt  # noqa: F401
    except Exception:
        pytest.skip("pywin32 not available on this host")
    assert canvas_credentials._pick_method() == "dpapi"


def test_payload_on_disk_not_plaintext(tmp_cred_paths):
    """Regression: stored file should NEVER contain the literal password,
    regardless of which protected encryption method was used."""
    canvas_credentials.store_credentials("fixture-user", "SuperSecret123!")
    cred, _ = tmp_cred_paths
    raw = cred.read_text(encoding="utf-8")
    assert "SuperSecret123!" not in raw
    assert "fixture-user" not in raw
