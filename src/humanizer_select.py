# SPDX-License-Identifier: AGPL-3.0-or-later
"""Per-segment winner selection: filter by lock_gate + wc_gate (deterministic),
sort by divergence desc, print top candidates so the inline meaning-gate caller
can review and confirm. Does NOT do meaning-gate itself (that's an LLM call done
inline by the orchestrating session per §7a).
"""
import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    args = ap.parse_args()
    data = json.loads(Path(args.inp).read_text(encoding="utf-8"))
    for seg in data["segments"]:
        sid = seg["seg_id"]
        owc = seg["original_word_count"]
        # gate filter
        eligible = [c for c in seg["candidates"] if c["lock_gate_pass"] and c["wc_gate_pass"]]
        # sort by divergence desc
        eligible.sort(key=lambda c: -c["divergence"])
        gated_out = [c for c in seg["candidates"] if not (c["lock_gate_pass"] and c["wc_gate_pass"])]
        print(f"\n=== {sid} (orig_wc={owc}, eligible={len(eligible)}/6) ===")
        for c in eligible:
            print(f"  [{c['strategy'][0].upper()}-{c['method']:<16}] wc={c['candidate_word_count']:>3} div={c['divergence']:.4f}")
        for c in gated_out:
            reasons = []
            if not c["lock_gate_pass"]:
                reasons.append(f"missing_locks={c['lock_check']['missing']}")
            if not c["wc_gate_pass"]:
                reasons.append(f"wc_ratio={c['wc_ratio']} (band {c['wc_band']})")
            print(f"  [X {c['strategy'][0].upper()}-{c['method']:<16}] wc={c['candidate_word_count']:>3} div={c['divergence']:.4f} — DROPPED: {', '.join(reasons)}")


if __name__ == "__main__":
    main()
