---
name: canvas-inside
description: Use for an approved Canvas Classic Quiz routed by canvas-execute. Build source-grounded study notes, run four independent native Codex answer passes, and perform only the exact quiz mutations authorized by a signed receipt; fail closed for New Quizzes, locks, missing sources, or incomplete authority.
---

# Canvas Classic Quiz workflow

Handle `online_quiz` assignments with a real Classic Quiz `quiz_id`. Supported
question types are multiple choice, multiple answers, true/false, matching,
short answer, fill-in-multiple-blanks, multiple dropdowns, numerical, and
essay. New Quizzes (`external_tool` with no `quiz_id`) and online text entries
are outside this skill.

Plan approval permits the approved local work only. It never grants authority
to start an attempt, save an answer or event, complete an attempt, or retake.

## Entry and artifact contract

Require `run_dir`, `course_id`, `assignment_id`, the validated assignment
snapshot and approved plan item. Create the only work directory with:

```python
from src.course_artifacts import ensure_stable_work_dir

work_dir = ensure_stable_work_dir(run_dir, course_id, assignment_id)
```

Its name is exactly `course-<course_id>__assignment-<assignment_id>`. Keep all
quiz evidence there:

```text
quiz_meta.json
readings/
references/
study_notes.md
submission.json
questions.json
questions_simplified.json
agent_passes/
final_answers.json
answer_log.json
attempt-1/
attempt-2/
audit/learning_log.json
result.json
```

Read `_private/canvas-inside-app.md` first and select the exact course block.
It may contain the course whitelist, recurring quiz scope, instructor framework
primer, expected canonical knowledge, human-hours window, rate limit, target
score band and retake threshold. If the block is absent, write `error` with
`reason_code=missing_course_overlay`, recommend a separate `canvas-bootstrap`
run, and stop. Never copy private overlay values into this tracked skill.

## 1. Classify without starting an attempt

Read the assignment, current submission and quiz metadata. Save the complete
quiz object atomically as `quiz_meta.json`, adding exact `course_id`, `quiz_id`
and `assignment_id`; its `id` must also equal `quiz_id`. Before answer or
complete mutations, Stage 4 adds the current `session_id`, positive integer
`attempt`, and `authorization_receipt_id`. Never copy a signature or validation
token into this metadata file.

Classify as follows:

| Evidence | Outcome |
|---|---|
| `online_quiz`, non-null `quiz_id`, `question_count >= 5`, and a finite `time_limit` | Continue as a full Classic Quiz |
| no `quiz_id`, or `external_tool` | `skipped`: unsupported New Quiz or non-quiz |
| one question plus video/lecture language or no time limit | `skipped`: required video interaction is unavailable |
| `locked_for_user`, proctoring, LockDown Browser, or identity-presence requirement | `skipped`: intrinsically manual |
| any other shape | `draft_ready` with existing `draft_path=quiz_meta.json` and `reason_code=unclassified_quiz` |

Do not infer the quiz shape from its name. If an inaccessible video or
third-party source may have a transcript, ask the student for the link. Continue
without it only when the remaining authoritative sources are sufficient.

## 2. Discover the real readings

Do this read-only stage before checking scheduling toggles or mutation
authority. It must produce `study_notes.md`, so a later `draft_ready` result has
a real deliverable.

Write `verification.log` at the same stage with measured PASS/FAIL lines for
metadata capture, required-reading coverage, source traceability, and
unresolved placeholders. An unclassified quiz that returns `quiz_meta.json`
must still record a real metadata-capture PASS. No `draft_ready` result is
valid while this log is missing, empty, or contains FAIL.

Use a four-layer source hunt; the Canvas description is only a routing hint.

1. **Section/week module:** list modules, identify the relevant section or week,
   then read every Page, download every File, and follow every External URL.
2. **Course files plus syllabus:** list course files, inspect the syllabus or
   schedule mapping, then locate the named textbook chapter, slides, lesson
   plan, or attachment.
3. **Local extraction:** save originals under `readings/`; extract searchable
   text from PDFs and other readable files beside them. Preserve page/source
   anchors.
