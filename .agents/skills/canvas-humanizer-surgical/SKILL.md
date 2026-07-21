---
name: canvas-humanizer-surgical
description: Use after canvas-humanizer when a local draft has specific meaning, grammar, citation, fluency, voice, or rubric defects. Repair only named segments, preserve safe text, and return a verified local artifact without submitting.
---

# canvas-humanizer-surgical

Apply a targeted second pass. Do not reopen the whole draft when only a small
set of segments is damaged.

## Inputs and boundaries

Require:

- `draft_path`, `output_path`, and prior `humanizer_log.json`;
- `course_id`, `assignment_id`, and stable assignment `work_dir`;
- voice register and relevant spec/rubric/source anchors;
- explicit issue list or an audit artifact identifying target segments;
- optional hard locks and banned-phrase list.

Require `work_dir` to end in
`course-<course_id>__assignment-<assignment_id>`. Keep a source copy and write
`surgical_log.json` beside the new output.
Validate the path against `src.course_artifacts.stable_work_dir` before writing.

This is local file transformation only. Never call Canvas, mutate an external
platform, write assignment `result.json`, or claim the assignment is ready.

Use the canonical sentence utilities from `src.humanizer_segmentation`, lock
logic from `src.humanizer_segment_extract.extract_locks`, and deterministic
scoring from `src.humanizer_score`.

## Stage 1: audit and role tagging

Map every target to `(doc_paragraph_index, intra_para_index)` and verify its
exact current text. Reject stale issue records whose anchor no longer matches.

Classify target roles conservatively:

- `intro_opener`, `intro_thesis`, `intro_setup`;
- `body_topic_sentence`, `body_quote_lead_in`, `body_quote_follow_up`;
- `body_elaboration`, `body_anecdote`, `body_closing`;
- `conclusion_thesis_restate`, `conclusion_structural`,
  `conclusion_closing`.

For each target, record severity (`MUST_FIX` or `SHOULD_FIX`), damage
dimensions, locks, rubric sensitivity, and one concrete repair objective.
Audit verdicts are diagnostic labels, not Canvas Pilot result statuses.

## Stage 2: build the fix queue

Include every MUST_FIX. Include SHOULD_FIX only when it is in a body position
and the repair has low source/rubric risk. Never modify a PASS segment.

Group targets by paragraph so one paragraph worker can see local continuity.
Set a document change budget before generation:

- change no more than the queued segments;
- preserve paragraph and sentence counts;
- preserve all direct quotes, citations, proper nouns, numbers, and required
  wording;
- keep total word count within the caller's assignment bounds.

## Stage 3: position-aware strategy

Use cleaner repairs for gate-sensitive positions and more visibly nonuniform
syntax only in safe body positions.

### Gate-sensitive positions

For introductions, thesis/topic sentences, quotation integration, and
conclusion thesis restatement:

- keep grammar clear enough for the rubric;
- prefer clause reorder, light article/preposition variation, or direct
  sentence simplification;
- do not add slang, new claims, or conspicuous grammar errors;
- keep subject, claim, and source relationship explicit.

### Body elaboration and anecdote

When the configured voice genuinely calls for it, allow controlled ESL-shaped
syntax such as limited article omission, topic-comment order, or one small
agreement slip. Never apply these markers to quotations, citations, formulas,
or a sentence whose meaning depends on tense/agreement precision.

### Backup

Use an academic-minimal repair that changes only the named defect when every
larger transformation fails a gate.

## Stage 4: parallel paragraph workers

Spawn one native Codex subagent per affected paragraph, in parallel within the
available thread limit. Give each worker:

- original and current paragraph;
- exact queued segment IDs and role/severity;
- locks, voice, rubric anchors, and banned phrases;
- strategy allowed for each segment;
- an instruction to return candidates only, never modify files.

Generate K candidates per target: normally 3 for MUST_FIX and 2 for eligible
SHOULD_FIX. Every candidate must be one sentence and preserve segment identity.

## Stage 5: gate and select

Deterministically reject candidates that:

- lose, duplicate, alter, or reorder required locks/citations;
- fall outside `src.humanizer_score.word_count_tolerance`;
- introduce unresolved placeholders or banned phrases;
- split/merge a segment or change paragraph count;
- violate caller numeric constraints.

Then use a fresh native Codex review subagent to evaluate meaning, voice,
grammar intelligibility, source grounding, and rubric damage for surviving
candidates. Select the greatest deterministic divergence among candidates that
fix the named defect and pass every gate. If none pass, use the academic-minimal
backup; if that fails, restore the original segment.

## Stage 6: document-level verification

Reassemble only accepted target replacements. Verify:

- every original non-target segment is byte-identical;
- paragraph/segment counts and order are unchanged;
- all quotes, citations, numbers, names, and hard locks remain;
- every MUST_FIX issue is either repaired or explicitly unresolved;
- banned phrases and unresolved placeholders are absent;
- word count remains within assignment limits;
- output opens with its original format and retains DOCX structure.

If a document-level check fails, roll back the offending replacement and rerun
once. Never broaden the queue to make a local repair easier.

## Stage 7: artifacts and handback

Write `output_path` atomically and create `surgical_log.json` containing:

- input/output paths and stable assignment IDs;
- target role, severity, damage dimensions, and source anchor;
- candidates and deterministic gate measurements;
- selected strategy/divergence or rollback reason;
- changed and unchanged segment counts;
- document-level checks and unresolved issues.

Return these paths to the caller. The caller must rerun its full assignment
spec/rubric/source checks before writing `draft_ready`.

## Failure behavior

- Missing/stale issue anchors: stop rather than repair the wrong sentence.
- No safe candidate: retain the original and log the unresolved issue.
- Output verification failure: preserve the input and reject the output.
- Never use an external detector score as permission to damage meaning or the
  rubric.
