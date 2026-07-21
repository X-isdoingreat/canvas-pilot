# SPDX-License-Identifier: AGPL-3.0-or-later
"""Parse a Canvas zyBooks-math-course Homework description to extract the instructor's
specific list of graded exercises.

Canvas description (HTML) contains a 2-column table:
  | Suggested Practice (self-checked) | Graded for Honest Effort (GradeScope) |
  | 1) 1.6.1 a, c, f, h               | 1) 1.7.3                              |
  | 2) 1.6.2 a, c, d                  | 2) 1.7.7 b, c, i                      |
  | ...                               | ...                                   |

We want only the SECOND column ("Graded for Honest Effort"). Extract a list
of (chapter, section, exercise, parts) tuples where parts is None for "all"
or a list of letter strings.

Usage:
    refs = parse_homework_spec(canvas_html)
    # → [(1,7,3,None), (1,7,7,['b','c','i']), (1,8,3,['d','e','f']), ...]
"""
from __future__ import annotations

import re
from html.parser import HTMLParser


# Regex to match a single exercise reference like "1.7.7 b, c, i" or "1.7.3" or
# "1.10.7 c - f". The exercise number is mandatory; sub-parts are optional.
# Formats seen in the wild:
#   "1.7.3"
#   "1.7.7 b, c, i"
#   "1.7.7 b, c, *i*"   (italics from instructor markup)
#   "1.10.7 c - f"      (range)
#   "1.10.7 c-f"        (range no spaces)
#   "1.10.10 c, d, f"
EXERCISE_RE = re.compile(
    r"""
    (?:^|\s|^\d+\)\s*)         # optional list number prefix
    (\d+)\.(\d+)\.(\d+)         # chapter.section.exercise
    \s*                         # optional whitespace
    ([a-z](?:\s*[-,]\s*[a-z])*\s*[a-z]?|\s*)?  # parts: letters with commas/dashes
    """,
    re.VERBOSE | re.IGNORECASE,
)


class _GradedColumnExtractor(HTMLParser):
    """Walks Canvas's HTML and extracts ONLY the text from the second <td>
    of the first table (the 'Graded for Honest Effort' column).

    Strategy: track depth of <table>/<tr>/<td>, find the table containing
    'Graded for Honest Effort', then within each subsequent <tr>, capture
    the text content of the second <td>.
    """

    def __init__(self):
        super().__init__()
        self.in_table = 0
        self.in_tr = 0
        self.in_td = 0
        self.td_index_in_row = -1
        self.current_text_buffer: list[str] = []
        self.row_cells: list[str] = []
        self.collected_graded_cells: list[str] = []
        self.found_graded_marker = False

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.in_table += 1
        elif tag == "tr":
            self.in_tr += 1
            self.td_index_in_row = -1
            self.row_cells = []
        elif tag == "td":
            self.in_td += 1
            self.td_index_in_row += 1
            self.current_text_buffer = []
        elif tag in ("p", "br", "li"):
            # Add a space to keep text from running together
            if self.in_td:
                self.current_text_buffer.append(" ")

    def handle_endtag(self, tag):
        if tag == "td":
            text = "".join(self.current_text_buffer).strip()
            self.row_cells.append(text)
            self.in_td -= 1
        elif tag == "tr":
            # End of row — if this row has a 2nd cell, capture it
            if len(self.row_cells) >= 2:
                graded_cell = self.row_cells[1]
                # Check if this is the header row
                if "graded" in graded_cell.lower():
                    self.found_graded_marker = True
                elif self.found_graded_marker:
                    self.collected_graded_cells.append(graded_cell)
            self.in_tr -= 1
        elif tag == "table":
            self.in_table -= 1

    def handle_data(self, data):
        if self.in_td:
            self.current_text_buffer.append(data)


def _expand_letter_range(letters_str: str) -> list[str]:
    """Parse 'b, c, i' or 'c - f' or 'c-f' or 'c, d, f' or '*b*, c, i' into a list of single letters."""
    if not letters_str or not letters_str.strip():
        return []
    # Strip italic markers and other non-essential chars
    s = re.sub(r"[*_]", "", letters_str.lower())
    s = s.strip().rstrip(".,")
    out: list[str] = []
    # Split on commas first
    parts = [p.strip() for p in s.split(",")]
    for p in parts:
        # Check for range "c - f" or "c-f"
        m = re.match(r"^([a-z])\s*-\s*([a-z])$", p)
        if m:
            start = ord(m.group(1))
            end = ord(m.group(2))
            for c in range(start, end + 1):
                out.append(chr(c))
        else:
            # Single letter
            m2 = re.match(r"^([a-z])$", p)
            if m2:
                out.append(m2.group(1))
    return out


def parse_homework_spec(canvas_html: str) -> list[tuple[int, int, int, list[str] | None]]:
    """Parse a Canvas Homework description HTML and return the list of
    graded exercise references.

    Returns: [(chapter, section, exercise, parts), ...]
    where parts is a list of letters or None meaning 'all sub-parts'.
    """
    extractor = _GradedColumnExtractor()
    extractor.feed(canvas_html)

    refs: list[tuple[int, int, int, list[str] | None]] = []

    # Each cell may contain multiple exercise references (one per <p>).
    # We re-split on the list-number markers "1)", "2)", etc.
    for cell in extractor.collected_graded_cells:
        # Split on "N)" patterns
        chunks = re.split(r"\b\d+\)\s*", cell)
        for chunk in chunks:
            chunk = chunk.strip()
            if not chunk:
                continue
            # Match the chapter.section.exercise prefix
            m = re.match(
                r"^(\d+)\.\s*(\d+)\.\s*(\d+)\s*(.*?)$",
                chunk,
            )
            if not m:
                continue
            ch = int(m.group(1))
            sec = int(m.group(2))
            ex = int(m.group(3))
            tail = m.group(4).strip()
            # tail may be empty (means "all"), or have letters
            if not tail or tail.startswith(".") or "Check" in tail:
                # "1.7.3" alone, or "1.10.3 a. Check out the definition of..."
                # In the second case there ARE letters, parse them first
                pre_period = tail.split(".", 1)[0].strip() if tail else ""
                letters = _expand_letter_range(pre_period) if pre_period else []
                if letters:
                    refs.append((ch, sec, ex, letters))
                else:
                    refs.append((ch, sec, ex, None))
                continue
            letters = _expand_letter_range(tail)
            if letters:
                refs.append((ch, sec, ex, letters))
            else:
                refs.append((ch, sec, ex, None))

    return refs


def format_refs(refs: list[tuple]) -> str:
    """Pretty-print a parsed spec for verification."""
    lines = []
    for ch, sec, ex, parts in refs:
        if parts is None:
            lines.append(f"  {ch}.{sec}.{ex} (all)")
        else:
            lines.append(f"  {ch}.{sec}.{ex} {', '.join(parts)}")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    from src import canvas_client as cv
    if len(sys.argv) >= 3:
        course_id, asg_id = sys.argv[1], sys.argv[2]
        a = cv.get_assignment(course_id, asg_id)
        desc = a.get("description") or ""
        print(f"=== {a.get('name')} ===")
        refs = parse_homework_spec(desc)
        print(f"{len(refs)} graded exercise references found:")
        print(format_refs(refs))
    else:
        print("Usage: python -m src.zybooks_spec_parser <course_id> <assignment_id>")
