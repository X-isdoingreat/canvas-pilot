# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import datetime as dt
import fnmatch
import functools
import hashlib
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

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from src.run_state import (  # noqa: E402
    CANONICAL_STATUSES,
    RunStateError,
    stable_work_dir,
    validate_quiz_submission_result,
    validate_result_json as _shared_validate_result_json,
)

VALID_STATUSES = set(CANONICAL_STATUSES)
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


def validate_result_schema(
    content: str, *, work_dir: Path | None = None
) -> tuple[bool, str]:
    return _shared_validate_result_json(content, root=ROOT, work_dir=work_dir)


_QUIZ_REQUIRED_NUMERIC_FIELDS = (
    "kept_score",
    "points_possible",
    "attempts_used",
    "allowed_attempts",
)


def _validate_quiz_submitted_schema(data: dict) -> tuple[bool, str]:
    try:
        validate_quiz_submission_result(data)
    except RunStateError as exc:
        return False, str(exc)
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


def leak_patterns() -> list[str]:
    """PII/private regexes for git-content leak scanning.

    Reuses the publish-time audit patterns from scripts/push_public_snapshot.py
    (single source of truth) plus real course IDs scraped from courses.yaml.
    Fail-open: returns [] on any error so the hook never hard-fails.
    """
    pats: list[str] = []
    try:
        import importlib.util
        path = ROOT / "scripts" / "push_public_snapshot.py"
        spec = importlib.util.spec_from_file_location("_pps_audit", path)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            pats.extend(p for _, p in getattr(mod, "PII_PATTERNS", []))
    except Exception:
        pass
    try:
        cy = ROOT / "courses.yaml"
        if cy.exists():
            for m in set(re.findall(r"\b\d{5,}\b", cy.read_text(encoding="utf-8", errors="ignore"))):
                pats.append(re.escape(m))
    except Exception:
        pass
    return pats


_GIT_LEAK_TRIGGER = re.compile(
    r"\bgit\s+(?:add|commit|push)\b",
    re.IGNORECASE,
)
_SNAPSHOT_TRIGGER = re.compile(
    r"(?:^|[;&|])\s*(?:python(?:\.exe)?|py(?:\.exe)?)\s+"
    r"(?:[^\s;&|]*[/\\])?push_public_snapshot\.py\b",
    re.IGNORECASE,
)


def _public_bound_changed_files() -> list[str]:
    """Changed files (vs HEAD) that WOULD reach the public snapshot — i.e. tracked
    and NOT `export-ignore`d. gitignored files never appear in `git diff` so they
    are already excluded. This is what makes the leak scan match the real publish
    surface (scripts/push_public_snapshot.py uses `git archive`, which honors
    export-ignore), so private-but-export-ignored files (e.g. .iclicker/, dated
    dev logs) don't cause false positives.
    """
    try:
        cp = subprocess.run(
            ["git", "diff", "HEAD", "--name-only"],
            cwd=ROOT, check=False, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            encoding="utf-8", errors="replace",
        )
        files = [ln.strip() for ln in (cp.stdout or "").splitlines() if ln.strip()]
    except Exception:
        return []
    out: list[str] = []
    for f in files:
        try:
            ca = subprocess.run(
                ["git", "check-attr", "export-ignore", "--", f],
                cwd=ROOT, check=False, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                encoding="utf-8", errors="replace",
            )
            if "export-ignore: set" in (ca.stdout or ""):
                continue  # excluded from the public archive
        except Exception:
            pass
        out.append(f)
    return out


# Full public-content lifecycle scanner.  This definition intentionally
# covers all publishable states while retaining the import-compatible name.
def _git_output(root: Path, args: list[str]) -> str:
    cp = subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        encoding="utf-8",
        errors="replace",
    )
    return cp.stdout or ""