4. **Public-source fallback:** only when the assigned text remains unavailable,
   search by exact title, author and book. Prefer the original text, publisher,
   author, library or other primary source. Save reconstructed notes under
   `references/` and label their confidence as medium or low.

If no sufficiently authoritative source remains after all four layers, write
`error` with `reason_code=required_reading_unavailable`; do not guess answers.

Build `study_notes.md` from the retrieved evidence. For each reading include:

- central thesis;
- key claims with page, paragraph, slide or URL anchors;
- names, dates, places and concepts;
- likely true/false or distinction targets;
- confidence and any source weakness.

For multiple readings, add cross-cutting themes. Put the overlay's instructor
framework primer at the top, clearly labeled as course context, and keep direct
source claims distinguishable from inference.

## 3. Preflight every mutation gate

After `study_notes.md` exists, enforce the four scheduling gates:

1. `CANVAS_QUIZ_AUTORUN=1`; otherwise return `draft_ready` with
   `draft_path=study_notes.md`.
2. Current `America/Los_Angeles` hour is inside `CANVAS_QUIZ_HUMAN_HOURS` or
   the overlay window; otherwise return the same `draft_ready` form.
3. `runs/_processed.json` contains fewer submitted quiz results in the prior
   six hours than `CANVAS_QUIZ_MAX_PER_RUN` or the overlay limit; otherwise
   return the same `draft_ready` form.
4. The exact course is in `whitelisted_course_ids`; otherwise write `skipped`.

Scheduling flags and a whitelist are not mutation authority. Require the signed,
unexpired `authorization_receipt_path` supplied by `canvas-submit` or an
authorized delegation; the interactive default is
`<work_dir>/mutation_authorization.json`. It must be bound to the current Canvas
origin, course, `target_type="quiz"`, exact `target_id=quiz_id`, current Codex
session, and exact action set. Validate every anticipated action through
`src.authorization.load_authorization_receipt` and
`validate_authorization_receipt` before starting, so a later scope failure
cannot waste an attempt.

| Runtime call | Required receipt action |
|---|---|
| `cv.start_quiz_submission(..., is_retake=False)` | `quiz.start` |
| every `cv.post_quiz_events(...)` | `quiz.event` |
| every `cv.answer_quiz_questions(...)` | `quiz.answer` |
| `cv.complete_quiz_submission(...)` | `quiz.complete` |
| `cv.start_quiz_submission(..., is_retake=True)` | `quiz.retake` |

Attempt 1 therefore needs `quiz.start`, `quiz.event`, `quiz.answer`, and
`quiz.complete`. Add `quiz.retake` only when the student's exact authorized
workflow includes another attempt. No action implies another, and no wildcard,
environment boolean, plan decision, overlay sentence, or prior receipt may
replace an exact action. If the receipt is absent, invalid, expired, origin-
mismatched, target-mismatched, session-mismatched, or missing a required action,
write `draft_ready` with `draft_path=study_notes.md` and make no mutation.

Pass the same validated receipt to every client mutation. The client remains
the authoritative enforcement boundary.

## 4. Open attempt 1 and collect questions

Start only after the entire attempt-1 scope has passed preflight:

```python
sub = cv.start_quiz_submission(
    course_id, quiz_id,
    authorization_receipt=authorization_receipt,
)
```

Save the submission id, attempt number, validation token, `end_at`, and response
clock to `submission.json`. Post one `session_started` event using the
`quiz.event` scope. Fetch questions only from the student submission endpoint:

```python
questions = cv.get_quiz_submission_questions(submission_id)
```

Save `questions.json`. Never bulk-post `question_viewed` events at open; pair
each view with its later answer. Immediately after start, atomically update
`quiz_meta.json` with `course_id`, `quiz_id`, `assignment_id`, the validated
receipt's `session_id` and `receipt_id` (stored as
`authorization_receipt_id`), and `attempt=sub["attempt"]`. These values bind
all later local evidence to this one open attempt.

## 5. Normalize every supported question type

Strip HTML for reasoning while retaining raw question and answer identifiers.
Write `questions_simplified.json`. Preserve these answer shapes exactly:

