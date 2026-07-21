# SPDX-License-Identifier: AGPL-3.0-or-later
"""Canvas LMS API client.

Cookie auth (default, `CANVAS_AUTH=cookie`): a headless Playwright Chromium
with a persistent profile at `.cookies/playwright-profile/` owns the auth
state — we never parse cookie names or schema. On 401, a headed browser
pops up; user logs in once; the headless picks up where it left off. No
JSON file, no cookie naming, no env override.

Token auth (`CANVAS_AUTH=token`, undocumented escape hatch; may be removed):
Bearer token from `CANVAS_TOKEN` through `requests.Session`. Retained for
the case where cookie SSO breaks at a specific school or for local dev
debugging. Not surfaced in any user-facing flow.

Both backends expose the same public API (`get`, `paginate`, `post_form`,
`post_json`, `put_json`, `download_file`, plus the high-level helpers
below).

Usage:
    python -m src.canvas_client --probe
    python -m src.canvas_client --courses
    python -m src.canvas_client --assignments <course_id>
    python -m src.canvas_client --forget-credentials
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlencode, urlparse

import requests

ROOT = Path(__file__).resolve().parent.parent


def _load_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


_load_env()


class CanvasSessionExpired(RuntimeError):
    """Cookie-mode session is expired and re-login failed or timed out."""


class QuizArbitrationEvidenceMissing(RuntimeError):
    """Quiz state-changing endpoints (answer/complete) refuse to fire unless
    the canonical canvas-inside SKILL.md §7 4-agent arbitration left evidence
    files in the work_dir. The gate is structural: the Codex skill and
    ``.codex/hooks/post_tool_guard.py`` provide the other defense layers."""


AUTH_MODE = os.environ.get("CANVAS_AUTH", "cookie").strip().lower()
TOKEN = os.environ.get("CANVAS_TOKEN", "")
BASE = os.environ.get("CANVAS_BASE", "").rstrip("/")
if not BASE:
    raise RuntimeError("CANVAS_BASE env var is required; see .env.example")


def _derive_web_base() -> str:
    """Web origin (no /api/v1). Used by cookie mode for the login URL."""
    explicit = os.environ.get("CANVAS_WEB_BASE", "").strip()
    if explicit:
        return explicit.rstrip("/")
    if BASE.endswith("/api/v1"):
        return BASE[: -len("/api/v1")]
    return BASE


WEB_BASE = _derive_web_base()


if AUTH_MODE not in ("token", "cookie"):
    raise RuntimeError(
        f"CANVAS_AUTH must be 'cookie' (token mode is undocumented; see source), "
        f"got: {AUTH_MODE!r}"
    )

if AUTH_MODE == "token" and not TOKEN:
    raise RuntimeError("CANVAS_AUTH=token but CANVAS_TOKEN not set in .env")


# ---------- HTTP backends ----------
#
# Two interchangeable backends behind the same public methods. Token mode
# is plain requests.Session. Cookie mode delegates everything to a headless
# Playwright Chromium so we never touch cookies, names, or schema by hand.

class _RequestsBackend:
    """Token mode: requests.Session with Bearer + browser-like headers.
    Some institutional anti-cheat / analytics tooling flags non-browser
    API callers (default python-requests UA stands out); spoofing as
    Chrome with normal Accept headers neutralizes that signal at zero
    cost."""

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Accept": "application/json+canvas-string-ids, application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "en-US,en;q=0.9",
            "X-Requested-With": "XMLHttpRequest",
        })
        self._session.headers["Authorization"] = f"Bearer {TOKEN}"

    def get(self, url: str, params: dict | None = None) -> Any:
        r = self._session.get(url, params=params, timeout=30)
        r.raise_for_status()
        return r.json()

    def get_with_headers(self, url: str, params: dict | None = None) -> tuple[Any, dict]:
        r = self._session.get(url, params=params, timeout=30)
        r.raise_for_status()
        return r.json(), dict(r.headers)

    def post_form(self, url: str, data) -> Any:
        # data may be dict OR list of (key, value) tuples (for repeated keys
        # like submission[file_ids][]).
        r = self._session.post(url, data=data, timeout=30)
        r.raise_for_status()
        return r.json() if r.content else {}

    def post_json(self, url: str, data: dict) -> Any:
        r = self._session.post(url, json=data, timeout=30)
        r.raise_for_status()
        return r.json() if r.content else {}

    def put_json(self, url: str, data: dict) -> Any:
        r = self._session.put(url, json=data, timeout=30)
        r.raise_for_status()
        return r.json() if r.content else {}

    def download(self, url: str, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        r = self._session.get(url, stream=True, timeout=120)
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        return dest

    def get_user_agent(self) -> str:
        return self._session.headers.get("User-Agent", "")

    def is_session_alive(self, timeout_s: int = 5) -> bool:
        """Bounded, read-only token validity probe.

        Tokens can be revoked even though they do not have cookie-style local
        expiry.  Cron recovery must observe that state instead of assuming any
        configured token remains valid forever.
        """
        try:
            response = self._session.get(f"{BASE}/users/self", timeout=timeout_s)
        except requests.RequestException:
            return False
        return response.status_code == 200


_USERNAME_SELECTORS = (
    'input[autocomplete="username"]',
    'input[name="j_username"]',
    'input[id*="username" i]',
    'input[id*="login" i]',
    'input[type="email"]:visible',
    'input[type="text"]:visible',
)
_PASSWORD_SELECTORS = (
    'input[autocomplete="current-password"]',
    'input[name="j_password"]',
    'input[id*="password" i]',
    'input[type="password"]:visible',
)

_DUO_TRUST_DEVICE_SELECTORS = (
    'button:has-text("Yes, this is my device")',
    '[role="button"]:has-text("Yes, this is my device")',
    'input[type="submit"][value="Yes, this is my device"]',
    'button:has-text("This is my device")',
    '[role="button"]:has-text("This is my device")',
    'button:has-text("Trust this browser")',
    '[role="button"]:has-text("Trust this browser")',
    'input[type="submit"][value="Trust this browser"]',
)
DUO_TRUST_DEVICE_WAIT_SEC = 60

# JS injected only when password persistence is explicitly enabled. It uses an
# exposed Python callback so the submitted values can be protected before the
# navigation destroys the page-local buffer.
_CAPTURE_LISTENER_JS = r"""
(() => {
    if (window.__cp_listener_installed) return;
    window.__cp_listener_installed = true;
    document.addEventListener('submit', (e) => {
        const form = e.target;
        if (!form || !form.querySelectorAll) return;
        const inputs = form.querySelectorAll('input');
        let u = null, p = null;
        for (const inp of inputs) {
            const t = (inp.type || '').toLowerCase();
            if (t === 'password' && !p) p = inp.value;
            else if (!u && (t === 'text' || t === 'email' || t === '')) u = inp.value;
        }
        if (u && p && window.__cp_capture) {
            try { window.__cp_capture(JSON.stringify({u: u, p: p})); } catch (_) {}
        }
    }, true);
})();
"""


def _try_click_duo_trust_device(page) -> bool:
    """Accept Duo's trusted-device prompt when it is visible.

    This is best-effort and intentionally narrow: only buttons with the
    trusted-device wording are clicked. If Duo changes the copy or frame
    structure, login falls back to the existing manual path.
    """
    try:
        frames = list(page.frames)
    except Exception:
        return False
    for frame in frames:
        for selector in _DUO_TRUST_DEVICE_SELECTORS:
            try:
                loc = frame.locator(selector)
                if loc.count() <= 0:
                    continue
                first = loc.first
                if not first.is_visible():
                    continue
                first.click(timeout=1000)
                print(
                    "[canvas_client] Accepted Duo trusted-device prompt.",
                    file=sys.stderr,
                )
                return True
            except Exception:
                continue
    return False


class _PlaywrightBackend:
    """Cookie mode: a headless Chromium with a persistent profile owns the
    auth state. We make Canvas API calls via `context.request`. On 401, we
    close the headless context, open a HEADED context against the same
    profile, wait for the user to log in (detected via /api/v1/users/self
    returning 200 from inside the page), then reopen headless and retry.

    No cookie names. No JSON schema. No CSRF parsing. The browser handles
    everything a browser already handles.
    """

    PROFILE_DIR = ROOT / ".cookies" / "playwright-profile"
    COOKIES_PATH = ROOT / ".cookies" / "session.json"
    LOGIN_TIMEOUT_SEC = 300  # 5 min for first-time SSO+2FA
    LOGIN_POLL_INTERVAL = 1.5
    AUTOFILL_REJECT_TIMEOUT_SEC = 15  # wait after autofill submit before declaring rejection — ONLY applies if Duo was never reached (see reached_duo gate in _login_interactive)

    def __init__(self) -> None:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            raise RuntimeError(
                "CANVAS_AUTH=cookie requires playwright. Install with:\n"
                "  pip install playwright\n"
                "  python -m playwright install chromium"
            ) from e
        self._sync_playwright = sync_playwright
        self._pw = sync_playwright().start()
        self._ctx = None  # type: ignore[assignment]
        self._auth_checked = False

    def _open_context(self, headless: bool):
        self.PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        return self._pw.chromium.launch_persistent_context(
            user_data_dir=str(self.PROFILE_DIR),
            headless=headless,
        )

    def _load_saved_cookies(self) -> None:
        """Restore cookies from disk into the current context. Best-effort
        — corrupt / malformed file is ignored and treated as no cookies
        (the next _auth_works check will then fail and trigger login)."""
        if not self.COOKIES_PATH.exists():
            return
        try:
            cookies = json.loads(self.COOKIES_PATH.read_text(encoding="utf-8"))
            if cookies:
                self._ctx.add_cookies(cookies)
        except Exception:
            pass

    def _save_cookies(self, cookies: list) -> None:
        """Persist cookies to disk so the next Python process can skip
        the browser popup. Chromium's user_data_dir only persists cookies
        with explicit expiry; Canvas's session cookie is session-scoped
        and gets dropped on context close, so the persistent profile alone
        isn't enough — we have to round-trip through our own JSON."""
        try:
            self.COOKIES_PATH.parent.mkdir(parents=True, exist_ok=True)
            self.COOKIES_PATH.write_text(json.dumps(cookies), encoding="utf-8")
        except Exception:
            pass  # best-effort; failure means next run pops browser, no big deal

    def _ensure_session(self) -> None:
        """Idempotent: open headless context, restore saved cookies from
        disk if any, verify auth, fall back to interactive login if needed."""
        if self._auth_checked and self._ctx is not None:
            return
        if self._ctx is None:
            self._ctx = self._open_context(headless=True)
            self._load_saved_cookies()
        if not self._auth_works():
            self._ctx.close()
            self._ctx = None
            cookies = self._login_interactive()
            self._ctx = self._open_context(headless=True)
            if cookies:
                self._ctx.add_cookies(cookies)
                self._save_cookies(cookies)
        self._auth_checked = True

    def _auth_works(self) -> bool:
        try:
            r = self._ctx.request.get(f"{BASE}/users/self")
            return r.status == 200
        except Exception:
            return False

    def is_session_alive(self, timeout_s: int = 5) -> bool:
        """Probe Canvas /users/self via APIRequestContext WITHOUT triggering
        interactive Chrome login. Returns True if cookies valid, False if
        dead or unable to probe within timeout_s.

        Unlike _ensure_session(), this method does NOT fall back to
        _login_interactive when cookies are dead — the caller decides what
        to do (e.g. cron sends a wake-up email and aborts that fire).
        """
        try:
            if self._ctx is None:
                self._ctx = self._open_context(headless=True)
                self._load_saved_cookies()
            r = self._ctx.request.get(
                f"{BASE}/users/self", timeout=timeout_s * 1000
            )
            return r.status == 200
        except Exception:
            return False

    def _login_interactive(self) -> list:
        """Open a headed Chromium and poll for Canvas auth.

        Two behaviors merged into one flow:

        - **autofill** (if persistence is enabled and a credential record
          exists): on each frame navigation, try to locate username + password
          fields via a layered selector chain, fill them, verify both fields
          are non-empty, then click submit. Rejection is only declared when the
          form never advanced past credential entry. Two gates protect good
          credentials from a slow second factor, and both are school-agnostic
          so forks at any institution benefit:
            1. Duo fast path — if a Duo frame (`*.duosecurity.com`) loaded, the
               password was accepted; keep credentials no matter how long Duo
               takes.
            2. Provider-neutral signal — `_credential_form_visible()`: a real
               wrong password re-renders the password form (field stays
               visible), whereas an accepted-but-slow password advances to the
               MFA step (field gone). Works for Duo / Okta / Microsoft / SMS
               alike, not just Duo.
          Only when `/users/self` still returns 401 after
          `AUTOFILL_REJECT_TIMEOUT_SEC`, the page is still off-Canvas, Duo was
          never reached, AND the credential form is still visible do we conclude
          the IdP rejected our credentials (almost always: user changed their
          password) → clear stored credentials so the next pass falls through to
          the manual-capture branch below. (Before these gates, an MFA push
          taking longer than the timeout was misread as a password rejection and
          wiped good credentials.)

        - **credential persistence** (explicit opt-in only): when
          `CANVAS_REMEMBER_CREDENTIALS=true`, a context-level exposed function
          listens for the submitted SSO username/password and stores them with
          DPAPI or Fernet after successful login. The default path does not
          install the capture listener and never persists the password.

        Cookies are captured BEFORE closing the context — Chromium drops
        session-scoped cookies (Canvas's session cookie has no explicit
        expiry) on context close, so the next headless context needs them
        re-injected via add_cookies().
        """
        from . import canvas_credentials

        remember_credentials = canvas_credentials.remember_credentials_enabled()
        stored = canvas_credentials.load_credentials()
        print(
            "[canvas_client] Opening browser to log in to Canvas. "
            "A Chromium window will pop up.",
            file=sys.stderr,
        )
        if stored:
            print(
                "[canvas_client] Stored credentials found — will auto-fill SSO form.",
                file=sys.stderr,
            )

        ctx = self._open_context(headless=False)

        capture_state = {"u": None, "p": None}
        autofill_state = {
            "credentials": stored,           # (u, p) or None
            "submitted_at": None,            # monotonic time of last autofill submit
            "cleared_after_reject": False,
            "reached_duo": False,            # True once a Duo frame loads = password accepted
        }

        def _on_capture(data: str) -> None:
            try:
                obj = json.loads(data)
                u, p = obj.get("u"), obj.get("p")
                if u and p and capture_state["u"] is None:
                    capture_state["u"] = u
                    capture_state["p"] = p
            except Exception:
                pass

        if remember_credentials:
            try:
                ctx.expose_function("__cp_capture", _on_capture)
            except Exception:
                # Re-binding the same name on context reuse raises — safe to ignore.
                pass

        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        def _inject_capture(frame) -> None:
            if not remember_credentials:
                return
            try:
                frame.evaluate(_CAPTURE_LISTENER_JS)
            except Exception:
                pass

        def _try_autofill(frame) -> None:
            creds = autofill_state["credentials"]
            if not creds:
                return
            u, p = creds
            try:
                user_sel = next(
                    (s for s in _USERNAME_SELECTORS if frame.locator(s).count() > 0),
                    None,
                )
                pass_sel = next(
                    (s for s in _PASSWORD_SELECTORS if frame.locator(s).count() > 0),
                    None,
                )
                if not user_sel or not pass_sel:
                    return
                user_loc = frame.locator(user_sel).first
                pass_loc = frame.locator(pass_sel).first
                user_loc.fill(u)
                pass_loc.fill(p)
                # Verify both fields actually accepted the value (silent-fail guard).
                if not user_loc.input_value() or not pass_loc.input_value():
                    return
                submit_loc = frame.locator(
                    'button[type="submit"], input[type="submit"]'
                ).first
                if submit_loc.count() > 0:
                    submit_loc.click()
                else:
                    pass_loc.press("Enter")
                autofill_state["submitted_at"] = time.monotonic()
                print(
                    "[canvas_client] Autofilled SSO form — confirm Duo on your phone.",
                    file=sys.stderr,
                )
            except Exception:
                pass

        def _on_framenavigated(frame) -> None:
            _inject_capture(frame)
            # Reaching a Duo frame proves Shibboleth accepted username+password;
            # any delay from here on is Duo/2FA, never a credential rejection.
            try:
                if "duosecurity.com" in frame.url or "duo.com" in frame.url:
                    autofill_state["reached_duo"] = True
            except Exception:
                pass
            if autofill_state["credentials"]:
                _try_autofill(frame)

        page.on("framenavigated", _on_framenavigated)

        page.goto(f"{WEB_BASE}/login")

        def _credential_form_visible() -> bool:
            """Provider-neutral 'still stuck on the password step' signal.
            True if a visible password input is still present in ANY frame —
            i.e. the IdP has not advanced past credential entry. Works for any
            second factor (Duo / Okta / Microsoft / SMS), not just Duo: a real
            wrong password re-renders the password form (field stays visible),
            whereas a slow-but-accepted password advances to the MFA step (field
            gone). Best-effort: any error returns False so we never wipe good
            credentials on an inconclusive read."""
            try:
                for fr in page.frames:
                    for s in _PASSWORD_SELECTORS:
                        loc = fr.locator(s)
                        if loc.count() > 0 and loc.first.is_visible():
                            return True
            except Exception:
                pass
            return False

        deadline = time.monotonic() + self.LOGIN_TIMEOUT_SEC
        while time.monotonic() < deadline:
            if _try_click_duo_trust_device(page):
                time.sleep(0.75)
                continue

            # Shibboleth-rejection watchdog.
            sub_at = autofill_state["submitted_at"]
            if (
                autofill_state["credentials"]
                and not autofill_state["cleared_after_reject"]
                and not autofill_state["reached_duo"]
                and sub_at is not None
                and time.monotonic() - sub_at > self.AUTOFILL_REJECT_TIMEOUT_SEC
            ):
                try:
                    in_canvas = page.url.startswith(WEB_BASE)
                except Exception:
                    in_canvas = False
                # Only declare rejection if we are still parked on the
                # credential-entry form. If the password field is gone, the
                # IdP advanced to a second factor = password was accepted;
                # the delay is MFA, not a bad password. (reached_duo above is
                # the Duo-specific fast path; this is the provider-neutral one.)
                if not in_canvas and _credential_form_visible():
                    try:
                        r_check = ctx.request.get(f"{BASE}/users/self")
                        if r_check.status == 401:
                            canvas_credentials.forget_credentials()
                            autofill_state["credentials"] = None
                            autofill_state["cleared_after_reject"] = True
                            print(
                                "[canvas_client] Stored credentials rejected "
                                "(password may have changed) — cleared. "
                                "Please log in manually; the new password "
                                "will be saved automatically.",
                                file=sys.stderr,
                            )
                    except canvas_credentials.CredentialStorageError as exc:
                        ctx.close()
                        raise CanvasSessionExpired(
                            "stored credentials were rejected but could not be deleted"
                        ) from exc
                    except Exception:
                        pass

            try:
                r = ctx.request.get(f"{BASE}/users/self")
                if r.status == 200:
                    if autofill_state["reached_duo"]:
                        duo_trust_deadline = (
                            time.monotonic() + DUO_TRUST_DEVICE_WAIT_SEC
                        )
                        while time.monotonic() < duo_trust_deadline:
                            if _try_click_duo_trust_device(page):
                                time.sleep(0.75)
                                break
                            time.sleep(0.25)
                    cookies = ctx.cookies()
                    # Persist captured credentials after a manual login or
                    # after rejected credentials were cleared. Skip a
                    # successful autofill path because that protected record
                    # is already current.
                    if (
                        capture_state["u"]
                        and capture_state["p"]
                        and (
                            stored is None
                            or autofill_state["cleared_after_reject"]
                        )
                    ):
                        try:
                            saved = canvas_credentials.store_credentials(
                                capture_state["u"], capture_state["p"]
                            )
                            if saved:
                                print(
                                    "[canvas_client] Saved SSO credentials — "
                                    "next login will only need Duo.",
                                    file=sys.stderr,
                                )
                        except Exception as e:
                            print(
                                f"[canvas_client] Credential save failed: {e}",
                                file=sys.stderr,
                            )
                    ctx.close()
                    print("[canvas_client] Login detected.", file=sys.stderr)
                    return cookies
            except Exception:
                # Context might be transiently busy / cookies mid-update.
                pass
            time.sleep(self.LOGIN_POLL_INTERVAL)
        ctx.close()
        raise CanvasSessionExpired(
            f"Login not completed within {self.LOGIN_TIMEOUT_SEC} seconds."
        )

    def _csrf_header(self) -> dict:
        """Canvas requires X-CSRF-Token on state-changing requests when the
        request is cookie-authed (the web UI does this automatically via JS).
        The token lives in the `_csrf_token` cookie, URL-encoded; Canvas wants
        it URL-decoded in the header. Without this, POST/PUT/DELETE to most
        write endpoints (notably /quizzes/<id>/submissions) returns HTTP 422
        unprocessable_content."""
        from urllib.parse import unquote
        try:
            for c in self._ctx.cookies():
                if c.get("name") == "_csrf_token":
                    return {"X-CSRF-Token": unquote(c.get("value", ""))}
        except Exception:
            pass
        return {}

    def _request(self, method: str, url: str, retried: bool = False, **kwargs):
        self._ensure_session()
        if method.lower() in ("post", "put", "delete", "patch"):
            existing = kwargs.get("headers") or {}
            merged = {**self._csrf_header(), **existing}
            if merged:
                kwargs = {**kwargs, "headers": merged}
        try:
            r = getattr(self._ctx.request, method)(url, **kwargs)
        except Exception as e:
            raise CanvasSessionExpired(f"playwright {method} error: {e}") from e
        if r.status == 401 and not retried:
            self._ctx.close()
            self._ctx = None
            self._auth_checked = False
            cookies = self._login_interactive()
            self._ctx = self._open_context(headless=True)
            if cookies:
                self._ctx.add_cookies(cookies)
                self._save_cookies(cookies)
            self._auth_checked = True
            return self._request(method, url, retried=True, **kwargs)
        if r.status == 401:
            raise CanvasSessionExpired(
                f"Got 401 on {method.upper()} {url} after re-login."
            )
        if r.status >= 400:
            raise requests.HTTPError(
                f"{method.upper()} {url} → HTTP {r.status}: {r.text()[:500]}"
            )
        return r

    def get(self, url: str, params: dict | None = None) -> Any:
        r = self._request("get", url, params=params or {})
        return r.json()

    def get_with_headers(self, url: str, params: dict | None = None) -> tuple[Any, dict]:
        r = self._request("get", url, params=params or {})
        # Playwright APIResponse.headers returns a dict[str, str].
        return r.json(), dict(r.headers)

    def post_form(self, url: str, data) -> Any:
        # Playwright's `form` parameter wants a dict and rejects repeated keys.
        # Canvas's submission[file_ids][] needs repeats — fall back to manual
        # urlencoded body when caller passes a list of tuples.
        if isinstance(data, list):
            body = urlencode(data).encode()
            r = self._request(
                "post", url, data=body,
                headers={"content-type": "application/x-www-form-urlencoded"},
            )
        else:
            r = self._request("post", url, form=data)
        return r.json() if r.body() else {}

    def post_json(self, url: str, data: dict) -> Any:
        r = self._request("post", url, data=data)
        return r.json() if r.body() else {}

    def put_json(self, url: str, data: dict) -> Any:
        r = self._request("put", url, data=data)
        return r.json() if r.body() else {}

    def download(self, url: str, dest: Path) -> Path:
        r = self._request("get", url)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(r.body())
        return dest

    def get_user_agent(self) -> str:
        try:
            self._ensure_session()
            page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()
            return page.evaluate("() => navigator.userAgent")
        except Exception:
            return "Mozilla/5.0 (Chromium via Playwright)"


