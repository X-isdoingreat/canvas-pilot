---
name: canvas-humanizer-surgical
description: Second-pass humanizer that fixes specific issues left over from canvas-humanizer (v2) without re-introducing LLM-shaped prose. v3 design uses per-position-differentiated ESL register — gate-sensitive positions (intro_opener / TS / quote integration / conclusion_thesis_restate) use P-esl-register-clean (ESL syntax/phrasing but clean grammar to protect the academic-writing R9 rubric), body positions (elaboration / anecdote) use P-esl-chinese-full (full ESL with visible article omission + SVA slip markers for true distribution escape). Fix scope expanded from MUST_FIX-only to MUST_FIX + body SHOULD_FIX so the body ESL strategies actually have segments to fire on (v1 surgical failed because all MUST_FIX were in gate-sensitive roles, leaving ESL with no targets). 3-layer nested orchestration. Invoked after canvas-humanizer when AI-detection score is acceptable but residual rubric / grammar / fluency issues exist.
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Grep
  - Agent
---

# canvas-humanizer-surgical v3 — per-position differentiated ESL

## §1 — Identity & contract (caller-facing)

**Inputs** (parsed from caller's prose context line):

| Arg | Required | Default / fallback | Example |
|---|---|---|---|
| `draft_path` | yes | — | path to already-humanized `.docx` (output of canvas-humanizer v2) |
| `output_path` | yes | — | path for surgical-fixed `.docx` |
| `voice_register` | yes | — | `advanced-academic-english` (informs the academic-minimal backup; ESL strategies override per-position) |
| `audit_path` | no | omits → skill runs internal audit | path to pre-derived audit JSON (with per-sentence issues + roles + fix_goals) |
| `pre_humanize_path` | no | omits → skip "what humanizer broke vs preexisting" comparison | path to pre-v2 baseline |
| `hard_locks` | no | empty | list of additional verbatim-preserve spans |
| `include_should_fix` | no | true | whether to include SHOULD_FIX in body roles (default true, key to letting body ESL fire) |
| `include_nice_to_fix` | no | false | whether to include NICE_TO_FIX in body roles |

**Outputs**:

- `output_path` — surgical-fixed `.docx`
- `<output_dir>/surgical_log.json` — full execution trace

**Status return**:

- `ok` — every MUST_FIX issue addressed AND all Stage E doc-level gates PASS
- `partial` — ≥1 MUST_FIX fell back to current_humanized OR a doc gate WARNs
- `error` — input validation failure

---

## §2 — Why surgical v3 (per-position differentiation)

**v1 surgical failure** (per-role gating + ESL fallback) regressed Grammarly AI score 28% → 48%. Root cause: 15 MUST_FIX issues all in gate-sensitive role (intro_opener / TS / quote integration / conclusion_thesis_restate); ESL was gated off there; P-academic restoration pulled prose back to LLM-training-distribution center.

**v2 design rejected** ("ESL primary everywhere"): would put visible grammar errors in rubric-graded positions. An academic-writing instructor's grading sample observed during calibration: Draft 1 (57 grammar errors) → 68/100; Draft 2 (clean) → 83/100. ESL with SVA slip + article omission in intro_opener / TS / conclusion thesis restate = R9 deduction in the most-graded positions.

**v3 (this skill)**: differentiate by position type.

| Position type | Strategy | Grammar |
|---|---|---|
| Gate-sensitive (intro_opener / TS / quote integration / conclusion thesis restate / conclusion structural) | **P-esl-register-clean** | Clean (no SVA slip, no article omission) |
| Body (body_elaboration / body_anecdote / conclusion_closing) | **P-esl-chinese-full** | Visible ESL markers (this is the point) |

Plus: expand fix scope from MUST_FIX-only to **MUST_FIX + body SHOULD_FIX** so body ESL has segments to fire on (v1's body roles had 0 MUST_FIX and were left untouched).

**Honest framing**: ESL register strategies as distribution escape are tested for the first time here. P-esl-register-clean (gate positions) is *hypothesis* — syntax-only ESL may not move detector signal enough without grammar markers. P-esl-chinese-full (body positions) is **the higher-confidence lever** because grammar-error patterns are *truly* outside LLM training distribution. Expected Grammarly delta: 28% → 18-25% (still a hypothesis; v1 surgical's reality was 28% → 48% which proves *clean academic restoration* hurts).

---

## §3 — Pipeline overview (3-layer nested)

```
Level 1: doc orchestrator
  ├─ Stage A: load audit data (per-sentence issues + roles)
  ├─ Stage B: build expanded fix queue (MUST_FIX all + body SHOULD_FIX)
  ├─ Stage C: cluster by paragraph; spawn workers in parallel
  ├─ Stage D: reassemble
  └─ Stage E: doc-level verify (R8 4-variant regex / R2 markers / quote count / word count / locks / R9 grammar tally)

Level 2: paragraph worker (one per paragraph, parallel)
  ├─ Receive paragraph + fix_goals + roles
  ├─ Spawn segment workers parallel
  └─ Assemble paragraph

Level 3: segment surgical worker (parallel within paragraph)
  ├─ Determine role → primary strategy + backup per §S2 of plan
  ├─ Generate K candidates per §6 (K varies by severity × role)
  ├─ Score per §7
  ├─ Pick winner (primary preferred)
  └─ Fallback chain: primary → backup → P-academic-minimal → current_humanized
```

**Concurrency**: ~25 fix ops × K~2.5 avg × 3 LLM calls each ≈ ~190 calls. Parallel candidate dispatch collapses wallclock to 5-15 min.

---

## §4 — Stage A: audit (role tagging + issue detection)

**Skip if** caller passed `audit_path` to a pre-derived audit JSON. Default: load `runs/2026-05-22/_humanizer_v2_smoketest/residual_issues_audit.json` (derived from earlier v2 humanized essay).

When running fresh, spawn 1 audit agent per v2 SKILL.md §4 (with role taxonomy below + low-confidence fallback).

### §4a — Role taxonomy (10 roles, position-typed)

**Gate-sensitive** (use P-esl-register-clean):
- `intro_opener` — sentence 1 of intro; R8 strict (pub info + author + title + date)
- `intro_thesis` — last sentence of intro; R2 thesis statement
- `intro_setup` — middle sentences of intro
- `body_TS` — first sentence of body paragraph; R2 + instructor mandate (judgment statement in writer's words)
- `body_quote_lead_in` — sentence immediately preceding a quoted span
- `body_quote_follow_up` — sentence immediately after quoted span; explains the quote
- `conclusion_thesis_restate` — first sentence of conclusion; R2 thesis restatement
- `conclusion_structural` — conclusion sentences referencing source data / policy lever

**Body** (use P-esl-chinese-full):
- `body_elaboration` — body sentences developing argument
- `body_anecdote` — personal experience (cousin / friends / Chinese intuition sentences)
- `conclusion_closing` — final sentence(s)

**Locked** (never touched):
- `body_quoted_sentence` — sentence containing verbatim [Author A] quote

### §4b — Role classification prompt

Same shape as v2 humanizer §4b (worked examples + low-confidence fallback). When confidence < 0.70, default to most restrictive role (treat ambiguous body_elaboration as body_TS) — prevents ESL-chinese-full from accidentally firing in gate-sensitive positions.

### §4c — Issue dimensions (per v2 humanizer §4c)

D1 rubric_violation, D2 grammar_tortured, D3 unnatural_syntax, D4 voice_register_drift, D5 new_AI_tell_introduced, D6 meaning_distortion, D7 lock_or_credential_loss. Severity ∈ {MUST_FIX, SHOULD_FIX, NICE_TO_FIX}.

---

## §5 — Stage B + C + D: paragraph worker dispatch

### §5a — Build fix queue

```python
fix_queue = []
for fix_goal in audit["prioritized_fix_goals"]:
    role = audit["per_sentence"][fix_goal["target_seg_id"]]["role"]
    severity = fix_goal["severity"]
    if severity == "MUST_FIX":
        fix_queue.append(fix_goal)
    elif severity == "SHOULD_FIX" and role in BODY_ROLES:
        if include_should_fix:
            fix_queue.append(fix_goal)
    elif severity == "NICE_TO_FIX" and role in BODY_ROLES:
        if include_nice_to_fix:
            fix_queue.append(fix_goal)
    # SHOULD_FIX / NICE_TO_FIX in gate roles → skip (don't risk breaking R8/R2 for non-critical fix)
```

`BODY_ROLES = {"body_elaboration", "body_anecdote", "conclusion_closing"}`.

### §5b — Doc-level budget envelope

```python
doc_budget = {
    "esl_marker_per_para_target": {"body": 5, "gate_segment": 1},  # body para 3-5 markers; gate segments 0-1
    "esl_marker_per_para_warn": {"body": 8, "gate_segment": 2},    # warn thresholds
    "word_count_band": (550, 650),
}
```

### §5c — Spawn paragraph workers in parallel

Standard pattern (same as v1 surgical §5c).

---

## §6 — Stage Level-3: per-segment K-candidate generation

For each fix_goal, segment worker determines role → strategy assignment → K candidates.

### §6a — Strategy assignment matrix

| Role | Primary | Backup | K (MUST_FIX) | K (SHOULD_FIX) | K (NICE_TO_FIX) |
|---|---|---|---|---|---|
| intro_opener | P-esl-register-clean | P-academic-minimal | 3 (2+1) | — | — |
| intro_thesis | P-esl-register-clean | P-academic-minimal | 3 | — | — |
| intro_setup | P-esl-register-clean | P-academic-minimal | 3 | — | — |
| body_TS | P-esl-register-clean | P-academic-minimal | 3 | — | — |
| body_quote_lead_in | P-esl-register-clean | P-academic-minimal | 3 | — | — |
| body_quote_follow_up | P-esl-register-clean | P-academic-minimal | 3 | — | — |
| body_elaboration | **P-esl-chinese-full** | P-esl-register-clean | 3 (2+1) | 2 (1+1) | 1 (1+0) |
| body_anecdote | **P-esl-chinese-full** | P-esl-register-clean | 3 | 2 | 1 |
| conclusion_thesis_restate | P-esl-register-clean | P-academic-minimal | 3 | — | — |
| conclusion_structural | P-esl-register-clean | P-academic-minimal | 3 | — | — |
| conclusion_closing | P-esl-chinese-full (mild) | P-esl-register-clean | 3 | 2 | 1 |

K = (primary count + backup count). E.g. K=3 for MUST_FIX body = 2 × P-esl-chinese-full + 1 × P-esl-register-clean.

### §6b — Strategy P-esl-register-clean (gate positions)

> **Task**: rewrite this sentence to fix `{fix_directive}`. Use **Chinese-student ESL register** but with **CLEAN grammar** (no agreement errors, no missing articles).
>
> Apply 2-3 of these **ESL syntax/phrasing markers** (do NOT introduce grammar errors):
>
> - **Native-prep choice ESL**: "on [Publication]" instead of "in [Publication]"; "on Etsy" / "on YouTube" stay native (these are platform names, not registers)
> - **Direct-translation idiom**: "as I see" (从我看来) instead of "in my view"; "more and more" (越来越) instead of "increasingly"; "comes from" (来自) for causation
> - **Topic-prominent syntax**: "About X, ..." or "As for Y, ..." sentence opener
> - **Simpler tense**: drop past perfect / future perfect where simple past / future suffices ("had been breaking" → "was breaking")
> - **Genitive-fronted possessive**: "[Author A]'s article" instead of "[Author A]'s article in/of/by"
> - **Soft connective**: "But" / "And" sentence-initial instead of "However" / "Moreover"
>
> **STRICT prohibitions** (these are R9 grammar fails — never apply at gate positions):
> - NO subject-verb agreement slip ("[Author A] argue" / "data show" where native is "[Author A] argues" / "data shows") — KEEP correct agreement
> - NO article omission ("the diagnosis" must stay "the diagnosis")
> - NO dropped auxiliary ("she writing" instead of "she is writing")
>
> Constraints:
> - Preserve every `[LOCK_N]` placeholder byte-for-byte.
> - Word count within ±20% of original (sliding band per §6h of v2 humanizer).
> - Preserve meaning faithfully.
>
> **Original (already humanized)**: `{current_humanized_segment}`
> **Issue to fix**: `{fix_directive}`
> **Role**: `{role}` (gate-sensitive — clean grammar required)
>
> Output ONLY the rewritten sentence, no preamble.

### §6c — Strategy P-esl-chinese-full (body positions)

> **Task**: rewrite this sentence to fix `{fix_directive}`. Use **Chinese-student ESL register WITH visible grammar markers**.
>
> Apply 2-3 of these patterns:
>
> - **Article omission**: drop "the" or "a" 1-2 times per sentence ("the diagnosis" → "diagnosis"; "a classmate" → "one classmate")
> - **Subject-verb agreement slip**: bare-stem 3rd-person singular verb 1 per 50 words ("[Author A] argues" → "[Author A] argue"; "the data show" — actually this is sometimes correct; pick clear cases)
> - **Direct-translation idiom**: "as I see" / "more and more" / "from one side ... from other side"
> - **Topic-prominent syntax**: "About X, ..."
> - **Simpler tense**: drop past perfect
> - **Native-prep choice ESL**: "on [Publication]"
> - **Chinese emphatic**: "they two both step" (中式 "他们两个都")
> - **Dropped auxiliary**: "she writing" / "they not offering" (use sparingly — only when adjacent context supports)
>
> Cap: **max 3 marker types per sentence**. Errors must look like authentic Chinese-English ESL, NOT broken-text caricature. Reader must still understand the sentence.
>
> Constraints:
> - Preserve every `[LOCK_N]` placeholder byte-for-byte. Article omission must NOT drop the article preceding `[LOCK_N]` placeholder.
> - Word count within ±20% of original.
> - Preserve meaning faithfully.
>
> **Original (already humanized)**: `{current_humanized_segment}`
> **Issue to fix**: `{fix_directive}`
> **Role**: `{role}` (body — ESL markers allowed)
>
> Output ONLY the rewritten sentence, no preamble.

### §6d — Strategy P-academic-minimal (backup)

Same as v1 surgical §6b — minimal lexical sub + adjacent-clause swap in academic register, no structural transformation.

### §6e — Lock substitution + word-count gate (sliding tolerance)

Same as v2 humanizer §4d + §6h.

---

## §7 — Scoring + selection

### §7a — Gate evaluation (LLM-judge + deterministic)

For each candidate, evaluate:

1. **satisfies_fix_goal** (LLM-judge binary, with NICE_TO_FIX relaxation): does candidate address `{fix_directive}`? For NICE_TO_FIX: "improvement is sufficient, perfect fix not required."
2. **structural_rubric_pass** (deterministic):
   - If role is `intro_opener`: R8 opener regex matches first sentence (4-variant alternation per §S5 of plan)
   - If role is `body_TS`: contains R2 TS marker (`convincingly argues` / `I agree` / `could have strengthened` / etc.)
   - If role is `conclusion_thesis_restate`: contains thesis-restate language
3. **meaning_preserved** (LLM-judge binary)
4. **locks_intact** (deterministic — check `[LOCK_N]` count + position post-substitute)

### §7b — Levenshtein divergence

Same as v1 surgical §7c.

### §7c — Final score

```python
def candidate_score(c) -> float:
    if not c["meaning_preserved"]: return -1
    if not c["satisfies_fix_goal"]: return -1
    if not c["structural_rubric_pass"]: return -1
    if not c["locks_intact"]: return -1
    return -c["divergence"]  # negate so max(score) = min divergence
```

Pick `argmax`. Primary-strategy candidates get **tiebreak preference** when multiple candidates have score within 0.05 of each other.

### §7d — Fallback chain (per §S6 of plan)

```
primary candidate(s) pass gates? → pick min divergence among them
else: backup candidate(s) pass gates? → pick min divergence among them
else: spawn 1 × P-academic-minimal as last-resort → if passes, use
else: fall back to current_humanized (mark fallback_to_humanized: true, log in surgical_log)
```

---

## §8 — Doc-level verify (Stage E)

Six checks, plus informational R9 grammar tally:

1. **R8 opener regex** (4-variant alternation from plan §S5):

```python
R8_OPENER_PATTERNS = [
    # Standard MLA: In "Title" (Publication, Date), Author ...
    r'^In\s+["“][^"”]+["”]\s*\([^)]+,\s*\d+\s+\w+\s+\d{4}\)\s*,\s*[A-Z][\w\.]+',
    # ESL variant 1: In article "Title" on Publication, Date, Author ...
    r'^In\s+article\s+["“][^"”]+["”]\s+on\s+[A-Z][\w\s]+,\s*\d+\s+\w+\s+\d{4}\s*,\s*[A-Z][\w\.]+',
    # ESL variant 2: In Author's article "Title" on Publication (Date), ...
    r'^In\s+[A-Z][\w\.]+\'s\s+article\s+["“][^"”]+["”]\s+on\s+[A-Z][\w\s]+\s*\(',
    # American date order: In "Title" (Pub, Month Day, Year), Author ...
    r'^In\s+["“][^"”]+["”]\s*\([^)]+,\s*\w+\s+\d+,\s*\d{4}\)\s*,\s*[A-Z][\w\.]+',
]
intro_first_sentence = split_sentences(intro_text)[0]
r8_pass = any(re.match(p, intro_first_sentence) for p in R8_OPENER_PATTERNS)
```

2. **R2 body TS markers** (each body paragraph's first sentence contains a TS marker):

```python
BODY_TS_MARKERS = [
    r'\bconvincingly\s+argues?\b', r'\bI\s+agree\b', r'\bcould\s+have\s+strengthened\b',
    r'\bone\s+idea\s+I\s+find\b', r'\bI\s+find\b', r'\b[Author A]\s+fails?\b',
]
```

3. **R2 conclusion thesis restatement** (first conclusion sentence has restate language):

```python
CONC_RESTATE_MARKERS = [
    r'\bargument\s+(?:is|holds?)\s+strongest', r'\bdefensible\s+version',
    r'\bstructural\s+diagnosis', r'\b[Author A].{0,30}(?:argue|claim|case|argument)',
]
```

4. **R8 quote count**: intro 0, body 1 each, conclusion 0.

5. **R9 word count band**: total in [550, 650].

6. **Locks**: 17/17 byte-for-byte present.

**R9 grammar tally (informational)**: count visible ESL markers per paragraph. Body 3-5 markers/para target; if > 8 → WARN. Gate segments 0-1 markers; if > 2 → WARN. Log to surgical_log.json regardless.

If any gate WARNs (not FAILs) → status=`partial`. Caller decides re-invoke vs accept.

---

## §9 — Atomic single pass; caller iterates

Same design as v1 surgical §9 + v2 humanizer §9. Skill is one atomic pass. Caller decides re-invoke based on Grammarly score + human read of grammar marker density.

---

## §10 — Write artifacts

### `surgical_log.json` (extends v1 surgical schema)

```json
{
  "version": 3,
  "draft_path": "...",
  "output_path": "...",
  "config": {
    "include_should_fix": true,
    "include_nice_to_fix": false,
    "strategies": ["P-esl-register-clean", "P-esl-chinese-full", "P-academic-minimal"],
    "fix_queue_size": 25
  },
  "audit": {
    "total_sentences": 23,
    "fix_queue_breakdown": {
      "MUST_FIX_gate": 8,
      "MUST_FIX_body": 0,
      "SHOULD_FIX_body": 10,
      "NICE_TO_FIX_body": 0
    },
    "role_distribution": {...}
  },
  "doc_level_gates": {
    "R8_opener_regex_4_variant": "PASS|FAIL",
    "R2_body_TS_markers": "PASS|FAIL",
    "R2_conclusion_restate": "PASS|FAIL",
    "R8_quote_count": "PASS|FAIL",
    "R9_word_count": "PASS|FAIL (N)",
    "locks_intact": "PASS|FAIL (17/17)",
    "R9_grammar_tally": {"body_per_para": [4, 5, 3], "gate_segments": [0, 1, 0, 0, 2], "warnings": []}
  },
  "status": "ok|partial|error",
  "fallback_segments": <int>,
  "segments_modified": <int>,
  "strategy_usage": {"P-esl-register-clean": <int>, "P-esl-chinese-full": <int>, "P-academic-minimal": <int>},
  "total_llm_calls": <int>,
  "wallclock_seconds": <float>,
  "segments": [...]
}
```

---

## §11 — Token budget + cross-layer coordination

Inherit from v1 surgical §11. Parallel candidate dispatch within segment; sequential per paragraph (level 2); parallel paragraphs (level 1).

---

## §12 — Return summary

> `canvas-humanizer-surgical v3 complete. status: <ok|partial|error>. <N> segments modified across <P> paragraphs. <F> segments fell back to current humanized. Strategy usage: P-esl-register-clean <a>, P-esl-chinese-full <b>, P-academic-minimal <c>. Doc gates: R8 <pass/fail>, R2 body TS <pass/fail>, R2 conclusion <pass/fail>, quote count <pass/fail>, word count <N>, locks 17/17. R9 grammar tally: body <[4,5,3] avg X>/para; gate segments <Y> markers. Log: <path>. Output: <path>.`

---

## §13 — Overlay

Read `_private/canvas-humanizer-surgical-app.md` if exists. Inline defaults:

```yaml
# Fix scope
include_should_fix: true            # KEY change vs v1 surgical — lets body ESL fire
include_nice_to_fix: false

# Per-role strategy assignment (replaces v1 surgical's per-role gating matrix)
role_strategy_assignment:
  intro_opener:               {primary: P-esl-register-clean, backup: P-academic-minimal}
  intro_thesis:               {primary: P-esl-register-clean, backup: P-academic-minimal}
  intro_setup:                {primary: P-esl-register-clean, backup: P-academic-minimal}
  body_TS:                    {primary: P-esl-register-clean, backup: P-academic-minimal}
  body_quote_lead_in:         {primary: P-esl-register-clean, backup: P-academic-minimal}
  body_quote_follow_up:       {primary: P-esl-register-clean, backup: P-academic-minimal}
  body_elaboration:           {primary: P-esl-chinese-full, backup: P-esl-register-clean}
  body_anecdote:              {primary: P-esl-chinese-full, backup: P-esl-register-clean}
  conclusion_thesis_restate:  {primary: P-esl-register-clean, backup: P-academic-minimal}
  conclusion_structural:      {primary: P-esl-register-clean, backup: P-academic-minimal}
  conclusion_closing:         {primary: P-esl-chinese-full-mild, backup: P-esl-register-clean}

# K candidates per (severity × role-type)
K_must_fix_gate: 3              # 2 primary + 1 backup
K_must_fix_body: 3              # 2 primary + 1 backup
K_should_fix_body: 2            # 1 primary + 1 backup
K_nice_to_fix_body: 1           # 1 primary only

# R9 grammar tally thresholds (informational warnings)
r9_body_marker_warn_threshold: 8        # body para > 8 markers = WARN
r9_gate_marker_warn_threshold: 2        # gate segment > 2 markers = WARN

# Word-count sliding tolerance (inherited from v2 humanizer)
word_count_tolerance_short: 0.40
word_count_tolerance_medium: 0.30
word_count_tolerance_long: 0.20

# Parallelism
parallel_candidate_dispatch: true
parallel_segment_dispatch: true
parallel_paragraph_dispatch: true

# Detector metadata (skill is atomic; caller iterates)
detector_api: manual
detector_target: 22

# Banned phrases (post-surgical sanity)
banned_words_post_surgical:
  - Moreover
  - Furthermore
  - In conclusion
  - In summary
  - It's worth noting
  - It is important to note
  - delve
  - leverage
  - multifaceted
  - plethora
  - paradigm
  - In today's world

hard_locks: []
```

---

## §14 — Worked example: 3 named MUST_FIX from v2 + 2 body SHOULD_FIX

### FG1 — intro_opener (P-esl-register-clean, MUST_FIX, K=3)

**v2 text** (P5_S0, role=intro_opener):
> "Employer concentration, paired with noncompete agreements, has narrowed the channels through which workers move between firms; this four-decade structural shift, [Author A] argues in '[Article Title]' ([Publication], 22 April 2026), explains the bleak entry-level job market facing young Americans."

**Fix goal**: restructure to begin with full pub info per R8.

**Allowed strategies**: P-esl-register-clean (primary), P-academic-minimal (backup).

**K=3 candidates**:

| k | Strategy | Output | Grammar | R8 regex | Score |
|---|---|---|---|---|---|
| 0 | P-esl-register-clean | "In [Author A]'s article '[Article Title]' on [Publication] (22 April 2026), she argues that the bleak entry-level job market facing young Americans comes from a forty-year structural shift: employer concentration paired with noncompete agreements has narrowed the channels through which workers move between firms." | ✓ clean ("she argues" not "she argue"; "the bleak" not "bleak") | ✓ matches ESL variant 2 regex | **min divergence — winner** |
| 1 | P-esl-register-clean | "About this article '[Article Title]' by [Author A] on [Publication] (22 April 2026), it argues that..." | ✓ clean | ✗ doesn't match any R8 pattern | disqualified |
| 2 | P-academic-minimal | "[Author A] argues in '[Article Title]' ([Publication], 22 April 2026) that employer concentration, paired with noncompete agreements, has narrowed..." | ✓ | ✗ "[Author A] argues in" — fails standard MLA regex (requires "In" first) | disqualified |

Winner: k=0 (P-esl-register-clean). ESL syntax markers: "[Author A]'s article" (genitive-fronted), "on [Publication]" (native-prep ESL), "comes from" (direct-translation idiom). R9 grammar clean.

### FG2 — conclusion_structural (P-esl-register-clean, MUST_FIX)

**v2 text** (P8_S1):
> "...such as the Oregon ban that hourly wages were found by [Author C] and [Author D] to have been raised by two to three percent..."

**Winner candidate** (P-esl-register-clean):
> "...such as the Oregon ban, which [Author C] and [Author D]'s study finds raised hourly wages by two to three percent..."

ESL markers: "[Author C] and [Author D]'s study" (genitive-fronted possessive), "finds raised" (present tense ESL choice). Grammar clean. [Author C] / [Author D] / Oregon / two to three percent locks intact.

### FG3 — body_anecdote (P-esl-chinese-full, MUST_FIX, K=3)

**v2 text** (P7_S6, body_anecdote — locative-fronted):
> "Into work the closed firms will not offer them, a classmate who sells stickers on Etsy from her dorm and a friend who taught himself coding from YouTube both step sideways."

**K=3 candidates**:

| k | Strategy | Output | Markers visible | Score |
|---|---|---|---|---|
| 0 | P-esl-chinese-full | "One my classmate sell stickers on Etsy from her dorm, another friend learn coding by himself from YouTube. They two both step sideways to work that closed firms not offering them." | "One my" (article + word-order), "sell"/"learn" (SVA), "They two both" (Chinese emphatic), "not offering" (dropped aux) — 4 markers | **winner** |
| 1 | P-esl-chinese-full | "About my classmate, she sell stickers on Etsy from dorm; my friend learn coding from YouTube by himself. Both of them step sideways into work which closed firms not give them." | "About X" (topic-prominent), "sell"/"learn" (SVA), "from dorm" (article omission) — 3 markers | runner-up |
| 2 | P-esl-register-clean (backup) | "A classmate of mine selling stickers on Etsy from her dorm and a friend of mine teaching himself coding from YouTube both step sideways into work that the closed firms will not offer them." | 0 grammar errors, but "A classmate of mine" / "a friend of mine" ESL genitive style + SVO restored | available but not picked (primary won) |

Winner: k=0. 4 visible ESL markers within budget (body target 3-5/para; this segment alone has 4, but it's the high-density body_anecdote sentence; remaining body paragraph sentences add 0-1 each).

### FG_SHOULD_1 — body_elaboration (P-esl-chinese-full, SHOULD_FIX, K=2)

**v2 text** (e.g., P6_S6, an [Author B] data sentence that's SHOULD_FIX D3 unnatural syntax):
> "[Author B] traces the stagnation to rising employer concentration across industries from media to health care, and to the spread of noncompete agreements, which the Government Accountability Office found had bound 38 percent of workers at some point, including more than half of the hourly and part-time workers covered by such clauses."

**Winner candidate** (P-esl-chinese-full):
> "[Author B] trace stagnation to two reasons: employer concentration rise across industries from media to health care, and noncompete agreements spread very widely. Government Accountability Office found these clauses bind 38 percent of workers at some point, including more than half of hourly and part-time workers."

Markers: "[Author B] trace" (SVA), "employer concentration rise" (SVA + article omission), "very widely" (ESL adverb intensification), "found these clauses bind" (tense simplification). Split into two sentences (more direct, Chinese-style sentence rhythm). All locks ([Author B], Government Accountability Office, 38 percent) intact.

### Aggregate strategy usage (this essay)

| Strategy | MUST_FIX gate (8) | MUST_FIX body (0) | SHOULD_FIX body (~10) | Total |
|---|---|---|---|---|
| P-esl-register-clean | 8 | 0 | 0-2 (backup) | 8-10 |
| P-esl-chinese-full | 0 | 0 | 8-10 | 8-10 |
| P-academic-minimal | 0 (rare, only on failed primary) | 0 | 0 | 0-1 |

Total fix ops: ~18-20. ESL fire rate: **~95%** (vs v1 surgical's 0%).

---

## §15 — What surgical v3 does NOT do

- Do not apply ESL grammar markers in gate-sensitive positions (intro_opener / TS / quote integration / conclusion_thesis_restate / conclusion_structural)
- Do not modify segments without an audited issue (unless include_nice_to_fix=true)
- Do not change quote contents (locked)
- Do not internally iterate against external detector — atomic single pass
- Do not claim ESL strategy guarantees AI score reduction — empirical hypothesis
- Do not silently accept fallback_to_humanized — log every instance

---

## §16 — Cheat sheet vs v1 surgical

| Dimension | v1 surgical (regressed to 48%) | v3 surgical (this) |
|---|---|---|
| Strategy pool | 5 (P-academic, P-academic-minimal, P-mixed, P-esl-chinese, P-esl-russian) | **3** (P-esl-register-clean, P-esl-chinese-full, P-academic-minimal) |
| Per-role | Gating matrix (allow/deny) | Primary assignment (per role pick) |
| Fix scope | MUST_FIX only (15) | MUST_FIX + body SHOULD_FIX (~25) |
| ESL fire rate | 0/8 (architectural exclusion) | ~17-19/25 (~95%) |
| Gate positions | P-academic dominant | P-esl-register-clean dominant (clean grammar) |
| Body positions | No segments to fire on | P-esl-chinese-full (visible markers) |
| R8 verify | Single narrow regex | 4-variant alternation |
| R9 grammar | Clean (good) | Body markers visible (intended); gates clean |
| Grammarly result | 28% → 48% (regression) | 28% → 18-25% (hypothesis) |

End of canvas-humanizer-surgical v3 SKILL.md.