@functools.lru_cache(maxsize=1)
def _public_scanner_module():
    import importlib.util

    scanner_path = ROOT / "scripts" / "push_public_snapshot.py"
    spec = importlib.util.spec_from_file_location("_canvas_public_scanner", scanner_path)
    if not spec or not spec.loader:
        raise RuntimeError("public snapshot scanner cannot be imported")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _public_bound(root: Path, path: str) -> bool:
    if not path or path.startswith(".git/"):
        return False
    attr = _git_output(root, ["check-attr", "export-ignore", "--", path])
    return "export-ignore: set" not in attr


def _named_files(root: Path, args: list[str]) -> set[str]:
    return {line.strip() for line in _git_output(root, args).splitlines() if line.strip()}


def _worktree_and_index_blobs(root: Path) -> list[tuple[str, str, str]]:
    paths = (
        _named_files(root, ["diff", "--name-only"])
        | _named_files(root, ["diff", "--cached", "--name-only"])
        | _named_files(root, ["ls-files", "--others", "--exclude-standard"])
    )
    blobs: list[tuple[str, str, str]] = []
    for path in sorted(paths):
        if not _public_bound(root, path):
            continue
        disk = root / path
        if disk.is_file():
            try:
                blobs.append((path, "worktree", disk.read_text(encoding="utf-8", errors="ignore")))
            except OSError:
                pass
        staged = _git_output(root, ["show", f":{path}"])
        if staged:
            blobs.append((path, "index", staged))
    return blobs


def _push_remote(command: str) -> str | None:
    match = re.search(
        r"\bgit\s+push(?:\s+--?[\w=-]+)*\s+([\w.-]+)",
        command,
        re.IGNORECASE,
    )
    return match.group(1) if match else None


def _outgoing_blobs(root: Path, command: str) -> list[tuple[str, str, str]]:
    bases: list[str] = []
    remote = _push_remote(command)
    branch = _git_output(root, ["branch", "--show-current"]).strip() or "main"
    if remote:
        bases.append(f"{remote}/{branch}")
    upstream = _git_output(
        root, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]
    ).strip()
    if upstream:
        bases.append(upstream)
    bases.extend(["origin/main", "public/main"])
    base = next(
        (
            candidate
            for candidate in bases
            if _git_output(root, ["rev-parse", "--verify", candidate]).strip()
        ),
        None,
    )
    revision = f"{base}..HEAD" if base else "HEAD"
    commits = [line for line in _git_output(root, ["rev-list", revision]).splitlines() if line]
    blobs: list[tuple[str, str, str]] = []
    for commit in commits:
        paths = _named_files(
            root,
            ["diff-tree", "--root", "--no-commit-id", "--name-only", "-r", commit],
        )
        for path in sorted(paths):
            if not _public_bound(root, path):
                continue
            content = _git_output(root, ["show", f"{commit}:{path}"])
            if content:
                blobs.append((path, f"commit:{commit[:12]}", content))
    return blobs


def _snapshot_blobs(root: Path, command: str) -> list[tuple[str, str, str]]:
    if not _SNAPSHOT_TRIGGER.search(command):
        return []
    source_match = re.search(r"--source(?:=|\s+)([^\s;&|]+)", command)
    source = source_match.group(1).strip("\"'") if source_match else "origin/main"
    if not _git_output(root, ["rev-parse", "--verify", source]).strip():
        return []
    blobs: list[tuple[str, str, str]] = []
    for path in sorted(_named_files(root, ["ls-tree", "-r", "--name-only", source])):
        if not _public_bound(root, path):
            continue
        content = _git_output(root, ["show", f"{source}:{path}"])
        if content:
            blobs.append((path, f"snapshot:{source}", content))
    return blobs


