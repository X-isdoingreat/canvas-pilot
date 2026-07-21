---
name: canvas-humanizer
description: Reduces AI-detection signals in drafted text by routing every non-locked sentence through round-trip translation (English → intermediate language → English) and selecting the candidate that maximises deterministic structural divergence from the LLM-shaped original while preserving meaning and voice register. v2 abandons v1's LLM-as-judge convergence loop (self-referential, can't beat real detectors), replacing it with (a) sentence-level segmentation, (b) K-candidate generation via round-trip translation, (c) Levenshtein-based divergence scoring, (d) optional pluggable real-detector adapter. Designed for unlimited-token / unlimited-iteration callers where wallclock matters more than spend.
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Grep
  - Agent
---

# canvas-humanizer v2 — round-trip translation + deterministic divergence search

## §1 — Identity & contract (caller-facing, identical to v1)

**Inputs** (parsed from caller's prose context line; pattern-matching is the same as v1):

| Arg | Required | Default / fallback | Example |
|---|---|---|---|
| `draft_path` | yes | — | `C:\...\essay.docx` (.docx or .md) |
| `output_path` | yes | — | `C:\...\essay.humanized.docx` |
| `voice_register` | yes | — | `advanced-academic-english` |
| `student_identity` | **no** | falls back to `voice_register` value | `advanced-academic-english` |

If the caller's prose context omits `student_identity`, v2 silently uses `voice_register` as the identity. This restores backward compatibility with v1 callers that may have hardcoded only three args.

**Outputs**:

- `output_path` — humanized draft
- `<output_dir>/humanizer_log.json` — per-segment trace (candidates, scores, language paths)

**Status return**:

- `ok` — every segment cleared the meaning+voice gate AND structural divergence > 0.30
- `partial` — at least one segment had to fall back to original because no candidate passed meaning gate
- `error` — input validation failure (missing file, missing arg, etc.)

**Caller compatibility**: input/output contract is **identical to v1**. canvas-essay §7.5 invocation works unchanged.

---

## §2 — Why v2 (read this once, then never again)

v1 failed in production with a Turnitin AI-detection result of **75% AI** despite v1's internal 3D audit reporting `status: ok`. Five root causes (do not re-discuss in v2 SKILL.md — they are settled):

1. **LLM-as-judge is self-referential.** v1 used Claude/GPT to score Claude/GPT-generated text. Audit pass ≠ Turnitin pass.
2. **±5% word-count clamp was a structural straitjacket.** Real humanization needs sentence restructuring, not lexical substitution.
3. **Banned-words list is cosmetic.** AI fingerprint is in token-probability distributions, not in 30 high-frequency words.
4. **3 sequential passes (vocab → sentence → texture) all happen inside the LLM-English distribution.** Each pass stays in the mode it's trying to escape.
5. **No adversarial feedback loop.** v1 couldn't query the actual detector, so it had no idea whether it was getting closer to or further from passing.

v2's response to each:

| v1 failure | v2 fix |
|---|---|
| LLM-as-judge | Deterministic Levenshtein-based divergence; no LLM scoring of LLM output |
| ±5% clamp | ±20% per segment (relaxed); paragraph total allowed ±15% (vs v1's hard preserve) |
| Banned-words | Kept as a post-translation sanity check only, NOT as primary mechanism |
| In-distribution rewriting | Round-trip translation through non-English intermediate forces re-encoding through a different token distribution |
| No adversarial signal | Pluggable detector adapter; supports `manual` mode where caller pastes external score and the skill iterates against it |

---

## §3 — Pipeline overview

```
Input docx/md
  ↓
[§4] Identify preservation locks   →  list of verbatim spans that NEVER round-trip
  ↓
[§5] Segment to sentences          →  flat list of segments, each marked humanizable/locked
  ↓
[§6] Round-trip K candidates       →  per humanizable segment, K=3 round-trips via different intermediate languages
  ↓
[§7] Score candidates              →  for each: (meaning_preserved × voice_intact × divergence) ; pick max
  ↓
[§8] Reassemble                    →  substitute locks back, glue segments into paragraphs preserving doc_index
  ↓
[§9] (Optional) Detector loop      →  if overlay's detector_api != none, call adapter; iterate from §6 with deeper perturbation if score > target
  ↓
[§10] Write artifacts              →  output_path + humanizer_log.json
```

---

## §4 — Preservation locks

Some spans MUST survive every round-trip byte-for-byte:

- **Direct quotes** — anything between `"..."` (or `“...”`) that matches the source text
- **Named entities** — author names, place names, proper nouns the caller supplies
- **Numbers + dates** — `38 percent`, `1982`, `22 April 2026`, `two to three percent`
- **Caller-supplied hard locks** — overlay field `hard_locks` (per-essay list)

### §4a — Lock identification

Run a Python helper to extract candidate locks:

```python
import re, json
from pathlib import Path

def extract_locks(text: str, hard_locks: list[str]) -> list[tuple[int, int, str]]:
    """Return list of (start_char, end_char, span_text) for spans that must not be touched.
    Order: leftmost first; non-overlapping (longer wins on conflict)."""
    locks = []
    # 1. Quoted spans (straight or curly)
    for m in re.finditer(r'"([^"]+)"|"([^"]+)"', text):
        s, e = m.span()
        locks.append((s, e, text[s:e]))
    # 2. Years 1900-2099
    for m in re.finditer(r'\b(19|20)\d{2}\b', text):
        locks.append((m.start(), m.end(), m.group(0)))
    # 3. Percent literals (38 percent, 2 to 3 percent, etc.)
    for m in re.finditer(r'\b\d+(?:\s*(?:to|and)\s*\d+)?\s+percent\b', text, re.I):
        locks.append((m.start(), m.end(), m.group(0)))
    # 4. Dates like "22 April 2026" / "April 22, 2026" / "May 22"
    for m in re.finditer(r'\b\d{1,2}\s+(January|February|March|April|May|June|July|August|September|October|November|December)(?:\s+\d{4})?\b|\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:,\s*\d{4})?\b', text):
        locks.append((m.start(), m.end(), m.group(0)))
    # 5. Age-cohort terms (Gen Z, Gen X, millennials, etc.) — Claude routinely
    #    translates "Gen Z" → "Generation Z" / "Z 世代" without the agent NE pass
    #    catching it. Regex coverage prevents this.
    for m in re.finditer(r'\b(Gen\s*(?:Z|X|Y|Alpha)|Generation\s*(?:Z|X|Y|Alpha)|Millennials?|Boomers?|Gen\s*Z-ers|Gen-Zers)\b', text, re.I):
        locks.append((m.start(), m.end(), m.group(0)))
    # 6. Caller-supplied hard locks (search literally)
    for span in hard_locks:
        for m in re.finditer(re.escape(span), text):
            locks.append((m.start(), m.end(), m.group(0)))
    # Deduplicate + resolve overlaps: sort by start asc, length desc; greedy keep
    locks.sort(key=lambda t: (t[0], -(t[1]-t[0])))
    out, last_end = [], -1
    for s, e, sp in locks:
        if s >= last_end:
            out.append((s, e, sp))
            last_end = e
    return out
```

### §4b — Named-entity locks via Agent

After regex extraction, spawn ONE agent to find named-entity locks the regex missed:

> **Task**: list every proper noun OR domain-specific term in this text that should be preserved verbatim across translation. Return a JSON list of exact strings as they appear in the text. Include:
>
> - Person names (e.g., `[Author A]`, `[Author B]`)
> - Organizations (e.g., `Government Accountability Office`, `Federal Trade Commission`)
> - Publications (e.g., `[Publication]`, `Times Opinion`)
> - Geographic locations (e.g., `Shanghai`, `Oregon`)
> - Brand / product / platform names (e.g., `Etsy`, `YouTube`, `Canvas`)
> - **Age-cohort terms** (e.g., `Gen Z`, `Gen X`, `Millennials`, `Boomers`) — these are commonly translated/expanded into `Generation Z` / `Z 世代` by translators and must be locked
> - Technical / discipline-specific terms (e.g., `Current Population Survey`, `noncompete agreements`)
>
> Do NOT include common nouns, generic abstractions, or verbs. Do NOT paraphrase entries. Return at most 25 items as a JSON array of strings.
>
> Text:
> ```
> {text}
> ```

Add the returned strings to `hard_locks` before §4a's pass.

### §4c — Mask placeholders

Replace each lock span with `[LOCK_N]` where N is the lock index (0-based). The masked text passes to translation; the lock list passes alongside. After round-trip, substitute `[LOCK_N]` → exact original bytes.

### §4d — Order of operations: split THEN mask, not mask THEN split

**Important** (per 2026-05-22 full-essay run): do the §5 sentence splitting on the **unmasked** text first, then mask each sentence with **paragraph-global** lock indices. The reverse order — mask-then-split — fails when a lock span absorbs sentence-ending punctuation (e.g. a quote ending in `."` followed by `This finding...`), because the splitter can no longer find the sentence boundary inside `[LOCK_N]`. Always split first, mask second, but keep lock indices consistent across the whole paragraph (don't reuse index 0 in two different sentences).

---

## §5 — Sentence segmentation

Default level: **sentence**. Overlay can override to `clause` or `paragraph`.

### §5a — Sentence tokenizer

Use Python regex (avoid pulling NLTK/spaCy — zero-dependency policy):

```python
def split_sentences(text: str) -> list[str]:
    """Conservative sentence splitter: handles common abbreviations, decimals, ellipses."""
    # Protect common abbreviations + numeric decimals + ellipses
    protected = text
    abbrevs = ['Mr.', 'Mrs.', 'Ms.', 'Dr.', 'Prof.', 'Inc.', 'Ltd.', 'St.', 'Jr.', 'Sr.', 'vs.', 'e.g.', 'i.e.', 'etc.', 'Co.', 'U.S.', 'U.K.']
    for ab in abbrevs:
        protected = protected.replace(ab, ab.replace('.', '\x00'))
    # Protect decimals (3.14, 1,000.50). Use lambda — a raw-string replacement r'\1\x00\2'
    # would inject the LITERAL 4-char sequence \x00, not a NUL byte, because Python raw
    # strings don't interpret \x escapes. Lambda lets us insert a real NUL.
    protected = re.sub(r'(\d)\.(\d)', lambda m: m.group(1) + '\x00' + m.group(2), protected)
    # Protect ellipses
    protected = protected.replace('...', '\x00\x00\x00')
    # Split on .!? followed by whitespace+capital, OR end-of-string
    parts = re.split(r'(?<=[.!?])\s+(?=[A-Z"\'])', protected)
    # Unprotect
    parts = [p.replace('\x00\x00\x00', '...').replace('\x00', '.') for p in parts]
    return [p.strip() for p in parts if p.strip()]
```

### §5b — Per-segment metadata

For each sentence:

```python
{
  "seg_id": "S{n}",
  "doc_paragraph_index": <int>,   # which paragraph in docx
  "intra_para_index": <int>,      # 0-based position within paragraph
  "original": "<text>",
  "word_count": <int>,
  "contains_lock": <bool>,        # does any LOCK_N placeholder appear?
  "humanizable": <bool>,          # not entirely a lock, not too short (<5 words)
}
```

Skip segments where `humanizable == False`: name-block lines, title, short interjections, sentences that are ≥80% lock content.

---

## §6 — Candidate generation (K candidates via TWO parallel strategies)

For each humanizable segment, generate **K candidates** (default K=6) via **two parallel strategies**:

- **Strategy R (round-trip translation)** — K_R candidates, each a round-trip through a different intermediate language. Perturbs prose via cross-lingual re-encoding. Default K_R = 3.
- **Strategy P (structured English paraphrase)** — K_P candidates, each applying a different deterministic structural transformation in English. Perturbs prose via explicit syntactic surgery. Default K_P = 3.

K = K_R + K_P. Both strategies feed the same downstream scoring (§7). Selection is "max divergence subject to meaning + voice preservation" across the unified pool, regardless of which strategy produced the candidate.

**Honest framing** (per §2's design review): round-trip via Claude itself is **perturbed diversification**, not true distribution escape — the intermediate Chinese/Japanese/German output is still rendered by the same model. Strategy R + Strategy P together act as **diverse paraphrase generators**; the deterministic Levenshtein selection in §7 is what gives the pool detector-relevant value.

**Empirical observation** (2026-05-22 full-essay run on 23 humanizable sentences): Strategy R won **0 of 23** times when round-trip is executed by Claude. Strategy P won **23 of 23** — clause_reorder dominated (13), with voice_flip (5) and nominalize_flip (5) splitting the rest. The honest read: in-Claude round-trip produces candidates that cluster too close to the original (divergence range 0.05-0.30), while structured English paraphrase produces explicit syntactic perturbation that consistently scores higher on Levenshtein. **If real distribution escape is the target** (e.g. trying to take Turnitin score from 75% to <20%), the round-trip hop needs an external engine (DeepL / Google Translate API) — the K_R bucket then becomes load-bearing. Until then, the K_R candidates are essentially "free additional variety" with low win rate; K_P is doing the actual humanization work.

**Dispatch mechanism** (clarified after 2026-05-22 smoke test):

- **Preferred (parallel)**: when overlay has `parallel_candidate_dispatch: true` (the default), the orchestrator spawns the K candidates for one segment as **K parallel Agent tool calls in a single message**. This collapses ~5x wallclock and is the production-intended mode when canvas-essay §7.5 invokes the skill via Skill tool from a Claude Code session.
- **Acceptable (inline)**: when the skill is being executed by a sub-agent that prefers in-context generation (e.g., a wrapping general-purpose agent doing a smoke test), the same prompts in §6b and §6d can be executed as **direct LLM completions** rather than spawned Agent calls. Outputs are identical; only parallelism is lost.

Both modes follow the same §6b/§6d prompt templates and the same §7 selection rule. Choose based on whether the executing context has the Agent tool available and a clear parallelism win.

### §6a — Strategy R: round-trip translation

Language pool (overlay-overridable as `languages_to_round_trip_through`):

```yaml
- zh         # Chinese — strong typological distance from English
- ja         # Japanese
- de         # German — close to English syntactically; gentle round-trip
- es         # Spanish — Latin family
- fr         # French
- ko         # Korean
```

For each candidate `k_r` in `[0, K_R)`, pick language `pool[k_r % len(pool)]`. K_R=3 → uses zh, ja, de.

### §6b — Translation prompts

**Hop 1: EN → intermediate language**

Spawn 1 Agent per candidate. Prompt:

> **Task**: Translate the following English sentence to {language}. Constraints:
> - Preserve every `[LOCK_N]` placeholder byte-for-byte. Do NOT transliterate, reorder, translate, or convert to characters in another script. The literal sequence `[LOCK_N]` (left bracket, the letters `LOCK`, underscore, digit, right bracket) must appear in your output exactly as in the input. Treat the `[LOCK_N]` token as if it were a code variable, not a translatable phrase.
> - Preserve meaning faithfully.
> - Do not add commentary, parentheticals, or footnotes.
> - Output ONLY the translation, no preamble.
>
> **Sentence**:
> ```
> {masked_segment}
> ```

**Hop 2: intermediate → EN (with register restoration)**

Spawn 1 Agent per candidate. Prompt:

> **Task**: Translate the following {language} sentence to English, in the register of {voice_register}.
>
> Constraints:
> - Preserve every `[LOCK_N]` placeholder byte-for-byte. Do NOT transliterate, reorder, translate, or convert to characters in another script. The literal sequence `[LOCK_N]` (left bracket, the letters `LOCK`, underscore, digit, right bracket) must appear in your output exactly as in the input. Treat the `[LOCK_N]` token as if it were a code variable, not a translatable phrase.
> - Use natural English; do not produce a literal word-by-word back-translation.
> - Voice register guidance for `{voice_register}`:
>   - `advanced-academic-english`: long complex sentences, formal vocabulary, no contractions, no slang
>   - `b1-b2-international-student`: simple sentence structures, occasional missing articles, present-tense leaning
>   - (others fall back to native fluent English)
> - Do not introduce banned words from this list: {banned_list}
> - Output ONLY the English translation, no preamble, no quotation marks around the output.
>
> **Sentence**:
> ```
> {intermediate_text}
> ```

### §6c — Substitute locks back

After hop 2, `[LOCK_N]` placeholders in the candidate get replaced with the exact original bytes from §4. If a candidate has lost a lock placeholder (translation broke it), discard that candidate and retry once with the EN → intermediate hop. If still broken after one retry, mark candidate as `lock_lost` and exclude from selection.

**Per-segment lock check** (per 2026-05-22 full-essay run): when checking "did this candidate lose any locks?", check only against the locks that **appeared in this segment's masked original**, not against the full paragraph's lock list. Paragraph-wide checks falsely fail candidates whose segment didn't contain a lock that other segments did. Compute `required_locks_for_this_segment = {N for N in re.findall(r'\[LOCK_(\d+)\]', masked_segment_input)}` and only verify those indices are present in the candidate output.

### §6d — Strategy P: structured English paraphrase

For each candidate `k_p` in `[0, K_P)`, apply one **structural transformation** to the original sentence. Each transformation is a deterministic LLM-prompted rewrite that targets a specific syntactic dimension.

Default transformation set (overlay-overridable as `paraphrase_strategies`):

| Index | Name | Transformation |
|---|---|---|
| 0 | `voice_flip` | passive ↔ active. If sentence is in active voice, rewrite as passive (and vice versa). Subject and object swap; verb morphology changes. |
| 1 | `nominalize_flip` | nominalization ↔ verb. Convert abstract-noun phrases ("the diagnosis", "the recognition that") into verbal clauses ("she diagnoses", "we recognize that"), or vice versa. |
| 2 | `clause_reorder` | move subordinate clause from sentence-final to sentence-initial position (or vice versa). E.g., "X, because Y." → "Because Y, X." |
| 3 | `merge_split` | if sentence has two independent clauses, split into two sentences; if it has one clause, optionally merge with a borrowed connector from the surrounding context. |
| 4 | `lead_swap` | move the most informative noun phrase from object/oblique position to subject position via voice or pivot. |
| 5 | `connector_swap` | replace discourse connectors ("however", "yet", "by contrast", "instead", "rather") with structurally different alternatives, including dropping the connector and letting sequencing carry the contrast. |

For K_P=3, default transformations used are `voice_flip`, `nominalize_flip`, `clause_reorder`. Overlay can list a different subset.

Per-candidate prompt (one Agent spawn per K_P transformation):

> **Task**: Rewrite the following English sentence by applying the `{transformation_name}` transformation:
>
> `{transformation_description}`
>
> Constraints:
> - Preserve every `[LOCK_N]` placeholder byte-for-byte. Do NOT transliterate, reorder, translate, or convert to characters in another script. The literal sequence `[LOCK_N]` must appear in your output exactly as in the input.
> - Preserve meaning faithfully. If the transformation is genuinely impossible for this sentence (e.g., `voice_flip` on an intransitive sentence), output the sentence unchanged.
> - Voice register: `{voice_register}` — keep formal/informal register intact.
> - Do not introduce banned words from this list: {banned_list}
> - Output ONLY the rewritten sentence, no preamble, no quotation marks around the output, no explanation of what you did.
>
> **Sentence**:
> ```
> {masked_segment}
> ```

If the transformation prompt returns the unchanged input verbatim (transformation was impossible), mark candidate as `paraphrase_inapplicable` and exclude from §7 selection — but the candidate is not a failure, just a non-contribution to the pool.

Strategy P candidates do NOT round-trip through a non-English language. They are direct in-English rewrites. The candidate's value comes from the structural transformation being explicit (not "rewrite to be different"), producing reliably high Levenshtein divergence on the dimension targeted by the transformation.

### §6e — Word-count gate per candidate (sliding tolerance)

Compute `candidate_word_count / original_word_count`. Tolerance scales by original sentence length — short sentences need wider bands because a single em-dash parenthetical or fronted adverbial clause adds 3-5 words that blow a tight band.

```python
def word_count_tolerance(original_wc: int) -> tuple[float, float]:
    """Return (lower, upper) ratio band. Short sentences get wider bands."""
    if original_wc <= 15:
        return (0.70, 1.40)   # ±40% — covers clause_reorder parentheticals on short sentences
    elif original_wc <= 25:
        return (0.75, 1.30)   # ±30%
    else:
        return (0.80, 1.20)   # ±20% — original v2 default for longer segments
```

Outside band → discard candidate. Applies to both Strategy R and Strategy P candidates.

**Rationale**: smoke-test (2026-05-22 intro pass) found that on 25-word sentences, the highest-divergence candidates (clause_reorder, divergence 0.81 and 0.65) were disqualified by a fixed ±20% band, costing the pipeline its best perturbation. Sliding tolerance keeps the high-divergence candidates while still blocking truly runaway expansions.

---

## §7 — Candidate scoring + selection (deterministic, no LLM judge)

For each surviving candidate, compute three scores:

### §7a — `meaning_preserved` (LLM-judge, binary 0/1)

Spawn 1 Agent per (segment × candidate) pair. Prompt:

> **Task**: Given the original sentence and a candidate rewording, return JSON `{"meaning_preserved": true | false, "voice_register_intact": true | false, "rationale": "<one sentence>"}`.
>
> A meaning is preserved if the candidate makes the same claim about the same subject; minor surface differences (word order, synonyms) are fine. Voice register is `{voice_register}` — flag if candidate drifts to a noticeably different register (e.g. casual when advanced-academic expected).
>
> **Original**:
> ```
> {original}
> ```
>
> **Candidate**:
> ```
> {candidate}
> ```
>
> Output strict JSON only.

This is the ONLY LLM-judge call in v2, and it's a binary semantic question (was meaning preserved?), not a graded AI-detection question. Self-reference risk is much lower because the judge isn't asked "does this look LLM-shaped?" — it's asked "is the meaning the same?".

### §7b — `voice_register_intact` (same agent, same JSON response)

Returned by the §7a agent.

### §7c — `structural_divergence` (deterministic)

Computed in Python — no LLM:

```python
def levenshtein(a: str, b: str) -> int:
    """Standard DP edit distance, character-level."""
    if not a: return len(b)
    if not b: return len(a)
    prev = list(range(len(b)+1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0]*len(b)
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            cur[j] = min(cur[j-1]+1, prev[j]+1, prev[j-1]+cost)
        prev = cur
    return prev[-1]

def divergence(original: str, candidate: str) -> float:
    """0.0 = identical; 1.0 = totally different. Higher = more humanized."""
    if not original and not candidate: return 0.0
    L = max(len(original), len(candidate))
    return levenshtein(original, candidate) / L
```

`divergence` is in `[0.0, 1.0]`. We **want it high** (more humanized = more different from LLM-shaped original).

### §7d — Final score + selection

```python
def candidate_score(c) -> float:
    if not c["meaning_preserved"] or not c["voice_register_intact"]:
        return 0.0
    return c["divergence"]
```

Pick `argmax`. If max score == 0.0 (no candidate passed meaning gate), **fall back to original sentence** and mark segment as `partial` in the log.

**Why this works**: the selection rule is "biggest structural change subject to meaning preservation". v1 picked "passes LLM-judge audit". v2's selection signal is computable and adversarial-aware: Levenshtein distance is a property of the actual text, not an LLM's opinion of the text.

---

## §8 — Reassemble

```python
# After all segments processed
paragraphs = {}  # doc_paragraph_index → list of (intra_index, final_text)
for seg in segments:
    text = seg["final_text"] if seg["humanizable"] else seg["original"]
    paragraphs.setdefault(seg["doc_paragraph_index"], []).append((seg["intra_para_index"], text))

# Sort within paragraph, join with single space
final_paragraphs = {}
for pi, segs in paragraphs.items():
    segs.sort(key=lambda t: t[0])
    final_paragraphs[pi] = " ".join(t for _, t in segs)
```

### §8a — .docx output

```python
from docx import Document
out = Document(draft_path)  # start from input to preserve styles, headers, tables, italics
for i, para in enumerate(out.paragraphs):
    if i in final_paragraphs and final_paragraphs[i] != para.text:
        # Replace text while preserving first run's formatting
        if para.runs:
            para.runs[0].text = final_paragraphs[i]
            for run in para.runs[1:]:
                run.text = ""
        else:
            para.add_run(final_paragraphs[i])
out.save(output_path)
```

### §8b — .md output

Same array order; join with `\n\n`.

### §8c — Paragraph-level word-count gate

After reassembly, for each humanized paragraph compute `final_wc / original_wc`. Must be in `[0.85, 1.15]` (paragraph-level ±15%). If outside band, the caller is at risk of breaching their hard-constraint band (e.g. 550-650 total). Log a paragraph-drift warning; do NOT fail the run (caller's verify is the authority).

---

## §9 — Atomic single-pass; iteration is the caller's responsibility

**v2 is atomic**: one invocation = one humanization pass over the full draft. The skill runs §4-§8 once, writes the artifacts (§10), and returns. It does NOT internally loop against a detector score.

This is a deliberate design choice driven by two facts:

1. **Claude Code's Bash tool runs `-NonInteractive`** — `read` from stdin within a Skill execution context will not block-and-wait for user paste. A "manual mode" loop inside the skill cannot poll the user for a Turnitin score between iterations.
2. **Iteration is a caller-level concern** — canvas-essay §7.5 already owns the post-humanizer flow. If the caller wants to iterate based on an external detector score, the caller (a) reads `humanizer_log.json`, (b) presents the output to the human for testing, (c) decides whether to re-invoke the skill with deeper perturbation.

### §9a — Metadata field for caller-side iteration logic

Overlay can declare `detector_api` and `detector_target` for the **caller's** convenience — but the skill does not consume these fields during execution:

```yaml
detector_api: manual   # "gptzero" | "sapling" | "originality" | "manual" | "none" — INFORMATIONAL ONLY
detector_target: 30    # AI-probability target; caller decides when to re-invoke
```

These fields appear in `humanizer_log.json.config` so the caller can read them. Use them in caller-side glue code (canvas-essay §7.5 wrapper, or a manual orchestration loop) rather than expecting the skill to act on them.

### §9b — Re-invocation pattern (caller cookbook)

When the caller wants a deeper humanization pass after seeing a high external-detector score:

1. Caller writes a new overlay (or modifies inline) with progressively more aggressive settings:
   - `K = 6 → 10` (more candidates per segment)
   - `languages_to_round_trip_through` rotated to languages not used in prior pass
   - `paraphrase_strategies` set to include more transformations
   - `segment_level: sentence → clause` (smaller units, more perturbation surface)
2. Caller re-invokes canvas-humanizer with the new overlay. v2 runs another atomic pass.
3. Caller re-checks external detector score, decides whether to stop.

This pattern moves the "feedback loop" out of the skill and into caller orchestration where stdin / API / human interaction are viable.

---

## §10 — Write artifacts

### `output_path` (humanized draft)

Written by §8.

### `humanizer_log.json`

```json
{
  "version": 2,
  "draft_path": "...",
  "output_path": "...",
  "voice_register": "...",
  "student_identity": "...",
  "config": {
    "K_total": 6,
    "K_roundtrip": 3,
    "K_paraphrase": 3,
    "languages_used": ["zh", "ja", "de"],
    "paraphrase_strategies_used": ["voice_flip", "nominalize_flip", "clause_reorder"],
    "segment_level": "sentence",
    "word_count_tolerance_per_segment": 0.20,
    "detector_api": "manual",
    "detector_target": 30
  },
  "total_paragraphs": <int>,
  "total_segments": <int>,
  "humanizable_segments": <int>,
  "locked_segments": <int>,
  "total_llm_calls": <int>,
  "avg_divergence": <float>,
  "fallback_count": <int>,
  "status": "ok" | "partial" | "error",
  "segments": [
    {
      "seg_id": "S1",
      "doc_paragraph_index": 5,
      "intra_para_index": 0,
      "original_word_count": 47,
      "final_word_count": 51,
      "winning_strategy": "roundtrip" | "paraphrase",
      "winning_method": "zh" | "voice_flip" | "...",
      "candidates_considered": 6,
      "candidates_passed_meaning_gate": 4,
      "candidates_lost_lock": 1,
      "candidates_paraphrase_inapplicable": 1,
      "final_divergence": 0.62,
      "status": "ok",
      "fallback_to_original": false
    }
  ]
}
```

### §10a — Atomic writes

Write to `.tmp` first, then `os.replace`. Same as v1.

---

## §11 — Token budget & telemetry

v2 has **no hard cap** on token spend per the caller spec. But it logs every Agent call to enable caller-side monitoring:

```python
log_entry = {
  "seg_id": seg_id,
  "phase": "ne_extract" | "translate_to_intermediate" | "translate_back" | "paraphrase" | "meaning_check",
  "strategy": "roundtrip" | "paraphrase",
  "method": lang_code | transformation_name,
  "input_tokens_est": int(len(prompt) / 4),
  "output_tokens_est": int(len(response) / 4),
}
```

These rows accumulate in `humanizer_log.json` under `agent_calls`. Caller can sum / monitor without an enforced cap.

**Realistic wallclock expectation** (per Subagent B review): for a 600-word essay with ~40 humanizable segments × K=6 candidates × (1-2 agent calls per candidate) + 1 meaning-check per candidate = roughly **300-500 sequential Agent calls per atomic pass**. At 1-3 seconds per Agent call, total wallclock is **5-15 minutes**. Callers should treat this as a non-interactive batch step, not a live workflow turn.

Soft warning logged at 5M token estimate (informational only; no abort).

### §11a — Parallel candidate generation (optional optimization)

If runtime is unacceptable, candidates within the SAME segment can be spawned **in parallel** (single message, multiple Agent tool calls). The K_R round-trip candidates' Hop 1 (EN→intermediate) plus the K_P paraphrase candidates can all be issued as one batched parallel dispatch (K_R + K_P = K agents fired simultaneously). Hop 2 (intermediate→EN) for the K_R candidates can also be parallel. Meaning-gate checks can be parallel. This collapses ~5x wallclock factor at the cost of more bursty token usage.

Per-segment iteration is still **sequential** (segment N+1 doesn't start until segment N is selected), since the win for parallelism is within-segment and segment results are mostly independent.

---

## §12 — Return summary

Skill returns to caller via plain prose:

> `canvas-humanizer v2 complete. status: <ok|partial|error>. <humanizable_segments> humanizable segments across <total_paragraphs> paragraphs. avg structural divergence: <float>. <fallback_count> segments fell back to original (meaning gate failed). Strategy R won <r_win_count>, Strategy P won <p_win_count>. Log: <output_dir>/humanizer_log.json. Output: <output_path>.`

Caller decides whether to re-invoke for another atomic pass based on external detector score (see §9b).

---

## §13 — Overlay (optional, with inline fallback)

Read `_private/canvas-humanizer-app.md` if it exists. Otherwise use the inline defaults:

```yaml
# Candidate pool — Strategy R (round-trip) + Strategy P (paraphrase)
K_roundtrip: 3                       # number of round-trip candidates per segment
K_paraphrase: 3                      # number of structured-paraphrase candidates per segment
                                     # K_total = K_roundtrip + K_paraphrase

# Strategy R config
languages_to_round_trip_through: [zh, ja, de, es, fr, ko]

# Strategy P config
paraphrase_strategies: [voice_flip, nominalize_flip, clause_reorder, merge_split, lead_swap, connector_swap]
# Order matters: K_paraphrase candidates use paraphrase_strategies[0:K_paraphrase]

# Common
segment_level: sentence              # "sentence" | "clause" | "paragraph"
word_count_tolerance_per_segment: 0.20
word_count_tolerance_per_paragraph: 0.15
parallel_candidate_dispatch: true    # see §11a; if true, spawn K candidates in parallel within a segment

# Detector metadata — INFORMATIONAL ONLY, skill does not loop on these
detector_api: manual                 # "none" | "manual" | "gptzero" | "sapling" | "originality"
detector_target: 30

meaning_gate_threshold: true_required  # candidates with meaning_preserved=false are discarded

banned_words_post_translation:        # kept from v1, but only as POST-translation sanity check
  - delve
  - leverage
  - tapestry
  - multifaceted
  - plethora
  - paradigm
  - holistic
  - Moreover
  - Furthermore
  - In conclusion
  - It's important to note
  # ... (full v1 list — applied AFTER round-trip; if banned word reappears, retry round-trip once)

hard_locks: []                        # caller can supply additional verbatim spans
```

Overlay deep-merges over these. Missing fields stay at default.

---

## §14 — Worked example (concrete numbers for one segment)

Original segment (from a real essay):

> "She cites [Author B] and his colleagues, who analyzed Current Population Survey data from 1982 through 2023 and found that 'employed workers today are about half as likely to receive a better-paying outside offer as they were in the 1980s.'"

**§4 lock identification**:

- LOCK_0: `[Author B]`
- LOCK_1: `Current Population Survey`
- LOCK_2: `1982`
- LOCK_3: `2023`
- LOCK_4: `"employed workers today are about half as likely to receive a better-paying outside offer as they were in the 1980s"`

**Masked segment**:

> "She cites [LOCK_0] and his colleagues, who analyzed [LOCK_1] data from [LOCK_2] through [LOCK_3] and found that [LOCK_4]."

**§6 candidate pool K=6 (K_R=3 round-trip + K_P=3 paraphrase)**:

Strategy R candidates (round-trip):

| k | Strategy | Method | Round-tripped result (after lock substitution) |
|---|---|---|---|
| 0 | R | zh | "She draws on the work of [Author B] and his colleagues, who studied Current Population Survey data spanning 1982 to 2023 and concluded that 'employed workers today are about half as likely to receive a better-paying outside offer as they were in the 1980s.'" |
| 1 | R | ja | "She references [Author B] and his collaborators, whose analysis of Current Population Survey data covering the span from 1982 to 2023 yielded the finding that 'employed workers today are about half as likely to receive a better-paying outside offer as they were in the 1980s.'" |
| 2 | R | de | "She cites [Author B] and his colleagues, who analyzed Current Population Survey data running from 1982 to 2023 and established that 'employed workers today are about half as likely to receive a better-paying outside offer as they were in the 1980s.'" |

Strategy P candidates (structured paraphrase):

| k | Strategy | Method | Paraphrased result |
|---|---|---|---|
| 3 | P | voice_flip | "[Author B] and his colleagues are cited for an analysis of Current Population Survey data from 1982 through 2023, which found that 'employed workers today are about half as likely to receive a better-paying outside offer as they were in the 1980s.'" |
| 4 | P | nominalize_flip | "She cites the analysis by [Author B] and his colleagues of Current Population Survey data covering 1982 through 2023, finding that 'employed workers today are about half as likely to receive a better-paying outside offer as they were in the 1980s.'" |
| 5 | P | clause_reorder | "Analyzing Current Population Survey data from 1982 through 2023, [Author B] and his colleagues — whom she cites — found that 'employed workers today are about half as likely to receive a better-paying outside offer as they were in the 1980s.'" |

**§7 scoring**:

| k | strategy | meaning | voice | divergence | score |
|---|---|---|---|---|---|
| 0 | R-zh | true | true | 0.41 | 0.41 |
| 1 | R-ja | true | true | 0.55 | 0.55 |
| 2 | R-de | true | true | 0.18 | 0.18 |
| 3 | P-voice_flip | true | true | 0.49 | 0.49 |
| 4 | P-nominalize | true | true | 0.33 | 0.33 |
| 5 | P-clause_reorder | true | true | **0.61** | **0.61 (max)** |

Pick k=5 (clause_reorder, Strategy P). Moving the analytical clause to sentence-initial position with the citation as a parenthetical dash insertion produced the most structural change while preserving meaning + voice + all 5 locks intact.

This is the per-segment unit. Multiply by N segments × K=6 candidates × (translation hops + meaning check) = the token spend per atomic pass. With ~40 segments in a 600-word essay that runs ~300-500 Agent calls; wallclock 5-15 minutes sequential or ~1-3 minutes with parallel candidate dispatch (§11a).

---

## §15 — What v2 does NOT do (carry-overs from v1's MUST NOT)

- Do **not** re-choose voice register. Caller supplies it; v2 preserves it.
- Do **not** change paragraph count. Segments reassemble within their source paragraphs.
- Do **not** humanize quote contents or named entities. Locks are immutable.
- Do **not** audit spec compliance / plagiarism / argument quality. That's the caller's audit (canvas-essay §Y).
- Do **not** submit anything to Canvas. Pure file I/O.
- Do **not** trust meaning_preserved=true if the candidate has lost a lock placeholder. Lock loss → discard.
- Do **not** fall through to original silently when meaning gate fails. Mark `fallback_to_original: true` so the caller can surface for human review.

---

## §16 — Differences from v1 at a glance (cheat sheet)

| Dimension | v1 | v2 |
|---|---|---|
| Segment level | paragraph | sentence |
| Per-segment passes | 3 sequential (vocab, sentence, texture) | K=6 candidates: 3 round-trip + 3 structured paraphrase |
| Cross-distribution claim | no (all LLM rewriting in English) | partial — round-trip via Claude is **perturbed diversification**, not true distribution escape; structured paraphrase adds explicit syntactic perturbation |
| Scoring | LLM-judge 3D (burstiness/perplexity/vocab) | deterministic Levenshtein + binary meaning gate |
| Convergence signal | LLM-judge threshold (self-referential) | structural divergence (computable, adversarial-aware) |
| Internal iteration | 4 passes per paragraph (capped) | **none — atomic single pass**; caller iterates via re-invocation if needed |
| Word-count tolerance | ±5% per paragraph | ±20% per segment, ±15% per paragraph |
| Banned-words role | primary mechanism | post-translation sanity check only |
| Detector adapter | none | metadata-only fields in overlay; caller acts on them (skill does not) |
| Languages | n/a | zh, ja, de, es, fr, ko (overlay-configurable) |
| Paraphrase transformations | n/a | voice_flip, nominalize_flip, clause_reorder, merge_split, lead_swap, connector_swap (overlay-configurable) |
| `student_identity` arg | required | optional (falls back to `voice_register`) |
| Wallclock per pass | ~2-5 min | 5-15 min (300-500 sequential Agent calls; parallel mode collapses ~5x) |

End of v2 SKILL.md.
