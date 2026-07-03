# Canvas Pilot — North Star

This document is the durable answer to "what is Canvas Pilot trying to be?"
The README describes today's surface. This file describes the trajectory.

If you are a fork user deciding whether to invest time learning this project,
read this first — it tells you what's solid right now and what's still on the
roadmap.

If you are working on the framework, this file is the single source of truth
for what counts as a real feature versus a stop-gap.

---

## What Canvas Pilot is

Canvas Pilot is a **turnkey product** for students whose coursework has a
high share of repeating-structure assignments (weekly readings, weekly
problem sets, weekly quizzes, weekly homework attached to a textbook
platform). It scans your Canvas, plans the week, and dispatches each
recurring assignment to a course-specific skill that produces a draft you
review before anything is submitted.

The product is not a "submit my homework for me" tool, and it is not a
research framework where every fork user has to write their own per-course
logic. It is closer to: **iCal for school + an assistant who already knows
how to do the four kinds of recurring assignment that show up week after
week.**

The four recurring kinds Canvas Pilot ships with first-class support for:

1. **Code course** — programming assignments where the spec lives on an
   instructor's external website and the deliverable is code (Python,
   typically; the framework is language-shaped, not language-locked).
2. **Writing course** — academic English, reading annotation, summary
   writing, response papers, long-form essays — assignments where the
   deliverable is prose (annotated PDF or DOCX).
3. **zyBook-backed math/discrete course** — assignments where the spec is
   a table of exercise references and the deliverable is solved problems
   rendered as a PDF.
4. **Online Canvas quiz** — open quizzes with a time limit, where the
   deliverable is a sequence of answers submitted within the window.

Each kind maps to a **generic skill** under
`.claude/skills/canvas-<name>/SKILL.md`, configured to your specific
school + course via a flat overlay at `_private/canvas-<name>-app.md`.
The writing-course kind is **split into two skills** — `canvas-reading-annotation`
(PDF markup pipeline) and `canvas-essay` (long-essay pipeline) — because
the pipelines share almost no machinery. `src/ac_eng_router.py` routes
each assignment to one or the other via a deterministic 6-layer cascade.
Total: **5 generic skills** for 4 recurring kinds.

---

## Design principles

These do not change between versions. Everything in the roadmap below
respects these principles.

### Skills are pipelines, not monoliths

A real assignment isn't "one prompt produces one output". A real
assignment has stages with distinct skill requirements. Writing a 5-page
research paper is research → outline → draft → humanize → verify,
not one function. Each stage is independently tunable, replaceable, and
inspectable. Personal design files customize specific stages, not the
whole skill.

### The approval gate is a filesystem boundary

`canvas-scan` writes `plan.json` and stops. `canvas-execute` reads it
after the user replies with approval. Two skills, two Skill-tool
dispatches — the user can interrupt between them. Prose instructions
cannot enforce this; filesystem state can.

### Drafts by default, submission only with standing authorization

Default behavior: produce a draft, you upload manually. Auto-submit is
per-skill, per-overlay, gated by a verification log that has to pass
before any upload call. Auto-submit is never the silent default.

### Agent stops at can't-do, not shouldn't-do

Per-course skills work for the **student**. A skill never refuses an
assignment because the instructor wrote a behavioral rule ("don't use
AI", "no collaboration", "no paraphrasing"); whether running the
framework on a given assignment is consistent with the operator's
school's policies is the operator's decision, in line with the
"Academic-integrity arbitration" non-scope clause below.

A skill stops only when it **physically cannot proceed**. Four
intrinsic can't-do categories: (1) physical impossibility (in-person
attendance, Lockdown Browser, paper submission, live signature),
(2) identity-bound (honesty contracts, ID verification, oral defense),
(3) input missing and unobtainable (spec cannot be found anywhere,
referenced file cannot be fetched and the student can't supply it),
(4) verification failure after retries.

For resources that are physically out of reach but might be obtainable
with the student's help — a video link, a password-protected download,
an external-site login — the skill **soft-stops**: offers to take a
URL or credential from the student, resumes if given, skips that step
and continues with what it can do otherwise.

Where a skill uses a voice register (e.g. a B1-B2 student tone), the
documented reason is **student-identity alignment** — the student
picks a register that matches who they actually are. The register is
part of the student's voice, not a posture the skill adopts for the
assignment. Output-quality concerns (where the deliverable has to
survive content-quality review) are a separate stage concern, handled
by the humanize stage below.

**scope-first onboarding**: `canvas-bootstrap` designs **one course
(or one cluster within a course) per invocation** — a tangible
deliverable every time the student runs it, rather than batch-
processing every course up front and presenting a wall of text.

### Output that looks human, by design

For assignments where authorship signals matter (writing courses,
extended responses), the pipeline includes a dedicated **humanize
stage** whose only job is to take the draft and produce output that
survives current AI-content detectors. This is a first-class stage with
its own verification, not a footnote. v0.1 ships with this stage present
in `canvas-reading-annotation` (writing) where the failure cost is highest.

For assignments where authorship signals don't matter (code, math
solutions, MCQ answers), the equivalent concern is **submission-pattern
human-ness** — pacing, timing, focus/blur events — handled at the
submission stage, not the content stage.