def git_leak_issue(command: str, *, root: Path | None = None) -> str | None:
    """Scan untracked/index/worktree/outgoing/snapshot states before publish."""
    if not command or not (
        _GIT_LEAK_TRIGGER.search(command) or _SNAPSHOT_TRIGGER.search(command)
    ):
        return None
    repo = root or ROOT
    try:
        scanner = _public_scanner_module()
        blobs = _worktree_and_index_blobs(repo)
        if re.search(r"\bgit\s+push\b", command, re.IGNORECASE):
            blobs.extend(_outgoing_blobs(repo, command))
        blobs.extend(_snapshot_blobs(repo, command))
        seen: set[tuple[str, str, str]] = set()
        for path, source, content in blobs:
            digest = hashlib.sha256(content.encode("utf-8", errors="ignore")).hexdigest()
            marker = (path, source, digest)
            if marker in seen:
                continue
            seen.add(marker)
            hits = scanner.audit_text(
                content,
                extra_patterns=scanner.local_private_patterns(repo),
            )
            if hits:
                labels = sorted({label for _, label in hits})
                return (
                    f"public git operation blocked: {path!r} ({source}) matches "
                    f"private-data scanner label(s) {labels}. Matched values are withheld. "
                    "Move private data under an ignored/export-ignored boundary before publishing."
                )
    except Exception:
        # Hook machinery remains fail-open for internal exceptions.  The
        # snapshot publisher invokes the same scanner again before any push.
        return None
    return None


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
    needs_refs = bool(
        re.search(r"https?://|\b(?:external|provided|lecture|reference|source|starter|chapter|according to)\b", text)
    )
    if not needs_refs:
        return None
    refs = work_dir / "references"
    if not refs.exists() or not any(
        p.is_file() and p.stat().st_size > 0 for p in refs.rglob("*")
    ):
        return f"spec grounding failed: {spec.relative_to(ROOT)} mentions external/provided references but references/ is empty"
    return None


ALLOWED_IDENTIFIERS = {
    "self", "cls", "True", "False", "None", "print", "len", "range", "str",
    "int", "float", "list", "dict", "set", "tuple", "Path", "json", "re",
    "const", "let", "var", "function", "return", "class", "public", "private",
    "static", "void", "string", "boolean", "number", "interface", "extends",
}


def _extract_code_from_pdf(pdf_path: Path) -> str:
    """Extract monospace (code-font) text from a PDF — keeps code blocks, drops
    narrative. Ported from .claude/hooks/check-identifier-grounding.py. Returns ""
    if PyMuPDF is unavailable (graceful: the .pdf branch then no-ops)."""
    try:
        import fitz  # type: ignore
    except Exception:
        return ""
    try:
        doc = fitz.open(str(pdf_path))
    except Exception:
        return ""
    spans: list[str] = []
    try:
        for page in doc:
            for blk in page.get_text("dict").get("blocks", []):
                for line in blk.get("lines", []):
                    for span in line.get("spans", []):
                        font = (span.get("font") or "").lower()
                        if "cour" in font or "mono" in font:
                            spans.append(span.get("text", ""))
    except Exception:
        pass
    finally:
        try:
            doc.close()
        except Exception:
            pass
    return "\n".join(spans)


def identifier_grounding_issue(work_dir: Path, draft_path: Path | None) -> str | None:
    if not draft_path or not draft_path.exists():
        return None
    code_suffixes = {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".rs", ".go", ".c", ".cc", ".cpp", ".h", ".hpp"}
    candidates = [draft_path]
    if draft_path.is_dir():
        candidates = [
            path for path in draft_path.rglob("*")
            if path.is_file() and (path.suffix.lower() in code_suffixes or path.suffix.lower() == ".pdf")
        ]
    chunks: list[str] = []
    for candidate in candidates:
        suffix = candidate.suffix.lower()
        if suffix in code_suffixes:
            chunks.append(candidate.read_text(encoding="utf-8", errors="ignore"))
        elif suffix == ".pdf":
            chunks.append(_extract_code_from_pdf(candidate))
    draft = "\n".join(chunks)
    if not draft.strip():
        return None
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
        try:
            disp = draft_path.relative_to(ROOT).as_posix()
        except ValueError:
            disp = draft_path.name
        return f"identifier grounding failed for {disp}: ungrounded identifiers {ungrounded[:8]}"
    return None


