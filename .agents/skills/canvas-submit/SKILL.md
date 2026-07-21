---
name: canvas-submit
description: Use only for a separate exact later-message Canvas command (`submit N`, `take quiz N`, or `retake quiz N`) for one current approved item. Create one scoped receipt, perform only that mutation, verify Canvas read-back, and write the canonical result. Reject broad, automatic, ambiguous, or hypothetical requests.
---

# canvas-submit

Perform one explicitly authorized Canvas mutation after the scan, approval, and
draft boundary. This skill is the interactive submit entry point; neither
`canvas-scan`, `canvas-execute`, nor a course drafting skill may invoke it on
the user's behalf.

## 1. Enforce the later-message boundary

Use the raw text of the **current user message**. Never reconstruct authority
from an earlier message, quoted text, a plan decision, an overlay, a schedule,
or the agent's own recommendation.

Pass the complete current message to
`src.mutation_approval.parse_mutation_command`. Accept only one whole
expression recognized by that parser:

- `submit N` or `提交第N项` for one ordinary assignment;
- `take quiz N`, `参加测验第N项`, or `做测验第N项` for one first quiz attempt;
- `retake quiz N`, `重做测验第N项`, or `重考测验第N项` for one explicitly
  authorized retake.

Outer whitespace may be retained, but no other prose is allowed. Reject
`submit all`, `approve all`, `please submit 1`, `submit 1 and 2`,
`take quiz 1 now`, hypotheticals, and any command copied from a prior turn. One message
authorizes at most one indexed target. Never translate a vague request into an
accepted command.

Plan approval is not submission authority. `approve 1`, `all`, `do 1`, and a
`plan.json` decision may authorize drafting through `canvas-execute`, but they
must never mint or substitute for a mutation receipt. This skill is not an
automatic-submit or cron workflow.

## 2. Bind the current plan target

Use only the run directory associated with the current scan presented in this
conversation. Require its non-expired `plan.json` and matching
`assignments.json`; do not search older run directories for a convenient
target. Validate them with
`src.run_state.validate_plan_assignments(..., run_dir=run_dir,
require_current=True)`.

The requested index must resolve to one contiguous 1-based plan item whose
`user_decision` is `approve` or `swap:canvas-*`, and that item must have a
one-to-one snapshot match. If the plan is absent, stale, unapproved, or
inconsistent, stop and require a fresh scan/approval. Never repair plan state
inside this skill.

Derive the only allowed work directory from immutable IDs:

```python
from src.run_state import stable_work_dir

work_dir = stable_work_dir(run_dir, course_id, assignment_id)
```

It must be named `course-<course_id>__assignment-<assignment_id>`. Never use a
course name, assignment name, slug, or arbitrary path as identity.

## 3. Require a verified ordinary-assignment draft

For `submit N`, perform this local fail-closed preflight before issuing a
receipt:

1. Require `<work_dir>/result.json` to exist.
2. Load it and call
   `src.run_state.validate_result(result, root=Path.cwd(),
   work_dir=work_dir)`; do not trust a status string without validation.
3. Require the validated status to be exactly `draft_ready`.
4. Require the resolved `draft_path` to be substantive and contained inside
   the stable work directory. Never submit a path supplied only in chat.
5. Call `src.run_state.validate_verification_log` on the verification evidence
   selected by the result contract. It must contain at least one `PASS` line,
   no `FAIL` line, and no unresolved placeholder/skeleton sentinel.
6. Confirm the result, plan item, snapshot, course ID, assignment ID, and
   intended payload all refer to the same target.

A missing draft, directory escape, error/skipped result, failed verification,
or ambiguous payload must stop before Canvas mutation. Do not regenerate, edit, or
silently replace the draft in this skill; return to the responsible course
skill instead.

Quiz commands do not use this ordinary-draft gate. Their read-only reading,
notes, arbitration, pacing, and mutation gates remain owned by
`canvas-inside`.

## 4. Issue one exact signed receipt

After the applicable local preflight, call
`src.mutation_approval.issue_interactive_authorization` with:

- the exact current `run_dir`;
- the configured origin from `src.canvas_client.BASE`, never a URL invented
  from chat;
- `user_text` equal to the verbatim current user message;
- the default protected local signing key and current Codex thread/session.

The helper repeats current-plan validation, derives the exact target/actions,
and writes these private artifacts below the stable work directory:

```text
mutation_authority.json
mutation_authorization.json
```

Use `synthetic_qa=True` only inside an independently verified, isolated local
QA Canvas. It is always false for a real Canvas origin. Do not print, copy,
publish, broaden, refresh, or hand-edit a receipt. A receipt for one course,
assignment/quiz, origin, session, or action cannot authorize another.

If authorization issuance fails, stop without mutation. Receipt issuance by
itself is not receipt consumption.

## 5. Dispatch one ordinary submission

Load `<work_dir>/mutation_authorization.json` with
`src.authorization.load_authorization_receipt` and pass that same receipt to
every write. Select one payload mode from the validated snapshot:

