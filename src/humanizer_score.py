# SPDX-License-Identifier: AGPL-3.0-or-later
"""Score humanizer candidates against original: Levenshtein divergence, word-count
gate, lock preservation. Pure-Python, no LLM calls.

Used as the deterministic side of canvas-humanizer §7c (LLM-judge meaning gate is
performed inline by the calling session). This script accepts a JSON candidates
file and writes per-candidate scores.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def levenshtein(a: str, b: str) -> int:
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            cur[j] = min(cur[j-1] + 1, prev[j] + 1, prev[j-1] + cost)
        prev = cur
    return prev[-1]


def divergence(original: str, candidate: str) -> float:
    if not original and not candidate:
        return 0.0
    L = max(len(original), len(candidate))
    return levenshtein(original, candidate) / L


def word_count_tolerance(original_wc: int) -> tuple:
    """Sliding tolerance — short sentences get wider band (§6e)."""
    if original_wc <= 15:
        return (0.70, 1.40)
    elif original_wc <= 25:
        return (0.75, 1.30)
    else:
        return (0.80, 1.20)


def check_locks(masked_original: str, candidate: str, lock_substitutions: list) -> dict:
    """Verify candidate preserves the verbatim lock TEXT (per §6c — locks were
    substituted back into the candidate before this scoring step).

    Accepts either:
      - candidate still has [LOCK_N] placeholders (legacy/pre-substitution path)
      - candidate has verbatim lock text inlined (post-substitution path, default)
    A lock is "preserved" if either the [LOCK_N] placeholder OR the verbatim
    lock text appears in the candidate. We check by lock_n: each required lock
    must be present in one of these two forms.
    """
    required_ns = set(re.findall(r'\[LOCK_(\d+)\]', masked_original))
    missing = []
    for n in sorted(required_ns):
        # Look for the placeholder OR the verbatim text
        placeholder_present = f"[LOCK_{n}]" in candidate
        lock_text = next((s["text"] for s in lock_substitutions if str(s["lock_n"]) == n), None)
        text_present = lock_text is not None and lock_text in candidate
        if not (placeholder_present or text_present):
            missing.append(n)
    return {
        "required": sorted(required_ns),
        "missing": missing,
        "ok": len(missing) == 0,
    }


def score_candidate(original: str, masked_original: str, original_wc: int,
                    candidate: str, lock_substitutions: list) -> dict:
    cand_wc = len(candidate.split())
    lock = check_locks(masked_original, candidate, lock_substitutions)
    div = divergence(original, candidate)
    lo, hi = word_count_tolerance(original_wc)
    wc_ratio = cand_wc / original_wc if original_wc else 0.0
    wc_ok = lo <= wc_ratio <= hi
    return {
        "candidate_word_count": cand_wc,
        "original_word_count": original_wc,
        "wc_ratio": round(wc_ratio, 4),
        "wc_band": [lo, hi],
        "wc_gate_pass": wc_ok,
        "lock_check": lock,
        "lock_gate_pass": lock["ok"],
        "divergence": round(div, 4),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True, help="JSON file with {segments: [{seg_id, original, masked_original, original_word_count, candidates:[{k, strategy, method, text}]}]}")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    data = json.loads(Path(args.inp).read_text(encoding="utf-8"))
    # We need lock_substitutions from the state file to verify verbatim lock text.
    # Look it up alongside.
    state_path = Path(args.inp).parent / "_state.json"
    locks_by_seg = {}
    if state_path.exists():
        st = json.loads(state_path.read_text(encoding="utf-8"))
        for p in st.get("humanizable_paragraphs", []):
            for s in p.get("sentences", []):
                locks_by_seg[s["seg_id"]] = s.get("lock_substitutions", [])
    out_segs = []
    for seg in data["segments"]:
        locks = locks_by_seg.get(seg["seg_id"], [])
        scored = []
        for c in seg["candidates"]:
            s = score_candidate(
                seg["original"], seg["masked_original"],
                seg["original_word_count"], c["text"], locks)
            scored.append({**c, **s})
        out_segs.append({**seg, "candidates": scored})
    Path(args.out).write_text(json.dumps({"segments": out_segs}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"scored {sum(len(s['candidates']) for s in out_segs)} candidates across {len(out_segs)} segments")
    print(f"out: {args.out}")


if __name__ == "__main__":
    main()