# Module-level backend, picked once at import time.
_backend = _RequestsBackend() if AUTH_MODE == "token" else _PlaywrightBackend()


def session_alive(timeout_s: int = 5) -> bool:
    """Is the Canvas session usable RIGHT NOW without triggering an interactive
    browser login? Token mode: always True. Cookie mode: GETs /users/self via
    APIRequestContext (no Chromium tab launch); True on 200, False on anything
    else within timeout_s seconds.

    Used by `canvas-cron` framework (scripts/cron_base.py) to short-circuit
    autonomous routine fires when cookies are expired — sends a wake-up email
    instead of headlessly popping Chrome that no one will click.
    """
    return _backend.is_session_alive(timeout_s=timeout_s)


# ---------- Public HTTP primitives ----------

def _parse_link_header(header: str) -> dict[str, str]:
    out = {}
    for part in header.split(","):
        m = re.match(r'\s*<([^>]+)>;\s*rel="([^"]+)"', part)
        if m:
            out[m.group(2)] = m.group(1)
    return out


def get(path_or_url: str, **params) -> Any:
    """GET single resource (no pagination)."""
    url = path_or_url if path_or_url.startswith("http") else f"{BASE}{path_or_url}"
    return _backend.get(url, params=params)


def paginate(path_or_url: str, **params) -> list[Any]:
    """GET with Link header pagination, returns flattened list."""
    url = path_or_url if path_or_url.startswith("http") else f"{BASE}{path_or_url}"
    out: list[Any] = []
    while url:
        data, headers = _backend.get_with_headers(
            url, params=params if "?" not in url else None
        )
        if isinstance(data, list):
            out.extend(data)
        else:
            out.append(data)
        link = headers.get("link") or headers.get("Link") or ""
        url = _parse_link_header(link).get("next")
        params = {}
    return out


