# SPDX-License-Identifier: AGPL-3.0-or-later
"""Public-safe Canvas login and session-recovery CLI.

This is a thin entry point over the browser/session primitives in
``src.canvas_client``.  It contains no institution-specific selectors,
credentials, URLs, or course identifiers.

Examples::

    python -m src.canvas_login --auto
    python -m src.canvas_login --probe
    python -m src.canvas_login --forget
"""
from __future__ import annotations

import argparse
import sys
from typing import Any


EXIT_OK = 0
EXIT_NOT_CONFIGURED = 2
EXIT_AUTH_REQUIRED = 3
EXIT_RUNTIME_ERROR = 4


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify or recover the local Canvas browser session. "
            "No password is persisted unless the existing explicit opt-in "
            "credential setting is enabled."
        )
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--auto",
        action="store_true",
        help="verify auth and open the existing interactive browser flow if needed",
    )
    mode.add_argument(
        "--probe",
        action="store_true",
        help="check current session health without opening an interactive login",
    )
    mode.add_argument(
        "--forget",
        "--forget-credentials",
        dest="forget",
        action="store_true",
        help="remove opt-in stored SSO credentials; Canvas cookies are unchanged",
    )
    return parser


def _load_client():
    from . import canvas_client

    return canvas_client


def _load_credentials():
    from . import canvas_credentials

    return canvas_credentials


def _classify_exception(exc: Exception) -> tuple[int, str]:
    text = str(exc)
    lowered = text.lower()
    if type(exc).__name__ == "CanvasSessionExpired":
        return EXIT_AUTH_REQUIRED, text
    status_code = getattr(getattr(exc, "response", None), "status_code", None)
    if status_code in {401, 403}:
        return EXIT_AUTH_REQUIRED, text
    if any(
        marker in lowered
        for marker in (
            "canvas_base",
            "canvas_token",
            "not set",
            "is required",
            "requires playwright",
        )
    ):
        return EXIT_NOT_CONFIGURED, text
    return EXIT_RUNTIME_ERROR, text


def probe(client: Any) -> int:
    session_alive = getattr(client, "session_alive", None)
    if not callable(session_alive):
        print(
            "Canvas session probe is unavailable in this installation. "
            "Reinstall requirements and retry --auto.",
            file=sys.stderr,
        )
        return EXIT_RUNTIME_ERROR
    try:
        alive = bool(session_alive(timeout_s=5))
    except Exception as exc:
        code, detail = _classify_exception(exc)
        print(f"Canvas session probe failed: {detail}", file=sys.stderr)
        return code
    if not alive:
        print(
            "Canvas session is not currently valid. Run "
            "`python -m src.canvas_login --auto` to open the recovery flow.",
            file=sys.stderr,
        )
        return EXIT_AUTH_REQUIRED
    print("Canvas session is valid.")
    return EXIT_OK


def auto_login(client: Any) -> int:
    get_self = getattr(client, "get_self", None)
    if not callable(get_self):
        print(
            "Canvas login recovery primitive is unavailable. Reinstall the "
            "project requirements and retry.",
            file=sys.stderr,
        )
        return EXIT_RUNTIME_ERROR
    try:
        user = get_self()
    except Exception as exc:
        code, detail = _classify_exception(exc)
        if code == EXIT_AUTH_REQUIRED:
            guidance = "Complete the browser login/second-factor prompt, then retry."
        elif code == EXIT_NOT_CONFIGURED:
            guidance = "Run canvas-setup to configure the Canvas host and auth mode."
        else:
            guidance = "Check network/browser availability and retry."
        print(f"Canvas login recovery failed: {detail}\n{guidance}", file=sys.stderr)
        return code
    if not isinstance(user, dict) or user.get("id") in (None, ""):
        print(
            "Canvas responded, but the current-user probe was incomplete. "
            "Run canvas-setup to verify the configured host.",
            file=sys.stderr,
        )
        return EXIT_RUNTIME_ERROR
    print("Canvas login verified.")
    return EXIT_OK


def forget_credentials(credentials: Any) -> int:
    forget = getattr(credentials, "forget_credentials", None)
    has_stored = getattr(credentials, "has_stored_credentials", None)
    if not callable(forget) or not callable(has_stored):
        print(
            "Credential cleanup primitives are unavailable in this installation.",
            file=sys.stderr,
        )
        return EXIT_RUNTIME_ERROR
    try:
        removed = bool(forget())
        if has_stored():
            print(
                "Stored credentials could not be removed; the protected file still exists.",
                file=sys.stderr,
            )
            return EXIT_RUNTIME_ERROR
    except Exception as exc:
        print(f"Failed to forget stored credentials: {exc}", file=sys.stderr)
        return EXIT_RUNTIME_ERROR
    if removed:
        print("Forgot stored SSO credentials. The next recovery requires manual entry.")
    else:
        print("No stored SSO credentials were present.")
    return EXIT_OK


def main(
    argv: list[str] | None = None,
    *,
    client: Any | None = None,
    credentials: Any | None = None,
) -> int:
    args = build_parser().parse_args(argv)

    if args.forget:
        try:
            provider = credentials or _load_credentials()
        except Exception as exc:
            code, detail = _classify_exception(exc)
            print(f"Credential cleanup is unavailable: {detail}", file=sys.stderr)
            return code
        return forget_credentials(provider)

    try:
        canvas = client or _load_client()
    except Exception as exc:
        code, detail = _classify_exception(exc)
        guidance = (
            "Run canvas-setup to configure the Canvas host/auth mode."
            if code == EXIT_NOT_CONFIGURED
            else "Install the project requirements and retry."
        )
        print(f"Canvas login is unavailable: {detail}\n{guidance}", file=sys.stderr)
        return code

    if args.probe:
        return probe(canvas)
    # No flag intentionally defaults to recovery, matching the historical
    # `python -m src.canvas_login` instruction used by automation messages.
    return auto_login(canvas)


if __name__ == "__main__":
    raise SystemExit(main())
