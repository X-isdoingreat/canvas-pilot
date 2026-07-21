---
name: canvas-humanizer
description: Use when a local academic draft needs a meaning-preserving humanizing pass with less uniform syntax while retaining rubric, source, lock, voice, and length constraints. Operates on local files only and returns a reviewable transformed draft plus diagnostics.
---

# canvas-humanizer

Transform a verified local draft without changing its assignment claims,
citations, quoted material, required structure, or platform state. This skill is
an optional drafting stage, never a correctness guarantee or submission step.

## Inputs and boundaries

Require:

- `draft_path`: existing `.docx` or `.md`;
- `output_path`: new file with the same extension;
- `voice_register`;
- `course_id`, `assignment_id`, and the caller's stable `work_dir`;
- optional `student_identity`, `hard_locks`, and rubric anchors.

`work_dir` must end in
`course-<course_id>__assignment-<assignment_id>`, as produced by
`src.course_artifacts.stable_work_dir`. Both input and output must be inside the
current assignment's private run tree. Refuse to overwrite the only source
copy; keep the pre-pass draft.

This skill performs local file I/O only. Never call Canvas or another learning
platform. It does not write assignment `result.json`; the calling course skill
does that after re-running its own verification.

Write `humanizer_log.json` beside `output_path`. Diagnostic values in that file
are internal pipeline outcomes, not Canvas Pilot result statuses.

## Deterministic helpers

Use the existing symbols instead of reimplementing them:

```python
from src.humanizer_segmentation import split_sentences, segment_paragraph
from src.humanizer_segment_extract import extract_locks
from src.humanizer_score import score_candidate, divergence
```

For DOCX extraction, the existing command is also available:

```text
python -m src.humanizer_segment_extract --draft <draft.docx> --out-dir <state-dir> --voice <voice>
```

It writes `_state.json` with paragraph/sentence IDs and masked locks.

## Stage 1: preserve before rewriting

Read the complete draft and rubric anchors. Mark metadata/title/name blocks and
paragraphs shorter than ten words as passthrough unless the caller explicitly
opts them in.

Extract and lock:

- direct quotations and quoted titles;
- dates, years, percentages, measurements, and required numbers;
- author/source names, citations, URLs, and bibliography entries;
- rubric-required headings and exact prompt language;
- caller-supplied hard locks.

Resolve overlaps longest-first and mask each sentence with paragraph-local
`[LOCK_N]` placeholders. Split into sentences before masking. Record original
paragraph index and intra-paragraph sentence index; those two values are the
canonical segment identity.

## Stage 2: generate candidates

For each humanizable sentence, create a small candidate pool using two
strategies. Batch independent native Codex subagents to reduce wall time, but
keep each subtask bounded to one masked sentence and one transformation.

### Strategy R: round trip

Generate up to three candidates through distinct intermediate languages. Each
subtask must:

1. translate masked English to the assigned intermediate language while
   preserving every `[LOCK_N]` byte-for-byte;
2. translate that result back to English in the requested voice;
3. return only the candidate sentence.

Treat this as controlled diversification, not proof of detector evasion.

### Strategy P: structured paraphrase

Generate up to three candidates using different structural operations:

- clause reorder;
- active/passive voice flip when grammatically possible;
- verbal/nominal form flip.

Each subtask preserves all locks and meaning, stays within the requested voice,
returns one complete sentence, and returns the original unchanged when the
operation is genuinely inapplicable.

Never pass the full private assignment to a candidate subagent. Give only the
masked sentence, voice, exact operation, and necessary rubric anchor.

## Stage 3: deterministic gates

Substitute lock text back and call `score_candidate(...)` for every candidate.
Reject a candidate if:

- any required lock is missing, duplicated, changed, or reordered improperly;
- its word-count ratio falls outside the helper's length-dependent band;
- it is identical to the original because the transformation was inapplicable;
- it introduces an unresolved placeholder.

Record lock, word-count, and divergence measurements in the log.

## Stage 4: independent meaning and voice gate

For the surviving candidates of one sentence, spawn one fresh native Codex
review subagent with the original, candidates, voice criteria, and only the
rubric anchors needed for that sentence. Require strict JSON per candidate:

```json
{
  "candidate_id": "P1",
  "meaning_preserved": true,
  "voice_register_intact": true,
  "rubric_damage": false,
  "reason": "short evidence-based explanation"
}
```

Reject any candidate with meaning loss, voice drift, new factual content,
citation damage, or rubric damage. The reviewer is a semantic gate; it does not
score stylistic preference.

## Stage 5: select and reassemble

Among candidates passing every gate, choose the greatest deterministic
Levenshtein divergence from the original. If none pass, retain the original and
mark a fallback. Do not force a rewrite merely to change text.

Reassemble sentences by `(doc_paragraph_index, intra_para_index)`. Preserve
paragraph count/order, passthrough paragraphs, headings, and DOCX layout. For a
DOCX, preserve styles, headers, tables, and non-text structure; replacing text
must not flatten the document.

Measure each final paragraph against its original word count. Flag ratios
outside `[0.85, 1.15]` for caller review. Check all locks again over the final
document.

## Stage 6: write artifacts atomically

Write the output to a temporary sibling and atomically replace `output_path`
only after it opens successfully. Write `humanizer_log.json` with:

- input/output paths and voice;
- paragraph and segment counts;
- candidate/gate counts per segment;
- selected strategy and divergence;
- fallback segments and reasons;
- paragraph word-count ratios;
- final lock, citation, and placeholder checks;
- internal outcome and limitations.

The log must not contain private source bodies beyond the minimum sentence-level
trace needed for local debugging.

## Stage 7: caller handback

Return the output and log paths plus a concise summary. Explicitly state that
the caller must rerun assignment-level checks for word count, citations,
structure, source grounding, and rubric coverage. Do not mark an assignment
ready or submitted here.

## Failure behavior

- Invalid/missing input: do not create output; write a diagnostic when possible.
- Some segments have no safe candidate: retain originals and continue.
- Output cannot reopen or final lock check fails: keep the original draft,
  remove the invalid temporary output, and report failure.
- Never weaken locks, meaning gates, or rubric gates to obtain more rewrites.