def _authorize_mutation(
    authorization_receipt,
    *,
    action: str | None,
    course_id: str | int | None,
    target_type: str | None,
    target_id: str | int | None,
    path: str | None = None,
    track_usage: bool = True,
) -> None:
    """Enforce the signed mutation kernel before a backend/network call."""
    from .authorization import (
        AuthorizationDenied,
        mutation_authorization_enforced,
        require_mutation_authorization,
    )

    complete_context = (
        bool(action)
        and course_id is not None
        and target_type in {"assignment", "quiz"}
        and target_id is not None
    )
    if not complete_context:
        if authorization_receipt is not None or mutation_authorization_enforced():
            raise AuthorizationDenied(
                "Canvas POST/PUT requires exact action, course, target_type, and target_id"
            )
        return
    if path is not None:
        from urllib.parse import unquote, urlsplit

        route = urlsplit(path).path
        segments = [unquote(segment) for segment in route.strip("/").split("/")]
        target_segment = "assignments" if target_type == "assignment" else "quizzes"
        path_matches = (
            len(segments) >= 4
            and segments[0] == "courses"
            and segments[1] == str(course_id)
            and segments[2] == target_segment
            and segments[3] == str(target_id)
        )
        if not path_matches:
            raise AuthorizationDenied(
                "Canvas mutation path does not match its exact course/target authorization context"
            )
    require_mutation_authorization(
        authorization_receipt,
        canvas_origin=BASE,
        course_id=course_id,
        target_type=str(target_type),
        target_id=target_id,
        action=str(action),
        track_usage=track_usage,
    )


