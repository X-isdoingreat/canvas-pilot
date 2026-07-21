---
name: canvas-ics33
description: Use for an approved programming assignment routed by canvas-execute. Resolve the private overlay and real spec from course pages, PDFs, or starter code; implement test-first, audit and package a draft, and submit only through a separately authorized exact-target Canvas workflow.
---

# canvas-ics33

Produce and verify one code-assignment artifact in any language. Treat the
Canvas assignment summary as a routing hint; the real specification controls
the work.

## Runtime contract

Require an approved current plan item, its assignment snapshot, `run_dir`, and
the exact work directory returned by:

```python
from src.course_artifacts import ensure_stable_work_dir

work = ensure_stable_work_dir(run_dir, course_id, assignment_id)
```

The directory name must be
`course-<course_id>__assignment-<assignment_id>`. Never use a course or
assignment name as filesystem identity. Keep all assignment writes below it:

```text
spec.md
spec-sources/
references/
repo/
draft/
REQUIREMENTS.md
constraints.md
research_findings.md
verification.log
audit/round-<n>.json
stages/
result.json
```

This skill handles code, code-adjacent short PDFs, and required development
history. Route essays, reading annotations, zyBook problem sets, and quizzes to
their dedicated skills. Use `skipped` only for an intrinsically manual task
such as an in-person defense, identity check, or proctored environment.

## Resolve the private course design

Read `_private/canvas-ics33-app.md` before fetching or generating anything.
The file may contain several courses and assignment kinds:

1. Select the exact `## Course <course_id>` block. Never inherit a similarly
   named course or another course's defaults.
2. Within that block, accept either a `### <kind>` or `#### <kind>` heading.
   Match its `naming_regex` against the complete assignment name and retain all
   named regex groups for URL and filename templates.
3. Resolve explicit inheritance only inside the selected course block.
4. Validate all required and conditional fields before any download or command.

The course block supplies `language` and optional `language_version`. Each kind
supplies these fields as applicable:

| Concern | Overlay fields |
|---|---|
| Spec | `naming_regex`, `spec_source`, `spec_url_base`, `spec_url_template` |
| References | `reference_fetch_patterns`, `reference_resolver` |
| Starter | `scaffold_distribution`, `scaffold_url_template` |
| Verification | `test_runner`, `coverage_command`, `coverage_target` |
| Package | `submission_format`, `bundle_command`, `zip_command` |
| Process | `process_severity`, `process_humanize_config` |
| Mutation eligibility | `auto_submit_scope`, `pre_submit_reviewer_for`, `cron_env_var` |

If the overlay, course block, or kind is absent, hand off to
`canvas-bootstrap` for that exact course/kind. Resume only after the design is
materialized and revalidated. If it remains unresolved, write `error` with
`reason_code=overlay_unresolved`. Never copy private overlay values into this
tracked skill or another public artifact.

## Pipeline

Run the stages in order unless first-run stage mode is active. Preserve every
intermediate artifact so a retry can resume from verified evidence.

### 1. Discover the real specification

Use the read-only Canvas helpers needed for the selected source chain:

```python
from src import canvas_client as cv

assignment = cv.get_assignment(course_id, assignment_id)
front_page = cv.get_front_page(course_id)
modules = cv.list_modules(course_id)
syllabus = cv.get_syllabus_body(course_id)
files = cv.list_assignment_files(course_id, assignment_id)
```

Resolve `spec_source` as follows:

| Value | Required action |
|---|---|
| `external_site` | Expand the overlay URL template with matched groups and fetch the exact page. |
| `front_page_link` | Read the actual front page, follow its relevant external link, then expand the template. |
| `attached_pdf` | Download the assignment PDFs with `cv.download_file` and extract all pages with PyMuPDF. |
| `starter_readme` | Acquire the scaffold in Stage 3, then read its README and referenced local files before Stage 4. |
| `canvas_description` | Use the description only when the overlay declares it to be the complete specification. |

Follow relevant module items, syllabus links, attached files, and specification
links until the deliverable is unambiguous. Save each source verbatim under
`spec-sources/` with source URL or Canvas file ID, retrieval time, and hash.
Write `spec.md` with a verbatim section and a clearly labeled normalized
summary. Preserve the original privately even if
`src.course_artifacts.redact_behavioral_rules` is used for deliverable-shape
analysis.

For a login-only optional source, ask for a user-provided link in interactive
mode and record the outcome. Continue without it only when the specification
proves it is nonessential. A missing required source is `error`; headless mode
must not prompt or guess.

### 2. Fetch every referenced source

Apply every `reference_fetch_patterns` regex to the verbatim specification.
For each match, use `reference_resolver` to retrieve the cited lecture note,
textbook section, prior implementation, starter file, or other upstream source.
Save the original artifact in `references/` and record its origin and hash in
`references/manifest.json`.

This stage is mandatory whenever the specification refers to an upstream
source. Do not invent a signature, identifier, data shape, exception, or
example. If a pattern matches and its source cannot be recovered, write
`error` with `reason_code=required_reference_unavailable`. An empty
`references/` directory is acceptable only when the source scan records zero
required references.

