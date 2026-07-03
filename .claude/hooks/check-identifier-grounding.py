# SPDX-License-Identifier: AGPL-3.0-or-later
"""PostToolUse(Write|Edit) hook: identifier-grounding check for code deliverables.

After a result.json is written with draft_ready/submitted, extract identifiers
from the draft (a source file or code blocks inside a .pdf) and verify every
non-trivial identifier either:
  (a) appears in spec.md
  (b) appears in any file under <work>/references/
  (c) is a language builtin / keyword / common short var (i, j, n, self, ...)

If any identifier is ungrounded, exit 2 and list them.

This is the hard-edge version of check-spec-grounding: that one catches
references that were never fetched at all; this one catches identifiers
in the draft that have no upstream source even when references/ has content
(i.e. spec said "use binary_search from lecture", references/ has the lecture,
but the draft invented variable names that don't match the lecture's code).

Language dispatch is by file extension — the framework SKILL.md is language-
neutral and the overlay specifies a project's language, but here the file
extension is a reliable signal that covers the same information without
needing to parse the overlay.

| Extension                   | Parser                                       |
|-----------------------------|----------------------------------------------|
| .py                         | Python `ast` (precise; catches names, attrs) |
| .java                       | Regex (declarations + method bodies)         |
| .js / .ts / .jsx / .tsx     | Regex                                        |
| .rs                         | Regex                                        |
| .go                         | Regex                                        |
| .c / .h / .cpp / .hpp       | Regex                                        |
| .pdf                        | Extract monospace text → Python `ast` fallback|
| other                       | Pass through                                 |

Regex parsers are intentionally zero-dependency (no javalang / esprima /
syn — installing those would burden fork users). They achieve ~80%
identifier-extraction precision, which is enough for this check's purpose
(catching gross mismatches like "draft uses `target`, lecture uses `key`")
and not enough to false-positive on local edge syntax.
"""
from __future__ import annotations

import ast
import builtins
import json
import keyword
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import block, passthrough, read_event, safe_main, matches_result_json, ROOT  # noqa: E402


# Identifiers that are always OK without appearing in spec or references.
# These are loop vars, math vars, language conventions — they show up in
# every codebase and aren't a meaningful authorship signal.
COMMON_OK = {
    # loop / temp / math vars
    "i", "j", "k", "n", "m", "x", "y", "z", "_",
    "a", "b", "c", "d", "p", "q", "r", "s", "t", "u", "v", "w",
    # Python conventions
    "self", "cls",
    # Python dunders — present in every class/module, not a grader signal
    "__init__", "__str__", "__repr__", "__eq__", "__hash__", "__lt__",
    "__le__", "__gt__", "__ge__", "__ne__", "__add__", "__sub__", "__mul__",
    "__truediv__", "__floordiv__", "__mod__", "__pow__", "__neg__",
    "__pos__", "__abs__", "__bool__", "__len__", "__iter__", "__next__",
    "__contains__", "__getitem__", "__setitem__", "__delitem__", "__call__",
    "__enter__", "__exit__", "__name__", "__main__", "__doc__",
    "__class__", "__dict__", "__module__", "__file__",
    # testing
    "fixture", "setUp", "tearDown", "assertEqual", "assertTrue",
    "assertFalse", "assertRaises", "assertIn", "assertIsNone", "TestCase",
    # error / exception conventions
    "e", "err", "ex", "exc", "Exception", "ValueError", "TypeError",
    "KeyError", "IndexError", "AttributeError", "RuntimeError",
    # common short names
    "len", "min", "max", "sum", "abs", "all", "any", "map", "filter",
    "list", "dict", "set", "tuple", "str", "int", "float", "bool",
    "print", "range", "enumerate", "zip", "sorted", "reversed",
}


# ---------- Python parser ----------