def post(
    path: str,
    *,
    authorization_receipt=None,
    mutation_action: str | None = None,
    mutation_course_id: str | int | None = None,
    mutation_target_type: str | None = None,
    mutation_target_id: str | int | None = None,
    **data,
) -> Any:
    """POST JSON body, guarded in Codex runtimes."""
    _authorize_mutation(
        authorization_receipt,
        action=mutation_action,
        course_id=mutation_course_id,
        target_type=mutation_target_type,
        target_id=mutation_target_id,
        path=path,
    )
    return _backend.post_json(f"{BASE}{path}", data)


def post_form(
    path: str,
    data,
    *,
    authorization_receipt=None,
    mutation_action: str | None = None,
    mutation_course_id: str | int | None = None,
    mutation_target_type: str | None = None,
    mutation_target_id: str | int | None = None,
) -> Any:
    """POST form body, guarded in Codex runtimes."""
    _authorize_mutation(
        authorization_receipt,
        action=mutation_action,
        course_id=mutation_course_id,
        target_type=mutation_target_type,
        target_id=mutation_target_id,
        path=path,
    )
    return _backend.post_form(f"{BASE}{path}", data)


def put(
    path: str,
    *,
    authorization_receipt=None,
    mutation_action: str | None = None,
    mutation_course_id: str | int | None = None,
    mutation_target_type: str | None = None,
    mutation_target_id: str | int | None = None,
    **data,
) -> Any:
    """PUT JSON body, guarded in Codex runtimes."""
    _authorize_mutation(
        authorization_receipt,
        action=mutation_action,
        course_id=mutation_course_id,
        target_type=mutation_target_type,
        target_id=mutation_target_id,
        path=path,
    )
    return _backend.put_json(f"{BASE}{path}", data)


def get_user_agent() -> str:
    """User-Agent currently being sent on Canvas API calls. Useful for
    event logging or when a downstream skill needs to mirror the same UA
    in an event payload. Stable across both auth modes."""
    return _backend.get_user_agent()


# ---------- High-level helpers ----------

def get_self() -> dict:
    return get("/users/self")


def list_courses(enrollment_state: str = "active") -> list[dict]:
    """List enrolled courses. `enrollment_state` ∈ {active, completed,
    invited_or_pending, all}."""
    return paginate("/courses", enrollment_state=enrollment_state, per_page=50)


def project_assignment_spec_for_opportunity(assignment: dict) -> dict:
    """Apply Opportunity's strict assignment-spec allowlist."""
    from .opportunity_evidence import (
        project_assignment_spec_for_opportunity as project,
    )
    return project(assignment)


def list_assignments_for_opportunity(course_id: str | int) -> list[dict]:
    """List safe assignment specs without requesting student submissions."""
    assignments = paginate(
        f"/courses/{course_id}/assignments",
        per_page=50,
        order_by="due_at",
    )
    return [
        project_assignment_spec_for_opportunity(assignment)
        for assignment in assignments
        if isinstance(assignment, dict)
    ]


def get_assignment_spec_for_opportunity(
    course_id: str | int, assignment_id: str | int
) -> dict:
    """Fetch one safe assignment spec without any submission include."""
    assignment = get(f"/courses/{course_id}/assignments/{assignment_id}")
    return project_assignment_spec_for_opportunity(assignment)


def get_submission_feedback_observation_for_opportunity(
    course_id: str | int, assignment_id: str | int
) -> dict:
    """Observe a completed sibling without returning raw student state."""
    from .opportunity_evidence import (
        project_submission_feedback_observation_for_opportunity as project,
    )

    assignment = get(
        f"/courses/{course_id}/assignments/{assignment_id}",
        include=["submission"],
    )
    return project(assignment)


