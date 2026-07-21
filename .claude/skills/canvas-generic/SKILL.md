---
name: canvas-generic
description: Fallback runtime-designed handler for Canvas assignments that don't fit any of the 5 specific skills (canvas-ics33 / canvas-reading-annotation / canvas-essay / canvas-zybooks / canvas-inside). Invoked by canvas-execute when an assignment's routing skill is `canvas-generic` — typically a cluster that canvas-bootstrap §3 marked "⚠ unclear" / "⚠ inline-only-or-unknown" / "⚠ quiz-id-missing". No overlay required; the skill performs full runtime investigation (description + front_page + modules + syllabus + attachments + external URLs), locates the grading rubric, downloads referenced inputs, then designs a per-assignment pipeline at runtime. Runs three sub-agent reviews (A — investigation completeness; B — verification checklist design; C — verification coverage review) and produces a draft with verification log. Auto-submit is never the default; output is always draft_ready for student review.
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - WebFetch
  - Skill
  - Agent
---

# canvas-generic — runtime-designed pipeline for novel assignments

## §1 — Identity & contract

**What this skill handles**: any pending Canvas assignment that does not fit the existing 5 specific skills (`canvas-ics33`, `canvas-reading-annotation`, `canvas-essay`, `canvas-zybooks`, `canvas-inside`). Trigger is **shape mismatch** — the cluster's submission types, naming pattern, and reference materials don't form a clean match for any specific skill. canvas-bootstrap routes these clusters here instead of forcing a wrong-shape specific skill or punting to canvas-skip.

**Invocation**: `canvas-execute` calls this skill when an assignment's `proposed_skill == "canvas-generic"`. canvas-bootstrap §7 writes the courses.yaml route entry for category-4 (unclear) clusters.

**Success criterion**: writes `result.json` with `status: "draft_ready"` and `draft_path` pointing at the produced artifact (.docx / .pdf / .py / .ipynb / a folder). canvas-generic **never auto-submits** — there is no overlay-level authorization mechanism by design. Student reviews → student uploads.

**Failure status**: `status: "error"` with explanatory `notes` if (a) Sub-agent A in Stage 4 flags missing critical sources the student cannot supply, (b) the grading rubric cannot be located anywhere, (c) Stage 5 cannot classify the output mode with confidence, (d) verification fails after 3 retry rounds, (e) Sub-agent C in Stage 10 flags an unresolvable coverage gap.