| Canvas submission type | Exact receipt action(s) | Required canonical payload | Allowed wrapper |
|---|---|---|---|
| `online_text_entry` | `assignment.submit_text` | one non-empty UTF-8 text draft | `src.canvas_submit_origin.submit_text_with_view` |
| `online_upload` | `assignment.upload_init`, `assignment.upload_blob`, `assignment.submit_files` | the draft file, or an explicit ordered `metadata.submission_files` list fully contained below `work_dir` | `src.canvas_submit_origin.upload_and_submit_files_with_view` |
| `online_url` | `assignment.submit_url` | one spec-verified HTTP(S) URL from the canonical draft metadata/artifact | `src.canvas_submit_origin.submit_url_with_view` |
| `online_quiz` | quiz-scoped actions only | no ordinary payload | hand off to `canvas-inside` as described below |

When the snapshot declares several supported types, require
`result.metadata.submission_type` to choose exactly one declared mode. Do not
pick the first type, submit the same artifact through multiple modes, glob a
directory, extract text from a binary document, or infer extra attachments.
Unsupported types such as `external_tool`, `on_paper`, and proctored delivery
are not made submit-capable by the user's command.

For file and text submissions, the receipt-aware
`python -m scripts.submit_canvas` CLI is an allowed adapter, but use only its
single-target mode with `--authorization-receipt`. Never use
`--batch-manifest` from this skill. The direct `src.canvas_submit_origin`
wrappers are preferred because they return the authoritative read-back object.
If the CLI is used, require exit code 0 and perform a fresh read-only Canvas
submission read-back before writing the result.

Never call `cv.submit_text`, `cv.submit_files`, `cv.submit_url`,
`cv.upload_submission_file`, or raw Canvas mutation endpoints here. The
origin wrappers must perform the pre-read, pass the exact receipt through each
write, and read the submission back after the write.

## 6. Hand Classic Quiz work to canvas-inside

For `take quiz N` or `retake quiz N`, require the snapshot to declare only
`online_quiz`, include the exact `quiz_id`, and route to `canvas-inside`.
Provide its native Codex skill handoff with:

```text
run_dir=<current run directory>
work_dir=<stable ID-based work directory>
course_id=<exact snapshot course ID>
assignment_id=<exact snapshot assignment ID>
quiz_id=<exact snapshot quiz ID>
authorization_receipt_path=<work_dir>/mutation_authorization.json
mutation_operation=quiz_take|quiz_retake
```

The first-attempt receipt must not contain `quiz.retake`. Only the exact
`retake quiz N` command may issue that action. Do not start, answer, complete,
or retake the quiz inline in this skill. `canvas-inside` must validate the
receipt, bind its quiz evidence to this work directory/session/attempt, perform
Canvas read-back, finalize receipt usage when required, and write the quiz
`result.json`. After the handoff, validate that result with
`src.run_state.validate_result` before reporting success.

## 7. Write only evidence-backed results

For an ordinary successful mutation, require the read-back to contain
`workflow_state` of `submitted` or `graded` and a real `submitted_at`. Require
`src.authorization.authorization_usage_status(receipt)` to show the matching
terminal assignment action before claiming consumption. Then atomically
replace `<work_dir>/result.json` with `src.run_state.write_result`, preserving
the verified draft path and at least these fields:

```json
{
  "status": "submitted",
  "draft_path": "<existing verified draft>",
  "submitted_at": "<Canvas read-back timestamp>",
  "authorization_receipt_id": "<exact receipt id>",
  "authorization_consumed": true,
  "metadata": {
    "skill": "canvas-submit",
    "submission_type": "<selected declared type>",
    "canvas_workflow_state": "submitted",
    "readback_verified": true,
    "attempt": 1,
    "verification_log_path": "<existing PASS log>"
  },
  "notes": "Canvas submission verified by read-back."
}
```

Copy actual read-back values; the example values are not defaults. Preserve
attachment metadata when Canvas returns it. Never write `submitted` from an
HTTP success alone, a CLI exit code alone, an upload response, or an agent
claim.

If the wrapper raises `src.canvas_submit_origin.AlreadySubmitted`, call
`existing_submission_result` and atomically write canonical
`status=submitted`, `reason_code=already_submitted` using the live read-back.
This branch is read-only: omit `authorization_receipt_id`, omit
`authorization_consumed`, and never claim the newly issued receipt was used.

For an authorization, network, mutation, or read-back failure, do not retry
automatically and do not claim submission. Preserve the draft and write an
honest canonical `error` result with the concrete failure evidence. If a write
outcome is uncertain, perform a read-only Canvas check; report `submitted`
only when that read-back proves it.

## 8. Close out narrowly

Report only the selected item, Canvas workflow state, attempt, submitted time,
and whether read-back proved success. Do not expose the signed receipt,
authority record, private origin/token, course identity, or unrelated plan
items. Do not initiate another target, a retake, or a second attempt without a
new exact later-message command.