### 3. Acquire the scaffold and freeze protected content

Use the declared `scaffold_distribution`:

| Mode | Action |
|---|---|
| `git_bundle` | Clone the resolved bundle or repository into `repo/`. |
| `zip_url` | Download the archive, reject path traversal, and extract into `repo/`. |
| `github_classroom` | Clone the exact student fork resolved by the private overlay. |
| `inline_in_spec` | Materialize only the explicitly identified starter code blocks. |
| `none` | Create an empty `repo/` for a from-scratch solution. |

Hash every `DO NOT MODIFY` block, fixed exception/type declaration, starter
filename, and submission helper before editing. Never modify the original
download outside `repo/`.

Write `REQUIREMENTS.md` with one item per gradable requirement: deliverable
names and types, interfaces, behavior, errors, required technique, forbidden
constructs, rubric lines, source dependencies, and package contents.

### 4. Build the constraints checklist

Write `constraints.md` as atomic yes/no propositions with a verbatim source
anchor. Include:

- every required filename, function, class, parameter, return type, and error;
- every `must`, `must not`, `do not`, allowed-import, and protected-block rule;
- every numeric phrase such as `exactly`, `at most`, `no more than`, minimum,
  maximum, page count, sentence count, function count, and coverage target;
- every specification example as an executable input/output assertion;
- every referenced identifier that must be grounded in `spec.md` or
  `references/`.

Name the measurement or parser that will verify each executable proposition.
Do not reduce a numeric requirement to a subjective review.

### 4.5. Research before improvising

Trigger this stage for a new technique or output shape, an unfamiliar numeric
constraint, a mismatch with the default pipeline, or relevant recent grader
feedback. Spawn two or three bounded native Codex subagents in parallel and
give them raw local artifacts rather than the current session's conclusions:

- **literal-spec verifier**: enumerate explicit requirements, constraints,
  forbidden items, and ambiguities from `spec.md`;
- **quality inferrer**: inspect the last five same-course results and available
  feedback, then propose mechanically checkable quality gates;
- **template-fit checker**: identify requirements not covered by Stages 5-8.

Save their separate findings and a synthesis to `research_findings.md`. Add
supported requirements and checks to the two checklists. Preserve conflicts
verbatim; never silently let inferred quality override a literal constraint.

### 5. Implement test-first

Plan small feature slices from the checklist. For each slice:

1. Add a test that fails for the missing behavior.
2. Run the overlay's `test_runner` and preserve the expected failure.
3. Implement the smallest grounded change without altering protected content.
4. Run the full test command and repair until green before the next slice.
5. If process history is enabled, commit only the green slice inside the
   assignment repository.

Add specification examples, boundary cases, error paths, and regression tests.
Run the configured coverage command after all slices; add tests for genuinely
uncovered requirements until the exact target passes. Never weaken starter
tests, alter their expected values, or proceed with a failing suite.

### 6. Build optional process history

Skip this stage when `process_severity: off` or history is not a deliverable.
Otherwise operate only on the assignment repository. Use the overlay's feature
stages, session spacing, message register, and few-shot examples to turn the
green Stage-5 checkpoints into the required development history.

When rebuilding local draft history, invoke Git with argument lists and set
`GIT_AUTHOR_DATE` and `GIT_COMMITTER_DATE` in the child process environment.
Preserve the configured author identity; never change global Git configuration
or the product repository's history. Audit commit count, chronological order,
message constraints, file diffs, and a clean final tree.

### 7. Run deterministic audits

Write one line per check to `verification.log`:

```text
PASS | requirement | measured: value
FAIL | requirement | measured: value
```

Run all of these from a clean state:

1. **Constraint measurements**: signatures, import/AST rules, counts, page and
   sentence limits, exact filenames, examples, and other numeric thresholds.
2. **Identifier grounding**: parse nontrivial identifiers with the
   language-appropriate parser and prove each required identifier appears in
   `spec.md`, `references/`, starter content, or the Canvas description.
3. **Tests and coverage**: run the complete test and coverage commands and
   record exit codes and measured percentages.
4. **Starter integrity**: compare protected-block hashes and required starter
   paths against the Stage-3 manifest.
5. **Requirement coverage**: map every `REQUIREMENTS.md` and `constraints.md`
   item to at least one measured line.

Repair and rerun the complete audit at most three times. Any remaining `FAIL`,
missing check, or ungrounded required identifier produces `error`, never
`draft_ready`.

### 7.5. Run an independent semantic audit

Spawn one fresh, read-only native Codex subagent with `spec.md`, both
checklists, optional research findings, `repo/`, and `draft/`. Require a JSON
array at `audit/round-1.json`; each gap contains:

```json
{"severity":"HIGH|MED|LOW","kind":"spec-violation|historical-risk|ambiguity-unresolved|format-mismatch","gap":"...","spec_anchor":"verbatim text","deliverable_anchor":"verbatim text or MISSING","fix_suggestion":"file and concrete change"}
```

