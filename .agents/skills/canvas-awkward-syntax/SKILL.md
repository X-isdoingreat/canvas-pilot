---
name: canvas-awkward-syntax
description: Use when a short local academic draft needs role-aware syntax diversification while preserving meaning, locks, source grounding, rubric-critical openings, and document structure. Produce a reviewable local variant and never submit.
---

# canvas-awkward-syntax

Create one direct structural rewrite per eligible sentence. This is a bounded
humanizing pass for short drafts, not permission to degrade rubric-critical
language or fabricate content.

## Inputs and boundaries

Require:

- `draft_path`, `output_path`, and `voice_register`;
- `course_id`, `assignment_id`, and stable assignment `work_dir`;
- assignment spec/rubric anchors and optional hard locks;
- optional role overrides for ambiguous sentences.

Require `work_dir` to end in
`course-<course_id>__assignment-<assignment_id>`. Keep the original and write
`awkward_log.json` beside the output.
Validate the path against `src.course_artifacts.stable_work_dir` before writing.

This skill reads and writes local files only. It never calls Canvas or another
learning platform, never writes assignment `result.json`, and never declares a
submission ready.

## Required helpers

Use the existing symbols:

```python
from src.humanizer_segmentation import split_sentences
from src.humanizer_segment_extract import extract_locks
from src.awkward_transformation_assigner import (
    ROLE_ALLOWLIST,
    assign_transformations,
    contains_banned,
    validate_transformation,
    write_assignment_report,
)
```

Do not duplicate the role allowlist or balancing solver in prose code.

## Stage 1: segment, lock, and infer roles

Split before masking. Preserve `(doc_paragraph_index, intra_para_index)` as the
canonical segment identity. Treat short metadata/title/name paragraphs as
passthrough.

Lock quotations, citations, source names, dates, years, numbers, percentages,
required headings, URLs, bibliography entries, and caller-supplied spans.

Infer roles from position and local evidence:

- first paragraph: opener, thesis, setup;
- body: topic sentence, quote lead-in/follow-up, elaboration, anecdote, closing;
- last paragraph: thesis restatement, structural reflection, closing.

When inference is ambiguous, prefer the safer gate-sensitive role or honor a
caller-provided role map. Never infer an anecdote/source relationship that the
text does not support.

## Stage 2: assign transformations deterministically

Build records containing `seg_id`, paragraph/sentence indexes, `role`, and
`v0_text`, then call `assign_transformations(records)`.

The helper enforces:

- role-specific allowlists;
- per-paragraph repetition caps;
- document-wide opener-category caps;
- short-sentence fallback;
- controlled body register breaks and a conclusion first-person shift only in
  allowed roles;
- deterministic relaxation when a strict assignment is infeasible.

Persist the assignment with `write_assignment_report(...)` before generation.

## Stage 3: transformation semantics

Apply exactly the operation assigned by the helper:

| Transformation | Required effect |
|---|---|
| `voice_flip` | active↔passive without changing actor/action |
| `clause_reorder` | move an existing subordinate clause; add no claim |
| `nominalize_flip` | verbal↔nominal structure with same proposition |
| `pseudo_cleft` | foreground an existing element with a cleft |
| `fronted_pp` | move one existing prepositional phrase to the front |
| `fronted_when` / `fronted_while` | foreground an existing temporal/contrast relation |
| `fronted_participle_post_author` | insert a source-grounded participial appositive after an author |
| `gerund_subject` | recast the existing action as a gerund subject |
| `right_branching_extension` | retain subject/main verb early and move existing modifiers rightward |
| `topic_comment_chinese` | limited topic-comment order in an allowed body role |
| `article_omission_esl` | omit at most the configured articles without obscuring reference |
| `dual_connective_chinese` | use the configured paired connective without changing logic |
| `extraposed_copula` | use an allowed `It is ... that ...` frame |
| `fact_noun_complement` | express the existing proposition through `the fact that` |
| `formulaic_verb_noun` | use an allowed verb-noun collocation with same relation |
| `folk_wisdom_opener` / `discourse_pleonasm` | add only a configured discourse frame, no new fact |
| `slang_break` | short related aside only in an allowed low-risk body slot |
| `first_person_reflection` | source-grounded first-person reflection in an allowed conclusion role |
| `minimal_lexical` | smallest safe fallback change |

Do not apply a transformation whose required semantic relation is absent. In
that case return the original and mark `inapplicable`.

Avoid em dashes and semicolons when the configured voice bans them. A
transformation-specific validator must check the required structure rather than
trusting the generated label.

## Stage 4: bounded native subagents

Spawn one native Codex subagent per sentence, in parallel within the current
thread limit. Give each only:

- masked sentence and locks;
- assigned transformation and exact semantics above;
- role, voice, and essential rubric/source anchor;
- punctuation and banned-phrase constraints;
- instruction to return one sentence and no explanation.

Subagents do not read or write files. The main session owns validation,
fallback, splicing, and all artifacts.

## Stage 5: validate each rewrite

Reject and retry once when any check fails:

- required `[LOCK_N]` set differs or substituted lock text changes;
- sentence count is not exactly one;
- `validate_transformation(original, candidate, assigned_name)["ok"]` is false;
- meaning, source relationship, tense/causality, or rubric requirement changes;
- word count falls outside the configured band;
- unresolved placeholder appears;
- `contains_banned(candidate)` returns a phrase;
- punctuation violates the configured ban.

Use one fresh native Codex semantic reviewer for ambiguous meaning/voice cases.
After one failed retry, restore the original sentence. Never relax lock,
meaning, source, or rubric gates.

## Stage 6: splice and document verification

Restore locks and reassemble by canonical indexes. Preserve paragraph count,
headings, citations, quotations, and non-text document structure.

Verify at document level:

- every lock and source anchor remains exactly once where expected;
- non-target/pass-through text is unchanged;
- no segment split/merge and no paragraph reorder;
- assignment word-count bounds still pass;
- every accepted rewrite passes `contains_banned`;
- DOCX/PDF/Markdown output opens and contains no unresolved placeholder.

If a document-level check fails, roll back the offending segments. If the
output still cannot verify, keep the original and report failure.

## Stage 7: artifacts and handback

Write `output_path` atomically. Write `awkward_log.json` with:

- stable assignment IDs and input/output paths;
- role and assigned transformation per segment;
- relaxation level from the deterministic solver;
- accepted/retried/fallback outcome and validator evidence;
- lock, word-count, banned-phrase, and document checks;
- transformation/category distribution;
- remaining human-review risks.

Return output/log paths to the caller. The calling course skill must rerun its
full spec/rubric/source verification before it can write `draft_ready`.

## Failure behavior

- Missing spec/rubric anchors for a rubric-sensitive draft: stop.
- Transformation inapplicable or unsafe: restore that original segment.
- Excessive fallbacks or document check failure: return the untouched original
  as safest artifact and say why.
- Do not optimize against one external detector result; correctness and rubric
  preservation outrank syntax divergence.
