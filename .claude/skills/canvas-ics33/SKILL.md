---
name: canvas-ics33
description: Generic code-course handler — programming assignments where the spec lives outside Canvas (instructor's external site, attached PDF, or referenced textbook), starter code is downloaded as a scaffold, code is written with test coverage, and the bundled artifact is submitted to Canvas. Language-neutral framework — Python/Java/JS/Rust/Go all use the same pipeline; the overlay specifies which language's test runner and submission format. Invoked by canvas-execute when an assignment's routing skill is `code_py`. Before doing anything, this skill loads `_private/canvas-ics33-app.md` which encodes your school/instructor-specific behavior (spec URL pattern, scaffold distribution mechanism, test runner command, submission format, auto-submit authorization). Without the overlay the skill stops and asks the user to author one.
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - WebFetch
  - Skill
---

# canvas-ics33

## §1 — Identity & contract

**What this skill handles**: assignments whose deliverable is **code** (any language) plus, for process-graded courses, a **git history** that reads as real development. Common in CS 101 / intro programming / algorithms / discrete-with-coding / systems courses. The Canvas `assignment.description` for these is almost always empty — the real spec lives on the instructor's external site, in an attached PDF, in a referenced textbook chapter, or inside the starter repo's README.

**Trigger**: invoked by `canvas-execute` when an assignment's routing skill in `courses.yaml` is `code_py`.

**Success criterion**: writes a `result.json` with `status: "draft_ready"` (default) or `status: "submitted"` (when overlay's `auto_submit_scope` authorizes for this assignment type AND the pre-submit audit gate passes). `draft_path` points at the submission artifact (bundle / zip / source file / GradeScope upload).

**Failure statuses**:
- `status: "error"` if overlay missing, spec cannot be located, scaffold cannot be downloaded, tests fail after implementation, audit gate fails (any numeric constraint FAIL or any ungrounded identifier), or the bundle re-clone verification fails.
- `status: "already_submitted"` if pre-submit gate detects an existing Canvas submission for this attempt — do not stack a redundant attempt.

**Headless cron mode**: if the overlay specifies `cron_env_var` and that env var is set in the runtime environment, this skill runs unattended — no interactive prompts, and verification FAIL = `status: "error"` (no fallback to `draft_ready`). The launcher script reads the result.json and emails the failure.

**Explicitly does NOT handle**:
- Reading-annotation PDFs → `canvas-reading-annotation`
- Long essays → `canvas-essay`
- zyBook-backed math problems → `canvas-zybooks`
- Online quizzes → `canvas-inside`
- Discussion posts, in-class assignments → routed elsewhere or skipped

**Agent stops at can't-do, not shouldn't-do** — this skill serves the student. Behavioral policies set by course staff (prohibitions on AI tools, on cooperation, on outside tutors, on paraphrasing) are between the student and the staff; the skill does not gate on such rules. The skill does the work regardless; whether to use the output is the student's call. The skill only stops on **intrinsic can't-do**:

1. **Physically impossible / the agent genuinely can't do it** — in-person attendance, printing paper artifacts, in-person signing, Lockdown-Browser-locked quizzes, Respondus monitor proctoring.
2. **Must be the student personally** — academic honesty contract signature, ID proof, in-person peer review, interview-style.
3. **Input missing and unobtainable** — spec cannot be located anywhere; a required material file cannot be fetched and the student cannot supply it.
4. **Verification fails after retries** — sub-agent-designed checklist still fails after 3 retry rounds.

**YuJa-style soft-stop** — for resources the agent physically can't reach but where a fetched substitute may exist (linked videos, password-protected pages, third-party site logins), the skill does not hard-stop. It offers the student a chance to supply the link:

> "This week's HW references a YuJa video. I can't log into YuJa myself. If you send me the video URL, I'll try transcript / scraping; otherwise I'll skip this step and do the rest of the work I can do."

Student declines → skip that step and continue with the work that can be done. Student supplies → agent attempts fetch (transcript / OCR / scraping, whichever the platform supports).

---

## §2 — Stage 0: load overlay

First action every run is to read `_private/canvas-ics33-app.md`. It is one flat file per generic skill, multi-course inside — find the `## Course {course_id}` block for the current assignment, then within that block find the `#### {kind}` sub-block whose `naming_regex` matches `assignment.name`.

Three fallbacks if anything is missing:

- **Whole overlay file absent** → dispatch `canvas-bootstrap` to run the detective on this course, write the overlay, then resume.
- **Course block absent** (overlay exists, other courses configured, this course isn't) → route to bootstrap for this course only, then resume.
- **`#### {kind}` sub-block absent** (course is configured but this assignment's naming pattern was never seen at bootstrap time) → ask the user the minimal subset of fields needed for this single assignment (which spec URL, scaffold distribution, submission format), append a new kind block to the overlay, continue.

If the overlay exists but Stage 0 still cannot resolve a kind for this assignment, write `status: "error"` and stop.

---

## §3 — Pipeline stages

Nine stages run sequentially per assignment. Each writes its output under `runs/<today>/<assignment>/<stage>/`. Stage outputs are traceable artifacts; if a downstream stage fails, the upstream artifacts let the user (or a retry) see exactly where things broke.

### Stage 1 — `fetch-spec`

The Canvas description is a routing hint, not the spec. Locate the real spec using the overlay's `spec_source` field:

| `spec_source` value | What the skill does |
|---|---|
| `external_site` | Read overlay's `spec_url_template` (uses regex named groups from `assignment_naming_regex`, e.g. `{base}/Projects/Project{project_num}/`), substitute the assignment number, WebFetch the page, save normalized prose to `<work>/spec.md` |
| `front_page_link` | Pull `cv.get_front_page(course_id)`, extract the external link from the HTML body, then apply `spec_url_template` against that base |
| `attached_pdf` | Download every PDF in `assignment.attachments`, extract text with PyMuPDF, concat to `<work>/spec.md` |
| `canvas_description` | Use `assignment.description` directly (rare; only for courses that put the full spec in Canvas) |
| `starter_readme` | Defer until Stage 3 (scaffold-download) lands the repo, then read its README.md |

Save the spec verbatim plus a normalized summary to `<work>/spec.md`. Both forms matter — the verbatim is the ground truth for later audits, the summary is what later stages read.

### Stage 2 — `fetch-references`

Specs often reference other materials ("the binary_search from our conversation about Searching", "the helper we wrote in lecture 4", "as shown in Chapter 3.2"). Inventing those instead of fetching them is the most common audit-stage failure (real incident 2026-04-13 on Set 2 Problem 5: invented variable names `target`, `mid` when the upstream source actually uses `key`, `middle` — draft was visibly wrong).

Grep `<work>/spec.md` against the overlay's `reference_fetch_patterns` (a regex list, e.g. `from\s+our\s+(?:conversation|lecture|notes)\s+(?:about|on)\s+([A-Z][\w ]+)`). For each match, follow the overlay's `reference_resolver` rule to fetch the upstream source (typically `{spec_base}/Notes/<Topic>/` for instructor-site courses; overlay can specify other resolvers like "grep the starter repo for the function name").

Save fetched sources verbatim to `<work>/references/<topic-or-name>.{md,py,java,...}`. Subsequent stages (especially Stage 7 audit identifier grounding) read this directory; an empty `references/` when the spec triggered a `reference_fetch_pattern` match is itself a fail signal.

The PostToolUse hook `check-spec-grounding.py` enforces this — if `spec.md` matches a reference pattern but `references/` is empty, the hook exits 2 and blocks `draft_ready`.

### Stage 3 — `download-scaffold`

By overlay's `scaffold_distribution`:

| Value | Action |
|---|---|
| `git_bundle` | Read `scaffold_url_template` (substitute assignment vars), `git clone <url> <work>/repo` |
| `zip_url` | WebFetch the zip, unzip into `<work>/repo` |
| `github_classroom` | Overlay specifies `classroom_org` + `assignment_prefix` — clone the student's fork URL |
| `inline_in_spec` | Skill creates `<work>/repo`, parses `<work>/spec.md` for code blocks (overlay can give a hint regex for "where in the spec the starter lives"), writes them as files |
| `none` | Just `mkdir <work>/repo` — student writes from scratch |

After scaffold, write `<work>/REQUIREMENTS.md` enumerating every gradable item the spec mentions: function names, file names, deliverable format, forbidden imports, rubric line items. This is what Stage 4 walks against the draft.

### Stage 4 — `constraints-checklist`

Parse `<work>/spec.md` + `<work>/REQUIREMENTS.md` and write `<work>/constraints.md` containing one bullet per yes/no testable proposition:

- **Hard rubric items**: function name X, file name Y, returns type Z
- **Numeric / quantitative limits**: grep spec for `(no more than|at most|exactly|only|fewer than|maximum|minimum|≤|≥)`; each match becomes a bullet with the verbatim spec language
- **Forbidden things**: grep for `(must not|forbidden|do not|cannot use|prohibited|no.*imports)`
- **Required identifiers**: function/class/exception names mentioned in spec — these become the input to Stage 7's identifier grounding check
- **Spec-provided examples**: every `f(x) → y` example becomes a "run f(x), assert == y" bullet

Numeric constraints are the easiest to miss — real incident 2026-04-09: a PDF deliverable had 4 sentences when spec said "no more than two or three sentences"; the audit caught it after submission. From that incident onwards, every numeric constraint in the spec becomes a `constraints.md` bullet whose Stage 7 verification runs an actual measurement (count sentences with `re.split(r'(?<=[.!?])\s+', text)`), not a vibe check.

### Stage 4.5 — `research-before-improvise` (run when spec doesn't fit the template)

Trigger (any of these in `<work>/spec.md` or `<work>/constraints.md`):
- Hard numeric constraint not seen in prior Project/Set kinds (e.g. unusual sentence count, page limit, exact module count)
- HW page references concepts not in the kind table (a new library, a new submission format, a new "must use technique X")
- Past 3 same-course assignments had grader comments flagging issues this spec also mentions
- Spec asks for sections / artifacts not produced by the default Stage-5-through-Stage-8 flow

When triggered, do NOT improvise. Spawn 2-3 agents IN PARALLEL — single message with multiple `Agent` tool calls (same idiom as `canvas-inside` §7c 4-agent arbitration):

- **Agent A — spec-verifier** (`subagent_type=general-purpose`):
  > Re-read `<work>/spec.md` from scratch. List literal requirements: input source, deliverable shape, hard numeric constraints (grep for "no more than" / "at most" / "exactly" / "one ... per" / "must" / "do not"), required sections, forbidden items, 1-3 ambiguities. Output under 400 words, plain markdown bullets.

- **Agent B — quality-inferrer** (`subagent_type=general-purpose`):
  > Read `<work>/spec.md` AND prior result.jsons under `runs/*/` for this same course (filter to last 5 by date). For each prior, pull grader feedback if available. Infer what "doing this well" requires beyond literal asks: quality criteria, common failure modes with verbatim grader quotes, recommended mechanically-checkable gates. Output under 400 words.

- (Optional) **Agent C — template-fit checker** (`subagent_type=general-purpose`):
  > Given canvas-ics33's default Stage 5→Stage 8 flow vs `<work>/spec.md`, list places where the template doesn't cover this assignment's specific requirements (e.g. missing rubric items, unusual submission format, extra deliverables). Output under 300 words.

Save the 3 reports to `<work>/research_findings.md`. Use the findings to:
- Add new bullets to `<work>/REQUIREMENTS.md` and `<work>/constraints.md`
- Augment the Stage 7 audit checklist with content-quality gates from Agent B's grader-history analysis
- Customize Stage 5's feature-stage plan for THIS HW's specific constraints

Then continue to Stage 5 with the refined plan. **If Agent A's hard constraints conflict with Agent B's inferred quality criteria, surface both in `<work>/research_findings.md` and let the implementer pick — do NOT silently merge.**

### Stage 5 — `test-first implement`

Plan a sequence of feature stages — for an 8-queens-style project, ~10 stages (skeleton+storage → read-only methods → add op → add-op-error → remove op → remove-op-error → row check → col check → diag check → edge cases). For a single-function Set Problem, 2-3 stages (happy path → edge/error → cleanup).

For each stage:

1. Edit the implementation file
2. Edit the test file to add tests for the new feature
3. Run overlay's `test_runner` command (e.g. `python -m unittest discover tests` / `./gradlew test` / `npm test` / `cargo test`). STOP if anything fails — fix before continuing.
4. If overlay's `process_severity` is not `off`, stage and commit (the commit itself is data for Stage 6 process_humanize — for now just commit with a placeholder message; Stage 6 will rewrite history with proper register and timestamps).

After all feature stages: if overlay specifies `coverage_target`, run `coverage_command` and check the target is met. Add tests for missed branches until target is hit. Don't proceed to Stage 6 / 7 if coverage is below target.

### Stage 6 — `process_humanize` (process-graded courses only)

**Skip this stage entirely** if overlay's `process_severity` is `off` (final code-only grading). Otherwise this stage rewrites the git history produced in Stage 5 to look like real undergraduate development — multiple commits spread over days, register-matched commit messages, occasional `wip` / `fix` / typo'd messages. This is the code-course equivalent of canvas-reading-annotation's text-humanize stage: same goal (output survives an authorship audit), different surface (commit log vs. PDF content).

Knobs (all from overlay's `process_humanize_config`):

| Knob | Example |
|---|---|
| `spread_days` | 3 — distribute commits across N days before due |
| `last_commit_lead_hours` | 2 — last commit is N hours before due_at, evening hours |
| `commits_per_session` | 2-4 randomized — cluster commits, then multi-hour gap |
| `inter_commit_gap_minutes` | 30-180 randomized |
| `commit_message_register` | free-form prose describing the voice — e.g. "undergrad lazy: 2-6 word fragments, lowercase OK, occasional typo, low-content commits `wip` / `fix` / `ok done` ~10% of total" |
| `few_shot_examples` | 2-3 example commit logs from the overlay author — used as register anchors |

Rewrite git history using backdated commits (preserve author identity from `.env`'s `GIT_AUTHOR_NAME` / `GIT_AUTHOR_EMAIL`):

```python
import subprocess, os
env = os.environ.copy()
env["GIT_AUTHOR_DATE"] = iso_timestamp
env["GIT_COMMITTER_DATE"] = iso_timestamp
subprocess.run(["git", "commit", "-m", msg], cwd=repo_path, env=env, check=True)
```

**Register anti-patterns** (avoid in generated messages regardless of overlay):
- Multi-clause "with X and Y" structure
- "in order to" / "so that" connector words
- Parentheticals "(basic / both directions)"
- Full professional imperatives ("Implement X to handle Y")

These read as LLM-polished, not how an actual undergrad writes commits in this class. The voice register's job is to match the student's identity (typically undergraduate-lazy in this course type). Overlay's `commit_message_register` and `few_shot_examples` are the authoritative voice — this list is the safety floor.

### Stage 7 — `audit`

Three audits, all writing to `<work>/verification.log` with one PASS/FAIL line + measured value per check. The `check-presubmit-audit.py` PreToolUse hook blocks Canvas submission if `verification.log` is missing or contains any FAIL.

**A. Numeric-constraint audit** (Ratchet 1+2+3): for every `constraints.md` bullet with a numeric limit or input/output example, run an actual measurement. Function name matches? `inspect.signature`. No imports? Parse with overlay's language AST/parser and check `Import` nodes. Sentence count ≤3? Extract text with PyMuPDF + regex split. Each check is a number, not a feeling.

**B. Identifier grounding audit** (Ratchet 5): parse the draft with the language-appropriate parser (overlay's `language` field selects the parser — Python via `ast.parse`, Java/JS/Rust/Go via regex parsers; see `.claude/hooks/check-identifier-grounding.py`), collect every non-trivial identifier (function names, parameter names, class names, attribute accesses; skip 1-letter loop vars and builtins). For each, confirm it appears in `<work>/spec.md` OR `<work>/references/*` OR `assignment.description`. Any ungrounded identifier = FAIL. Fix: either rename to match upstream, or fetch the missing upstream source.

**C. Test/coverage check**: run overlay's `test_runner` once more (clean state); record exit code. Run `coverage_command` if overlay specified one; parse output for the `coverage_target` percentage. Both FAIL the audit if either misses.

For high-stakes submissions (Projects, midterms), optionally invoke the `pre-submit-reviewer` agent — it sees spec + draft cold (no inherited session context) and returns rubric-by-rubric PASS/FAIL. Its verdict counts as authoritative for the gate.

### Stage 7.5 — `post-delivery self-audit` (MANDATORY, never skip)

Runs AFTER Stage 7's existing 3-layer audit (numeric / identifier-grounding / test-coverage) and BEFORE Stage 8's bundle step. It is a 4th audit layer that catches what the first 3 don't: **spec-vs-deliverable gap diff with verbatim anchors**. The first 3 layers measure FORMAT/STRUCTURE; this one measures SEMANTIC COVERAGE.

Spawn 1 audit agent (`subagent_type=general-purpose`), inputs:
- `<work>/spec.md` (verbatim spec)
- `<work>/REQUIREMENTS.md` (Stage 4 derived requirements)
- `<work>/constraints.md` (Stage 4 derived constraints)
- `<work>/research_findings.md` if Stage 4.5 ran
- Every file in `<work>/repo/` (the implementation)
- Every file in `<work>/draft/` (the produced submission artifact)

Agent prompt:
> Compare the spec + requirements + constraints + research findings against the implementation and the draft artifact. Return a JSON array of gaps. For each gap, use this schema:
>
> ```json
> {
>   "severity": "HIGH" | "MED" | "LOW",
>   "kind": "spec-violation" | "historical-risk" | "ambiguity-unresolved" | "format-mismatch",
>   "gap": "<one-line description>",
>   "spec_anchor": "<verbatim quote from spec/requirements/constraints showing the requirement>",
>   "deliverable_anchor": "<verbatim quote from code/draft file showing the violation, or 'MISSING' if requirement is unaddressed>",
>   "fix_suggestion": "<one-line concrete fix referencing the file + change>"
> }
> ```
>
> Honesty rules: (a) quote VERBATIM from both spec and deliverable — do not paraphrase; (b) if no gaps, return `[]` exactly; (c) if a requirement is genuinely ambiguous, prefer `ambiguity-unresolved` over guessing a violation; (d) cross-check function signatures against spec using your knowledge of `inspect.signature`-style analysis.

Save response to `<work>/audit/round_1.json` (atomic write: `.json.tmp` then `os.replace`).

Read the JSON. If ANY `severity == "HIGH"` gap:
1. For each HIGH gap, apply the `fix_suggestion` to the corresponding file under `<work>/repo/` or `<work>/draft/`.
2. Re-run Stage 7's 3-layer audit (in case fixes broke a numeric or grounding check).
3. Re-run Stage 7.5 (round_2.json), then round_3.json if needed.
4. After 3 rounds with HIGH gaps still present → write result.json `status: error`, `notes: "Stage 7.5 self-audit failed after 3 revision rounds; see <work>/audit/round_*.json"`. Stop.

If round_1 (or any subsequent round) returns `[]` or only LOW/MED gaps → proceed to Stage 8.

**Token budget note**: 1 agent × up to 3 rounds × ~5k tokens each = ~15k tokens worst case per assignment. Acceptable for Projects (graded out of 30, ~1 per 2 weeks); for high-frequency Sets, consider tightening §X triggers so §X→§Y only fires when truly warranted.

### Stage 8 — `bundle` + `re-clone verify`

By overlay's `submission_format`:

| Value | Bundling action | Verify action |
|---|---|---|
| `git_bundle` | Run overlay's `bundle_command` (e.g. `python prepare_submission.py`); cp the produced `.bundle` to `<work>/draft/` | `git clone <bundle> /tmp/verify && cd /tmp/verify && <test_runner>` — all tests must pass |
| `zip` | Run overlay's `zip_command` (e.g. `zip -r project.zip src tests`); cp to `<work>/draft/` | `unzip` to `/tmp/verify`, run `<test_runner>` |
| `single_file` | cp the source file (`problem1.py`, `Solution.java`, etc.) to `<work>/draft/` | run `<test_runner>` against the file from outside the work tree |
| `online_text_entry` | Read the source file contents to memory for the submit step | (verify already done in Stage 7-C) |
| `gradescope` | Run overlay's `zip_command`; cp the produced zip to `<work>/draft/` — submission step (Stage 9) is manual (link to GradeScope, not auto-upload) | Same as `zip` |

If re-clone verify fails: do NOT mark `draft_ready`. Status: `error`. The bundle is broken in some way the local tests didn't catch (gitignored test files, missing imports in the bundle, etc.).

### Stage 9 — `submit`

For `gradescope` submission_format: skill always writes `status: "draft_ready"`. GradeScope upload is manual — the user clicks the link in `REPORT.md`. Stop here.

For `canvas` submission paths (everything else): check overlay's `auto_submit_scope`:

- If unset or `ask-each-scan`: write `status: "draft_ready"`, do not call Canvas submit API. The user uploads manually after reviewing.
- If matches this assignment (e.g. `auto_submit_scope: "Set N Problem M: confirmed"` and assignment is named "Set 3 Problem 2"): call the canvas_submit_origin wrapper.

```python
from src import canvas_submit_origin as cso
try:
    verify = cso.upload_and_submit_files_with_view(
        course_id, assignment_id, [draft_path]
    )
except cso.AlreadySubmitted:
    # Pre-gate detected an existing submission — don't stack another
    write_result_json(status="already_submitted")
    return
assert verify["workflow_state"] == "submitted"
write_result_json(status="submitted", submitted_at=verify["submitted_at"])
```

Three reasons to always use `upload_and_submit_files_with_view` over a bare `cv.submit_files` call (see `src/canvas_submit_origin.py` module docstring):

1. **Pre-gate**: re-fetches `get_submission` and raises `AlreadySubmitted` if already submitted — avoids stacking a redundant attempt over an instructor's existing grade notes.
2. **Post-verify**: re-fetches submission after upload and returns canonical state (`attachments`, `submitted_at`, final `attempt`).
3. **Traffic shape** matches SpeedGrader's natural navigation pattern (deliberate, separate from production-mode logging concerns).

The PreToolUse hook `check-presubmit-audit.py` recognizes both `cv.submit_files` and `_with_view` wrappers — the verification.log gate applies to both paths.

**Headless cron invariant**: if overlay's `cron_env_var` is set in the runtime env:
- Verification PASS → submit → `status: "submitted"` (normal path).
- Verification FAIL → `status: "error"`, NO fallback to `draft_ready`. The launcher's post-CC verifier emails the failure with the CC log path.
- Submit step itself fails after verification PASS (network, 401, Canvas 5xx) → `status: "error"`.

The launcher does its own post-CC `cv.get_submission` check + escalating-subject email; this skill just has to be honest about what state it ended in.

---

## §3.5 — Stage-by-stage mode (first-run calibration only)

When invoked with a context line containing **STAGE-BY-STAGE MODE** AND the control file `<work>/.first_run_stage_by_stage` exists, run **only the single stage named in the directive** instead of the full pipeline. This mode is set by `canvas-bootstrap` §8 during first-run calibration so the student can review each stage's output before the next stage runs.

Behavior:

1. Read `<work>/.first_run_stage_by_stage` to confirm. If absent (or if no stage-by-stage directive is present in context), run the full pipeline as usual.
2. Parse the directive for the stage name (`fetch-spec`, `fetch-references`, `download-scaffold`, `constraints-checklist`, `test-first-implement`, `process_humanize`, `audit`, `bundle-verify`, `submit`).
3. Run **only** that stage's substeps from §3 above. Earlier stages must already have produced their artifacts in `<work>/` — bootstrap §8 dispatches in order, so this is normally the case; if an artifact is missing, write `<work>/stages/{stage_name}.done` with `ERROR: prior artifact {path} missing` and stop.
4. After substeps complete, write a 1-3 sentence English summary to `<work>/stages/{stage_name}.done` describing what was done and where the artifacts are. Then STOP — do not advance.

Daily dispatch (canvas-execute) does not set the marker; this skill runs full-pipeline as usual outside of bootstrap §8.

## §3.6 — Stage-by-stage time bands

Used by canvas-bootstrap §8 to announce expected duration before invoking each stage:

| Stage | Band | One-line description |
|---|---|---|
| 1 fetch-spec | short | Fetch the assignment's real spec from instructor's external site / PDF / front-page link |
| 2 fetch-references | short | Pull upstream materials the spec mentions (lecture notes, prior code) |
| 3 download-scaffold | short | Download and unpack the starter scaffold |
| 4 constraints-checklist | short | Extract yes/no testable propositions from spec (hard limits, forbidden things) |
| 4.5 research-before-improvise | medium | (Conditional) deeper investigation when spec doesn't fit prior shapes |
| 5 test-first-implement | long | Write tests + code with iterative coverage gates |
| 6 process_humanize | medium | (Conditional) rewrite git history into backdated multi-commit register |
| 7 audit | medium | Identifier-grounding + numeric-constraint + coverage check |
| 7.5 post-delivery-self-audit | medium | Mandatory final pass; catches what the formal checks missed |
| 8 bundle-verify | medium | Package per submission_format, re-clone into temp, re-run tests |
| 9 submit | short | (Conditional) upload to Canvas via `_with_view` wrapper |

Band meaning: `short` ~1 min, `medium` ~3-5 min, `long` ~10+ min.

---

## §4 — Personal course design schema

The overlay (`_private/canvas-ics33-app.md`) is one flat markdown file containing one `## Course {id}` block per course routing to this skill. Each course block holds one or more `#### {kind}` sub-blocks per recurring assignment kind. Recognized fields:

**Course-level** (one set per `## Course` block):

| Field | Required | Example |
|---|---|---|
| `course_id` | yes | `12345` |
| `course_name` | yes | `"Code Course A — Spring 2026"` |
| `instructor` | optional | `"Dr. Example"` |
| `language` | yes | `python` (also: `java`, `js`, `ts`, `rust`, `go`, `c`, `cpp`) |
| `language_version` | optional | `3.11` |

**Sub-block fields** (per `#### {kind}`):

| Field | Required | Example |
|---|---|---|
| `naming_regex` | yes | `^Project (?P<project_num>\d+)$` |
| `spec_source` | yes | `external_site` / `front_page_link` / `attached_pdf` / `canvas_description` / `starter_readme` |
| `spec_url_template` | conditional | `{base}/Projects/Project{project_num}/` (required when `spec_source` is `external_site` / `front_page_link`) |
| `spec_url_base` | conditional | `https://www.example.edu/~prof/cs101/` (sets `{base}` for the template) |
| `reference_fetch_patterns` | optional | regex list — e.g. `["from\\s+our\\s+(?:conversation\|lecture)\\s+about\\s+([A-Z]\\w+)"]` |
| `reference_resolver` | conditional | `{spec_base}/Notes/<match>/` |
| `scaffold_distribution` | yes | `git_bundle` / `zip_url` / `github_classroom` / `inline_in_spec` / `none` |
| `scaffold_url_template` | conditional | `{base}/Projects/Project{project_num}/Project{project_num}.git` |
| `test_runner` | yes | `python -m unittest discover tests -v` |
| `coverage_command` | optional | `python -m coverage run --branch --source=<module> -m unittest discover tests && python -m coverage report` |
| `coverage_target` | optional, default `none` | `100%` / `90%` / `none` |
| `submission_format` | yes | `git_bundle` / `zip` / `single_file` / `online_text_entry` / `gradescope` |
| `bundle_command` | conditional | `echo Y \| python prepare_submission.py` |
| `zip_command` | conditional | `cd repo && zip -r ../draft/solution.zip src tests` |
| `process_severity` | yes | `off` / `low` / `medium` / `high` |
| `process_humanize_config` | conditional | dict — required when `process_severity != off` (see Stage 6 knobs table) |
| `auto_submit_scope` | optional, default `ask-each-scan` | `"Set N Problem M: confirmed"` |
| `pre_submit_reviewer_for` | optional, default `(none)` | `"Projects, midterms, finals"` — list of assignment shapes where the `pre-submit-reviewer` agent should be invoked before submit |
| `cron_env_var` | optional | `ICS33_CRON_RUN` (skill enters headless cron mode when this env var is set) |

---

## §5 — Worked demo overlay

A complete overlay for a fictional Python course. Fork users copy-paste-modify this rather than writing from scratch.

````markdown
# canvas-ics33 — Personal Course Design

This file holds per-course overlays for the canvas-ics33 skill.

## Course 99999 — Code Course A (Spring 2026)

- course_name: Code Course A — Intro Programming
- instructor: Dr. Example
- language: python
- language_version: 3.11

### Project N

- naming_regex: `^Project (?P<project_num>\d+)$`
- spec_source: front_page_link
- spec_url_base: (extracted from `cv.get_front_page(course_id).body` HTML link)
- spec_url_template: `{base}/Projects/Project{project_num}/`
- reference_fetch_patterns:
    - `from\s+our\s+(?:conversation|lecture|notes)\s+(?:about|on)\s+([A-Z][\w ]+)`
    - `the\s+provided\s+(?:implementation|code)\s+of\s+(\w+)`
- reference_resolver: `{spec_base}/Notes/<match>/`
- scaffold_distribution: git_bundle
- scaffold_url_template: `{base}/Projects/Project{project_num}/Project{project_num}.git`
- test_runner: `python -m unittest discover tests -v`
- coverage_command: `python -m coverage run --branch --source=<module> -m unittest discover tests && python -m coverage report`
- coverage_target: 100%
- submission_format: git_bundle
- bundle_command: `echo Y | python prepare_submission.py`
- process_severity: high
- process_humanize_config:
    spread_days: 3
    last_commit_lead_hours: 2
    commits_per_session: 2-4
    inter_commit_gap_minutes: 30-180
    commit_message_register: |
        Undergrad lazy. 2-6 word fragments. Lowercase OK and preferred.
        Abbreviations: "w" not "with", "+" not "and". Occasional typo
        (1 in 5-8). Low-content commits sprinkled in: "wip" / "fix" /
        "ok done" ~10% of total. Avoid multi-clause "with X and Y"
        structure, "in order to" connectors, parentheticals.
    few_shot_examples:
        - skeleton + storage
        - queens() has_queen()
        - with_added basic
        - dup error
        - remove + missing err
        - row check
        - wip
        - col + diag attacks
        - edge cases + 8q test
- auto_submit_scope: "Project N: ask-each-scan"
- pre_submit_reviewer_for: "Projects, midterms, finals"
- cron_env_var: ICS33_CRON_RUN

### Set N Problem M

- naming_regex: `^Set (?P<set_num>\d+) Problem (?P<problem_num>\d+)$`
- spec_source: front_page_link
- spec_url_base: (same as Project N)
- spec_url_template: `{base}/Exercises/Set{set_num}/`
- reference_fetch_patterns: (inherits)
- reference_resolver: (inherits)
- scaffold_distribution: none
- test_runner: `python -m unittest tests/test_problem{problem_num}.py`
- coverage_command: (none)
- coverage_target: none
- submission_format: single_file
- process_severity: medium
- process_humanize_config:
    spread_days: 1
    commits_per_session: 1-2
    commit_message_register: (inherits from Project N)
    few_shot_examples:
        - first pass
        - tests
        - fix edge
- auto_submit_scope: "Set N Problem M: confirmed"
- cron_env_var: ICS33_CRON_RUN
````

For a Java course, the same shape applies with different command values:

```markdown
- language: java
- test_runner: `./gradlew test`
- coverage_command: `./gradlew jacocoTestReport`
- coverage_target: 90%
- submission_format: zip
- zip_command: `cd repo && zip -r ../draft/project.zip src/ build.gradle`
```

Framework prose stays unchanged — only overlay command strings differ.

Multiple courses routing to this skill all live in the same `_private/canvas-ics33-app.md` file, each as its own `## Course` block. Bootstrap appends new course blocks rather than rewriting the whole file.

---

## What you MUST NOT do

- Do NOT trust `assignment.description` as the spec — for code courses it is almost always empty or just a routing hint. Use `spec_source` to locate the real spec.
- Do NOT skip Stage 2 (`fetch-references`) when the spec mentions external materials. Inventing identifiers / signatures that don't match the upstream source fails the Stage 7 identifier-grounding audit (and would have been visibly wrong to the grader regardless of the audit).
- Do NOT write the whole solution in one commit when `process_severity` is high. The grader penalizes single-commit dumps. Stage 5 produces placeholder commits; Stage 6 spreads them realistically.
- Do NOT match the LLM-professional commit message register (multi-clause, "in order to", parentheticals). Match overlay's `commit_message_register` voice exactly.
- Do NOT mark `draft_ready` with any `FAIL` line in `<work>/verification.log`. Fix the draft and re-verify; if still failing after 3 retry rounds, write `status: "error"` with the failure list.
- Do NOT call `cv.submit_files` directly. Always go through `canvas_submit_origin.upload_and_submit_files_with_view` so the pre-gate / post-verify wrapper applies.
- Do NOT submit when `auto_submit_scope` is `ask-each-scan` or unset — write `status: "draft_ready"` and let the user upload after reviewing.
- Do NOT submit even with valid `auto_submit_scope` if any audit step failed. The PreToolUse hook will block the submit call regardless, but the skill should not attempt it.
- Do NOT fall back to `draft_ready` in headless cron mode (overlay's `cron_env_var` set). Verification FAIL = `status: "error"`. Nobody is going to see the draft until the next scheduled run.
- Do NOT modify the namedtuple / exception / "DO NOT MODIFY" blocks in scaffold code. Graders fingerprint these.
- Do NOT rename deliverable files (`queens.py` not `Queens.py`; `problem1.py` not `set1_problem1.py`). Auto-graders match exactly.