| Canvas type | `final_answers.json` answer value |
|---|---|
| `multiple_choice_question` | one answer id |
| `true_false_question` | one answer id |
| `multiple_answers_question` | list of answer ids |
| `matching_question` | list of `{answer_id, match_id}` objects |
| `short_answer_question` | terse exact-match token, not a sentence |
| `fill_in_multiple_blanks_question` | `{blank_id: terse token}` |
| `multiple_dropdowns_question` | `{blank_id: answer_id}` |
| `numerical_question` | number or numeric string within the stated tolerance |
| `essay_question` | source-grounded prose string |

For blank questions, union prompt `[variable_name]` tokens with every returned
`answers[].blank_id`; those variable names are the submission keys. Keep
dropdown options grouped by blank. Never paste raw reading text into an essay.

## 6. Run four independent native Codex subagents in parallel

Spawn four separate native Codex subagents in one parallel dispatch, before
awaiting any one result. Give each `study_notes.md`, normalized questions and
the source files, but do not give it another pass, a proposed final answer, or
the expected disagreement.

- **notes-first:** answer from `study_notes.md`, then verify uncertain claims in
  the exact source.
- **grep-first:** search the full extracts for every question before using
  general knowledge; cite a source anchor.
- **framework-aware:** use direct readings first and the overlay primer only for
  explicit lecture/framing questions.
- **contrarian:** challenge traps, negations, restrictive words, matching
  pairings and every option in a multiple-answer question.

Require each subagent to return only a JSON array. Every entry includes `qnum`,
`question_id`, `type`, the correctly shaped `answer`, `confidence`, a concise
`reasoning`, and `source_anchor`. Short and blank answers use the most likely
accepted token; alternatives belong in reasoning, never in the answer value.

Preserve each returned array verbatim under `answers` in an evidence envelope
whose `context` exactly repeats `quiz_meta.json`'s six binding fields and whose
`agent_role` names that pass. Save the four envelopes immediately as:

```text
agent_passes/notes_first.json
agent_passes/grep_first.json
agent_passes/framework_aware.json
agent_passes/contrarian.json
```

They must be valid, independently produced JSON files. Do not synthesize four
personas in one response, clone a file, or manufacture disagreement. All four
may honestly choose the same answers when their independent reasoning and
source checks support that consensus.

## 7. Arbitrate and write canonical evidence

Tabulate all four passes per question:

- 4-0 agreement: accept it;
- 3-1: take the majority and record the dissent;
- 2-2: resolve from an exact source anchor, wording and course framework;
- differing multiple-answer sets: verify every option separately.

Write `final_answers.json` before any answer mutation:

```json
{
  "context": {
    "course_id": "12",
    "quiz_id": "34",
    "assignment_id": "56",
    "session_id": "<current Codex session>",
    "attempt": 1,
    "authorization_receipt_id": "<receipt id>"
  },
  "arbitration_notes": {
    "unanimous_count": 4,
    "flagged_qnums": [3],
    "Q3": "2-2 split resolved from source anchor ..."
  },
  "answers": [
    {
      "qnum": 1,
      "question_id": 101,
      "type": "multiple_choice_question",
      "answer": 1001,
      "confidence": "high",
      "source_anchor": "reading-a.txt paragraph 8"
    }
  ]
}
```

The integer `arbitration_notes.unanimous_count`, the exact current-attempt
`context`, and at least four JSON files in `agent_passes/` are required by
`src.canvas_client._require_canonical_arbitration_evidence`. Answer consensus
is valid; four canonically identical substantive arrays (answers plus reasoning)
are copy-paste evidence and fail. If honest evidence cannot satisfy that guard,
write `error`; never forge it. A degraded method is
allowed only when `CANVAS_QUIZ_DEGRADED_OK` contains the student's verbatim,
specific consent of at least ten non-space characters, and that same text is
recorded as `degraded_method_user_consent`. It bypasses only the arbitration
evidence guard, never the signed mutation receipt.

Use `src.quiz_focus_events.pick_flagged_questions` for a capped subset of
low/medium-confidence questions. The optional
`src.quiz_strategic_miss.maybe_flip_answers` branch runs only when
`CANVAS_QUIZ_STRATEGIC_MISS=1`; never flip a high-confidence or constructed-
response answer and retain its full log. It does not grant mutation authority.

## 8. Save answers with paced interaction