### One assignment = one work directory = one result.json

The Stop hook refuses to release the session until every dispatched
assignment has produced a valid result. No silent partial completion.

### `assignment.description` is rarely the real spec

Per-course skills treat the Canvas description as a routing hint and
pull the actual instructions from instructor websites, attached PDFs,
module pages, or referenced readings. Where the spec lives for a
specific course goes in that course's personal design file.

### No mocking on integration boundaries

Tests against Canvas use recorded fixtures or a sandbox course; mocks
don't catch drift between the spec and the real API.

---

## The five generic skills

Each shipped skill is structured as an **N-stage pipeline**. The pipeline
is described in the public `SKILL.md`. School- and instructor-specific
customization for individual stages lives in the user's
`_private/canvas-<name>-app.md`.

### `canvas-ics33` — code course

```
fetch-spec → fetch-references → download-scaffold → constraints-checklist →
test-first implement → process_humanize (process-graded courses only) →
audit (identifier-grounding + numeric-constraint + coverage check) →
bundle + re-clone verify → submit (if authorized)
```

The framework is **language-neutral** — the overlay specifies which
language's test runner, build command, and submission format. The same
9-stage prose drives a Python+unittest+git-bundle course or a
Java+gradle+jar course; only the overlay command strings differ.

`process_humanize` is a first-class stage parallel to
`canvas-reading-annotation`'s text humanize: for process-graded courses
(grader looks at git log), it rewrites the commit history into a
multi-commit, backdated, undergrad-message-register sequence. Off by
default; overlay's `process_severity` enables it.

Personal design specifies: course id, language + test runner / coverage
command / submission format, instructor's spec URL pattern, scaffold
distribution mechanism (git bundle / zip / GitHub Classroom / inline /
none), reference-fetch regex patterns, process_humanize knobs (spread
days, commit message register, few-shot examples), auto-submit scope,
headless cron env var name.

### `canvas-reading-annotation` — writing course (PDF markup)

```
classify (reading_annotation / video_exercises / in_class_skip / ...) →
locate_reading (overlay's reading_files mapping) →
extract_text_and_blanks (PyMuPDF underscore-group find) →
annotate_pdf (color highlights + margin notes in place) →
fill_answer_blanks (typed answers at ≥90% line width, in target voice) →
verify (6-check gate: line fill, note density, color family, page count,
        no overlap, no sticky icons) → submit (if authorized)
```

Personal design specifies: course id(s), homework module id, reading-file
mapping, color rubric (vocab family vs content family), voice register
(free-form description of student voice), instructor rubric verbatim,
video→worksheet pairings.

### `canvas-essay` — writing course (long-form essay)

```
load_persona (MBTI-derived tone vector) →
parse_spec (walk attached PDFs / module pages / external links) →
load_sample_essays (few-shot anchor) →
generate (outline → body → revise) →
figure_captions + works_cited (3-layer cascade) →
verify (word count ≥ spec minimum, citation count, figure caption count) →
output (.docx / .pdf per overlay) → submit (if authorized)
```

Personal design specifies: essay name trigger patterns (consumed by
`src/ac_eng_router.py`), voice register specifics, sample essay path,
citation style (MLA / APA / Chicago), figure caption format, persona-
derivation template.

### `canvas-zybooks` — zyBook-backed math/discrete course

```
classify (written HW / take-home exam / reading completion)  →
fetch-spec (Canvas description table OR attached PDF)  →
fetch-exercises (zyBook API)  →  solve  →  render-LaTeX-PDF  →
verify (subquestion count, no placeholder leaks)  →
draft-only (GradeScope upload is manual)
```

Personal design specifies: Canvas course id, zyBook course code, JWT
auth path, course-context primer for the solver, instructor-specific
notation rules (e.g. "name each law you apply, one law per step"),
assignment naming convention.

### `canvas-inside` — online Canvas quiz

```
classify (full quiz vs single-question-video-quiz vs unknown) →
4 safety gates (autorun / human-hours / per-cron rate / whitelist) →
reading discovery (4-layer hunt: module → files+syllabus → PDF → web) →
study_notes.md → 4-agent arbitration (notes-first / grep-first /
framework-aware / contrarian) → paced-submit (humanness: timing,
blur/focus, sequence non-linearity, optional strategic miss) →
complete → score-check → retake-with-feedback (Layer 2 gated)
```

Submission-pattern humanness is implemented as named Python helpers
called by the SKILL.md, not as configurable overlay knobs:
`src.quiz_pacing.compute_answer_schedule` (log-normal per-question
timing, 78% time utilization, outlier injection),
`src.quiz_pacing.build_answer_sequence` (skip-ahead pass + revisit
pass), `src.quiz_focus_events.pick_blur_slots` /
`pick_flagged_questions` (page_blurred/focused pairs + question_flagged
events), `src.quiz_strategic_miss.maybe_flip_answers` (optional,
env-gated). The framework prose calls these by exact name.

