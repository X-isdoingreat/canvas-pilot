---
name: canvas-humanizer-loop
description: Nested-loop wrapper around canvas-humanizer that runs the round-trip humanizer, audits its output for meaning/structure/rubric damage via 3 parallel sub-agents with majority vote, dispatches per-segment 1-in-1-out rewrites for damaged segments, then re-humanizes (with already-converged segments locked) — up to max_iter=3 with 3 layered convergence guards (MUST_FIX==0, per-segment verdict monotonicity, structural-drift). Designed to give callers a detector-low + meaning-intact + rubric-clean draft as drop-in replacement for canvas-humanizer. Caller interface is identical to canvas-humanizer; loop logic is internal.
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Grep
  - Agent
  - Skill
---

# canvas-humanizer-loop — iterative humanize → audit → rewrite → re-humanize convergence

## §1 — Identity & contract (caller-facing)

**Inputs** (parsed from caller's prose context line; same pattern as canvas-humanizer):

| Arg | Required | Default | Example |
|---|---|---|---|
| `draft_path` | yes | — | `C:\...\essay.docx` (.docx or .md) |
| `output_path` | yes | — | `C:\...\essay.loop.docx` |
| `voice_register` | yes | — | `advanced-academic-english` |
| `max_iter` | no | `3` | `3` |
| `student_identity` | no | falls back to `voice_register` | `b1-b2-international-student` |

**Outputs**:

- `output_path` — final humanized draft (the iter with lowest `severity_score` across history)
- `<output_dir>/loop_log.json` — per-iter trace (humanizer log paths, audit paths, broken segs, rewrites, verdict history, convergence reason, best_iter)
- Per-iter artifacts in `<output_dir>/_loop_iter_<N>/`:
  - `humanized.docx` (humanizer output that iter)
  - `humanizer_log.json` (delegated from canvas-humanizer)
  - `audit_a.json`, `audit_b.json`, `audit_c.json` (3 parallel audits)
  - `merged_audit.json` (post-majority-vote)
  - `rewritten.docx` (if iter did rewrites)

**Status return**:

- `ok` — converged with MUST_FIX == 0
- `partial` — exited via oscillation guard / max_iter / structural-drift; returned best historical iter
- `error` — input validation failure

**Caller compatibility**: drop-in replacement for `canvas-humanizer`. Caller passes the same draft_path / output_path / voice_register and gets back a humanized docx; the loop's iteration is invisible at the interface.

---

## §2 — Why this skill exists (read once)

`canvas-humanizer` v2 round-trip humanizer on the writing course's Response Paper Final Draft (2026-05-21) produced detector score **28** (baseline 75) — the lowest of any draft variant — but `humanizer_log.v2.json` showed `p_wins:23, r_wins:0` (paraphrase strategy won all 23 segments), and ~6-8 segments had broken rubric / meaning / cadence:

- R8 opener buried in clause 2 (article citation no longer leads the sentence)
- Anecdote subject pushed to end of sentence (rhetorical setup destroyed)
- Conclusion thesis-restatement deleted
- Systemic Yoda-syntax (fronted-wh-clause subjects, absolute-phrase openers)

`canvas-humanizer-surgical` then rewrote MUST_FIX segments **without re-humanizing** → detector climbed back to 35 (surgical v1) / 42 (surgical-v3). The rewrite was a meaning rescue but each rewritten sentence re-entered the LLM distribution that humanizer had just escaped.

**This skill's hypothesis**: humanizer breaking a given segment is statistical noise in K=6 candidate Levenshtein-argmax, not a deterministic failure. If we (a) precisely identify broken segments, (b) rewrite them to meaning-preserving prose that is neither V0 nor V_humanized, (c) re-feed to the same humanizer, the K=6 candidates for those segments come from a different starting point and probably don't re-break the same way. Loop until convergence or budget exhaustion.

CEO design decisions (2026-05-22):

- Rewrite step is a **new minimal 1-in-1-out sub-agent**, not a composition of `canvas-humanizer-surgical`. Surgical has multi-segment autonomy and can split sentences; the loop's rewrite is strictly one-sentence-in / one-sentence-out.
- Wallclock budget: accept 45-90 min. Don't trim `max_iter` or auditor count for speed.
- CEO is not in the loop. All audit + rewrite + convergence judgment is sub-agent automated.

---

## §3 — Pipeline overview

```
Input docx
  ↓
[§4]  iter loop (max_iter=3):
  ↓
  [§4.1] Skill(canvas-humanizer, current_draft, hard_locks=converged_seg_texts)
         → humanized_<N>.docx + humanizer_log.json
  ↓
  [§4.2] Agent × 3 parallel (audit subagent)
         → 3 × residual_issues_audit.json
  ↓
  [§4.3] Majority-vote merge → merged_audit.json
  ↓
  [§4.4] Structural-drift check (split_sentences re-check per paragraph)
  ↓
  [§4.5] Update verdict history per (doc_paragraph_index, intra_para_index)
  ↓
  [§4.6] Convergence guards (3 layered):
         (a) MUST_FIX == 0 → return current humanized (status=ok)
         (b) Per-seg verdict monotonicity violated → return best historical iter (status=partial)
         (c) Same paragraph drifts 2 iters in a row → return best historical iter (status=partial)
         (d) iter == max_iter → return best historical iter (status=partial)
  ↓
  [§4.7] Agent × N parallel (rewrite-subagent), N = broken segs count
         → splice rewrites into humanized_<N> → rewritten_<N>.docx
  ↓
  [§4.8] Build converged_seg_texts for next iter's hard_locks
         (with uniqueness pre-flight per §10)
  ↓
[§5-12] Write loop_log.json + select best iter's docx as output_path
```

---

## §4 — Per-iter algorithm (executable pseudocode)

```python
# Loop state
best_iter_index = None
best_severity = float("inf")
verdict_history = {}      # (para_idx, intra_idx) -> list of verdicts across iters
drift_strikes = {}        # (para_idx) -> consecutive drift count
iter_artifacts = []       # list of per-iter dicts for loop_log.json
current_draft_path = draft_v0

for iter_num in range(1, max_iter + 1):
    iter_dir = output_dir / f"_loop_iter_{iter_num}"
    iter_dir.mkdir(exist_ok=True)

    # §4.1 — Run humanizer (with converged segs as hard_locks from iter ≥ 2)
    converged_seg_texts = _build_converged_locks(verdict_history, iter_num, current_draft_path)
    invoke_skill(
        "canvas-humanizer",
        draft_path=current_draft_path,
        output_path=iter_dir / "humanized.docx",
        voice_register=voice_register,
        hard_locks=converged_seg_texts,  # via overlay or runtime arg
    )
    humanizer_log = load_json(iter_dir / "humanizer_log.json")
    humanized_path = iter_dir / "humanized.docx"

    # §4.2-4.3 — 3 parallel audits, majority-vote merge
    audit_paths = dispatch_parallel_audits(humanized_path, draft_v0, humanizer_log, iter_dir)
    merged_audit = merge_audits_majority_vote(audit_paths)
    save_json(iter_dir / "merged_audit.json", merged_audit)

    # §4.4 — Structural-drift check
    drifted_paragraphs = detect_structural_drift(humanized_path, humanizer_log)
    for para_idx in drifted_paragraphs:
        drift_strikes[para_idx] = drift_strikes.get(para_idx, 0) + 1

    # §4.5 — Update verdict history
    for sent_entry in merged_audit["per_sentence"]:
        key = (sent_entry["doc_paragraph_index"], sent_entry["intra_para_index"])
        verdict_history.setdefault(key, []).append(sent_entry["verdict"])

    # Compute severity_score
    must_fix = merged_audit["aggregate_stats"]["total_MUST_FIX"]
    should_fix = merged_audit["aggregate_stats"]["total_SHOULD_FIX"]
    nice = merged_audit["aggregate_stats"]["total_NICE_TO_FIX"]
    severity_score = must_fix * 3 + should_fix * 2 + nice * 1

    # Track best iter
    if severity_score < best_severity:
        best_iter_index = iter_num
        best_severity = severity_score

    iter_artifacts.append({
        "iter": iter_num,
        "humanized_path": str(humanized_path),
        "merged_audit_path": str(iter_dir / "merged_audit.json"),
        "audit_paths": [str(p) for p in audit_paths],
        "severity_score": severity_score,
        "broken_segs": _extract_broken_segs(merged_audit),
        "structurally_drifted_paras": list(drifted_paragraphs),
    })

    # §4.6 — Convergence guards
    if must_fix == 0:
        return _finalize(best_iter_index=iter_num, reason="MUST_FIX==0", status="ok")

    if iter_num > 1 and _oscillation_detected(verdict_history):
        return _finalize(best_iter_index, reason="oscillation", status="partial")

    if any(c >= 2 for c in drift_strikes.values()):
        return _finalize(best_iter_index, reason="structural_drift_persistent", status="partial")

    if iter_num == max_iter:
        return _finalize(best_iter_index, reason="max_iter_hit", status="partial")

    # §4.7 — Dispatch rewrites for broken segs (parallel)
    broken_segs = _extract_broken_segs(merged_audit)
    rewrites = dispatch_parallel_rewrites(broken_segs, humanized_path, draft_v0, voice_register)

    # §4.7 — Splice rewrites back; mark any split_required segs as drift
    rewritten_path = iter_dir / "rewritten.docx"
    splice_status = splice_rewrites(humanized_path, rewrites, rewritten_path)
    for seg in splice_status["split_required_segs"]:
        para_idx = seg["doc_paragraph_index"]
        drift_strikes[para_idx] = drift_strikes.get(para_idx, 0) + 1

    iter_artifacts[-1]["rewritten_segs"] = rewrites
    current_draft_path = rewritten_path

return _finalize(best_iter_index, reason="max_iter_hit", status="partial")
```

The above is the **executable contract**. When this skill is invoked, the agent acting as orchestrator follows this control flow literally — call canvas-humanizer via Skill tool, dispatch audits/rewrites via Agent tool, write artifacts at the indicated paths, terminate per the guards.

---

## §5 — Audit sub-agent prompt template

**Dispatch**: 3 parallel `Agent(subagent_type="general-purpose", ...)` calls in a single message, identical prompt, different instance.

**Output schema**: identical to `runs/2026-05-22/_humanizer_v2_smoketest/residual_issues_audit.json`. Write to `_loop_iter_<N>/audit_<a|b|c>.json`.

**Prompt template** (substitute `{...}` placeholders at dispatch time):

```
You are an audit sub-agent for canvas-humanizer-loop. Your job: detect every segment in a humanized essay where humanizer broke meaning, structure, or rubric compliance — and classify each issue by 7-dimension taxonomy + 3-severity scale.

CONTEXT
- Original V0 essay (pre-humanizer): {v0_path} — read this fully
- Humanized version (current iter output): {humanized_path} — read this fully
- humanizer_log.json: {humanizer_log_path} — read for per-segment doc_paragraph_index / intra_para_index / winning_strategy_used
- Voice register contract: {voice_register}
- Rubric anchors (assignment-specific):
  - R8 opener: first sentence of intro must match regex ^In ["][^"]+["]\s*\([^)]+\),\s*[A-Z]\w+ (article title + publication + author + verb)
  - R8 person introduction: full name + credential on first mention, last name only after
  - R8 quote count: intro 0, body paragraphs 1 each, conclusion 0
  - R8 conclusion thesis-restatement: first sentence of conclusion must echo the intro's thesis claim
  - R9 word count band: {word_count_band} (e.g., 550-650)
  - R9 banned patterns: long em-dash strings, "in conclusion", "in summary", "delve into", "tapestry", "navigate the landscape"

TASK
For each sentence in the humanized doc, identify all issues across these 7 dimensions:

| Dim | Name | What to flag |
|---|---|---|
| D1 | rubric_violation | Concrete spec-anchor failures (R8/R9 above) |
| D2 | grammar_tortured | Garbled / ungrammatical output (NOT intentional ESL) |
| D3 | unnatural_syntax | Yoda-style fronting, pseudo-cleft chains, absolute-phrase openers, fronted-wh-clause subjects, parallel passive openers across consecutive sentences |
| D4 | voice_register_drift | Tone mismatch vs voice_register contract (e.g., slang in academic, archaisms beyond register) |
| D5 | new_AI_tell_introduced | Em-dash overuse (>2/paragraph), rhetorical inversion clusters, uniform cadence patterns the humanizer created |
| D6 | meaning_distortion | Claim direction reversed, hedge strength changed, numbers/quote text altered, anecdote subject moved out of first 1/3 of sentence |
| D7 | lock_or_credential_loss | Person introduced by last name only (missing first name + credential), quote text bytes differ, named entity lost |

For each issue:
- severity: MUST_FIX (rubric break / meaning reversed / cadence-cluster signature) | SHOULD_FIX (single instance, isolated) | NICE_TO_FIX (stylistic preference)
- anchor: ~10-word verbatim excerpt of the offending text
- rubric_ref: R-number if applicable (R2/R8/R9), else null
- fix_directive: 1-2 sentences telling a rewrite agent what to do (be concrete: "Restore opening to lead with full publication info" not "fix the syntax")

For each sentence:
- seg_id: "P{doc_paragraph_index}_S{intra_para_index}" — derive from humanizer_log.json segments[]
- paragraph: "intro" | "body 1" | "body 2" | "conclusion" (infer from doc_paragraph_index — paragraphs after name-block/title)
- v2_text: the sentence as it appears in humanized doc
- pre_humanize_text: the corresponding sentence from V0 (match by doc_paragraph_index + intra_para_index)
- issues: array of issue objects (can be empty)
- winning_strategy_used: read from humanizer_log.json
- verdict:
  - "broken" if any MUST_FIX issue, OR ≥2 SHOULD_FIX in cadence-cluster dimensions (D3 + D5)
  - "needs_surgical" if exactly 1 SHOULD_FIX with no MUST_FIX
  - "minor" otherwise (zero issues, or only NICE_TO_FIX, or 1 SHOULD_FIX in a non-cadence dimension)

OUTPUT FORMAT
Emit a single JSON object matching residual_issues_audit.json schema:

{
  "audit_date": "YYYY-MM-DD",
  "target_doc": "{humanized_path}",
  "doc_word_count": <int>,
  "doc_sentence_count": <int>,
  "doc_paragraph_count": <int>,
  "aggregate_stats": {
    "sentences_with_zero_issues": <int>,
    "sentences_with_one_issue": <int>,
    "sentences_with_multiple_issues": <int>,
    "total_MUST_FIX": <int>,
    "total_SHOULD_FIX": <int>,
    "total_NICE_TO_FIX": <int>,
    "issues_by_dimension": {"D1_rubric_violation": <int>, ...},
    "clustering": "Free-form 2-4 sentence summary of where issues concentrate"
  },
  "per_sentence": [
    {
      "seg_id": "P5_S0",
      "doc_paragraph_index": 5,
      "intra_para_index": 0,
      "paragraph": "intro",
      "v2_text": "...",
      "pre_humanize_text": "...",
      "issues": [
        {
          "dimension": "D1_rubric_violation",
          "severity": "MUST_FIX",
          "anchor": "...",
          "rubric_ref": "R8",
          "fix_directive": "..."
        }
      ],
      "winning_strategy_used": "clause_reorder",
      "verdict": "broken"
    }
  ]
}

CRITICAL CONSTRAINTS
- Do NOT speculate. Only flag what is concretely demonstrable from comparing v2_text vs pre_humanize_text against rubric anchors.
- Do NOT downgrade severity to avoid triggering downstream rewrites. Loop logic depends on accurate severity.
- Do NOT flag intentional ESL register markers (article omission, occasional SVA slip in body paragraphs) as D2 grammar_tortured — those are voice_register strategy.
- Quote the exact rubric anchor text in rubric_ref when D1 fires.
```

---

## §6 — Majority-vote merge algorithm

After 3 audits return, merge into a single `merged_audit.json`:

```python
def merge_audits_majority_vote(audit_paths: list[Path]) -> dict:
    audits = [load_json(p) for p in audit_paths]

    # Build per-seg issue tables
    # key = (seg_id, dimension), value = list of (severity, anchor, rubric_ref, fix_directive)
    issue_votes = {}
    seg_verdicts = {}  # seg_id -> list of verdicts from 3 agents

    for audit in audits:
        for sent in audit["per_sentence"]:
            seg_id = sent["seg_id"]
            seg_verdicts.setdefault(seg_id, []).append(sent["verdict"])
            for issue in sent["issues"]:
                key = (seg_id, issue["dimension"])
                issue_votes.setdefault(key, []).append(issue)

    # Aggregation: keep an (seg_id, dimension) issue iff ≥2 of 3 agents flagged it
    # Severity = max severity across the agents that flagged it (MUST_FIX > SHOULD_FIX > NICE_TO_FIX)
    SEVERITY_RANK = {"MUST_FIX": 3, "SHOULD_FIX": 2, "NICE_TO_FIX": 1}

    confirmed_issues_per_seg = {}  # seg_id -> list of merged issue dicts
    for (seg_id, dim), votes in issue_votes.items():
        if len(votes) < 2:
            continue  # only 1 agent flagged; drop
        max_sev = max(votes, key=lambda v: SEVERITY_RANK[v["severity"]])
        merged_issue = {
            "dimension": dim,
            "severity": max_sev["severity"],
            "anchor": max_sev["anchor"],
            "rubric_ref": max_sev["rubric_ref"],
            "fix_directive": max_sev["fix_directive"],
            "votes": len(votes),
        }
        confirmed_issues_per_seg.setdefault(seg_id, []).append(merged_issue)

    # Verdict aggregation: majority of 3 (or break tie to broken > needs_surgical > minor)
    VERDICT_RANK = {"broken": 3, "needs_surgical": 2, "minor": 1}

    def pick_verdict(verdict_list):
        counts = {v: verdict_list.count(v) for v in set(verdict_list)}
        max_count = max(counts.values())
        winners = [v for v, c in counts.items() if c == max_count]
        return max(winners, key=lambda v: VERDICT_RANK[v])

    # Rebuild per_sentence with confirmed issues + voted verdict
    template_audit = audits[0]
    merged_per_sentence = []
    for sent in template_audit["per_sentence"]:
        seg_id = sent["seg_id"]
        merged_per_sentence.append({
            **sent,
            "issues": confirmed_issues_per_seg.get(seg_id, []),
            "verdict": pick_verdict(seg_verdicts.get(seg_id, [sent["verdict"]])),
        })

    # Recompute aggregate_stats from merged data
    aggregate_stats = _recompute_aggregate(merged_per_sentence)

    return {
        "audit_date": template_audit["audit_date"],
        "target_doc": template_audit["target_doc"],
        "doc_word_count": template_audit["doc_word_count"],
        "doc_sentence_count": template_audit["doc_sentence_count"],
        "doc_paragraph_count": template_audit["doc_paragraph_count"],
        "aggregate_stats": aggregate_stats,
        "per_sentence": merged_per_sentence,
    }
```

**Why ≥2 agree (not 2 of 3 strict)**: 3-agent design is robust under one agent being a bad draw; majority is the conservative gate. **Severity max** intentionally biases toward false-positive over false-negative — a wrongly-flagged-broken segment wastes a rewrite call (cheap); a missed-broken segment ships a broken essay (expensive).

---

## §7 — Convergence guards (3 layered)

### Guard 1 — MUST_FIX zero

```python
if merged_audit["aggregate_stats"]["total_MUST_FIX"] == 0:
    return _finalize(iter_num, reason="MUST_FIX==0", status="ok")
```

This is the success case. No rubric breaks remaining → ship current humanized.

### Guard 2 — Per-segment verdict monotonicity

```python
def _oscillation_detected(verdict_history: dict) -> bool:
    """Catch segments whose verdict regresses: broken→minor→broken, or needs_surgical→broken."""
    for seg_key, hist in verdict_history.items():
        if len(hist) < 2:
            continue
        # If a segment was "minor" or "needs_surgical" at some point and is "broken" later, oscillation
        ranks = [VERDICT_RANK[v] for v in hist]  # broken=3, needs_surgical=2, minor=1
        for i in range(1, len(ranks)):
            if ranks[i] > ranks[i-1]:  # got worse
                return True
    return False
```

This catches **lateral failure substitution** — humanizer fixed D1 in seg X but introduced D3+D5 in same seg the next iter. Scalar `severity_score` regression check misses this because the score might look stable while individual segments rotate failures. Per-seg monotonicity is the precise gate.

On detection → return historical-best iter.

### Guard 3 — Structural-drift persistence

```python
if any(strikes >= 2 for strikes in drift_strikes.values()):
    return _finalize(best_iter_index, reason="structural_drift_persistent", status="partial")
```

A paragraph whose segment count changes (round-trip split a sentence into two) is marked drifted that iter. If the **same** paragraph drifts 2 iters in a row, the loop gives up on that paragraph's surgical convergence and returns the best historical iter.

### Hard cap — max_iter

```python
if iter_num == max_iter:
    return _finalize(best_iter_index, reason="max_iter_hit", status="partial")
```

Belt-and-suspenders. Default max_iter=3.

---

## §8 — Structural-drift detection

Each iter, after humanizer returns, re-split every paragraph and compare to `humanizer_log.json`'s reported per-paragraph segment count:

```python
from src.humanizer_segmentation import split_sentences

def detect_structural_drift(humanized_docx_path: Path, humanizer_log: dict) -> set[int]:
    """Return set of doc_paragraph_index where re-split count != humanizer_log's count."""
    paragraphs = read_docx_paragraphs(humanized_docx_path)
    expected_counts = {}
    for seg in humanizer_log["segments"]:
        p = seg["doc_paragraph_index"]
        expected_counts[p] = max(expected_counts.get(p, 0), seg["intra_para_index"] + 1)
    actual_counts = {i: len(split_sentences(p)) for i, p in enumerate(paragraphs)}
    drifted = set()
    for p_idx in expected_counts:
        if actual_counts.get(p_idx, 0) != expected_counts[p_idx]:
            drifted.add(p_idx)
    return drifted
```

Uses `src/humanizer_segmentation.py:split_sentences` — same function canvas-humanizer §5a uses internally — guaranteeing the loop's view of segments matches the humanizer's view.

Drifted paragraphs cannot be rewritten segment-by-segment (the rewrite-subagent's 1-in-1-out contract assumes stable seg_ids). On drift: skip per-seg rewrites for that paragraph this iter; record the strike.

---

## §9 — Rewrite sub-agent prompt template

**Dispatch**: For each broken seg in `merged_audit`, fire one `Agent(subagent_type="general-purpose", ...)` call. All N rewrites for a single iter go in a single message (parallel).

**Prompt template** per broken seg:

```
You are a rewrite sub-agent for canvas-humanizer-loop. Your single job: rewrite ONE sentence to fix issues identified by the audit, while staying invisible to AI detectors AND preserving the original meaning.

INPUTS
- v0_sentence (pre-humanizer original): "{v0_sentence}"
- v_humanized_sentence (current broken version): "{v_humanized_sentence}"
- broken_dimensions:
  {broken_dimensions_json}   # array of {dimension, severity, fix_directive}
- role: {role}                 # one of: intro_opener, intro_thesis, intro_setup, body_TS, body_quote_lead_in, body_quote_follow_up, body_elaboration, body_anecdote, conclusion_thesis_restate, conclusion_structural, conclusion_closing
- voice_register: {voice_register}
- context_prev_sentence: "{context_prev}"
- context_next_sentence: "{context_next}"

HARD CONSTRAINTS (all must pass; fail any → emit split_required=true and stop)

1. ONE-IN-ONE-OUT
   Output exactly ONE complete sentence. Do not split into two sentences. Do not merge with adjacent. If the fix_directive demands splitting (e.g., "split this overlong sentence"), refuse and set split_required=true.

2. NOT V0, NOT V_HUMANIZED
   Sentence-level edit distance must be > 0.3 vs BOTH v0_sentence AND v_humanized_sentence. (Approx: at least 30% of words must differ in either inflection, order, or choice from each baseline.) This is the avoid-detector-pattern constraint.

3. MEANING + RHETORICAL SETUP PRESERVED
   - Propositional content identical to v0_sentence: claim direction same, numbers same, quoted text byte-identical, person names identical
   - Rhetorical setup:
     • If role = body_anecdote: subject (the anecdote agent — "my cousin", "a classmate") MUST appear in the first 1/3 of the sentence
     • If role = body_TS or conclusion_thesis_restate: main claim must appear in first half of sentence (open with the point, don't bury it)
     • If role = intro_opener: must match regex ^In ["][^"]+["]\s*\([^)]+\),\s*[A-Z]\w+ (article title + publication + author + verb)
     • If role = body_quote_lead_in: must end with a clause that sets up the quote that follows (typically with "that," or a colon)

4. ROLE-AWARE REGISTER STRATEGY
   This determines HOW you rewrite (the policy that prevents re-introducing detector signal).

   IF role ∈ {intro_opener, intro_thesis, body_TS, body_quote_lead_in, body_quote_follow_up, conclusion_thesis_restate, conclusion_structural}:
       Strategy = ESL-register-clean
       - ESL-flavored syntax/word order OK (e.g., topicalization "What [Author A] argues is that...", non-standard but grammatical hedges)
       - Grammar must be CLEAN: no article omission, no SVA slip, correct tense
       - This protects R9 rubric compliance for grade-sensitive positions

   IF role ∈ {body_elaboration, body_anecdote, conclusion_closing}:
       Strategy = ESL-chinese-full
       - Visible article omission ("Chinese intuition I grew up with", not "the Chinese intuition...")
       - Occasional subject-verb agreement slip ("My cousin show...", "[Author B] trace...")
       - These create natural ESL distribution that detectors don't pattern-match as AI
       - Cap: at most 2 grammar-marker slips per sentence; do not stack 3+ markers (sounds tortured)

   Why two strategies: canvas-humanizer-surgical v1 used ESL-clean uniformly and detector climbed 28→48 because clean-register sentences re-entered LLM distribution. v3 used ESL-full in gates and broke R9 (instructor counts visible grammar errors as wrong). Per-role split is the empirical fix.

5. CONTEXT FIT
   - context_prev_sentence and context_next_sentence are provided so your rewrite reads as part of the flowing paragraph, not as an isolated unit
   - Do not duplicate language from either context sentence (avoid lexical repetition triplets that detectors flag)
   - Discourse connector (if any) must be appropriate to the prev→current relationship; do not introduce a "however" if the prev sentence already opened with "however"

OUTPUT (JSON)
{
  "rewritten_sentence": "<one complete English sentence>",
  "rationale": "<2-3 sentences: which broken_dimensions you fixed, which strategy you applied, how meaning was preserved>",
  "split_required": false,
  "edit_distance_from_v0": <0.0-1.0>,
  "edit_distance_from_v_humanized": <0.0-1.0>
}

If you cannot satisfy all 5 hard constraints, emit:
{
  "rewritten_sentence": "",
  "rationale": "<why constraint X cannot be met for this sentence>",
  "split_required": true,
  "blocked_constraint": "<one of: 1_one_in_one_out, 2_not_v0_or_v_humanized, 3_meaning_setup, 4_role_register, 5_context_fit>"
}

Do not include the original sentences in your output. Just the JSON above.
```

---

## §10 — Hard_locks uniqueness pre-flight

Before passing converged-seg verbatim text as `hard_locks` to canvas-humanizer in iter ≥ 2:

```python
def build_converged_locks(verdict_history, iter_num, current_draft_path):
    """Return list of sentence strings to pass as hard_locks. Skips collision-prone segs."""
    if iter_num == 1:
        return []  # no locks first iter

    paragraphs = read_docx_paragraphs(current_draft_path)
    locks = []
    for (para_idx, intra_idx), hist in verdict_history.items():
        # A seg is "converged" if its LAST verdict was minor or needs_surgical (not broken)
        if not hist or hist[-1] == "broken":
            continue
        # Get the seg's current text
        sentences = split_sentences(paragraphs[para_idx])
        if intra_idx >= len(sentences):
            continue  # paragraph drifted; don't lock
        candidate = sentences[intra_idx]
        # Uniqueness pre-flight: count occurrences across the full doc
        full_text = "\n".join(paragraphs)
        if full_text.count(candidate) != 1:
            log(f"lock collision skipped: {candidate[:60]}...")
            continue
        locks.append(candidate)
    return locks
```

**Risk acknowledgment**: when a collision is detected and the seg isn't locked, that already-converged segment goes through humanizer's K=6 candidate selection again — possibly producing a new break. The next iter's audit catches this. The verdict-monotonicity guard (§7 Guard 2) catches the "was minor, now broken" case and exits to historical best.

---

## §11 — seg_id canonical form

**Within the loop, the canonical identifier for any segment is the tuple `(doc_paragraph_index, intra_para_index)`.** All in-memory state (verdict_history, drift_strikes) keys on this tuple. Strings ("S0", "P5_S0") are derived only for human-readable interfaces (audit JSON, sub-agent prompts).

| Producer | Native format | Derived from |
|---|---|---|
| `humanizer_log.json` segments[] | `seg_id: "S{n}"` + `doc_paragraph_index` + `intra_para_index` | Read tuple directly from the latter two |
| `residual_issues_audit.json` per_sentence[] | `seg_id: "P5_S0"` + `doc_paragraph_index` + `intra_para_index` | Read tuple directly from the latter two |
| Loop dispatch to audit subagent | Pass tuple + "P5_S0" string both | Constructed from tuple |
| Loop dispatch to rewrite subagent | Pass tuple + "P5_S0" string both | Constructed from tuple |
| `loop_log.json` verdict_history_per_seg | Stringified tuple: `"(5,0)"` | JSON-safe key serialization |

**Splicing rewrites back into the docx**: locate the target paragraph by `doc_paragraph_index`, run `split_sentences` on it, replace index `intra_para_index` with the rewrite, re-join with a single space (preserves docx paragraph structure). DO NOT splice into the docx XML directly — round-trip through plain text via python-docx is safer.

---

## §12 — loop_log.json schema

Written to `<output_dir>/loop_log.json` after `_finalize`:

```json
{
  "skill": "canvas-humanizer-loop",
  "version": 1,
  "draft_v0_path": "...",
  "voice_register": "...",
  "max_iter": 3,
  "iter_count": 2,
  "convergence_reason": "MUST_FIX==0 | oscillation | max_iter_hit | structural_drift_persistent",
  "status": "ok | partial | error",
  "best_iter": 2,
  "best_severity_score": 4,
  "output_docx_path": "...",
  "iter_history": [
    {
      "iter": 1,
      "humanized_path": "_loop_iter_1/humanized.docx",
      "humanizer_log_path": "_loop_iter_1/humanizer_log.json",
      "audit_paths": ["_loop_iter_1/audit_a.json", "_loop_iter_1/audit_b.json", "_loop_iter_1/audit_c.json"],
      "merged_audit_path": "_loop_iter_1/merged_audit.json",
      "severity_score": 12,
      "broken_segs": [
        {"doc_paragraph_index": 5, "intra_para_index": 0, "dimensions": ["D1", "D3"], "severity": "MUST_FIX"}
      ],
      "rewritten_segs": [
        {"doc_paragraph_index": 5, "intra_para_index": 0, "rewritten": "...", "edit_distance_from_v0": 0.42, "edit_distance_from_v_humanized": 0.55, "split_required": false}
      ],
      "structurally_drifted_paras": []
    }
  ],
  "verdict_history_per_seg": {
    "(5,0)": ["broken", "minor"],
    "(7,2)": ["broken", "broken"]
  },
  "wallclock_seconds": 4823
}
```

---

## §13 — Execution mode (how the orchestrator runs)

This skill is **agent-orchestrated**, not Python-script-orchestrated. When the caller dispatches `canvas-humanizer-loop` via the Skill tool, the receiving agent:

1. Reads this SKILL.md.
2. Parses caller's prose context for `draft_path`, `output_path`, `voice_register`, optional `max_iter`.
3. Walks the §4 control flow, calling:
   - `Skill(skill="canvas-humanizer", args="...")` for the round-trip humanization step
   - `Agent(subagent_type="general-purpose", prompt="<§5 audit template>")` × 3 in one message for parallel audit
   - `Agent(subagent_type="general-purpose", prompt="<§9 rewrite template>")` × N in one message for parallel rewrites
4. Uses Bash + python-docx to read/write docx files between sub-agent calls.
5. Uses `src.humanizer_segmentation:split_sentences` (via inline Bash python invocation) for the structural-drift check.
6. Writes all per-iter artifacts to `<output_dir>/_loop_iter_<N>/` and the final summary to `<output_dir>/loop_log.json`.

**Why agent-orchestrated, not Python**: the audit and rewrite steps are LLM dispatches that need the Agent tool. Wrapping the whole loop in Python would require the agent to use Bash repeatedly to spawn sub-agents through a script wrapper — adds complexity without benefit. The orchestrator (you, reading this) calls Skill + Agent tools directly.

**Time budget**: ~45-90 min wallclock for max_iter=3 (humanizer ~5-15min × 3 + 3-parallel audit ~5-10min × 3 + parallel rewrites ~3-5min × 3). Acceptable by CEO decision.

---

## §14 — Verification (caller-side smoke test)

Before this skill is wired into `canvas-essay` §7.5 as a drop-in replacement, run a smoke test:

1. **Input**: `runs/2026-05-21/Writing_Course__Response_Paper_Final_Draft/draft/essay.txt` (V0)
2. **Invocation**: `Skill(skill="canvas-humanizer-loop", args="draft_path:<V0> output_path:<output>/essay.loop.docx voice_register:advanced-academic-english max_iter:3")`
3. **Expected outputs**:
   - `essay.loop.docx` — final humanized variant
   - `loop_log.json` with `iter_count ≥ 2` (V2 has ~6-8 broken; ≥1 round of rewrite expected)
4. **Quality verification** (manual or sub-agent):
   - Detector test: Grammarly / GPTZero score ≤ V2 baseline (28), target < 30
   - Rubric anchors per `runs/2026-05-21/.../audit/round_1.json`:
     - R8 opener regex passes ✓
     - [Author C] + [Author D] first-mention has full name + "economists" credential ✓
     - Conclusion thesis-restatement present ✓
     - Word count in [550, 650] ✓
   - Meaning sanity: no Yoda syntax, no anecdote subject after first 1/3, no missing thesis
5. **Regression alarm**: if detector > V2 baseline OR any rubric anchor fails → loop has design bug; do not ship.

Sub-skill component testing (recommended before loop integration):
- Test the §5 audit-subagent prompt in isolation on `essay.humanized.v2.docx`; compare output to existing `residual_issues_audit.json` from 2026-05-22 smoketest. Schemas should align; verdict assignments should agree on ≥80% of segments.
- Test the §9 rewrite-subagent prompt on 1-2 of the known-broken segs from V2 (e.g., P5_S0 intro opener); verify it produces a rewrite that satisfies all 5 hard constraints.

---

## §15 — Open questions for v2 of this skill

Items deferred from v1 design:

- **Detector score integration**: loop currently terminates on audit-internal verdict only. Caller checks detector ONCE after loop exits. A v2 could accept a `detector_callback` parameter that pastes detector score per iter, adding a 2D termination condition (audit clean AND detector < target). Not implemented in v1.
- **Role-aware K-candidate scoring inside canvas-humanizer**: the deeper fix to the V2 "p_wins:23, r_wins:0" problem is making canvas-humanizer's scoring function role-aware (penalize candidates that violate R8 opener regex, anecdote subject position, etc.). This loop is the outer compensator; role-aware scoring would be the inner fix. Deferred — loop should be sufficient for the AC_ENG class of essays.
- **Rewrite-subagent strategy library expansion**: currently 2 strategies (ESL-register-clean / ESL-chinese-full). Future could add register variants (academic-American-native, ESL-Spanish-substrate, etc.) for different student identities.
