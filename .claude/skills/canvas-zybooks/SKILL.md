---
name: canvas-zybooks
description: Generic zyBook-backed math/discrete course handler — written homework, take-home exams, reading-completion. Invoked by canvas-execute when an assignment's routing skill is `zybooks`. Before doing anything, this skill loads `_private/canvas-zybooks-app.md` which encodes your school/instructor-specific behavior (zyBook course code, JWT cookie path, course-context primer, instructor's grading rule). Without the overlay the skill stops and asks the user to author one.
---

# canvas-zybooks — generic zyBook-course framework

This is the **framework skeleton**. The actual handling pattern for a
zyBook-backed course depends on parameters that vary by instructor and
school (which zyBook code maps to which Canvas course, the JWT auth
file location, the course-context primer for the LLM solving the
problems, the notation rules used by the course). Those live in a
local overlay file.

## §1 — Agent service model

**Agent stops at can't-do, not shouldn't-do** — this skill serves the student. Behavioral policies set by course staff (prohibitions on AI tools, on cooperation, on outside tutors, on paraphrasing) are between the student and the staff; the skill does not gate on such rules. The skill does the work regardless; whether to use the output is the student's call. The skill only stops on **intrinsic can't-do**:

1. **Physically impossible / the agent genuinely can't do it** — in-person attendance, printing paper artifacts, in-person signing, Lockdown-Browser-locked quizzes, Respondus monitor proctoring.
2. **Must be the student personally** — academic honesty contract signature, ID proof, in-person peer review, interview-style.
3. **Input missing and unobtainable** — spec cannot be located anywhere; a required material file cannot be fetched and the student cannot supply it.
4. **Verification fails after retries** — sub-agent-designed checklist still fails after 3 retry rounds.

**YuJa-style soft-stop** — for resources the agent physically can't reach but where a fetched substitute may exist (linked videos, password-protected pages, third-party site logins), the skill does not hard-stop. It offers the student a chance to supply the link:

> "This week's HW references a YuJa video. I can't log into YuJa myself. If you send me the video URL, I'll try transcript / scraping; otherwise I'll skip this step and do the rest of the work I can do."

Student declines → skip that step and continue with the work that can be done. Student supplies → agent attempts fetch (transcript / OCR / scraping, whichever the platform supports).

The voice register and overlay parameters reflect the student's identity (which course, which level, which subject background), not a posture toward third-party detection systems.

## Step 0 — load the local application overlay

Before any other step, read `_private/canvas-zybooks-app.md` in this
project's root. **That file is the operating skill for your specific
course context.** If it doesn't exist, stop and tell the user:

> No `_private/canvas-zybooks-app.md` found. This skill is a framework
> skeleton; the actual handling logic depends on school- and
> instructor-specific parameters. See the canvas-pilot README "Local
> application overlays" section for how to author one for your course.

If the overlay exists, follow its instructions in full — its
prescriptions take precedence whenever this skeleton defers to "your
instructor's rule" or "your school's behavior".

## Framework pattern

A zyBook-course handler typically:

1. Classifies the assignment kind: written homework (HTML table in
   Canvas description), take-home exam (attached PDF), reading
   completion.
2. For written homework: parses the Canvas description's table to
   extract `(chapter, section, exercise, parts)` refs.
3. For take-home exam: downloads the attached PDF and extracts
   per-question text.
4. Calls zyBook's API with the student's JWT (from overlay-specified
   cookie file) to fetch the matching section exercises.
5. Solves each problem with LLM judgment, applying the overlay's
   course-context primer + grading rules.
6. Renders a typed PDF with LaTeX (MathJax) for the math notation,
   filling in `[answer needed]` placeholders.
7. Verifies subquestion count and rendering before writing to draft.
8. Does **not** upload — the student delivers to GradeScope manually.

## §X — Research before improvise (run when the spec doesn't fit the 3 standard kinds)

Trigger (any of these from the Canvas description / attached PDF / zyBook fetched content):
- Canvas description table has columns or column ordering different from the standard "Suggested Practice / Graded for Honest Effort" pattern
- Take-Home Exam PDF references a question type the overlay hasn't seen (e.g. a new proof technique, a new notation system)
- Reading Week assignment points to a section that has unusual exercise types not in the overlay's `course_context_primer`
- Past 3 same-course assignments had grader comments mentioning issues this spec also touches

When triggered, do NOT improvise. Spawn 2-3 agents IN PARALLEL — single message with multiple `Agent` tool calls (same idiom as `canvas-inside` §7c 4-agent arbitration):

- **Agent A — spec-verifier** (`subagent_type=general-purpose`): re-read the Canvas description / attached PDF from scratch. List literal requirements (which sub-exercises by letter, hard numeric constraints, forbidden things, required notation), 1-3 ambiguities. Output <400 words.

- **Agent B — quality-inferrer** (`subagent_type=general-purpose`): read this spec + past N (=5) result.jsons for same-course assignments + their grader comments (via `cv.get('/courses/<cid>/assignments/<aid>/submissions/self?include[]=submission_comments')`). Infer what "doing this well" requires beyond literal asks: notation conventions the instructor enforces, common failure modes with verbatim grader quotes, recommended mechanically-checkable gates (e.g. "each step must name the law applied"). Output <400 words.