**Three independent enforcement layers** prevent bypass of the 4-agent
arbitration:
1. `src.canvas_client._require_canonical_arbitration_evidence` — the
   `complete_quiz_submission` and `answer_quiz_questions` APIs refuse
   to fire unless `runs/<work>/agent_passes/` contains ≥4 distinct
   JSON files.
2. `.claude/hooks/check-router-complete.py` Stop hook — blocks session
   stop when `kept_score/points_possible < 0.95` AND attempts remain
   AND `scoring_policy == keep_highest`, forcing a retake.
3. `.claude/hooks/_lib.py:_validate_quiz_submitted_schema` — rejects
   any quiz `result.json` with `status: submitted` lacking
   `agent_passes_count >= 4`, the canonical numeric fields, or
   `human_ness_diagnostics.views_paired_with_answers == true`.

Personal design specifies: whitelisted course ids, instructor framework
primer (prose), expected canonical knowledge, auto-take scope,
human-hours window, max-per-run, strategic-miss default,
target-score-band, retake-pass-band.

---

## Roadmap

### v0.1 — first public release

Ships:
- Five framework skills (`canvas-setup`, `canvas-bootstrap`, `canvas-scan`,
  `canvas-execute`, `canvas-skip`) — all working, walked through real fork
  testing.
- Five generic per-course skills as **functional pipelines**, each with
  the stages enumerated above. Humanize stage present for
  `canvas-reading-annotation`. Submission-pattern human-ness present for
  `canvas-inside`.
- One worked example personal design file per skill, documented in
  `docs/SKILL_DESIGN.md`.
- Cookie auth via Playwright as the only supported auth path.
- Codex sidecar mirrors for the five framework skills.

Explicitly does NOT include:
- Token-mode auth (some schools disable it; cookie works at every school
  that has Canvas, so we ship only cookie).
- A web UI. Everything is Claude Code in this directory.
- Auto-detection of which generic skill to use for a new course. The
  user picks at bootstrap time.

### v0.2 — robustness pass

- Humanize stage extended where the deliverable is prose (writing-course skills primarily) — not just canvas-essay
  (writing, quiz response writing), not just writing.
- Retry policies on Canvas API flakes (Canvas is flaky; v0.1 lets errors
  propagate, v0.2 distinguishes transient vs. terminal).
- Better failure messages for partial pipeline failures (e.g. when the
  humanize stage fails verification but the draft itself is fine).

### v0.5 — multi-school portability

- A second school's worked example in `_examples/` (a fork user has
  contributed an overlay from a second school for a code course; we verify it runs
  end-to-end before merge).
- The personal design schema stabilizes and is documented as a contract.

### v1.0 — production-ready turnkey

- The five generic skills are robust enough that a fork user at any
  US-based Canvas-using school can run `canvas-setup`, answer ~3
  questions, and have their week of recurring assignments drafted
  without authoring custom prose.
- Verification gates are tight enough that auto-submit can ship as an
  opt-in default for low-risk assignment types.

---

## What is intentionally NOT in scope

- **Replacing Claude Code.** This is a Claude Code project, not a
  standalone CLI. The product depends on Claude Code's skill dispatch,
  tool use, and approval semantics. Trying to factor out Claude Code
  produces a worse product and an unmaintainable framework.
- **Supporting LMSes other than Canvas.** Each LMS has enough API
  surface area that supporting two means supporting two frameworks.
  Canvas is broad enough; v1.0 is "good at Canvas", not "decent at
  three LMSes".
- **A multi-tenant SaaS.** Canvas Pilot is a per-user local install.
  Multi-tenant introduces auth, payment, and abuse vectors we don't want
  to absorb. If you want this as a service, fork it and host it for
  yourself.
- **Hand-rolled detector-bypass telemetry.** The humanize stage
  is a stage in a pipeline, not a research program. We ship what works
  against current detectors and update when they update. We do not
  publish "how to beat detector X" guides; that work lives in the stage
  itself.
- **Academic-integrity arbitration.** Whether running this on a given
  assignment is appropriate is a decision the operator has to make in
  light of their school's policies. The framework is opinion-neutral on
  that question and ships no policy-screening logic.

---

## How this doc gets updated

When a real shipped version reaches one of the milestones above, the
matching v0.x / v1.0 section gets updated in-place to past tense ("v0.1
shipped 2026-MM-DD, scope as described"). The roadmap sections below the
current version stay forward-looking.

When a stage of the five generic skills materially changes shape (a new
stage gets added, an old one retired, a stage's contract changes), the
"five generic skills" section gets updated and a one-line entry goes in
the relevant skill's SKILL.md changelog.

This file is the contract. The skills are the implementation. When they
diverge, this file is right and the skills are bugs.