def list_assignments(course_id: str | int) -> list[dict]:
    return paginate(
        f"/courses/{course_id}/assignments",
        per_page=50,
        order_by="due_at",
        include=["submission"],
    )


def get_assignment(course_id: str | int, assignment_id: str | int) -> dict:
    return get(
        f"/courses/{course_id}/assignments/{assignment_id}",
        include=["submission"],
    )


def get_syllabus_body(course_id: str | int) -> str:
    """Return the course syllabus HTML body, or an empty string."""
    course = get(f"/courses/{course_id}", include=["syllabus_body"])
    return str(course.get("syllabus_body") or "")


def list_assignment_files(course_id: str | int, assignment_id: str | int) -> list[dict]:
    """Return assignment attachments plus Canvas file links in its body."""
    assignment = get(
        f"/courses/{course_id}/assignments/{assignment_id}",
        include=["submission"],
    )
    files: list[dict] = [
        dict(item) for item in (assignment.get("attachments") or []) if isinstance(item, dict)
    ]
    seen = {str(item.get("id")) for item in files if item.get("id") is not None}
    for file_id in extract_file_ids(assignment.get("description")):
        if str(file_id) in seen:
            continue
        files.append(get_file(file_id))
        seen.add(str(file_id))
    return files


def get_rubric(course_id: str | int, assignment_id: str | int) -> list[dict]:
    """Return the Canvas-attached assignment rubric, if one exists."""
    assignment = get(
        f"/courses/{course_id}/assignments/{assignment_id}",
        include=["rubric"],
    )
    rubric = assignment.get("rubric") or []
    return [dict(item) for item in rubric if isinstance(item, dict)]


def get_submission(course_id: str | int, assignment_id: str | int) -> dict:
    return get(
        f"/courses/{course_id}/assignments/{assignment_id}/submissions/self"
    )


def get_file(file_id: str | int) -> dict:
    return get(f"/files/{file_id}")


# ---------- Modules / Pages / Front page ----------

def get_front_page(course_id: str | int) -> dict:
    return get(f"/courses/{course_id}/front_page")


def list_modules(course_id: str | int) -> list[dict]:
    return paginate(f"/courses/{course_id}/modules", per_page=50)


def list_module_items(course_id: str | int, module_id: str | int) -> list[dict]:
    return paginate(f"/courses/{course_id}/modules/{module_id}/items", per_page=50)


def get_page(course_id: str | int, page_url: str) -> dict:
    return get(f"/courses/{course_id}/pages/{page_url}")


def list_folders(course_id: str | int) -> list[dict]:
    return paginate(f"/courses/{course_id}/folders", per_page=50)


def list_files_in_folder(folder_id: str | int) -> list[dict]:
    return paginate(f"/folders/{folder_id}/files", per_page=50)


def get_quiz_submission_questions(submission_id: str | int) -> list[dict]:
    """Student-side endpoint that returns questions for an open quiz submission.
    /quizzes/<id>/questions returns 403 for students; this works."""
    base_root = BASE.rsplit('/api', 1)[0]
    url = f"{base_root}/api/v1/quiz_submissions/{submission_id}/questions"
    data = _backend.get(url, params={"per_page": 50})
    return data.get("quiz_submission_questions", [])


def download_file(url: str, dest: Path) -> Path:
    """Download a Canvas file (URL must include verifier or be authenticated)."""
    return _backend.download(url, dest)


# ---------- Quiz API ----------

def list_quizzes(course_id: str | int) -> list[dict]:
    return paginate(f"/courses/{course_id}/quizzes", per_page=50)


def get_quiz(course_id: str | int, quiz_id: str | int) -> dict:
    return get(f"/courses/{course_id}/quizzes/{quiz_id}")


def get_quiz_questions(course_id: str | int, quiz_id: str | int) -> list[dict]:
    return paginate(f"/courses/{course_id}/quizzes/{quiz_id}/questions", per_page=50)


def _find_quiz_work_dir(course_id: str | int, quiz_id: str | int) -> Path | None:
    """Locate the work_dir for this (course_id, quiz_id) by scanning
    runs/<date>/<slug>/quiz_meta.json files. Returns the work_dir Path or
    None if no matching meta file exists.

    Scans newest-date-first under ROOT/runs/. Match is by quiz_meta.json's
    `id` field (Canvas quiz id) — course_id is verified as a sanity check.
    """
    cid = str(course_id)
    qid = str(quiz_id)
    runs_root = ROOT / "runs"
    if not runs_root.exists():
        return None
    date_dirs = sorted(
        (d for d in runs_root.iterdir() if d.is_dir() and re.match(r"\d{4}-\d{2}-\d{2}", d.name)),
        reverse=True,
    )
    for date_dir in date_dirs:
        for work_dir in date_dir.iterdir():
            if not work_dir.is_dir():
                continue
            meta = work_dir / "quiz_meta.json"
            if not meta.exists():
                continue
            try:
                data = json.loads(meta.read_text(encoding="utf-8"))
            except Exception:
                continue
            if (
                str(data.get("course_id", "")) == cid
                and str(data.get("id", data.get("quiz_id", ""))) == qid
            ):
                return work_dir
    return None


def _quiz_receipt_context(authorization_receipt: Any) -> dict[str, Any]:
    """Return the non-secret receipt fields used to bind quiz evidence."""

    from .authorization import load_authorization_receipt

    if isinstance(authorization_receipt, Mapping):
        receipt = dict(authorization_receipt)
    elif authorization_receipt is not None:
        receipt = load_authorization_receipt(authorization_receipt)
    else:
        raise QuizArbitrationEvidenceMissing(
            "bound quiz evidence requires the same signed authorization receipt "
            "used by the mutation call"
        )
    receipt_id = receipt.get("receipt_id")
    session_id = receipt.get("session_id")
    if not isinstance(receipt_id, str) or not receipt_id.strip():
        raise QuizArbitrationEvidenceMissing(
            "bound quiz evidence requires authorization_receipt_id"
        )
    if not isinstance(session_id, str) or not session_id.strip():
        raise QuizArbitrationEvidenceMissing(
            "bound quiz evidence requires the receipt session_id"
        )
    return {"receipt_id": receipt_id.strip(), "session_id": session_id.strip()}


def _bound_quiz_context(
    *,
    course_id: str | int,
    quiz_id: str | int,
    assignment_id: str | int | None,
    attempt: int | None,
    authorization_receipt: Any,
) -> dict[str, Any]:
    """Build the exact context every current-attempt evidence file must carry."""

    from .authorization import current_authorization_session

    if assignment_id is None or not str(assignment_id).strip():
        raise QuizArbitrationEvidenceMissing(
            "Codex quiz mutations require the exact assignment_id"
        )
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
        raise QuizArbitrationEvidenceMissing(
            "Codex quiz mutations require the current positive integer attempt"
        )
    receipt_context = _quiz_receipt_context(authorization_receipt)
    current_session = current_authorization_session()
    if not current_session:
        raise QuizArbitrationEvidenceMissing(
            "Codex quiz mutations require a current session identifier"
        )
    if receipt_context["session_id"] != current_session:
        raise QuizArbitrationEvidenceMissing(
            "quiz evidence receipt session does not match the current Codex session"
        )
    return {
        "course_id": str(course_id),
        "quiz_id": str(quiz_id),
        "assignment_id": str(assignment_id),
        "session_id": current_session,
        "attempt": attempt,
        "authorization_receipt_id": receipt_context["receipt_id"],
    }


def _validate_quiz_context_object(
    value: Any,
    expected: Mapping[str, Any],
    *,
    artifact: str,
) -> None:
    if not isinstance(value, Mapping):
        raise QuizArbitrationEvidenceMissing(
            f"{artifact} must contain a context object bound to this quiz attempt"
        )
    for field, expected_value in expected.items():
        actual = value.get(field)
        if field == "attempt":
            matches = (
                not isinstance(actual, bool)
                and isinstance(actual, int)
                and actual == expected_value
            )
        else:
            matches = str(actual) == str(expected_value)
        if not matches:
            raise QuizArbitrationEvidenceMissing(
                f"{artifact} context.{field} does not match the current quiz attempt"
            )