Use `src.quiz_pacing.compute_answer_schedule` and `build_answer_sequence`, plus
`src.quiz_focus_events.pick_blur_slots`. Target about 78% of the Canvas time
limit, include non-linear revisits, and spend at least 30 seconds on every
first-answer slot. Base deadline decisions on Canvas's response clock and
`end_at`, not an unverified local clock.

For each sequence slot, preserve this order:

1. post `question_viewed` with `quiz.event`;
2. wait the scheduled read/thinking interval;
3. optionally post paired `page_blurred` and `page_focused` events;
4. optionally post `question_flagged` once;
5. call `cv.answer_quiz_questions` with `course_id`, `quiz_id`, `assignment_id`,
   explicit `work_dir`, and `quiz.answer` authority;
6. post `question_answered` with `quiz.event`;
7. append timings and event outcomes to `answer_log.json`.

The answer call must receive the value from `final_answers.json` verbatim; do
not reshape it during submission. Pass the same validated receipt and exact
stable `work_dir`; an enforced Codex runtime rejects omitted or stale context.

An HTTP 500 from an answer save is a possible false negative. Immediately read
back `cv.get_quiz_submission_questions(submission_id)`, compare the stored
answer to the canonical value, and re-post only a genuine mismatch. Treat it as
an error only when the readback remains wrong or empty after that targeted
retry. Record the response and readback evidence.

## 9. Complete and verify

`CANVAS_QUIZ_SUBMIT=0` disables completion but grants no authority; return
`draft_ready` with `draft_path=study_notes.md` and note that the authorized
attempt remains open. Otherwise call `cv.complete_quiz_submission` with the
`quiz.complete` scope plus `assignment_id`, explicit `work_dir`, and the same
validated receipt used by the attempt.

A completion HTTP 500 is also inconclusive. Read back
`cv.get_submission(course_id, assignment_id)`. Treat `workflow_state` of
`submitted` or `graded`, or a real `submitted_at`, as success. If readback says
the attempt did not finalize, write `error`, leave it open, surface the exact
state, and do not automatically repeat `/complete`.

## 10. Score and retake only under the declared policy

Read the kept score, points possible, attempt count, allowed attempts and
scoring policy from Canvas. Use the overlay retake threshold, default `0.95`.

- At or above threshold: stop after attempt 1.
- No attempts remain: stop and record the limit.
- Policy is `keep_latest` or `keep_average`: do not risk another attempt.
- Below threshold with attempts left and `keep_highest`: take attempt 2 unless
  the student explicitly declines and the verbatim decline is recorded as
  `degraded_method_user_consent`.

Before a retake, require a still-valid exact `quiz.retake` scope in addition to
`quiz.event`, `quiz.answer`, and `quiz.complete`. `quiz.start` does not imply
`quiz.retake`.

Fetch attempt-1 feedback with `cv.get_quiz_attempt_feedback` when visible. Save
it as `attempt-1/feedback.json`. For repeated questions, keep verified-correct
answers and fix verified misses. Question banks may reshuffle, so start the
authorized retake, fetch its actual questions, and treat every new question as
new work. If feedback is hidden, rearbitrate all uncertain questions.

Archive attempt-1 pass/evidence files under `attempt-1/`. Then run four fresh
parallel subagents for attempt 2 and write their raw JSON plus fresh
`final_answers.json` to the canonical root paths before saving answers; archive
the finished set under `attempt-2/` afterward. Run the same paced event/answer
loop and completion readback. Save `attempt-2/plan.json`, submission data and
`attempt2_method` (`feedback-driven`, `rearbitration`, or a documented hybrid).
Under `keep_highest`, verify `kept_score` from Canvas rather than merely
assuming the local maximum. On attempt 2, atomically replace the attempt value
in `quiz_meta.json` and create fresh pass/final evidence whose context carries
that same attempt, session, and receipt before any answer mutation.

After the final chosen attempt is read-back verified, inspect
`src.authorization.authorization_usage_status(receipt)`. If the receipt allows
`quiz.retake` but no retake is chosen, or the ledger otherwise lacks
`terminal_at`, call
`src.authorization.finalize_authorization_usage(receipt, reason=...)`. A second
completion may already mark it terminal; verify that rather than assuming it.
Only a ledger entry with `terminal_at` permits
`authorization_consumed=true` in the submitted result.