- (Optional) **Agent C — template-fit checker**: list places where the overlay's standard 3-kind flow doesn't cover this specific assignment. Output <300 words.

Save the reports to `<work>/research_findings.md`. Use the findings to augment the rendering plan, add new gates to Step 7's verification, and override the overlay's default notation rules where this HW has stricter requirements.

## §Y — Post-delivery self-audit (MANDATORY, never skip)

Runs AFTER Step 7's subquestion-count + rendering verification and BEFORE the student delivers to GradeScope. Adds a semantic spec-vs-deliverable diff layer.

Spawn 1 audit agent (`subagent_type=general-purpose`), inputs:
- The Canvas description text + any attached PDF text
- The zyBook fetched exercise text (`<work>/zybook_exercises/`)
- `<work>/research_findings.md` if §X ran
- The produced PDF deliverable (extract text via PyMuPDF for the agent)
- Past 3 same-course grader comments

Agent prompt:
> Return a JSON array of gaps using this schema:
> ```json
> {
>   "severity": "HIGH" | "MED" | "LOW",
>   "kind": "spec-violation" | "historical-risk" | "ambiguity-unresolved" | "format-mismatch" | "notation-drift" | "missing-subquestion",
>   "gap": "<one-line description>",
>   "spec_anchor": "<verbatim quote from Canvas description / PDF / zyBook>",
>   "deliverable_anchor": "<verbatim quote from PDF, or 'MISSING' if a subquestion is unaddressed>",
>   "fix_suggestion": "<one-line concrete fix referencing the page + question>"
> }
> ```
> Honesty rules: quote verbatim; if no gaps return `[]`; for math notation, check law-naming convention (overlay's `instructor-specific notation rules`).

Save to `<work>/audit/round_1.json` (atomic write). If ANY HIGH gap: apply each `fix_suggestion`, re-render PDF, re-run Step 7 + §Y audit. Max 3 rounds. After 3 rounds with HIGH gaps remaining → `status: error`, notes pointing to `<work>/audit/`.

Token note: 1 agent × up to 3 rounds × ~5k tokens = ~15k per assignment. zybooks is GradeScope-delivered (CEO uploads manually), so this gate is the last line of defense before CEO sees the PDF.

## Local application overlay specifies

- Canvas course ID + zyBook course code
- JWT cookie file path (e.g. `.zybooks_localstorage.json`)
- Course-context primer (e.g. "Boolean logic, predicates, quantifiers,
  proofs, sets, relations, graphs")
- Instructor-specific notation rules (e.g. "name the laws, one law per
  step")
- Assignment naming scheme (e.g. "Homework N", "Take-Home Exam N",
  "Reading Week N")
- LaTeX rendering config (fonts, MathJax version)

The overlay is intentionally free-form Markdown — this skeleton loads
it verbatim into the CC context and lets the overlay's prose guide
the flow. Phase 2 of the canvas-pilot upgrade extracts more framework
logic into this skeleton and leaves a thinner overlay; for now the
overlay is the complete original skill description moved verbatim from
`.claude/skills/canvas-zybooks/SKILL.md`.

---

## Stage-by-stage mode (first-run calibration only)

When invoked with a context line containing **STAGE-BY-STAGE MODE** AND the control file `<work>/.first_run_stage_by_stage` exists, run **only the single stage named in the directive** instead of the full pipeline. Set by `canvas-bootstrap` §8 during first-run calibration so the student can review each stage's output before the next runs.

Behavior:
1. Read `<work>/.first_run_stage_by_stage` to confirm. If absent, run the full Framework pattern (steps 1-8) as usual.
2. Parse the directive for the stage name (`classify`, `parse-table-or-pdf`, `fetch-exercises`, `solve`, `render-pdf`, `verify`, `self-audit`).
3. Run **only** that stage's substeps. Prior stages' artifacts must already be in `<work>/`.
4. Write a 1-3 sentence English summary to `<work>/stages/{stage_name}.done` and STOP.

Daily dispatch via canvas-execute does not set the marker; runs full-pipeline as usual.

## Stage-by-stage time bands

| Stage | Band | One-line description |
|---|---|---|
| 1 classify | short | Decide written-HW / take-home-exam / reading-completion |
| 2 parse-table-or-pdf | short | Parse Canvas description HTML table OR attached PDF for exercise refs |
| 3 fetch-exercises | short | Call zyBook API with JWT to fetch matching section exercises |
| 4 solve | long | LLM judgment per problem applying overlay's notation rules |
| 5 render-pdf | medium | LaTeX/MathJax render to typed PDF with `[answer needed]` placeholders filled |
| 6 verify | short | Subquestion count + no placeholder leaks |
| 7 self-audit | medium | Mandatory final pass; catches notation-drift / missing-subquestion / spec-violation |

Band: `short` ~1 min, `medium` ~3-5 min, `long` ~10+ min. zybooks does NOT submit (GradeScope upload is manual).
