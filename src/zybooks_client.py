# SPDX-License-Identifier: AGPL-3.0-or-later
"""zyBooks REST client.

Auth model: zyBooks does NOT use cookies. The auth_token (JWT) lives in
localStorage["ember_simple_auth-session-5"], extracted by scripts/zybooks_explore.py
which does a fresh playwright login. JWT validity is ~36-48 hours.

This module reads the token from .zybooks_localstorage.json and provides
typed helpers for assignments, sections, and exercises.

Usage:
    from src import zybooks_client as zb
    zb.list_assignments()           # all assignments in the current zybook
    zb.get_section(1, 6)            # full content of chapter 1 section 6
    zb.exercises_for_section(1, 6)  # just the type=exercise resources
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parent.parent
LOCALSTORAGE_PATH = ROOT / ".zybooks_localstorage.json"
ENV_PATH = ROOT / ".env"


def _load_env() -> None:
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


_load_env()

# zyBook code; we URL-encode the ampersand
ZYBOOK_CODE = os.environ.get("ZYBOOK_CODE", "EXAMPLE_SCHOOL&EXAMPLE_COURSE_2026")
ZB = quote(ZYBOOK_CODE, safe="")

BASE = "https://zyserver.zybooks.com/v1"
BASE2 = "https://zyserver2.zybooks.com/v1"


class ZybooksAuthError(Exception):
    pass


class ZybooksTokenExpired(ZybooksAuthError):
    pass


def _load_token() -> tuple[str, int]:
    """Returns (auth_token, user_id). Raises ZybooksAuthError if no token."""
    if not LOCALSTORAGE_PATH.exists():
        raise ZybooksAuthError(
            f"{LOCALSTORAGE_PATH.name} missing. Run `python -m scripts.zybooks_explore` "
            f"first to do a fresh playwright login and dump the token."
        )
    storage = json.loads(LOCALSTORAGE_PATH.read_text(encoding="utf-8"))
    raw = storage.get("ember_simple_auth-session-5")
    if not raw:
        raise ZybooksAuthError("ember_simple_auth-session-5 missing from localStorage dump")
    session = json.loads(raw)
    auth = session.get("authenticated", {}).get("session", {})
    token = auth.get("auth_token")
    user_id = auth.get("user_id")
    if not token or not user_id:
        raise ZybooksAuthError("auth_token or user_id missing")
    return token, int(user_id)


_session = requests.Session()
_token: str | None = None
_user_id: int | None = None
_session.headers.update({
    "Accept": "application/json, text/plain, */*",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
})


def _ensure_auth(*, force_reload: bool = False) -> tuple[str, int]:
    """Load the local JWT only when an actual zyBooks request needs it.

    Importing this module must remain safe in a clean Canvas Pilot clone where
    the student has never configured zyBooks.  A missing or malformed token
    still fails closed at the first network helper call.
    """

    global _token, _user_id
    if force_reload or _token is None or _user_id is None:
        _token, _user_id = _load_token()
        _session.headers["Authorization"] = f"Bearer {_token}"
    return _token, _user_id


def clear_cached_auth() -> None:
    """Forget in-process auth so a refreshed localStorage dump is re-read."""

    global _token, _user_id
    _token = None
    _user_id = None
    _session.headers.pop("Authorization", None)


def get(path: str, base: str = BASE, **params) -> Any:
    """GET an API endpoint. Raises ZybooksTokenExpired on 401."""
    _ensure_auth()
    url = path if path.startswith("http") else f"{base}{path}"
    r = _session.get(url, params=params, timeout=30)
    if r.status_code == 401:
        clear_cached_auth()
        raise ZybooksTokenExpired(
            "JWT expired. Re-run `python -m scripts.zybooks_explore` to refresh."
        )
    r.raise_for_status()
    return r.json()


def post(path: str, base: str = BASE, **data) -> Any:
    _ensure_auth()
    url = path if path.startswith("http") else f"{base}{path}"
    r = _session.post(url, json=data, timeout=30)
    if r.status_code == 401:
        clear_cached_auth()
        raise ZybooksTokenExpired("JWT expired")
    r.raise_for_status()
    return r.json() if r.content else {}


# ---------- High level helpers ----------

def whoami() -> dict:
    _, user_id = _ensure_auth()
    return get(f"/user/{user_id}")


def list_assignments() -> list[dict]:
    """All assignments (Week N buckets) for the current zybook."""
    data = get(f"/zybook/{ZB}/assignments")
    return data.get("assignments", [])


def get_section(chapter: int | str, section: int | str) -> dict:
    """Full section content with all activities. The 'section' field of the
    response has content_resources, title, etc."""
    data = get(f"/zybook/{ZB}/chapter/{chapter}/section/{section}")
    return data.get("section", {})


def exercises_for_section(chapter: int | str, section: int | str) -> list[dict]:
    """Just the type=exercise resources from a section. These are the
    end-of-section problems CEO writes up by hand."""
    sec = get_section(chapter, section)
    return [r for r in sec.get("content_resources", []) if r.get("type") == "exercise"]


def participations_for_section(chapter: int | str, section: int | str) -> list[dict]:
    """Inline participation activities (multiple_choice / custom). These are
    NOT exercises but are graded; they're what you do as you read the section."""
    sec = get_section(chapter, section)
    return [
        r for r in sec.get("content_resources", [])
        if r.get("activity_type") == "participation"
    ]