def _explicit_quiz_work_dir(
    work_dir: Path | str | None,
    *,
    course_id: str | int,
    quiz_id: str | int,
    assignment_id: str | int | None,
    expected_context: Mapping[str, Any],
) -> Path:
    """Validate the single stable work directory and its current quiz metadata."""

    from .run_state import stable_work_dir

    if work_dir is None:
        raise QuizArbitrationEvidenceMissing(
            "Codex answer/complete calls require explicit work_dir"
        )
    candidate = Path(work_dir).resolve()
    if not candidate.is_dir():
        raise QuizArbitrationEvidenceMissing(
            "explicit quiz work_dir does not exist or is not a directory"
        )
    run_dir = candidate.parent
    runs_root = (ROOT / "runs").resolve()
    if (
        run_dir.parent.resolve() != runs_root
        or re.fullmatch(r"\d{4}-\d{2}-\d{2}", run_dir.name) is None
    ):
        raise QuizArbitrationEvidenceMissing(
            "explicit quiz work_dir must be under runs/<YYYY-MM-DD>/"
        )
    expected_dir = stable_work_dir(run_dir, course_id, assignment_id).resolve()
    if candidate != expected_dir:
        raise QuizArbitrationEvidenceMissing(
            "explicit quiz work_dir is not the stable "
            "course-<course_id>__assignment-<assignment_id> directory"
        )

    meta_path = candidate / "quiz_meta.json"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise QuizArbitrationEvidenceMissing(
            "explicit quiz work_dir requires valid quiz_meta.json"
        ) from exc
    if not isinstance(meta, Mapping):
        raise QuizArbitrationEvidenceMissing("quiz_meta.json must be a JSON object")
    if str(meta.get("id", "")) != str(quiz_id):
        raise QuizArbitrationEvidenceMissing(
            "quiz_meta.json id does not match the current quiz_id"
        )
    _validate_quiz_context_object(meta, expected_context, artifact="quiz_meta.json")
    return candidate


def _require_canonical_arbitration_evidence(
    course_id: str | int,
    quiz_id: str | int,
    *,
    work_dir: Path | str | None = None,
    assignment_id: str | int | None = None,
    attempt: int | None = None,
    authorization_receipt: Any = None,
    require_bound_context: bool = False,
) -> Path:
    """Hard gate: refuse quiz state-changing API calls unless the canonical
    canvas-inside SKILL.md §7 4-agent arbitration left evidence in the work_dir.

    Required artifacts inside `<runs/<date>/<slug>>/`:
      - `quiz_meta.json` (already required to locate the dir)
      - `final_answers.json` with `arbitration_notes.unanimous_count` (int)
      - `agent_passes/` directory with at least 4 `.json` files
      - Four substantive pass payloads that are not canonical copy-pastes

    In an enforced Codex mutation path, callers also supply the explicit stable
    work_dir plus assignment, attempt, session, and receipt context.  Every
    evidence artifact must bind to that same context.  Direct legacy unit-test
    calls may omit those extra values; production answer/complete calls may not.

    Raises QuizArbitrationEvidenceMissing on any failure. Returns the
    work_dir Path on success.

    NOTE: an explicit override exists for the case where the user has
    granted in-session authorization for a degraded method. Set
    CANVAS_QUIZ_DEGRADED_OK=<verbatim user quote> in the environment for
    that one process. The override is intentionally awkward (env var with
    real text content, not a boolean) so it leaves an audit trail and
    can't be flipped on accident.
    """
    expected_context: dict[str, Any] | None = None
    if require_bound_context:
        expected_context = _bound_quiz_context(
            course_id=course_id,
            quiz_id=quiz_id,
            assignment_id=assignment_id,
            attempt=attempt,
            authorization_receipt=authorization_receipt,
        )
        resolved_work_dir = _explicit_quiz_work_dir(
            work_dir,
            course_id=course_id,
            quiz_id=quiz_id,
            assignment_id=assignment_id,
            expected_context=expected_context,
        )
    elif work_dir is not None:
        resolved_work_dir = Path(work_dir).resolve()
        meta_path = resolved_work_dir / "quiz_meta.json"
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise QuizArbitrationEvidenceMissing(
                "explicit legacy work_dir requires valid quiz_meta.json"
            ) from exc
        if (
            not isinstance(meta, Mapping)
            or str(meta.get("course_id", "")) != str(course_id)
            or str(meta.get("id", meta.get("quiz_id", ""))) != str(quiz_id)
        ):
            raise QuizArbitrationEvidenceMissing(
                "explicit legacy work_dir quiz_meta.json does not match course_id + quiz_id"
            )
    else:
        resolved_work_dir = _find_quiz_work_dir(course_id, quiz_id)

    override = os.environ.get("CANVAS_QUIZ_DEGRADED_OK", "").strip()
    if override and len(override) > 10:
        # Caller has explicit human authorization. Still log to stderr so
        # it's visible in the session.
        print(
            f"warning: canvas-inside evidence gate bypassed via "
            f"CANVAS_QUIZ_DEGRADED_OK={override!r}",
            file=sys.stderr,
        )
        if resolved_work_dir is not None:
            return resolved_work_dir
        # Even with override, we need a work_dir to write result.json into.
        raise QuizArbitrationEvidenceMissing(
            f"override active but no work_dir found for course={course_id} quiz={quiz_id} — "
            f"create runs/<today>/<slug>/quiz_meta.json first"
        )

    if resolved_work_dir is None:
        raise QuizArbitrationEvidenceMissing(
            f"no work_dir with quiz_meta.json matching course={course_id} quiz={quiz_id}. "
            f"canvas-inside SKILL.md §1 requires saving quiz metadata to "
            f"<work>/quiz_meta.json before any state-changing call."
        )

    final_answers = resolved_work_dir / "final_answers.json"
    if not final_answers.exists():
        raise QuizArbitrationEvidenceMissing(
            f"{final_answers.relative_to(ROOT).as_posix()} missing. "
            f"canvas-inside SKILL.md §7c requires writing final_answers.json with "
            f"arbitration_notes after 4-agent dispatch + tabulation."
        )
    try:
        fa_data = json.loads(final_answers.read_text(encoding="utf-8"))
    except Exception as e:
        raise QuizArbitrationEvidenceMissing(
            f"{final_answers.relative_to(ROOT).as_posix()} is not valid JSON: {e}"
        )

    notes = fa_data.get("arbitration_notes")
    if not isinstance(notes, dict) or not isinstance(notes.get("unanimous_count"), int):
        raise QuizArbitrationEvidenceMissing(
            f"{final_answers.relative_to(ROOT).as_posix()} missing "
            f"arbitration_notes.unanimous_count (int). This field is the marker "
            f"that 4-agent arbitration actually ran — see SKILL.md §7c. "
            f"Self-stamped 'method: single-pass' style notes do NOT satisfy this gate."
        )

    if expected_context is not None:
        _validate_quiz_context_object(
            fa_data.get("context"),
            expected_context,
            artifact="final_answers.json",
        )

    passes_dir = resolved_work_dir / "agent_passes"
    if not passes_dir.is_dir():
        raise QuizArbitrationEvidenceMissing(
            f"{passes_dir.relative_to(ROOT).as_posix()}/ directory missing. "
            f"canvas-inside SKILL.md §7b requires saving each of the 4 agents' raw "
            f"answer JSON files here before arbitration."
        )
    pass_files = sorted(p for p in passes_dir.glob("*.json") if p.is_file())
    if len(pass_files) < 4:
        raise QuizArbitrationEvidenceMissing(
            f"{passes_dir.relative_to(ROOT).as_posix()}/ has {len(pass_files)} "
            f"agent_pass file(s); need ≥4. SKILL.md §7b mandates 4 parallel "
            f"agent dispatches with distinct priming."
        )

    # Anti-copy-paste: consensus is valid, but the complete substantive
    # answers/reasoning payload cannot be canonically identical in all 4 files.
    pass_payloads: list[Any] = []
    for pf in pass_files[:4]:
        try:
            payload = json.loads(pf.read_text(encoding="utf-8"))
        except Exception as e:
            raise QuizArbitrationEvidenceMissing(
                f"{pf.relative_to(ROOT).as_posix()} not valid JSON: {e}"
            )
        if expected_context is not None:
            if not isinstance(payload, Mapping) or not isinstance(payload.get("answers"), list):
                raise QuizArbitrationEvidenceMissing(
                    f"{pf.relative_to(ROOT).as_posix()} must be an evidence envelope "
                    f"with context and answers"
                )
            _validate_quiz_context_object(
                payload.get("context"),
                expected_context,
                artifact=pf.name,
            )
        pass_payloads.append(payload)

    def _canonical_substantive_pass(payload: Any) -> str:
        """Canonicalize substantive answers/reasoning, ignoring envelope labels.

        Honest agents may unanimously choose the same answers.  Their independent
        reasoning/source checks remain distinct, while a cloned array stays
        identical even if the caller changes only ``agent_role`` or context.
        """

        substantive = payload.get("answers") if isinstance(payload, Mapping) else payload
        return json.dumps(
            substantive,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )

    canonical_payloads = {_canonical_substantive_pass(p) for p in pass_payloads}
    if len(canonical_payloads) < 2:
        raise QuizArbitrationEvidenceMissing(
            f"{passes_dir.relative_to(ROOT).as_posix()}/ contains 4 files but "
            f"all substantive pass payloads are canonically identical. Unanimous "
            f"answers are allowed, but copied answers plus reasoning are not "
            f"independent arbitration."
        )

    return resolved_work_dir