# ---- §0 required-sources manifest (ported 1:1 from .claude/hooks/_lib.py +
#      check-source-manifest.py, return-style for post_tool_guard) ----

def overlay_path_for_skill(skill_name: str) -> Path:
    normalized = str(skill_name).strip()
    if normalized.startswith("canvas-"):
        normalized = normalized[len("canvas-"):]
    return ROOT / "_private" / f"canvas-{normalized}-app.md"


def _manifest_scope(text: str, course_id) -> str:
    first = re.search(r"^##\s+Course\s+", text, re.MULTILINE)
    if first is None:
        return text
    preamble = text[:first.start()]
    if course_id in (None, ""):
        return preamble
    cid = re.escape(str(course_id))
    m = re.search(rf"^##\s+Course\s+{cid}\b.*$", text, re.MULTILINE)
    if not m:
        return preamble
    start = m.end()
    nxt = re.search(r"^##\s+", text[start:], re.MULTILINE)
    blk = text[start: start + nxt.start()] if nxt else text[start:]
    return preamble + "\n\n" + blk


def load_required_sources(skill_name, course_id, kind, overlay_path=None) -> list:
    try:
        import yaml  # type: ignore
    except Exception:
        return []
    op = Path(overlay_path) if overlay_path else overlay_path_for_skill(str(skill_name))
    if not op.exists():
        return []
    try:
        text = op.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    block_text = _manifest_scope(text, course_id)
    merged: dict = {}
    for m in re.finditer(r"```ya?ml[^\n]*\n(.*?)\n```", block_text, re.DOTALL | re.IGNORECASE):
        try:
            parsed = yaml.safe_load(m.group(1))
        except Exception:
            continue
        if isinstance(parsed, dict) and isinstance(parsed.get("required_sources"), list):
            for s in parsed["required_sources"]:
                if isinstance(s, dict) and s.get("id"):
                    merged[s["id"]] = s
    if not merged:
        return []
    out: list = []
    for s in merged.values():
        kinds = s.get("applies_to_kinds")
        if kind in (None, ""):
            out.append(s)
        elif kinds in (None, [], "*") or (isinstance(kinds, list) and kind in kinds):
            out.append(s)
    return out


def _source_present(work_dir: Path, entry: dict) -> bool:
    if not isinstance(entry, dict):
        return False
    rel = entry.get("path")
    if not rel:
        return False
    p = Path(rel)
    if not p.is_absolute():
        p = work_dir / rel
    try:
        if not p.exists():
            return False
        if p.is_dir():
            return any(p.iterdir())
        return p.stat().st_size > 0
    except Exception:
        return False


def _load_source_acks(work_dir: Path) -> set:
    ack = work_dir / ".sources_ack"
    out: set = set()
    if not ack.exists():
        return out
    try:
        text = ack.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if obj.get("action") == "skip" and len(str(obj.get("quote", "")).strip()) >= 10:
            sid = obj.get("source_id")
            if sid:
                out.add(sid)
    return out