def get_assignment_by_title(title: str) -> dict | None:
    """Find an assignment by exact title (e.g. 'Week 2'). Returns None if not found."""
    for a in list_assignments():
        if a.get("title") == title:
            return a
    return None


def sections_in_assignment(assignment: dict) -> list[tuple[int, int]]:
    """Returns [(chapter, section), ...] tuples for an assignment."""
    return [
        (s.get("chapter_number"), s.get("section_number"))
        for s in assignment.get("sections", [])
    ]


# ---------- HTML / LaTeX text extraction ----------

def extract_text_blocks(content_array: list) -> str:
    """zyBooks 'text' fields are arrays of {text, attributes} dicts. This
    flattens them to a single HTML string."""
    if not content_array:
        return ""
    out = []
    for block in content_array:
        if isinstance(block, dict):
            out.append(block.get("text", ""))
        elif isinstance(block, str):
            out.append(block)
    return "".join(out)


def exercise_to_dict(resource: dict, mandatory_only: bool = False) -> dict:
    """Convert a type=exercise resource to a clean dict suitable for rendering.

    Each exercise has N questions. Some are 'worked examples' (zyBooks shows
    them with solutions, student doesn't need to do them), others are
    'student must solve'. The marker is in `property_overrides`, a JSON-encoded
    list of {student_view: true|false}, one per question:

      student_view=true  → worked example (already has a solution in payload)
      student_view=false → student must solve (mandatory)

    If mandatory_only=True, we filter out the worked examples and only return
    the questions the student is required to write up. The setup text and
    title are still included.

    Returns: {title, setup_html, questions: [{text_html, solution_html_or_None,
    is_mandatory, original_index}]}
    """
    payload = resource.get("payload") or {}
    setup = extract_text_blocks(payload.get("setup", []))

    # Decode property_overrides to know which questions are mandatory
    overrides_raw = resource.get("property_overrides") or "[]"
    try:
        overrides = json.loads(overrides_raw) if isinstance(overrides_raw, str) else overrides_raw
    except json.JSONDecodeError:
        overrides = []

    questions = []
    for i, q in enumerate(payload.get("questions", [])):
        ov = overrides[i] if i < len(overrides) and isinstance(overrides[i], dict) else {}
        # student_view=True in property_overrides means it IS a worked example
        # (visible to student as a model answer). student_view=False means the
        # student is supposed to write the answer themselves.
        is_worked_example = bool(ov.get("student_view"))
        is_mandatory = not is_worked_example
        if mandatory_only and not is_mandatory:
            continue
        text = extract_text_blocks(q.get("text", []))
        solution = extract_text_blocks(q.get("solution", [])) if q.get("solution") else None
        questions.append({
            "text_html": text,
            "solution_html": solution,
            "is_mandatory": is_mandatory,
            "original_index": i + 1,  # 1-based original numbering
        })
    return {
        "title": resource.get("caption", ""),
        "setup_html": setup,
        "questions": questions,
    }


# ---------- CLI ----------

def _main():
    import sys
    args = sys.argv[1:]
    if not args or args[0] == "--whoami":
        u = whoami()
        _, user_id = _ensure_auth()
        user = u.get("user") or u
        print(f"OK zyBooks user: {user.get('first_name','?')} {user.get('last_name','?')}")
        print(f"   user_id: {user_id}")
        print(f"   zybook code: {ZYBOOK_CODE}")
        return
    if args[0] == "--assignments":
        for a in list_assignments():
            secs = a.get("sections", [])
            chapters = sorted({s.get("chapter_number") for s in secs if s.get("chapter_number")})
            print(f"  {a['assignment_id']:8} {a['title']:25} chapters={chapters} sections={len(secs)}")
        return
    if args[0] == "--section" and len(args) >= 3:
        ch, sec = args[1], args[2]
        s = get_section(ch, sec)
        print(f"Section {ch}.{sec}: {s.get('title','?')}")
        for r in s.get("content_resources", []):
            t = r.get("type") or "?"
            cap = (r.get("caption") or "")[:60]
            print(f"  {t:20} {cap}")
        return
    if args[0] == "--exercises" and len(args) >= 3:
        ch, sec = args[1], args[2]
        exs = exercises_for_section(ch, sec)
        for ex in exs:
            d = exercise_to_dict(ex)
            print(f"\n=== {d['title']} ===")
            print(f"Setup: {re.sub('<[^>]+>','',d['setup_html'])[:200]}")
            for i, q in enumerate(d['questions'], 1):
                txt = re.sub('<[^>]+>','',q['text_html'])[:80]
                sol = "(solution)" if q['solution_html'] else "(no solution)"
                print(f"  Q{i}: {txt} {sol}")
        return
    print(__doc__)


if __name__ == "__main__":
    _main()
