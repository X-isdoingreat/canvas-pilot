# SPDX-License-Identifier: AGPL-3.0-or-later
"""Canvas SSO credential storage.

Used by `canvas_client._login_interactive` to remember the user's SSO
username + password between sessions so the headed login popup only needs
Duo confirmation on subsequent fires (instead of full re-typing).

Three encryption layers, tried in order:

  1. **DPAPI** (Windows) — `win32crypt.CryptProtectData`, blob bound to
     the current Windows user account. Best-in-class for our threat model
     (same encryption Chrome uses for its own saved passwords).
  2. **Fernet** (cross-platform) — `cryptography.fernet.Fernet` with a
     32-byte key stored next to the blob at `.cookies/credentials.key`
     (chmod 0o600). Fallback when pywin32 unavailable.
  3. **Base64** (anywhere) — last-resort obfuscation only. Prints a
     one-time stderr warning when this path is taken.

File format on disk (`.cookies/credentials.dat`):
    {"version": 1, "method": "dpapi"|"fernet"|"base64",
     "payload": "<base64-encoded blob>"}

The payload, once decrypted, is JSON: {"u": "<username>", "p": "<password>"}.

Both files (`credentials.dat` + `credentials.key`) sit under `.cookies/`,
which is already covered by `.gitignore` — no separate ignore rule needed.
"""
from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CRED_PATH = ROOT / ".cookies" / "credentials.dat"
KEY_PATH = ROOT / ".cookies" / "credentials.key"

_BASE64_WARNED = False


def _pick_method() -> str:
    try:
        import win32crypt  # noqa: F401
        return "dpapi"
    except Exception:
        pass
    try:
        from cryptography.fernet import Fernet  # noqa: F401
        return "fernet"
    except Exception:
        pass
    return "base64"


def _encrypt_dpapi(plaintext: bytes) -> bytes:
    import win32crypt
    blob = win32crypt.CryptProtectData(plaintext, None, None, None, None, 0)
    return blob


def _decrypt_dpapi(blob: bytes) -> bytes:
    import win32crypt
    _, plaintext = win32crypt.CryptUnprotectData(blob, None, None, None, 0)
    return plaintext


def _get_fernet_key() -> bytes:
    from cryptography.fernet import Fernet
    if KEY_PATH.exists():
        return KEY_PATH.read_bytes()
    key = Fernet.generate_key()
    KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    KEY_PATH.write_bytes(key)
    try:
        os.chmod(KEY_PATH, 0o600)
    except Exception:
        pass  # Windows ignores chmod; NTFS ACL inherited from .cookies/ dir
    return key


def _encrypt_fernet(plaintext: bytes) -> bytes:
    from cryptography.fernet import Fernet
    return Fernet(_get_fernet_key()).encrypt(plaintext)


def _decrypt_fernet(blob: bytes) -> bytes:
    from cryptography.fernet import Fernet
    return Fernet(_get_fernet_key()).decrypt(blob)


def _warn_base64_once() -> None:
    global _BASE64_WARNED
    if _BASE64_WARNED:
        return
    _BASE64_WARNED = True
    print(
        "\033[1;31m[canvas_credentials] WARNING: system-level encryption "
        "unavailable; storing SSO credentials as base64 (obfuscation only, "
        "NOT real encryption). Install pywin32 (Windows) or cryptography "
        "for proper protection.\033[0m",
        file=sys.stderr,
    )


def store_credentials(username: str, password: str) -> None:
    """Persist (username, password) to disk, encrypted via the best
    available method. Overwrites any prior stored credentials."""
    if not username or not password:
        return
    plaintext = json.dumps({"u": username, "p": password}).encode("utf-8")
    method = _pick_method()
    if method == "dpapi":
        blob = _encrypt_dpapi(plaintext)
    elif method == "fernet":
        blob = _encrypt_fernet(plaintext)
    else:
        _warn_base64_once()
        blob = base64.b64encode(plaintext)
    record = {
        "version": 1,
        "method": method,
        "payload": base64.b64encode(blob).decode("ascii"),
    }
    CRED_PATH.parent.mkdir(parents=True, exist_ok=True)
    CRED_PATH.write_text(json.dumps(record), encoding="utf-8")


def load_credentials() -> tuple[str, str] | None:
    """Return (username, password) if a usable stored credential exists,
    else None. Corrupt / undecryptable files are treated as 'no credentials'
    — caller falls back to manual login."""
    if not CRED_PATH.exists():
        return None
    try:
        record = json.loads(CRED_PATH.read_text(encoding="utf-8"))
        if record.get("version") != 1:
            return None
        method = record.get("method")
        blob = base64.b64decode(record.get("payload", ""))
        if method == "dpapi":
            plaintext = _decrypt_dpapi(blob)
        elif method == "fernet":
            plaintext = _decrypt_fernet(blob)
        elif method == "base64":
            plaintext = base64.b64decode(blob)
        else:
            return None
        data = json.loads(plaintext.decode("utf-8"))
        u, p = data.get("u"), data.get("p")
        if not u or not p:
            return None
        return (u, p)
    except Exception:
        return None


def forget_credentials() -> bool:
    """Remove the stored credentials (and the Fernet key file, if present).
    Returns True if anything existed and was removed, False otherwise."""
    removed_any = False
    for path in (CRED_PATH, KEY_PATH):
        if path.exists():
            try:
                path.unlink()
                removed_any = True
            except Exception:
                pass
    return removed_any


def has_stored_credentials() -> bool:
    return CRED_PATH.exists()