def _infer_source_context(work_dir: Path, result_data: dict | None = None) -> dict:
    contexts: list[dict] = []
    if isinstance(result_data, dict):
        contexts.append(result_data)
    for name in ("source_context.json", "assignment.json", "context.json"):
        path = work_dir / name
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, dict):
            contexts.append(data)

    merged: dict = {}
    for context in contexts:
        for dest, candidates in {
            "course_id": ("course_id",),
            "assignment_id": ("assignment_id",),
            "skill_name": ("skill_name", "proposed_skill", "skill"),
            "kind": ("assignment_kind", "pattern_kind", "kind"),
        }.items():
            if merged.get(dest) not in (None, ""):
                continue
            for candidate in candidates:
                if context.get(candidate) not in (None, ""):
                    merged[dest] = context[candidate]
                    break

    # Generic result kinds describe the output protocol, not an overlay's
    # recurring assignment kind.  Treat them as unknown so every mandatory
    # source declaration is considered instead of accidentally selecting none.
    if merged.get("kind") in {"quiz", "assignment", "code", "document"} and not any(
        context.get("assignment_kind") or context.get("pattern_kind") for context in contexts
    ):
        merged["kind"] = None

    plan_path = work_dir.parent / "plan.json"
    if plan_path.exists():
        try:
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
        except Exception:
            plan = {}
        for item in plan.get("items", []) if isinstance(plan, dict) else []:
            if not isinstance(item, dict):
                continue
            if item.get("course_id") in (None, "") or item.get("assignment_id") in (None, ""):
                continue
            expected = stable_work_dir(
                work_dir.parent, item["course_id"], item["assignment_id"]
            ).name
            id_match = merged.get("assignment_id") not in (None, "") and str(
                item.get("assignment_id")
            ) == str(merged.get("assignment_id"))
            if work_dir.name != expected and not id_match:
                continue
            merged.setdefault("course_id", item.get("course_id"))
            merged.setdefault("assignment_id", item.get("assignment_id"))
            merged.setdefault("skill_name", item.get("proposed_skill") or item.get("skill"))
            merged.setdefault("kind", item.get("assignment_kind") or item.get("kind"))
            break
    return merged


def source_manifest_issue(work_dir: Path, result_data: dict | None = None) -> str | None:
    """Reason string if mandatory §0 overlay sources weren't loaded for a
    draft_ready/submitted result, else None. Caller confirms status first.
    Missing ``sources.json`` is a failure when the selected overlay declares
    mandatory sources; omission is not a bypass.
    """
    receipt_path = work_dir / "sources.json"
    if receipt_path.exists():
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except Exception:
            return ("<work>/sources.json is not valid JSON. Rewrite as "
                    "{course_id, skill_name, kind, sources:{<id>:{enforcement,status,path}}}.")
        if not isinstance(receipt, dict):
            return "sources.json must be a JSON object."
    else:
        receipt = _infer_source_context(work_dir, result_data)
        receipt["sources"] = {}
    course_id = receipt.get("course_id")
    skill_name = receipt.get("skill_name")
    kind = receipt.get("kind")
    receipt_sources = receipt.get("sources")
    if not isinstance(receipt_sources, dict):
        receipt_sources = {}
    if not skill_name:
        return None
    required = load_required_sources(skill_name, course_id, kind)
    mandatory = [s for s in required if s.get("enforcement", "mandatory") == "mandatory"]
    if not mandatory:
        return None
    if not receipt_path.exists():
        return (
            "Mandatory overlay sources exist, but <work>/sources.json is missing. "
            "Write the source receipt before claiming draft_ready/submitted."
        )
    acked = _load_source_acks(work_dir)
    problems = []
    for src in mandatory:
        sid = src.get("id")
        entry = receipt_sources.get(sid) if sid else None
        status = (entry or {}).get("status")
        if status == "loaded":
            if _source_present(work_dir, entry):
                continue
            problems.append((src, "loaded-but-no-file-on-disk"))
            continue
        if status == "soft_stop_acked" and sid in acked:
            continue
        problems.append((src, status))
    if not problems:
        return None
    lines = ["MANDATORY SOURCES NOT LOADED for this draft:"]
    for src, status in problems[:10]:
        extra = f" what={src.get('what')}" if src.get("what") else ""
        lines.append(f"  - {src.get('id')} [{status or 'absent from sources.json'}]{extra}")
    lines.append(
        "Run Stage 0.5: fetch each into <work>/sources/ and set status 'loaded'; or soft-stop, "
        "ask the user, record verbatim authorization in <work>/.sources_ack and set "
        "'soft_stop_acked'. Do NOT fabricate from general knowledge."
    )
    return "\n".join(lines)