**Explicitly does NOT handle**:
- Anything one of the 5 specific skills handles correctly — those exist for a reason and carry domain-specific guards (e.g. canvas-inside's 3-layer arbitration enforcement, canvas-ics33's bundle re-clone verify, canvas-zybooks' API integration). If canvas-bootstrap can route to a specific skill, it must do so first.
- Lockdown-Browser quizzes / Respondus proctoring → `canvas-skip` (intrinsic can't-do #1).

**Agent stops at can't-do, not shouldn't-do** — this skill serves the student. Behavioral policies set by course staff (don't use AI / no collaboration / no paraphrasing) are between the student and the staff; this skill does not gate on such rules. The skill does the work regardless; whether to use the output is the student's call. The skill stops only on intrinsic can't-do:

1. **Physically impossible** — in-person attendance, paper submission, live signature, LDB-locked quiz, Respondus monitor.
2. **Identity-bound** — honesty contract signature, ID verification, in-person peer review, oral defense.
3. **Input missing and unobtainable** — spec/rubric/inputs cannot be located, AND Sub-agent A's recovery attempts fail, AND the student cannot supply the missing material.
4. **Verification fails after retries** — 3 rounds at Stage 9 / 2 rounds of B↔C iteration at Stage 10.

**YuJa-style soft-stop** — for resources physically out of reach but possibly obtainable with student help (linked videos, password-protected pages, third-party logins), Sub-agent A surfaces them as `blocking_unreachables` and the skill offers to take a URL / transcript / credential from the student. Student declines → skip that input and continue with what is reachable; note in `result.json.notes`.

---

## §2 — Stage 0: load per-cluster learnings overlay

Unlike the 5 specific skills which have one framework-wide overlay (`_private/canvas-ics33-app.md`, etc.), canvas-generic has a **per-cluster learnings overlay** at `_private/canvas-generic-<course_id>-<cluster_slug>.md`. The slug is computed deterministically via `src.overlay_utils.cluster_filename_slug(cluster_norm)` — bootstrap §7.1 creates the file empty when it routes a ⚠ category-4 cluster here.

**Compute the path**:

```python
from src.overlay_utils import canvas_generic_overlay_path

path = canvas_generic_overlay_path(course_id, cluster_norm)
# e.g. "_private/canvas-generic-12345-reading-annotation-week.md"
```

`cluster_norm` comes from the invocation context (canvas-execute passes `course_id` + `assignment_id`; this skill computes `cluster_norm` from the assignment's name via `src.recurring_patterns.normalize()`).

**Read the file**:

- If file present and has a `## User preferences (recurring)` section with content: parse the bullet list. Pass the resulting `user_preferences` dict into Stage 5 (classify-output), Stage 6 (design-pipeline), and Stage 7 (generate) as priming. Pass `workflow_notes` (from the `## Workflow notes` section) into Stage 6.
- If file is missing: this cluster wasn't bootstrapped properly. Tell the user "canvas-generic learnings file not found at {path}. I'll proceed with a clean runtime investigation, but I won't be able to honor prior preferences. To fix, re-run canvas-bootstrap on this cluster." Then continue to Stage 1.
- If file present but empty (only frontmatter + empty sections): normal — first dispatch on this cluster. Continue to Stage 1 with no priming.

**What's in learnings (NOT in scope)**:

- **Pipeline design** is NEVER cached in learnings. canvas-generic re-discovers output mode + pipeline stages every dispatch (Stages 5-6). The justification is that input materials may change week to week (one week reading-heavy, next week math-heavy); pipeline shape should reflect this assignment's specific shape.
- **Investigation results** (current spec, current rubric) are NEVER cached. Stages 1-4 always run fresh; the spec might have changed.

**What learnings DOES cache** (user preferences only, accumulated via Layer 2 permanent rule across past dispatches):

- voice register / persona preference
- color rubric (for pdf_annotated mode)
- citation style preference
- format preferences (font, paragraph indentation, etc.)
- forbidden phrases the user has objected to in past drafts
- workflow tweaks ("skip the figure-caption substage — this cluster never has figures")

**Why not just an overlay like the specific skills**: a learnings file is per-cluster (multiple cluster files for the same course are normal), and starts empty (no manual authoring). Specific-skill overlays are per-framework (one file aggregating multiple courses) and are authored by bootstrap §6 batched ask + §8 calibration. The learnings model fits canvas-generic's "stateless runtime design + accumulated user preferences" hybrid.

If you find yourself wishing canvas-generic had richer per-cluster pipeline design baked into the overlay, that's the signal the cluster should graduate to a specific skill — see §11 below.

---

## §3 — Working directory

```
runs/<today>/<work>/
├── spec.md                    # Stage 1 — consolidated assignment shape + description + linked sources summary
├── references/                # Stage 3 — downloaded files (name matches check-spec-grounding hook)
├── investigation/
│   ├── rubric.md              # Stage 2 — extracted grading criteria
│   ├── unreachable.txt        # Stage 3 — resources we could not fetch
│   └── review_a.json          # Stage 4 — Sub-agent A verdict
├── pipeline_design.md         # Stage 5-6 — chosen output mode + pipeline stages
├── draft/                     # Stage 7 output
│   └── <produced_artifact>
├── verification_checklist.md  # Stage 8 — Sub-agent B output
├── verification.log           # Stage 9 — measured results
├── review_c.json              # Stage 10 — Sub-agent C verdict
├── humanizer_log.json         # if Stage 7's humanize sub-step ran
└── result.json
```

---

## Stage 1 — fetch-context

Pull every read source for this assignment:

```python
from src import canvas_client as cv

a = cv.get_assignment(course_id, assignment_id)
description = (a.get("description") or "")
front_page = cv.get_front_page(course_id)
modules = cv.list_modules(course_id)
syllabus = cv.get_syllabus_body(course_id)
attached_files = cv.list_assignment_files(course_id, assignment_id)
```

Apply the `redact_behavioral_rules` filter from canvas-bootstrap §5a to every external text body (description, front_page, syllabus, module wiki pages) — instructor conduct rules must never enter this skill's working set.

Write `spec.md` with:
- `assignment.name`, `points_possible`, `due_at`, `submission_types`, `allowed_extensions`.
- Redacted description.
- Front page excerpt where it mentions this assignment kind (search front_page body for assignment name fragments).
- Module hits — `list_modules` items whose name fragment-matches the assignment.
- Syllabus excerpt where it mentions this assignment kind.
- Every external URL found in the above, deduped. Mark each as `INSTRUCTOR_SITE` / `READING` / `THIRD_PARTY` based on host.

## Stage 2 — find-rubric

Locate the grading rubric in this order:

1. **Canvas-attached rubric** — `cv.get_rubric(course_id, assignment_id)`. If present, render to `investigation/rubric.md` as a bulleted list of criteria + point breakdown.
2. **Spec body grep** — search `spec.md` + downloaded attached PDFs for `rubric` / `criteria` / `graded on` / `points breakdown` / `you will be evaluated on` / `assessment criteria`. Capture the surrounding paragraph.
3. **Module / syllabus grep** — same patterns across module wiki page bodies and `syllabus`.
4. **Instructor-external URL fetch** — if Stage 1 found INSTRUCTOR_SITE URLs, fetch and grep them.

If nothing found after all 4 layers: write `rubric.md` with the literal first line `RUBRIC NOT FOUND - student must supply`. Sub-agent A will flag this in Stage 4 and the skill will ask the student for the rubric URL or paste before proceeding.

## Stage 3 — locate-inputs

Download every file referenced by the assignment to `references/`:

- All `attached_files` from `cv.list_assignment_files`.
- All PDFs / readings linked from `spec.md` or module wiki pages.
- Starter code / scaffold archives if any (zip / git-bundle / GitHub Classroom).
- INSTRUCTOR_SITE URLs from Stage 1 — fetch the HTML body.

For URLs that are fetchable but content-unclear (Google Doc share links, third-party platforms), attempt anonymous fetch first; if redirected to a login wall, log to `investigation/unreachable.txt` with the URL and the wall type.

For YuJa / password-protected / cookie-required resources: log to `unreachable.txt` and Sub-agent A will surface them as `blocking_unreachables`.

## Stage 4 — Sub-agent A: review investigation

Spawn one general-purpose agent via the Agent tool. Use this exact prompt template (fill in the bracketed paths):

> You are reviewing the investigation phase of a Canvas assignment that doesn't fit any specialized skill. The investigation outputs are in `[runs/<today>/<work>/]`. Read every file under `spec.md`, `investigation/rubric.md`, `references/`, and `investigation/unreachable.txt`. Then answer:
>
> 1. Is the assignment's deliverable clear? In one sentence, what is the student expected to produce?
> 2. Is the rubric documented? If `rubric.md` starts with `RUBRIC NOT FOUND`, this is critical.
> 3. Are all referenced materials downloaded under `references/`? List any reading / data / scaffold the spec mentions but isn't present.
> 4. Are there sources you suspect were missed (front-page links not followed, module wiki pages not pulled, instructor-site sub-pages)? List them with where to look.
> 5. Do the unreachable resources block the work, or can the assignment be completed without them?
>
> Output strict JSON with these fields:
> - `deliverable_clear`: bool
> - `deliverable_summary`: string (one sentence)
> - `rubric_found`: bool
> - `inputs_complete`: bool
> - `missing_sources`: string[]   // where-to-look hints
> - `blocking_unreachables`: string[]   // unreachable resources that genuinely block the work
> - `verdict`: 'proceed' | 'recover' | 'stop'
> - `recovery_actions`: string[]   // populated only when verdict == 'recover'
>
> Do not output prose around the JSON.

Save output to `investigation/review_a.json`.

**Handling the verdict**:

- **stop** → write `result.json` with `status: "error"`, `notes` = a one-paragraph summary of why (paraphrase from Sub-agent A's deliverable_summary + missing_sources). End the skill.
- **recover** → for each `recovery_action`:
  - If it's a "fetch X URL" the skill missed → run the fetch and append to `references/`.
  - If it's a "no rubric" recovery → tell the student: "I couldn't find a grading rubric anywhere for this assignment. If you have a copy or a link, paste it or send the URL. Otherwise I'll do my best with the assignment description alone, but verification will be looser." Wait for student response.
  - If it's a `blocking_unreachable` → YuJa-style soft-stop: tell the student "This assignment references [resource]. I can't reach it from here. If you can paste the relevant content or send a transcript, I'll use it; otherwise I'll proceed without it and flag the gap in my notes."
  - After recovery actions complete, re-run Stage 4 with the same prompt. Max 2 recovery rounds. If verdict is still not `proceed` after round 2, escalate to `stop`.
- **proceed** → continue to Stage 5.

## Stage 5 — classify-output

Pick the output mode based on `spec.md` + `investigation/rubric.md` + `assignment.submission_types` + what's in `references/`. **Plus**: if Stage 0's `user_preferences` contains a `preferred_output_mode` hint from prior dispatches, prefer that mode when this assignment's signals are ambiguous (e.g. when both `doc_prose` and `pdf_typed` could fit, learnings nudges toward whichever the student has settled on). Write the chosen mode as the first line of `pipeline_design.md`:

| Mode | Trigger conditions |
|---|---|
| `doc_prose` | submission_types contains `online_upload` or `online_text_entry` AND rubric mentions word count / paragraph structure / essay shape. Output: .docx (or .md if rubric is silent on format). |
| `pdf_annotated` | submission_types contains `online_upload` AND `references/` contains a reading PDF AND rubric mentions annotation / highlights / margin notes. Output: annotated copy of the source PDF. |
| `pdf_typed` | submission_types contains `online_upload` AND rubric mentions math notation / LaTeX / problem set / numerical answers. Output: typed PDF. |
| `code` | submission_types contains `online_upload` AND `references/` has a scaffold OR rubric mentions "submit your code" / file extensions like `.py` / `.js`. Output: source file(s) or archive. |
| `form_answers` | submission_types contains `online_text_entry` AND rubric is a list of short questions OR assignment description contains a list of questions. Output: text submission body. |
| `mixed` | multiple of the above apply (e.g. lab report = pdf_typed + code). Decompose into constituent modes; treat each as a sub-pipeline. |

**If no mode matches with confidence** (less than 80% confident the right mode is one of these): write `result.json` with `status: "error"`, `notes: "could not classify output mode for assignment; investigation/ has full context; please dispatch a specific skill manually or extend canvas-generic"`. End the skill.

## Stage 6 — design-pipeline

Append the pipeline stages to `pipeline_design.md`. Use the template matching the Stage 5 mode. **Apply Stage 0 learnings**: if `workflow_notes` from the learnings overlay says to skip / reorder / parameterize a stage (e.g. "skip figure-caption substage — this cluster never has figures"), honor that. If `user_preferences` specifies voice register / citation style / format, fold those into the stage template's parameter slots (e.g. `voice_register: <learnings.voice_register>` instead of the default B1-B2).

**doc_prose**:
```
1. draft — prose generator, target word count from rubric, voice register inferred from
   assignment context (default B1-B2 international-student for undergraduate; advanced
   academic if rubric demands graduate-level voice)
2. canvas-humanizer — Skill tool invocation, voice register fixed from step 1
3. export — render to .docx (or rubric-specified format)
```

**pdf_annotated**:
```
1. read source PDF from references/
2. extract underscore-group answer blanks via PyMuPDF
3. annotate inline — coordinate-based left-margin notes (x < 80), color rubric
   per rubric.md if specified, else default green=vocab pink=content
4. fill answer blanks at ≥90% line width in target voice
5. render output PDF
```

**pdf_typed**:
```
1. parse problem statements from spec.md + references/
2. solve each problem (LLM judgment + show work)
3. render solutions to LaTeX
4. compile to PDF via MathJax
```

**code**:
```
1. analyze scaffold in references/ (if present)
2. read tests if any (rubric "tests pass" criterion)
3. implement — test-first if tests exist, else direct-to-spec
4. run tests / lint per rubric's criteria
5. package per submission_format (single file / zip / git bundle)
```

**form_answers**:
```
1. extract question list from spec.md
2. answer each question, citing source from references/ where applicable
3. format as text submission body
```

**mixed**: list each constituent mode's stages with a prefix, then a concatenation step at the end.

Adjust each template's stages for rubric specifics:
- Citation style mentioned in rubric → add a `citations` substage between draft and export.
- Specific notation rule ("name each law you apply") → add to the generator prompt.
- Required figure count → add to the draft prompt + Stage 8 checklist.

## Stage 7 — generate

Run the pipeline designed in Stage 6. Write artifacts to `draft/`.

**For `doc_prose`**: after the draft is produced, invoke `canvas-humanizer` via the Skill tool with `input_path=draft/<filename>` and `voice_register` from Stage 6 step 1. Humanizer writes humanized output back to the same path and writes `humanizer_log.json` to the work dir.

**For `code`**: if `references/` contains a test scaffold, run the tests after each generation pass; iterate until passing (max 5 implementation rounds, then `status: "error"`). If no tests exist, generate, then run `python -m py_compile` (or equivalent for the language) to confirm parseable.

**For `pdf_annotated`**: use PyMuPDF following the same pattern as `canvas-reading-annotation` (coordinate-based left-margin annotation, ≥90% line-width answer fills). Apply the color rubric from `rubric.md` if specified; default green=vocab pink=content otherwise.

**For `pdf_typed`**: render via MathJax → PDF. Ensure no `[placeholder]` literals leak.

**For `form_answers`**: write the body to `draft/submission.txt`.

**For `mixed`**: run each constituent sub-pipeline producing its own artifact, then concatenate or co-locate per the rubric's stated submission shape.

## Stage 8 — Sub-agent B: design verification

Spawn one general-purpose agent. Use this exact prompt template:

> You are designing a verification checklist for a Canvas assignment draft. Read these files:
> - `[runs/<today>/<work>/]investigation/rubric.md` — the grading criteria
> - `[runs/<today>/<work>/]draft/` — the produced draft
> - `[runs/<today>/<work>/]pipeline_design.md` — the chosen output mode
>
> Produce a numbered checklist where each item is a yes/no testable proposition derived from a specific rubric line:
>
> - For **numeric constraints** (word count, page count, citation count, function count, problem count): the check must produce a measured number with a pass criterion threshold.
> - For **structural constraints** (thesis paragraph present, conclusion present, figure caption format, required section headings): the check must locate the expected structural element and report present/absent.
> - For **voice/register constraints**: the check must spot-check ≥3 paragraphs against named criteria from the rubric (e.g. "no contractions in academic register").
> - For **content/correctness constraints** that aren't mechanically checkable (e.g. "argument is persuasive"): mark as `human_review` and skip the check.
>
> Output a markdown checklist to `verification_checklist.md`. Each item must be on its own line in this format:
>
> ```
> - [ ] <one-line check description> | measurement: <how to measure> | pass criteria: <threshold>
> ```
>
> If the rubric is missing (`rubric.md` starts with `RUBRIC NOT FOUND`), fall back to a generic checklist for the Stage 5 output mode:
> - `doc_prose`: word_count > 0, no `[placeholder]` strings, no MBTI 4-letter codes leaked, file opens cleanly in the target reader.
> - `pdf_annotated`: page count matches source PDF, at least one annotation per page, no overlapping annotations, color rubric applied where specified.
> - `pdf_typed`: page count > 0, no `[placeholder]`, every problem from spec has a corresponding solution.
> - `code`: file parses (lang-specific compile/parse check), tests pass if tests exist.
> - `form_answers`: every question in the spec has a non-empty answer.

Save the checklist to `verification_checklist.md`.

## Stage 9 — verify

Run every check in `verification_checklist.md` in order. Each check produces a line in `verification.log`:

```
PASS | word_count >= 500 | measured: 612
PASS | citation_count >= 3 | measured: 5
FAIL | thesis_in_intro_paragraph | measured: not detected in first 200 words
SKIP | argument_is_persuasive | reason: human_review (not mechanically checkable)
```

Use the SAME measurement primitives as the specific skills:
- `len(text.split())` for word count.
- `page_count` from PyMuPDF for PDFs.
- `ast.parse` + `[node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]` for function counts.
- `re.findall` for citation patterns.

If any `FAIL`: re-enter Stage 7 with the failing checks fed back into the generator prompt as explicit constraints. Max 3 retry rounds. If still failing after round 3 → `result.json` with `status: "error"`, `notes` listing the persistent FAILs.

## Stage 10 — Sub-agent C: review verification

Spawn one general-purpose agent. Use this exact prompt template:

> You are reviewing whether a verification checklist actually covers the assignment's rubric. Read:
> - `[runs/<today>/<work>/]investigation/rubric.md`
> - `[runs/<today>/<work>/]verification_checklist.md`
> - `[runs/<today>/<work>/]verification.log`
>
> Answer:
>
> 1. For each rubric line that is mechanically checkable, is there a corresponding check in the checklist?
> 2. Are any checks **false-pass risks**? Example: a "has citations" check that passes on any `[1]` even if it's not a real citation; a "thesis present" check that just looks for the word "thesis"; a "no placeholders" check that misses Unicode-formatted ones.
> 3. Are any rubric items un-checkable mechanically and skipped — does that leave a non-trivial grading risk?
>
> Output strict JSON:
> - `coverage_gaps`: string[]   // rubric items that should have a check but don't
> - `false_pass_risks`: string[]   // checks that look like they pass but might not catch real failures
> - `human_review_items`: string[]   // rubric items that are intrinsically subjective
> - `verdict`: 'verification_sufficient' | 'add_checks' | 'human_review_required'
>
> Do not output prose around the JSON.

Save to `review_c.json`.

**Handling the verdict**:

- **add_checks** → re-enter Stage 8 with `coverage_gaps` + `false_pass_risks` as additional inputs to Sub-agent B's prompt. Then re-run Stage 9. Max 2 rounds of B↔C iteration. If verdict is still `add_checks` after round 2, downgrade to `human_review_required`.
- **human_review_required** → continue to Stage 11 but include `review_c.human_review_items` in `result.json.notes` so the student knows what to spot-check before uploading.
- **verification_sufficient** → continue to Stage 11.

## Stage 11 — export + result

The draft artifact is already at `draft/<filename>` from Stage 7. Finalize the filename if needed (e.g. attach `.final` suffix, rename to match Canvas's expected filename pattern from `assignment.allowed_extensions`).

Write `result.json`:

```json
{
  "status": "draft_ready",
  "draft_path": "runs/<today>/<work>/draft/<filename>",
  "verification_log_path": "runs/<today>/<work>/verification.log",
  "output_mode": "doc_prose",
  "humanizer_applied": true,
  "sub_agent_a_verdict": "proceed",
  "sub_agent_c_verdict": "verification_sufficient",
  "human_review_items": [],
  "notes": "..."
}
```

**Never auto-submit.** canvas-generic has no overlay-level authorization mechanism by design. Status is always `draft_ready` or `error`. The student reviews the draft and uploads manually.

---

## Hook contract

Hooks the skill must satisfy:

- **Stop hook** (`check-router-complete.py`) — every assignment in `assignments.json` must have a `result.json`. Stage 11 writes one; on error paths in Stages 4 / 5 / 9 / 10, write the error `result.json` before stopping.
- **PostToolUse `check-result-schema.py`** — `result.json.status` must be one of `draft_ready` / `error`. (No `submitted` because canvas-generic never submits.)
- **PostToolUse `check-spec-grounding.py`** — for `status: "draft_ready"`, if `spec.md` mentions external references but `references/` is empty, the hook blocks. Stage 3 must download what's reachable; Stage 4 Sub-agent A must surface what isn't.
- **PreToolUse `check-presubmit-audit.py`** — not relevant; canvas-generic never calls `cv.submit_files`.
- **PostToolUse `check-identifier-grounding.py`** — for `code` output mode producing `.py` files, every suspicious identifier must be grounded in `spec.md` / `references/` / Python builtins. Same as canvas-ics33.

---

## §11 — When to graduate a cluster to a specific skill

canvas-generic is the runtime-design fallback. The 5 specific skills exist BECAUSE certain assignment shapes (code with test runners / quiz with arbitration / zyBook tables / annotation rubrics / long essays with citation styles) deserve a pre-designed pipeline.

Three sub-agent reviews (A / B / C) replace what the overlay would have specified. Token cost: a canvas-generic dispatch runs roughly 3× the LLM calls of a comparable specific-skill dispatch.

For low-frequency clusters (a one-off assignment, a course you take once), this is the right tradeoff.

For high-frequency clusters (an assignment kind that fires every week for a quarter), graduating to a specific skill is worth it. Signs that a cluster should graduate:

- canvas-generic has run on the same cluster 4+ times.
- Sub-agent C keeps flagging the same coverage_gaps each run (= the verification logic is converging on a stable shape that should be hardcoded).
- The pipeline_design.md stages are essentially identical across runs (= the pipeline is converging on a stable shape).

When this happens: re-run canvas-bootstrap on the cluster, manually override the route from `canvas-generic` to whichever specific skill matches the converged pipeline shape (or, rarely, file an issue to add a sixth specific skill).

---

## §12 — Stage-by-stage mode (first-run calibration only)

When invoked with a context line containing **STAGE-BY-STAGE MODE** AND the control file `<work>/.first_run_stage_by_stage` exists, run **only the single stage named in the directive** instead of the full pipeline. Set by `canvas-bootstrap` §8 during first-run calibration so the student reviews each stage before the next runs.

Behavior:
1. Read `<work>/.first_run_stage_by_stage` to confirm. If absent, run the full 11-stage pipeline as usual.
2. Parse the directive for the stage name (`fetch-context`, `find-rubric`, `locate-inputs`, `sub-agent-a`, `classify-output`, `design-pipeline`, `generate`, `sub-agent-b`, `verify`, `sub-agent-c`, `export`).
3. Run **only** that stage's substeps from §3 above. Prior stages' artifacts must already be in `<work>/`.
4. Write a 1-3 sentence English summary to `<work>/stages/{stage_name}.done` and STOP.

Daily dispatch via canvas-execute does not set the marker; runs full-pipeline as usual.

## §13 — Stage-by-stage time bands

| Stage | Band | One-line description |
|---|---|---|
| 1 fetch-context | short | Pull description + front_page + modules + syllabus + attached files + URLs |
| 2 find-rubric | short | 4-layer rubric hunt (Canvas API → spec grep → module grep → external fetch) |
| 3 locate-inputs | medium | Download every referenced file to `references/` (PDFs, scaffolds, instructor site HTML) |
| 4 sub-agent-a | medium | Investigation completeness review; may trigger recovery loop |
| 5 classify-output | short | Pick output mode (doc_prose / pdf_annotated / pdf_typed / code / form_answers / mixed) |
| 6 design-pipeline | short | Sketch per-mode stages tailored to the rubric |
| 7 generate | long | Run the designed pipeline; for `doc_prose` invokes `canvas-humanizer` |
| 8 sub-agent-b | medium | Design verification checklist from the rubric |
| 9 verify | medium | Run every checklist item with measured PASS/FAIL/SKIP |
| 10 sub-agent-c | medium | Verification coverage review; may trigger 1 round of add-checks |
| 11 export | short | Finalize artifact + write result.json |

Band: `short` ~1 min, `medium` ~3-5 min, `long` ~10+ min. canvas-generic does NOT submit; output is always `draft_ready` for student review.
