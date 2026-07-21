# SPDX-License-Identifier: AGPL-3.0-or-later
"""gws CLI email helper — single shell-out entry point shared by all
schedulers / alerts in this project. The actual binding is the `gws` Google
Workspace CLI; caller supplies recipient / subject / body, this module owns
the subprocess + MIME encoding + error logging.

Uses the raw Gmail API path (`gws gmail users messages send --json {raw:b64}`)
with `email.message.EmailMessage` so non-ASCII subjects/bodies are RFC 2047 /
MIME encoded correctly. The simpler `gws gmail +send` shape causes mojibake
in some non-Gmail clients (Outlook desktop, Apple Mail, etc.) when subject
contains Chinese characters — see .iclicker/src/notify.py history.

Generic by design: no default recipient, no hardcoded paths, no school-specific
strings. Each caller keeps its own RECIPIENT constant and optional gws path.

Usage from Python:
    from src.gws_email import send_email
    ok = send_email("subject", "body", "user@example.com",
                    log=my_log_fn, gws_cmd="gws")

Usage from CLI (for ad-hoc test / one-shot):
    python -m src.gws_email --to user@example.com --subject hi --body hello
"""
from __future__ import annotations

import base64
import json
import shutil
import subprocess
import sys
from email.message import EmailMessage
from typing import Callable, Optional


def send_email(
    subject: str,
    body: str,
    to: str,
    log: Optional[Callable[[str], None]] = None,
    timeout_s: int = 60,
    gws_cmd: str = "gws",
) -> bool:
    """Send one email via the gws CLI's raw Gmail API path. Returns True on success.

    Builds an EmailMessage so non-ASCII subjects/bodies are MIME-encoded
    correctly. Submits via `gws gmail users messages send --json {raw:b64}`.

    `log` is called with one string on each failure; default prints to stderr.
    Success path is silent. `gws_cmd` defaults to "gws" (PATH lookup); pass an
    absolute path if your gws is a .cmd shim that the OS won't resolve at run
    time (typical for cron contexts where PATH is minimal).

    From header is set to the same address as To — current callers are all
    self-notify; gws sends as the authenticated account regardless.
    """
    _log = log or (lambda m: print(m, file=sys.stderr, flush=True))
    # Resolve gws_cmd: shutil.which honors Windows PATHEXT so "gws" resolves
    # to "C:\path\to\gws.cmd" (subprocess.run with shell=False doesn't do this
    # implicitly). If which() returns None, fall through and let subprocess
    # raise FileNotFoundError so the caller sees a clear message.
    resolved = shutil.which(gws_cmd) or gws_cmd
    try:
        msg = EmailMessage()
        msg["From"] = to
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        raw_b64 = base64.urlsafe_b64encode(msg.as_bytes()).rstrip(b"=").decode("ascii")
        r = subprocess.run(
            [resolved, "gmail", "users", "messages", "send",
             "--params", '{"userId":"me"}',
             "--json", json.dumps({"raw": raw_b64})],
            capture_output=True, text=True, timeout=timeout_s, shell=False,
        )
        if r.returncode == 0:
            return True
        _log(f"gws gmail send exit {r.returncode}: stderr={r.stderr[:300]}")
        return False
    except FileNotFoundError:
        _log(f"gws gmail send: binary '{gws_cmd}' not found on PATH "
             f"(shutil.which returned None) — pass gws_cmd=absolute_path "
             f"or add gws to PATH")
        return False
    except Exception as e:
        _log(f"gws gmail send exception: {e}")
        return False


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Send one email via gws.")
    p.add_argument("--to", required=True)
    p.add_argument("--subject", required=True)
    p.add_argument("--body", required=True)
    p.add_argument("--gws-cmd", default="gws", help="gws binary path (default: PATH lookup)")
    args = p.parse_args()
    ok = send_email(args.subject, args.body, args.to, gws_cmd=args.gws_cmd)
    sys.exit(0 if ok else 1)