def extract_py_identifiers(code: str) -> set[str]:
    """Return all ast.Name ids + attribute accesses + parameter names + def names."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
            for a in node.args.args + node.args.kwonlyargs:
                names.add(a.arg)
        elif isinstance(node, ast.ClassDef):
            names.add(node.name)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
    return names


def extract_py_from_pdf(pdf_path: Path) -> str:
    """Extract monospace (code-font) text from a PDF — preserves the code
    blocks while ignoring narrative paragraphs."""
    try:
        import fitz  # type: ignore[import-not-found]
    except ImportError:
        return ""
    try:
        doc = fitz.open(str(pdf_path))
    except Exception:
        return ""
    code_spans: list[str] = []
    for page in doc:
        for blk in page.get_text("dict").get("blocks", []):
            for line in blk.get("lines", []):
                for span in line.get("spans", []):
                    font = (span.get("font") or "").lower()
                    if "cour" in font or "mono" in font:
                        code_spans.append(span.get("text", ""))
    doc.close()
    return "\n".join(code_spans)


# ---------- Regex parsers (zero-dep) ----------

IDENT_REGEX = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _identifiers_from_declarations(code: str, declaration_keywords: tuple[str, ...]) -> set[str]:
    """Extract identifiers declared after any of `declaration_keywords`,
    plus all identifier-shaped tokens for broad-pass identifier counting.

    The keyword-anchored extraction is precise (catches `class Foo`,
    `function bar`, etc.); the broad-pass token extraction catches usages
    (`Foo()` callsites, `bar.x` attribute accesses) that the keyword pass
    misses. The union of both is the input to the grounding check.
    """
    names: set[str] = set()
    # Precise: declaration keyword + identifier
    kw_pattern = r"\b(?:" + "|".join(declaration_keywords) + r")\s+(\w+)"
    for m in re.finditer(kw_pattern, code):
        names.add(m.group(1))
    # Broad: every identifier-shaped token (filtered later against COMMON_OK
    # and language keywords)
    names |= set(IDENT_REGEX.findall(code))
    return names


JAVA_KEYWORDS = {
    "abstract", "assert", "boolean", "break", "byte", "case", "catch", "char",
    "class", "const", "continue", "default", "do", "double", "else", "enum",
    "extends", "final", "finally", "float", "for", "goto", "if", "implements",
    "import", "instanceof", "int", "interface", "long", "native", "new",
    "package", "private", "protected", "public", "return", "short", "static",
    "strictfp", "super", "switch", "synchronized", "this", "throw", "throws",
    "transient", "try", "void", "volatile", "while", "true", "false", "null",
    "var", "yield", "record", "sealed", "permits", "non-sealed",
    "String", "System", "out", "println", "print", "Object", "Integer",
    "Double", "Float", "Boolean", "Long", "Short", "Byte", "Character",
    "Math", "List", "Map", "Set", "ArrayList", "HashMap", "HashSet",
    "Exception", "RuntimeException", "Override", "args",
}


def extract_java_identifiers(code: str) -> set[str]:
    return _identifiers_from_declarations(
        code,
        ("class", "interface", "enum", "void", "int", "String", "boolean",
         "long", "double", "float", "char", "byte", "short", "var",
         "public", "private", "protected", "static", "final", "record"),
    ) - JAVA_KEYWORDS


JS_KEYWORDS = {
    "var", "let", "const", "function", "class", "extends", "return", "if",
    "else", "for", "while", "do", "switch", "case", "default", "break",
    "continue", "throw", "try", "catch", "finally", "new", "delete",
    "typeof", "instanceof", "in", "of", "void", "null", "undefined",
    "true", "false", "this", "super", "import", "export", "from", "as",
    "async", "await", "yield", "static", "get", "set",
    "console", "log", "error", "warn", "info", "Object", "Array", "String",
    "Number", "Boolean", "Promise", "Map", "Set", "JSON", "Math", "Date",
    "RegExp", "Error", "window", "document", "module", "exports", "require",
}


def extract_js_identifiers(code: str) -> set[str]:
    return _identifiers_from_declarations(
        code,
        ("var", "let", "const", "function", "class", "async\\s+function"),
    ) - JS_KEYWORDS


RUST_KEYWORDS = {
    "as", "async", "await", "break", "const", "continue", "crate", "dyn",
    "else", "enum", "extern", "false", "fn", "for", "if", "impl", "in",
    "let", "loop", "match", "mod", "move", "mut", "pub", "ref", "return",
    "self", "Self", "static", "struct", "super", "trait", "true", "type",
    "unsafe", "use", "where", "while",
    "String", "str", "Vec", "Option", "Result", "Some", "None", "Ok", "Err",
    "Box", "Rc", "Arc", "i8", "i16", "i32", "i64", "i128", "u8", "u16",
    "u32", "u64", "u128", "f32", "f64", "bool", "char", "isize", "usize",
    "println", "print", "format", "vec", "panic",
}


def extract_rust_identifiers(code: str) -> set[str]:
    return _identifiers_from_declarations(
        code,
        ("fn", "struct", "enum", "let", "const", "trait", "impl", "mod", "type", "pub\\s+fn"),
    ) - RUST_KEYWORDS


GO_KEYWORDS = {
    "break", "case", "chan", "const", "continue", "default", "defer", "else",
    "fallthrough", "for", "func", "go", "goto", "if", "import", "interface",
    "map", "package", "range", "return", "select", "struct", "switch", "type",
    "var", "true", "false", "nil", "iota",
    "string", "int", "int8", "int16", "int32", "int64", "uint", "uint8",
    "uint16", "uint32", "uint64", "byte", "rune", "bool", "float32", "float64",
    "complex64", "complex128", "error", "make", "new", "len", "cap", "append",
    "copy", "delete", "close", "panic", "recover", "fmt", "Println", "Printf",
    "Errorf", "main",
}


def extract_go_identifiers(code: str) -> set[str]:
    return _identifiers_from_declarations(
        code,
        ("func", "var", "const", "type"),
    ) - GO_KEYWORDS


C_KEYWORDS = {
    "auto", "break", "case", "char", "const", "continue", "default", "do",
    "double", "else", "enum", "extern", "float", "for", "goto", "if", "inline",
    "int", "long", "register", "restrict", "return", "short", "signed",
    "sizeof", "static", "struct", "switch", "typedef", "union", "unsigned",
    "void", "volatile", "while", "true", "false",
    # C++
    "class", "namespace", "public", "private", "protected", "virtual",
    "override", "new", "delete", "this", "template", "typename", "using",
    "try", "catch", "throw", "nullptr", "string", "vector", "std", "cout",
    "cin", "endl", "printf", "scanf", "main", "include", "define",
}


def extract_c_identifiers(code: str) -> set[str]:
    return _identifiers_from_declarations(
        code,
        ("int", "char", "long", "short", "double", "float", "void", "struct",
         "enum", "union", "static", "extern", "const", "auto", "class",
         "typedef"),
    ) - C_KEYWORDS


# ---------- Dispatch ----------

DISPATCH = {
    ".py":   ("python", extract_py_identifiers),
    ".java": ("java",   extract_java_identifiers),
    ".js":   ("js",     extract_js_identifiers),
    ".jsx":  ("js",     extract_js_identifiers),
    ".ts":   ("ts",     extract_js_identifiers),
    ".tsx":  ("ts",     extract_js_identifiers),
    ".rs":   ("rust",   extract_rust_identifiers),
    ".go":   ("go",     extract_go_identifiers),
    ".c":    ("c",      extract_c_identifiers),
    ".h":    ("c",      extract_c_identifiers),
    ".cpp":  ("cpp",    extract_c_identifiers),
    ".hpp":  ("cpp",    extract_c_identifiers),
    ".cc":   ("cpp",    extract_c_identifiers),
}


def language_keywords_for(lang: str) -> set[str]:
    if lang == "python":
        return set(dir(builtins)) | set(keyword.kwlist)
    return {
        "java":   JAVA_KEYWORDS,
        "js":     JS_KEYWORDS,
        "ts":     JS_KEYWORDS,
        "rust":   RUST_KEYWORDS,
        "go":     GO_KEYWORDS,
        "c":      C_KEYWORDS,
        "cpp":    C_KEYWORDS,
    }.get(lang, set())


def tokens_in_text(text: str) -> set[str]:
    """Coarse identifier extraction from arbitrary text (spec.md / reference files)."""
    return set(IDENT_REGEX.findall(text))


@safe_main
def main():
    event = read_event()
    if not event:
        passthrough()
    if event.get("tool_name") not in ("Write", "Edit"):
        passthrough()

    tool_input = event.get("tool_input") or {}
    file_path = tool_input.get("file_path", "")
    if not matches_result_json(file_path):
        passthrough()

    rj = Path(file_path)
    if not rj.exists():
        passthrough()
    rj = rj.resolve()

    try:
        data = json.loads(rj.read_text(encoding="utf-8"))
    except Exception:
        passthrough()

    status = data.get("status")
    if status not in ("draft_ready", "submitted"):
        passthrough()

    draft_path_str = data.get("draft_path")
    if not draft_path_str:
        passthrough()

    draft = Path(draft_path_str)
    if not draft.is_absolute():
        draft = ROOT / draft_path_str
    if not draft.exists():
        passthrough()

    suffix = draft.suffix.lower()

    # Pick parser by extension
    if suffix == ".pdf":
        draft_code = extract_py_from_pdf(draft)
        lang, parser = "python", extract_py_identifiers
    elif suffix in DISPATCH:
        draft_code = draft.read_text(encoding="utf-8", errors="ignore")
        lang, parser = DISPATCH[suffix]
    else:
        passthrough(f"identifier check: extension {suffix!r} has no parser, skip")

    if not draft_code.strip():
        passthrough("identifier check: no code in draft, skip")

    draft_idents = parser(draft_code)
    if not draft_idents:
        # Parser found nothing — fall back to broad token extraction so the
        # grounding check has something to work with.
        draft_idents = set(IDENT_REGEX.findall(draft_code))

    # Strip language keywords + common short names
    draft_idents -= language_keywords_for(lang)
    draft_idents -= COMMON_OK

    # Collect grounding source text. spec.md is the primary source — if it's
    # missing the audit cannot run meaningfully (assignments.json metadata
    # alone is insufficient grounding). Stage 1 fetch-spec is responsible for
    # writing spec.md; if it didn't, that's a fetch-spec failure, not an audit
    # failure. Skip rather than false-block.
    work_dir = rj.parent
    spec_md = work_dir / "spec.md"
    if not spec_md.exists():
        passthrough("identifier check: no spec.md, primary grounding source missing, skip")

    source_text: list[str] = [spec_md.read_text(encoding="utf-8", errors="ignore")]
    for name in ("REQUIREMENTS.md", "constraints.md"):
        p = work_dir / name
        if p.exists():
            source_text.append(p.read_text(encoding="utf-8", errors="ignore"))
    refs_dir = work_dir / "references"
    if refs_dir.exists():
        for f in refs_dir.rglob("*"):
            if f.is_file() and f.suffix.lower() in (".md", ".py", ".java", ".js",
                                                     ".ts", ".rs", ".go", ".c",
                                                     ".cpp", ".h", ".txt", ".html"):
                try:
                    source_text.append(f.read_text(encoding="utf-8", errors="ignore"))
                except Exception:
                    pass
    # Also include the assignment description itself
    aj = work_dir.parent / "assignments.json"
    if aj.exists():
        try:
            source_text.append(aj.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            pass

    if not source_text:
        passthrough("identifier check: no spec/refs to ground against, skip")

    grounded: set[str] = set()
    for txt in source_text:
        grounded |= tokens_in_text(txt)

    ungrounded = sorted(draft_idents - grounded)
    if not ungrounded:
        passthrough(f"identifier check ({lang}): all {len(draft_idents)} idents grounded")

    # Only block on identifiers that look "central" — used more than once OR
    # at least 5 chars long. Filters out one-off temp variables that aren't
    # a meaningful grader signal.
    suspicious: list[tuple[str, int]] = []
    for name in ungrounded:
        uses = len(re.findall(rf"\b{re.escape(name)}\b", draft_code))
        if uses >= 2 or len(name) >= 5:
            suspicious.append((name, uses))

    if not suspicious:
        passthrough(f"identifier check ({lang}): {len(ungrounded)} ungrounded but all low-signal")

    lines = [
        f"hook check-identifier-grounding ({lang}): UNGROUNDED IDENTIFIERS IN DRAFT.",
        "",
        f"Draft {draft.name} uses identifiers that appear NOWHERE in the spec, "
        f"requirements, or fetched references:",
        "",
    ]
    for name, uses in suspicious[:15]:
        lines.append(f"  - {name!r}  (used {uses}x)")
    lines.append("")
    lines.append(
        "This is the shape of the most common visible-to-grader code-course "
        "failure: the draft uses identifier names that don't match what the "
        "actual upstream source (lecture / textbook / starter repo) uses. "
        "The grader's autograder or rubric compares against the real source, "
        "so invented names = wrong even if the algorithm is right."
    )
    lines.append("")
    refs_path = work_dir / "references"
    try:
        refs_display = refs_path.relative_to(ROOT).as_posix()
    except ValueError:
        refs_display = refs_path.as_posix()
    lines.append(
        "→ Either (a) WebFetch the missing source and save it to "
        f"{refs_display}/, or "
        "(b) rename the draft's identifiers to match the actual spec/source, "
        "or (c) if the identifiers are genuinely your choice (no upstream to match), "
        "add a note to spec.md documenting them."
    )
    block("\n".join(lines))


if __name__ == "__main__":
    main()
