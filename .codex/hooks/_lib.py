# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import datetime as dt
import fnmatch
import functools
import os
import keyword
import json
import re
import subprocess
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
HOOK_DIR = Path(__file__).resolve().parent

VALID_STATUSES = {"draft_ready", "submitted", "skipped", "error"}
PRIVATE_PATTERNS = [
    r"[\w.\-+]+@[\w.\-]+\.edu\b",
    r"\bcourse_id\s*[:=]\s*\d{4,}\b",
    r"\bassignment_id\s*[:=]\s*\d{4,}\b",
    r"\binstructor\s+(?:real\s+)?name\b",
]


def read_event() -> dict:
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def emit(data: dict) -> None:
    print(json.dumps(data, ensure_ascii=False))


def deny_pretool(reason: str) -> None:
    emit({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    })
    sys.exit(0)


def block_post(reason: str, context: str | None = None) -> None:
    payload = {"decision": "block", "reason": reason}
    if context:
        payload["hookSpecificOutput"] = {
            "hookEventName": "PostToolUse",
            "additionalContext": context,
        }
    emit(payload)
    sys.exit(0)


def block_stop(reason: str) -> None:
    emit({"decision": "block", "reason": reason})
    sys.exit(0)


def pass_stop() -> None:
    emit({"continue": True})
    sys.exit(0)


