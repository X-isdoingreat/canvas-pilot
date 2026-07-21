"""One-shot helper: read a .docx, extract paragraphs, segment to sentences,
identify regex+caller locks, mask each sentence with paragraph-global lock indices.
Writes a _state.json the calling humanizer session consumes.

Reused by canvas-humanizer atomic-pass orchestration. Idempotent.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from docx import Document
try:  # module execution: ``python -m src.humanizer_segment_extract``
    from .humanizer_segmentation import split_sentences
except ImportError:  # direct script execution: ``python src/humanizer_segment_extract.py``
    from humanizer_segmentation import split_sentences


def extract_locks(text: str, hard_locks: list) -> list:
    locks = []
    # Quoted spans (straight + curly)
    for m in re.finditer(r'"([^"]+)"|"([^"]+)"', text):
        locks.append((m.start(), m.end(), text[m.start():m.end()]))
    # Years
    for m in re.finditer(r'\b(19|20)\d{2}\b', text):
        locks.append((m.start(), m.end(), m.group(0)))
    # Percent literals (N percent, N to N percent)
    for m in re.finditer(r'\b\d+(?:\s*(?:to|and)\s*\d+)?\s+percent\b', text, re.I):
        locks.append((m.start(), m.end(), m.group(0)))
    # Dates
    for m in re.finditer(
        r'\b\d{1,2}\s+(January|February|March|April|May|June|July|August|September|October|November|December)(?:\s+\d{4})?\b'
        r'|\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:,\s*\d{4})?\b',
        text):
        locks.append((m.start(), m.end(), m.group(0)))
    # Age-cohort terms
    for m in re.finditer(
        r'\b(Gen\s*(?:Z|X|Y|Alpha)|Generation\s*(?:Z|X|Y|Alpha)|Millennials?|Boomers?|Gen\s*Z-ers|Gen-Zers)\b',
        text, re.I):
        locks.append((m.start(), m.end(), m.group(0)))
    # Caller-supplied hard locks
    for span in hard_locks:
        for m in re.finditer(re.escape(span), text):
            locks.append((m.start(), m.end(), m.group(0)))
    # Resolve overlaps: sort by start asc, length desc; greedy keep
    locks.sort(key=lambda t: (t[0], -(t[1]-t[0])))
    out, last_end = [], -1
    for s, e, sp in locks:
        if s >= last_end:
            out.append({"start": s, "end": e, "text": sp})
            last_end = e
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--draft", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--voice", default="advanced-academic-english")
    ap.add_argument("--identity", default=None)
    args = ap.parse_args()

    draft = Path(args.draft)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    doc = Document(draft)
    paragraphs = [
        {"i": i, "text": p.text}
        for i, p in enumerate(doc.paragraphs)
        if p.text.strip()
    ]

    # NE locks for the current essay. Split into public (source-material entities,
    # safe to commit) and private (student/instructor/course identity, loaded from
    # gitignored _private/ne_locks.json). The private file is created per-essay by
    # the caller; absent file → public-only mode (degrades gracefully).
    PUBLIC_ESSAY_NE_LOCKS = [
        "[Author A]", "[Author B]", "[Author C]", "[Author D]",
        "[Publication]", "[Publication]", "Current Population Survey",
        "Government Accountability Office", "Federal Trade Commission",
        "Etsy", "YouTube", "Shanghai", "Oregon",
        "noncompete agreements", "noncompete",
        "[Author A]", "[Author B]", "[Author C]", "[Author D]",
        "Gen Z",
    ]

    def _load_private_ne_locks() -> list:
        cfg = Path("_private/ne_locks.json")
        if not cfg.exists():
            return []
        try:
            data = json.loads(cfg.read_text(encoding="utf-8"))
            return [s for s in data if isinstance(s, str)]
        except (json.JSONDecodeError, OSError):
            return []

    NE_LOCKS = PUBLIC_ESSAY_NE_LOCKS + _load_private_ne_locks()

    segments_plan = []
    seg_counter = 0
    passthrough = []

    for p in paragraphs:
        wc = len(p["text"].split())
        if wc < 10:
            passthrough.append({"doc_paragraph_index": p["i"], "text": p["text"], "humanizable": False, "reason": "name-block-or-title"})
            continue

        raw_sents = split_sentences(p["text"])
        para_locks = extract_locks(p["text"], NE_LOCKS)

        cursor = 0
        sent_records = []
        for intra_idx, sent in enumerate(raw_sents):
            idx = p["text"].find(sent, cursor)
            if idx < 0:
                idx = p["text"].find(sent)
            sent_start = idx
            sent_end = idx + len(sent)
            cursor = sent_end

            # locks within this sentence (use paragraph-global indices)
            sent_locks = [(li, l) for li, l in enumerate(para_locks)
                          if l["start"] >= sent_start and l["end"] <= sent_end]

            masked = sent
            lock_subs = []
            for li, l in sorted(sent_locks, key=lambda t: -t[1]["start"]):
                rel_s = l["start"] - sent_start
                rel_e = l["end"] - sent_start
                masked = masked[:rel_s] + f"[LOCK_{li}]" + masked[rel_e:]
                lock_subs.append({"lock_n": li, "text": l["text"]})

            swc = len(sent.split())
            is_hum = swc >= 5 and not re.fullmatch(r'\s*(\[LOCK_\d+\]\s*[.,]?\s*)+', masked)

            sent_records.append({
                "seg_id": f"S{seg_counter}",
                "doc_paragraph_index": p["i"],
                "intra_para_index": intra_idx,
                "original": sent,
                "masked_original": masked,
                "lock_substitutions": lock_subs,
                "word_count": swc,
                "humanizable": is_hum,
            })
            seg_counter += 1

        segments_plan.append({
            "para_id": f"P{p['i']}",
            "doc_paragraph_index": p["i"],
            "paragraph_text": p["text"],
            "paragraph_word_count": wc,
            "paragraph_locks": para_locks,
            "sentences": sent_records,
        })

    identity = args.identity or args.voice
    state = {
        "draft_path": str(draft),
        "output_path": str(out_dir / "humanized.docx"),
        "voice_register": args.voice,
        "student_identity": identity,
        "hard_locks": [],
        "ne_locks_used": NE_LOCKS,
        "passthrough_paragraphs": passthrough,
        "humanizable_paragraphs": segments_plan,
    }

    (out_dir / "_state.json").write_text(
        json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    total = sum(len(p["sentences"]) for p in segments_plan)
    hum = sum(1 for p in segments_plan for s in p["sentences"] if s["humanizable"])
    print(f"paragraphs total: {len(paragraphs)}")
    print(f"paragraphs humanizable: {len(segments_plan)}")
    print(f"segments total: {total}")
    print(f"segments humanizable: {hum}")
    print(f"state written: {out_dir / '_state.json'}")

    for p in segments_plan:
        print(f"\n=== {p['para_id']} (doc_index={p['doc_paragraph_index']}, wc={p['paragraph_word_count']}, locks={len(p['paragraph_locks'])}) ===")
        for s in p["sentences"]:
            flag = "H" if s["humanizable"] else "."
            print(f"  [{flag}] {s['seg_id']} wc={s['word_count']}: {s['masked_original'][:120]}")


if __name__ == "__main__":
    main()