Require verbatim anchors and `[]` exactly when no gap exists. Repair every HIGH
gap, rerun all Stage-7 checks, and repeat the semantic audit for at most three
rounds using atomic temporary-file replacement. Persistent HIGH gaps produce
`error`; retain MED/LOW items as explicit human-review metadata.

### 8. Package, reopen, and retest on Windows

Create the exact declared artifact under `draft/`:

| Format | Draft artifact |
|---|---|
| `git_bundle` | Run the configured bundle command and copy the resulting bundle. |
| `zip` | Prefer Python `zipfile`; otherwise run the configured command in an explicit working directory. |
| `single_file` | Copy the exact required source or PDF filename. |
| `online_text_entry` | Freeze the exact text as `draft/submission.txt`. |
| `gradescope` | Produce the required archive but leave delivery manual. |

Use `pathlib`, `shutil.copy2`, `zipfile`, `tempfile.TemporaryDirectory`, and
`subprocess.run([...], cwd=..., check=...)` with full paths. Do not depend on a
Unix shell or command chaining. Create the verification directory under the
assignment work tree, then clone or re-extract the packaged artifact there,
run the full tests and coverage again, and compare required file hashes. A
package that cannot be independently reopened and retested is `error`.

For configured high-stakes kinds, spawn the `pre-submit-reviewer` native Codex
subagent after packaging. Give it only the work-directory path and require a
rubric-by-rubric cold review. `BLOCK` requires repair, complete re-audit, and a
new review; unresolved `BLOCK` forbids mutation.

### 9. Finalize or submit

Default to `draft_ready`. `gradescope`, absent `auto_submit_scope`, and
`ask-each-scan` always remain local drafts. A matching `auto_submit_scope`
means only that this workflow is eligible to request a mutation; it is not
Canvas authority.

Submission additionally requires a separate, signed, unexpired
`authorization_receipt_path` supplied by `canvas-submit` or an authorized
delegation; the interactive default is
`<work>/mutation_authorization.json`. It must be bound to the exact Canvas
origin, course, assignment, current session, and required actions:

- file upload: `assignment.upload_init`, `assignment.upload_blob`, and
  `assignment.submit_files`;
- text entry: `assignment.submit_text`.

Load and validate the receipt with `src.authorization` before the first write.
Then use only `src.canvas_submit_origin`:

- Canvas file formats: call
  `upload_and_submit_files_with_view(..., authorization_receipt=receipt)` with
  the packaged draft and the three exact file actions above;
- `online_text_entry`: read the frozen `draft/submission.txt` as UTF-8 and call
  `submit_text_with_view(..., authorization_receipt=receipt)` with the exact
  `assignment.submit_text` action. Do not upload the text snapshot as a file.

Do not create or broaden a receipt in this skill, and never call a lower-level
Canvas mutation helper. The wrapper must perform the pre-read, use the same
exact receipt for every write, and prove the final state by read-back.

If `AlreadySubmitted` is raised, call `existing_submission_result` and record
canonical `submitted` with `reason_code=already_submitted`; do not create
another attempt. On success record `submitted_at`, read-back workflow state,
`metadata.readback_verified=true`, attempt, attachment metadata, the receipt
ID, and `authorization_consumed=true`. A network, authorization, or read-back
failure produces `error`.

## First-run stage mode

Run a single named stage only when both conditions hold:

- the invocation contains `STAGE-BY-STAGE MODE` and names the stage; and
- `<work>/.first_run_stage_by_stage` exists.

Accept `fetch-spec`, `fetch-references`, `download-scaffold`,
`constraints-checklist`, `research-before-improvise`,
`test-first-implement`, `process-history`, `audit`, `semantic-audit`,
`bundle-verify`, and `submit`. Verify prior artifacts, run only the named
stage, atomically write `stages/<stage>.done` with a short outcome, and stop.
If a prerequisite is missing, write the stage error marker and do not advance.
Normal `canvas-execute` dispatch runs the full pipeline.

## Canonical result contract

Write exactly one `result.json` through `src.course_artifacts.write_course_result`
or `src.run_state.write_result`:

- `draft_ready`: an existing, reopened, retested `draft_path` and no failed
  verification line;
- `submitted`: a valid `draft_path` or `submitted_at`, all-PASS verification,
  verified read-back metadata, and for a new mutation a receipt ID plus
  `authorization_consumed=true`; use `reason_code=already_submitted` for a
  pre-existing read-only attempt;
- `skipped`: only an intrinsically manual/unsupported task, with notes;
- `error`: missing required evidence, unresolved overlay/spec, failed tests or
  audit, broken package, denied mutation, or failed read-back.

Include test count, coverage, verification-log path and totals, package hash,
commit count when applicable, receipt ID when a write occurred, and human
review items in metadata. These four statuses are exhaustive.

When the selected overlay's `cron_env_var` is active, never prompt and never
degrade a failed verification or failed submission to `draft_ready`. Write
`error` honestly so the scheduler can report it.