def safe_main(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except SystemExit:
            raise
        except BaseException:
            try:
                HOOK_DIR.mkdir(parents=True, exist_ok=True)
                with (HOOK_DIR / "hook-errors.log").open("a", encoding="utf-8") as f:
                    f.write(f"\n--- {dt.datetime.now().isoformat()} {fn.__name__} ---\n")
                    f.write(traceback.format_exc())
            except Exception:
                pass
            sys.exit(0)
    return wrapper


def today_dir() -> Path:
    return ROOT / "runs" / (os.environ.get("CODEX_TEST_DATE") or dt.date.today().isoformat())


def matches_result_json(path: str | None) -> bool:
    if not path:
        return False
    p = Path(path).as_posix()
    return p.endswith("/result.json") and (p.startswith("runs/") or "/runs/" in p)


def validate_result_schema(content: str) -> tuple[bool, str]:
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        return False, f"result.json is not valid JSON: {e}"
    if not isinstance(data, dict):
        return False, "result.json must be a JSON object"
    status = data.get("status")
    if status not in VALID_STATUSES:
        return False, f"status={status!r} is not one of {sorted(VALID_STATUSES)}"
    if status == "draft_ready":
        draft_path = data.get("draft_path")
        if not draft_path:
            return False, "draft_ready requires draft_path"
        candidate = Path(draft_path)
        if not candidate.is_absolute():
            candidate = ROOT / candidate
        if not candidate.exists():
            return False, f"draft_path does not exist: {draft_path}"
    if status == "submitted" and not (data.get("draft_path") or data.get("submitted_at")):
        return False, "submitted requires draft_path or submitted_at"
    return True, ""


def slugify(value: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_\- ]", "", value or "")
    return re.sub(r"\s+", "_", s).strip("_")[:60] or "untitled"


def batch_sections() -> dict[str, str]:
    path = ROOT / "docs" / "CODEX_BATCHES.md"
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    parts = re.split(r"(?m)^##\s+", text)
    sections: dict[str, str] = {}
    for part in parts[1:]:
        first, _, rest = part.partition("\n")
        name = first.strip()
        sections[name.split()[0]] = first + "\n" + rest
    return sections


def batch_status(batch_text: str) -> str | None:
    m = re.search(r"(?m)^status:\s*(\S+)", batch_text)
    return m.group(1) if m else None


def current_batch() -> tuple[str | None, str | None, str | None]:
    for batch_id, text in batch_sections().items():
        status = batch_status(text)
        if status == "in_progress":
            return batch_id, status, text
    for batch_id, text in batch_sections().items():
        status = batch_status(text)
        if status == "next":
            return batch_id, status, text
    return None, None, None


def allowed_patterns(batch_text: str) -> list[str]:
    lines = batch_text.splitlines()
    patterns: list[str] = []
    in_allowed = False
    for line in lines:
        if line.strip() == "allowed_files:":
            in_allowed = True
            continue
        if in_allowed:
            if line.startswith("- "):
                patterns.append(line[2:].strip())
            elif line and not line.startswith(" "):
                break
    return patterns


def _normalize(path: str) -> str:
    return path.strip().strip('"').replace("\\", "/")


def path_allowed(path: str, patterns: list[str]) -> bool:
    p = _normalize(path)
    if p.startswith("?? "):
        p = p[3:]
    for pat in patterns:
        q = _normalize(pat)
        if q.endswith("/**"):
            if p.startswith(q[:-3].rstrip("/") + "/"):
                return True
        if fnmatch.fnmatch(p, q):
            return True
        if p == q:
            return True
    return False


def changed_files() -> list[str]:
    try:
        cp = subprocess.run(
            ["git", "status", "--short"],
            cwd=ROOT,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return []
    files: list[str] = []
    for line in cp.stdout.splitlines():
        if not line.strip():
            continue
        path = line[3:] if len(line) > 3 else line
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        files.append(path.strip().strip('"'))
    return files


def contains_private_marker(text: str) -> bool:
    return any(re.search(pat, text, flags=re.IGNORECASE) for pat in PRIVATE_PATTERNS)


def validate_verification_log(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, f"missing verification.log at {path}"
    text = path.read_text(encoding="utf-8", errors="ignore")
    if "FAIL" in text:
        return False, f"verification.log contains FAIL at {path}"
    if "PASS" not in text:
        return False, f"verification.log has no PASS evidence at {path}"
    return True, ""


def spec_grounding_issue(work_dir: Path) -> str | None:
    spec = work_dir / "spec.md"
    if not spec.exists():
        return None
    text = spec.read_text(encoding="utf-8", errors="ignore").lower()
    needs_refs = any(word in text for word in ["external", "provided", "lecture", "reference", "source"])
    if not needs_refs:
        return None
    refs = work_dir / "references"
    if not refs.exists() or not any(p.is_file() for p in refs.rglob("*")):
        return f"spec grounding failed: {spec.relative_to(ROOT)} mentions external/provided references but references/ is empty"
    return None


ALLOWED_IDENTIFIERS = {
    "self", "cls", "True", "False", "None", "print", "len", "range", "str",
    "int", "float", "list", "dict", "set", "tuple", "Path", "json", "re",
}


def identifier_grounding_issue(work_dir: Path, draft_path: Path | None) -> str | None:
    if not draft_path or draft_path.suffix != ".py" or not draft_path.exists():
        return None
    draft = draft_path.read_text(encoding="utf-8", errors="ignore")
    identifiers = set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]{3,}\b", draft))
    identifiers = {x for x in identifiers if not keyword.iskeyword(x) and x not in ALLOWED_IDENTIFIERS}
    if not identifiers:
        return None
    grounding_text = ""
    for name in ["spec.md", "requirements.md", "constraints.md"]:
        path = work_dir / name
        if path.exists():
            grounding_text += "\n" + path.read_text(encoding="utf-8", errors="ignore")
    refs = work_dir / "references"
    if refs.exists():
        for path in refs.rglob("*"):
            if path.is_file() and path.suffix.lower() in {".txt", ".md", ".py", ".html"}:
                grounding_text += "\n" + path.read_text(encoding="utf-8", errors="ignore")
    ungrounded = sorted(x for x in identifiers if x not in grounding_text)
    if ungrounded:
        return f"identifier grounding failed for {draft_path.relative_to(ROOT)}: ungrounded identifiers {ungrounded[:8]}"
    return None