def start_quiz_submission(
    course_id: str | int,
    quiz_id: str | int,
    *,
    authorization_receipt=None,
    is_retake: bool = False,
) -> dict:
    action = "quiz.retake" if is_retake else "quiz.start"
    return post(
        f"/courses/{course_id}/quizzes/{quiz_id}/submissions",
        authorization_receipt=authorization_receipt,
        mutation_action=action,
        mutation_course_id=course_id,
        mutation_target_type="quiz",
        mutation_target_id=quiz_id,
    )


def answer_quiz_questions(
    quiz_submission_id: str | int,
    attempt: int,
    validation_token: str,
    answers: list[dict],
    course_id: str | int | None = None,
    quiz_id: str | int | None = None,
    *,
    assignment_id: str | int | None = None,
    work_dir: Path | str | None = None,
    authorization_receipt=None,
) -> Any:
    """Post answers to an open quiz submission.

    Legacy non-Codex callers may omit the context kwargs.  In an enforced Codex
    runtime, course_id, quiz_id, assignment_id, and explicit work_dir are all
    mandatory and the evidence must bind to this session, attempt, and receipt.
    """
    from .authorization import mutation_authorization_enforced

    enforce_bound_context = mutation_authorization_enforced()
    if enforce_bound_context and (
        course_id is None
        or quiz_id is None
        or assignment_id is None
        or work_dir is None
    ):
        raise QuizArbitrationEvidenceMissing(
            "Codex answer_quiz_questions requires course_id, quiz_id, "
            "assignment_id, and explicit work_dir"
        )
    if course_id is not None and quiz_id is not None:
        if enforce_bound_context:
            # Validate signed scope without consuming it, bind the local evidence,
            # then record this exact mutation immediately before the backend call.
            _authorize_mutation(
                authorization_receipt,
                action="quiz.answer",
                course_id=course_id,
                target_type="quiz",
                target_id=quiz_id,
                track_usage=False,
            )
        _require_canonical_arbitration_evidence(
            course_id,
            quiz_id,
            work_dir=work_dir,
            assignment_id=assignment_id,
            attempt=attempt,
            authorization_receipt=authorization_receipt,
            require_bound_context=enforce_bound_context,
        )
    else:
        print(
            "warning: answer_quiz_questions called without course_id/quiz_id "
            "kwargs — evidence gate skipped (complete_quiz_submission will still gate). "
            "Update caller to pass course_id=, quiz_id= per SKILL.md §8.",
            file=sys.stderr,
        )
    _authorize_mutation(
        authorization_receipt,
        action="quiz.answer",
        course_id=course_id,
        target_type="quiz",
        target_id=quiz_id,
    )
    base_root = BASE.rsplit('/api', 1)[0]
    url = f"{base_root}/api/v1/quiz_submissions/{quiz_submission_id}/questions"
    return _backend.post_json(url, {
        "attempt": attempt,
        "validation_token": validation_token,
        "quiz_questions": answers,
    })


def complete_quiz_submission(
    course_id: str | int,
    quiz_id: str | int,
    submission_id: str | int,
    attempt: int,
    validation_token: str,
    *,
    assignment_id: str | int | None = None,
    work_dir: Path | str | None = None,
    authorization_receipt=None,
) -> Any:
    from .authorization import mutation_authorization_enforced

    enforce_bound_context = mutation_authorization_enforced()
    if enforce_bound_context and (assignment_id is None or work_dir is None):
        raise QuizArbitrationEvidenceMissing(
            "Codex complete_quiz_submission requires assignment_id and explicit work_dir"
        )
    if enforce_bound_context:
        _authorize_mutation(
            authorization_receipt,
            action="quiz.complete",
            course_id=course_id,
            target_type="quiz",
            target_id=quiz_id,
            track_usage=False,
        )
    _require_canonical_arbitration_evidence(
        course_id,
        quiz_id,
        work_dir=work_dir,
        assignment_id=assignment_id,
        attempt=attempt,
        authorization_receipt=authorization_receipt,
        require_bound_context=enforce_bound_context,
    )
    _authorize_mutation(
        authorization_receipt,
        action="quiz.complete",
        course_id=course_id,
        target_type="quiz",
        target_id=quiz_id,
    )
    return _backend.post_json(
        f"{BASE}/courses/{course_id}/quizzes/{quiz_id}/submissions/{submission_id}/complete",
        {"attempt": attempt, "validation_token": validation_token},
    )


def post_quiz_events(
    course_id: str | int,
    quiz_id: str | int,
    events: list[dict],
    *,
    authorization_receipt=None,
) -> Any:
    """Post the submission events that the Canvas web UI normally generates
    as the student interacts with the quiz (session_started, question_viewed,
    page_focused, ...). Without these, instructor-side analytics show an
    empty event list which is itself a signal."""
    _authorize_mutation(
        authorization_receipt,
        action="quiz.event",
        course_id=course_id,
        target_type="quiz",
        target_id=quiz_id,
    )
    return _backend.post_json(
        f"{BASE}/courses/{course_id}/quizzes/{quiz_id}/submissions/self/events",
        {"quiz_submission_events": events},
    )


