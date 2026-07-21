---
name: canvas-humanizer-loop
description: Use when a local draft needs repeated canvas-humanizer passes with independent meaning, structure, citation, voice, and rubric-damage checks. Converge conservatively, return the safest local artifact, and never submit.
---

# canvas-humanizer-loop

Wrap `canvas-humanizer` in a bounded repair loop. The purpose is to catch
damage introduced by rewriting, not to keep rewriting until an external score
changes.

## Inputs and boundaries

Accept the same paths and voice inputs as `canvas-humanizer`, plus:

- `course_id`, `assignment_id`, and the stable assignment `work_dir`;
- optional `spec_path`, `rubric_path`, `source_paths`, and `hard_locks`;
- `max_iter`, default 3 and hard-capped at 3.

Require `work_dir` to end in
`course-<course_id>__assignment-<assignment_id>`. Write loop artifacts below
`<output_dir>/_loop_iter_<N>/` and `loop_log.json` beside the final output.
Validate the path against `src.course_artifacts.stable_work_dir` before writing.

This skill performs local file work only. It does not call Canvas, write an
assignment `result.json`, or declare submission readiness. The caller must run
its course-level verification after the loop.

Use `src.humanizer_segmentation.split_sentences` and
`paragraph_segment_counts`; do not invent another splitter.

## Iteration layout

```text
_loop_iter_1/
  humanized.docx
  humanizer_log.json
  audit-a.json
  audit-b.json
  audit-c.json
  merged-audit.json
  repair-log.json
_loop_iter_2/
...
loop_log.json
```

Use atomic JSON/text writes. Keep the original draft and every iteration so the
best safe artifact can be recovered.

## Stage 1: preflight

1. Read the complete original, spec, rubric, and necessary source excerpts.
2. Confirm hard locks are unique enough to track. If a lock occurs multiple
   times, index occurrences rather than relying on raw string replacement.
3. Capture original paragraph order, segment counts, citations, headings,
   numeric constraints, and source anchors.
4. Reject missing required spec/rubric/source inputs when the caller says they
   are mandatory.

## Stage 2: run one humanizer pass

Invoke the Codex `canvas-humanizer` skill using the current iteration input and
write its output/log into `_loop_iter_<N>/`. On the first iteration the input is
the original. On later iterations the input is the repaired prior output with
already-safe segments locked.

If the humanizer cannot produce a valid output, stop and return the safest
historical artifact (the original if no iteration succeeded).

## Stage 3: three independent audits

Spawn three native Codex audit subagents in parallel. Give each only the raw
original, current output, spec/rubric anchors, source excerpts, and the schema
below. Do not give them another reviewer's verdict.

Each auditor evaluates every canonical segment
`(doc_paragraph_index, intra_para_index)` for:

- meaning/factual drift;
- missing, altered, duplicated, or moved locks/citations;
- structural damage or segment merge/split;
- grammar that obscures meaning;
- voice-register drift;
- rubric or source-grounding damage;
- word-count/format risk.

Require strict JSON:

```json
{
  "segments": [
    {
      "doc_paragraph_index": 3,
      "intra_para_index": 1,
      "verdict": "MUST_FIX",
      "dimensions": ["meaning_drift"],
      "original_anchor": "exact text",
      "current_anchor": "exact text",
      "fix_directive": "one specific repair"
    }
  ]
}
```

Allowed verdicts are `PASS`, `SHOULD_FIX`, and `MUST_FIX`; these are audit
verdicts, not Canvas Pilot result statuses.

## Stage 4: majority merge

Merge by canonical segment ID:

- `MUST_FIX` when at least two auditors say MUST_FIX, or one says MUST_FIX and
  another independently flags the same damage dimension;
- `SHOULD_FIX` when at least two say SHOULD_FIX and no majority MUST_FIX;
- otherwise `PASS`.

Any deterministic failure—missing lock/citation, changed paragraph count,
segment split/merge, unresolved placeholder, or missing required heading—is
`MUST_FIX` regardless of model vote.

Write `merged-audit.json` with all three raw verdicts, merged verdict,
dimensions, and exact anchors. Do not hide disagreement.

## Stage 5: convergence decision

Finish successfully when there are zero merged MUST_FIX segments and all
deterministic document checks pass. SHOULD_FIX items may remain only when a
repair would create greater meaning/rubric risk; preserve them in the log for
the caller.

Stop early and return the safest historical iteration when any guard fires:

1. **verdict monotonicity** — the same segment improves and then regresses;
2. **structural drift persistence** — the same paragraph changes segment count
   in two consecutive iterations;
3. **oscillation** — the same damage dimension alternates across iterations;
4. **hard cap** — `max_iter` reached.

Rank historical iterations by, in order: deterministic failures, MUST_FIX
count, source/citation damage, SHOULD_FIX count, then total divergence. Never
prefer style divergence over correctness.

## Stage 6: targeted repair

For each merged MUST_FIX segment, spawn one bounded native Codex repair
subagent. Send only the original segment, current segment, locks, voice, rubric
anchor, damage dimensions, and merged fix directive.

Require one complete replacement sentence and strict metadata. The repair may
not split or merge segments. Validate locks, citations, word-count band, and
placeholder absence deterministically. If validation fails, retry once; then
restore the original segment.

Lock every PASS segment before the next humanizer invocation. Reassemble the
repaired document without changing paragraph order or formatting and record
each accepted/rejected repair in `repair-log.json`.

## Stage 7: finalize

Copy the safest selected iteration to `output_path` atomically. Reopen it and
rerun final checks against the original:

- paragraph/heading structure;
- canonical segment mapping;
- all locks, citations, numbers, and source anchors;
- caller-supplied word-count bounds;
- no unresolved placeholders.

Write `loop_log.json` with iteration summaries, raw/merged audit paths, repair
counts, convergence reason, selected iteration, remaining review items, and
verification limitations. Return paths to the caller, which must rerun the
assignment-level rubric gate.

## Failure behavior

- Never delete or overwrite the original.
- Never continue merely because iteration budget remains.
- Never silently accept a structural-drift or citation failure.
- If every transformed iteration is worse, return the verified original and
  say so explicitly.