## 11. Post-submit learning audit

After final grading, if per-question feedback is visible, spawn one fresh native
Codex subagent with `final_answers.json`, all raw passes, `study_notes.md`, exact
sources and feedback. Ask only for high-confidence misses and require JSON with
question, picked/correct answer, source anchor used, corrected source anchor,
whether the passes disagreed, and a concrete lesson.

Atomically save the array to `audit/learning_log.json` and reference it in
`result.json`. This is a non-gating learning step; it never changes a finished
submission or creates another attempt. Skip it honestly when item-level
feedback is unavailable.

## 12. Canonical result and diagnostics

Write only `draft_ready`, `submitted`, `skipped`, or `error` through
`src.run_state.write_result`. Every `draft_ready` branch must point to an
existing `study_notes.md` or `quiz_meta.json`; never claim notes before Stage 2
created them. Canvas `graded` belongs only in
`metadata.canvas_workflow_state`, never in `status`.

A submitted quiz result includes at least:

```json
{
  "kind": "quiz",
  "status": "submitted",
  "submitted_at": "<verified Canvas timestamp>",
  "metadata": {"canvas_workflow_state": "submitted", "readback_verified": true},
  "authorization_receipt_id": "<non-secret receipt id>",
  "authorization_consumed": true,
  "quiz_id": "<quiz id>",
  "questions_answered": 5,
  "attempt_1_score": 5,
  "attempt_2_score": null,
  "kept_score": 5,
  "points_possible": 5,
  "percent": 100.0,
  "attempts_used": 1,
  "allowed_attempts": 2,
  "scoring_policy": "keep_highest",
  "agent_passes_count": 4,
  "attempt2_method": null,
  "attempt1_feedback_unavailable": false,
  "degraded_method_user_consent": null,
  "human_ness_diagnostics": {
    "user_agent_used": "<observed browser user agent>",
    "human_hours_window": "<enforced local window>",
    "started_at_pt_hour": 13,
    "views_paired_with_answers": true,
    "total_answer_time_seconds": 420,
    "total_time_limit_seconds": 600,
    "time_utilization": 0.7,
    "per_question_cv": 0.45,
    "answer_sequence_linear": false,
    "revisits": 1,
    "events_posted": 12,
    "blur_events_count": 1,
    "flagged_questions_count": 1,
    "outlier_count": 0,
    "strategic_miss_enabled": false,
    "strategic_miss_count": 0
  }
}
```

Compute diagnostics from `answer_log.json`, not from expectation:

- coefficient of variation is standard deviation divided by mean over initial
  answer sleeps;
- sequence is non-linear only when order changed or a revisit occurred;
- view pairing is true only when every view was emitted beside its answer;
- blur, flag, event, outlier and strategic-miss counts come from actual logs.

Also record attempt scores, `attempt2_method`, feedback availability and
`learning_log` when applicable. Validate the final payload before atomic write.

## First-run stage mode

Honor a single-stage directive only when both the invocation contains
`STAGE-BY-STAGE MODE` and `<work_dir>/.first_run_stage_by_stage` exists.
Supported ordered stages are `classify`, `reading-discovery`, `study-notes`,
`safety-gates`, `open-submission`, `arbitration`, `paced-submit`, `complete`,
`score-check`, `retake`, and `learning-audit`.

Run exactly the named stage, require all prior artifacts, write a concise
`stages/<stage>.done`, and stop. Mutation stages still require the same signed
receipt, scheduling gates and arbitration evidence. Never use first-run mode to
bypass a gate or start an attempt during draft-only bootstrap calibration.
Normal daily execution runs the full ordered workflow.

## Non-negotiable stops

- Do not mutate a quiz without the exact signed receipt action for that call.
- Do not start outside the whitelist, authorized time/rate window, or declared
  autorun mode.
- Do not bulk-view, burst-answer, forge pass evidence, or create an executable
  bypass under `runs/`.
- Do not guess missing readings or blank identifiers.
- Do not retry a readback-confirmed completion failure.
- Do not expose receipt secrets, private overlay content, or source-restricted
  course material in tracked files or chat.