def get_quiz_attempt_feedback(course_id: str | int, quiz_id: str | int, submission_id: str | int) -> dict | None:
    """After attempt 1 completes, fetch per-question correctness if the quiz
    settings allow students to see correct answers.

    Returns a dict shaped like:
      {
        "settings_visible": True,
        "fetched_at": "<iso>",
        "per_question": [
          {"question_id": <id>, "answer_ids_marked_correct": [<id>, ...]},
          ...
        ],
      }
    or None if `quiz['show_correct_answers']` is False (instructor disabled
    feedback) or the time-window for visibility hasn't opened / has closed
    (`show_correct_answers_at` / `hide_correct_answers_at`).

    The returned `per_question.answer_ids_marked_correct` is what the §10
    feedback-driven retake flow uses as ground truth for attempt 2.
    """
    import datetime as _dt

    quiz = get_quiz(course_id, quiz_id)
    if not quiz.get("show_correct_answers", False):
        return None

    # Visibility window: if show_correct_answers_at is in the future, not
    # visible yet. If hide_correct_answers_at is in the past, already hidden.
    now = _dt.datetime.now(_dt.timezone.utc)

    def _parse(ts: str | None) -> _dt.datetime | None:
        if not ts:
            return None
        try:
            return _dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            return None

    show_at = _parse(quiz.get("show_correct_answers_at"))
    hide_at = _parse(quiz.get("hide_correct_answers_at"))
    if show_at and now < show_at:
        return None
    if hide_at and now > hide_at:
        return None

    # Refetch the questions endpoint after completion. Canvas marks correct
    # answers via `answers[].weight == 100` when feedback is visible.
    questions = get_quiz_submission_questions(submission_id)
    per_question = []
    for q in questions:
        correct_ids = []
        for a in q.get("answers", []) or []:
            if a.get("weight") == 100:
                correct_ids.append(a.get("id"))
        per_question.append({
            "question_id": q.get("id"),
            "answer_ids_marked_correct": correct_ids,
        })

    return {
        "settings_visible": True,
        "fetched_at": now.isoformat(),
        "per_question": per_question,
    }


# ---------- Submission API ----------

def submit_text(
    course_id: str | int,
    assignment_id: str | int,
    body: str,
    *,
    authorization_receipt=None,
) -> dict:
    return post_form(
        f"/courses/{course_id}/assignments/{assignment_id}/submissions",
        {"submission[submission_type]": "online_text_entry",
         "submission[body]": body},
        authorization_receipt=authorization_receipt,
        mutation_action="assignment.submit_text",
        mutation_course_id=course_id,
        mutation_target_type="assignment",
        mutation_target_id=assignment_id,
    )


def submit_url(
    course_id: str | int,
    assignment_id: str | int,
    url: str,
    *,
    authorization_receipt=None,
) -> dict:
    return post_form(
        f"/courses/{course_id}/assignments/{assignment_id}/submissions",
        {"submission[submission_type]": "online_url",
         "submission[url]": url},
        authorization_receipt=authorization_receipt,
        mutation_action="assignment.submit_url",
        mutation_course_id=course_id,
        mutation_target_type="assignment",
        mutation_target_id=assignment_id,
    )


# ---------- File upload (3-step Canvas dance) ----------

def upload_submission_file(
    course_id: str | int,
    assignment_id: str | int,
    local_path: Path,
    *,
    authorization_receipt=None,
) -> dict:
    """3-step Canvas file upload scoped to a student submission.

    Step 1: POST init to Canvas → upload_url + upload_params (via backend).
    Step 2: multipart POST file content to upload_url (S3 — uses raw `requests`
            because it's a different domain with pre-signed auth, not Canvas).
    Step 3: 201 → file dict in body. 3xx → GET the Location header (back to
            Canvas, via backend so cookies/token are reattached).
    """
    # Validate the complete two-mutation upload scope before initializing an
    # upload slot, so an init-only receipt cannot leave an orphaned partial.
    _authorize_mutation(
        authorization_receipt,
        action="assignment.upload_init",
        course_id=course_id,
        target_type="assignment",
        target_id=assignment_id,
        track_usage=False,
    )
    _authorize_mutation(
        authorization_receipt,
        action="assignment.upload_blob",
        course_id=course_id,
        target_type="assignment",
        target_id=assignment_id,
        track_usage=False,
    )
    size = local_path.stat().st_size
    name = local_path.name
    init = post_form(
        f"/courses/{course_id}/assignments/{assignment_id}/submissions/self/files",
        {"name": name,
         "size": str(size),
         "content_type": "application/octet-stream",
         "on_duplicate": "rename"},
        authorization_receipt=authorization_receipt,
        mutation_action="assignment.upload_init",
        mutation_course_id=course_id,
        mutation_target_type="assignment",
        mutation_target_id=assignment_id,
    )
    upload_url = init.get("upload_url")
    params = init.get("upload_params") or {}
    if not upload_url:
        raise RuntimeError(f"step 1 returned no upload_url: {init}")

    # The binary upload is a second mutation on a pre-signed origin.  It is
    # still scoped by the Canvas assignment receipt and is checked immediately
    # before the raw requests call.
    _authorize_mutation(
        authorization_receipt,
        action="assignment.upload_blob",
        course_id=course_id,
        target_type="assignment",
        target_id=assignment_id,
    )
    with open(local_path, "rb") as fh:
        # File field MUST be last per Canvas docs.
        files = {"file": (name, fh, "application/octet-stream")}
        # Step 2: raw requests — S3 pre-signed URL, our auth would be wrong.
        r = requests.post(upload_url, data=params, files=files,
                          allow_redirects=False, timeout=300)
    if r.status_code == 201:
        return r.json()
    if r.status_code in (301, 302, 303, 307, 308):
        loc = r.headers.get("Location")
        if not loc:
            raise RuntimeError(f"step 2 redirected with no Location: {r.status_code}")
        # Step 3: redirect points back to Canvas — go through backend so the
        # auth state (Bearer token OR Playwright cookies) is attached.
        return _backend.get(loc)
    r.raise_for_status()
    return r.json() if r.content else {}


def submit_files(
    course_id: str | int,
    assignment_id: str | int,
    file_ids: list,
    *,
    authorization_receipt=None,
) -> dict:
    """Create an online_upload submission referencing already-uploaded file ids.
    Uses repeated form key 'submission[file_ids][]' which is what Canvas expects."""
    flat: list[tuple[str, str]] = [("submission[submission_type]", "online_upload")]
    for fid in file_ids:
        flat.append(("submission[file_ids][]", str(fid)))
    return post_form(
        f"/courses/{course_id}/assignments/{assignment_id}/submissions",
        flat,
        authorization_receipt=authorization_receipt,
        mutation_action="assignment.submit_files",
        mutation_course_id=course_id,
        mutation_target_type="assignment",
        mutation_target_id=assignment_id,
    )


# ---------- File link extraction ----------

FILE_LINK_RE = re.compile(r'/courses/(\d+)/files/(\d+)')


def extract_file_ids(html: str | None) -> list[str]:
    if not html:
        return []
    return list({m.group(2) for m in FILE_LINK_RE.finditer(html)})


# ---------- CLI ----------

def _main():
    args = sys.argv[1:]
    if args and args[0] == "--forget-credentials":
        from . import canvas_credentials
        try:
            removed = canvas_credentials.forget_credentials()
        except canvas_credentials.CredentialStorageError as exc:
            print(f"Failed to forget stored SSO credentials: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc
        if canvas_credentials.has_stored_credentials():
            print(
                "Failed to forget stored SSO credentials: file still exists",
                file=sys.stderr,
            )
            raise SystemExit(1)
        if removed:
            print("Forgot stored SSO credentials. Next login will require manual entry.")
        else:
            print("No stored SSO credentials found — nothing to forget.")
        return
    if not args or args[0] == "--probe":
        me = get_self()
        print(f"OK Canvas user: {me.get('name')} (id={me.get('id')})")
        courses = list_courses()
        print(f"{len(courses)} active courses:")
        for c in courses:
            print(f"  {c.get('id')} | {c.get('course_code')} | {c.get('name')}")
        return
    if args[0] == "--courses":
        print(json.dumps(list_courses(), indent=2))
        return
    if args[0] == "--assignments" and len(args) >= 2:
        cid = args[1]
        for a in list_assignments(cid):
            sub = a.get("submission") or {}
            print(f"  {a.get('id')} | due={a.get('due_at')} | submitted={sub.get('workflow_state')} | {a.get('name')}")
        return
    print(__doc__)


if __name__ == "__main__":
    _main()
