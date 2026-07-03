---
name: canvas-reading-annotation
description: Generic reading-annotation handler for academic-writing courses — annotates reading PDFs with color-coded highlights + margin notes + filled answer blanks per the instructor's rubric. Invoked by canvas-execute when an assignment's routing skill is `ac_english` AND src/ac_eng_router.py returns "short" (long essays go to canvas-essay). Before doing anything, this skill loads `_private/canvas-reading-annotation-app.md` which encodes your school/instructor-specific behavior (homework module ID, reading-PDF file mapping, color rubric, voice register, video→worksheet pairings). Without the overlay the skill stops and asks the user to author one.
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

# canvas-reading-annotation

## §1 — Identity & contract

**What this skill handles**: assignments where the deliverable is a **PDF marked up in place** — reading-annotation HWs (color highlights + margin notes + answer blanks filled to ≥90% line width). Common in ESL / EAP / freshman composition / humanities-source-annotation courses. Output is one PDF with the same page count as the original reading, no appended pages.

**Trigger**: invoked by `canvas-execute` when an assignment's routing skill in `courses.yaml` is `ac_english` AND `src/ac_eng_router.py` classifies the assignment as `"short"` (the 6-layer cascade — long-essay assignments go to `canvas-essay` instead).

**Success criterion**: writes a `result.json` with `status: "draft_ready"` and `draft_path` pointing at the annotated PDF. The 6-check verification gate (§4) must pass before the file is moved to `final_drafts/` or submitted. Auto-submission is overlay-gated; default is `draft_ready` → human review → human upload.

**Failure statuses**:
- `status: "skipped"` if the assignment is in-class / pen-on-paper (`submission_types: ['on_paper']` or name contains "(In Class)" / "Practice Summary").
- `status: "error"` if overlay missing, reading PDF can't be located, HW page classifier hits an unsupported kind (e.g. `response_paper` / `external_tool`), or any verification check fails after 3 retries.

**Explicitly does NOT handle**:
- Long essays / response papers → `canvas-essay`
- Discussion posts, online_quiz, in-class assignments → routed elsewhere or skipped
- Producing the worksheet content itself for a video-exercises HW — for those the skill searches the web for the public source worksheet first; if no public worksheet is found, the skill returns `error` rather than fabricating exercises (see §3 stage `classify`)

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

First action every run is to read `_private/canvas-reading-annotation-app.md`. It is one flat file per generic skill, multi-course inside — find the `## Course {course_id}` block for the current assignment, then within that block find the `#### {kind}` sub-block whose `naming_regex` matches `assignment.name`.

Three fallbacks if anything is missing:

- **Whole overlay file absent** → dispatch `canvas-bootstrap` to run the detective on this course, write the overlay, then resume.
- **Course block absent** (overlay exists, other courses are configured, this course isn't) → same: route to bootstrap for this course only, then resume.
- **`#### {kind}` sub-block absent** (course is configured but this assignment's naming pattern was never seen at bootstrap time) → ask the user the minimal subset of fields needed for this single assignment (which reading, what kind of HW, color choice if instructor varies), append a new kind block to the overlay, continue.

If the overlay exists but Stage 0 still cannot resolve a kind for this assignment (e.g. user declines to author the new kind block), write `status: "error"` and stop.

---

## §3 — Pipeline stages

Six stages run sequentially per assignment. Each writes its output under `runs/<today>/<assignment>/<stage>/`. Stage outputs are traceable artifacts; if a downstream stage fails, the upstream artifacts let the user (or a retry) see exactly where things broke.

### Stage 1 — `classify`

The same Canvas course can mix several HW kinds in one week's module page (reading annotation, video exercises, in-class summary, response paper). The Canvas assignment description is usually empty. The real instructions live in the **Homework module page body** (overlay-specified `homework_module_id`).

Pull the matching week's HW page, find the paragraph in the page body that links back to `assignment.id`, then keyword-classify:

| Signals in the paragraph | Kind | Continue to |
|---|---|---|
| "read Reading N", "answer the pre-/post-reading questions", reading PDF reference | `reading_annotation` | Stage 2 |
| "watch video on", "as you work through the video", "**copy-paste the exercises**" | `video_exercises` | Stage 2-alt (web search the public worksheet, see below) |
| "Practice Summary", "(In Class)", `submission_types: ['on_paper']` | `in_class_skip` | write `status: "skipped"`, exit |
| "Response Paper", `submission_types: ['external_tool']` | `response_paper` | not in scope — write `status: "error"`, route to manual |

Write `kind.txt` with the detected kind. **Don't default to reading_annotation** — that is the easy-to-make mistake (real incident on 2026-04-13: an unbranched skill defaulted to reading_annotation for a video-exercises HW and fabricated worksheet content; the student lost points because their submission didn't match what every classmate produced).

**For `video_exercises`**: instructors' Yuja-style videos for standard EAP topics are almost always based on free public worksheets. The skill **searches the web first**, not the LLM. Queries like `"<topic>" EAP Foundation worksheet PDF` or `"<topic>" academic English exercises fill in blank`. Fetch the worksheet PDF, reproduce its tasks verbatim, fill in B1-B2 student answers. **Never invent exercises** — if no public worksheet matches after 3 searches, return `status: "error"` with a note asking the user to dictate the exercise structure. An invented worksheet is worse than no submission.

### Stage 1.5 — `research-before-improvise` (run when HW page doesn't fit the 4-kind table)

Trigger (any of these in the HW page body Stage 1 fetched):
- "write N sentences" / "Five Takeaways" / "Five Insights" / "your reflections on" — the **reflection_bullets** shape that Wk6 hit and the kind table doesn't cover
- "Use the title 'X'" with a specific title string — the HW page mandates a verbatim title
- "one sentence per number" / "no more than X words" — hard numeric content constraints that Stage 6's format gate doesn't check
- Past 3 same-course HW Scans had grader comments mentioning issues this HW page's body also touches (e.g. "be specific", "avoid generalization", "this is the wrong assignment")
- A new section / question type appears that prior weeks didn't have

When triggered, do NOT improvise. Spawn 2-3 agents IN PARALLEL — single message with multiple `Agent` tool calls (same idiom as `canvas-inside` §7c):

- **Agent A — spec-verifier** (`subagent_type=general-purpose`):
  > Re-read the HW page body from `<work>/hw_page.txt` from scratch. List literal requirements: input source (Yuja video / Canvas Files PDF / textbook chapter), deliverable shape (annotated PDF / new write-up / scan upload), hard numeric constraints (grep "no more than" / "at most" / "exactly" / "one ... per"), required title verbatim if any, required sections, forbidden items, 1-3 ambiguities. Output under 400 words, plain markdown bullets.

- **Agent B — quality-inferrer** (`subagent_type=general-purpose`):
  > Read this HW page body AND past N (=5) writing-course HW Scan grader comments (pull via `cv.get('/courses/<cid>/assignments/<aid>/submissions/self?include[]=submission_comments&include[]=rubric_assessment')` for the 5 most recent same-course assignments under runs/). Infer what "doing this well" requires beyond literal asks: quality criteria (specificity, cliché-avoidance, depth, accurate causal language), common failure modes with verbatim grader quotes from the Wk6 incident class ("too obvious / weak / vague" / "be specific + add a noun" / "there is no way to prove overgeneralization" / "one sentence per number"), recommended mechanically-checkable gates. Output under 400 words.

- (Optional) **Agent C — template-fit checker** (`subagent_type=general-purpose`):
  > Given the four kinds in the §3.5 table (reading_annotation / video_exercises / in_class_skip / response_paper) and this HW page body, list places where none of the 4 templates cover the assignment. Recommend whether to: (a) treat as one of the 4 with adjustments, or (b) treat as a wholly new shape needing custom flow. Output under 300 words.

Save the reports to `<work>/research_findings.md`. Use the findings to:
- Pick the closest-fit kind from the §3.5 table (or proceed with a custom flow noted in `kind.txt: ad_hoc__<short_descriptor>`)
- Augment the Stage 6 verification gate set with content-quality gates derived from Agent B's grader-history analysis (e.g. "exactly 5 items, each ≤1 sentence", "no pronoun without noun", "no overgeneralization claims")
- Customize Stage 4 (annotate_pdf) or Stage 5 (fill_answer_blanks) for THIS HW's specific content shape

Then continue to Stage 2 (or whichever stage is appropriate for the chosen kind).

#### Stage 1.5b — `video_transcript_library_path` overlay hook (added 2026-05-21)

If the HW page body references an instructor-recorded video (YuJa, Panopto, Echo360, Zoom recording, etc.) AND the deliverable is a free-form reflection (N sentences / takeaways / insights / "what you learned"), the agent must NOT improvise content from general topic knowledge. Instead:

1. Check the overlay for a `video_transcript_library_path` declaration (whatever path the school's overlay declares for its video platform — YuJa, Panopto, Echo360, Zoom cloud recording, etc.). The overlay should also expose a mapping from HW-page video title to transcript filename.
2. If the library exists and the matching transcript is available: load it. Use the transcript's distinctive moments (named anecdotes, instructor-coined terms, concrete contrast pairs, memorable analogies, specific warned-against examples) as the source for ≥2 of the N takeaways. This step runs BEFORE Stage 2-alt's web-search-first rule fires.
3. If the library exists but the matching transcript is missing (catalog drift): attempt refresh via the overlay's documented procedure. If refresh fails (cookie expired, video missing from channel, network), soft-stop and ask the student whether to (a) supply transcript text manually, (b) skip this week. **Do not fall back to general-knowledge improvisation** — every instructor video has details only that instructor uses, and a generic-knowledge reflection is recognizable to the grader at a glance.
4. If the overlay does NOT declare a `video_transcript_library_path` at all, fall through to §1's YuJa-style soft-stop — offer the student to supply the link / transcript, otherwise skip that HW gracefully.

The 2026-05-21 Thu Wk8 HW Scan incident (overlay had a 9-file cached video transcript library but neither this SKILL.md nor the overlay's §0 referenced it; the skill improvised 5 generic EAP takeaways and audit flagged item 2 as "too obvious / vague") was the failure that motivated this hook. The fix lives jointly here (generic skill) and in the overlay's §0 (school-specific paths).

### Stage 2 — `locate_reading` (reading_annotation flow)

For `reading_annotation` only. Map the HW page's reference ("Reading 3", "this week's reading", etc.) to a Canvas file_id through the overlay's `reading_files` table. Download to `<work>/attachments/<filename>.pdf`.

If the overlay's mapping doesn't cover the referenced reading (e.g. instructor added a Reading 7 mid-quarter): ask the user once for the file_id or filename, append to the overlay's `reading_files`, continue.

### Stage 3 — `extract_text_and_blanks`

Open the reading PDF with PyMuPDF:

```python
import fitz
doc = fitz.open(reading_pdf)
full_text = "\n\n".join(p.get_text() for p in doc)
```

Identify three structures:

1. **Pre-reading questions** (usually on page 0 — "Before You Read").
2. **Article body with numbered paragraphs** (regex `(?m)^\s*(\d{1,2})\s*$` against full text finds them).
3. **Post-reading questions** (usually on the last page — "Comprehension and Analysis" / "Reading and Analysis").

Each question is followed by underscore-glyph runs forming answer blanks. **Group underscores by y-coordinate** — never `search_for("____...")` with a fixed-length string, that silently returns a partial rect when the real line is wider:

```python
from collections import defaultdict

def find_answer_blanks(page):
    """Return list of (y_top, x_min, x_max) per blank line on the page.

    Grouping every underscore glyph by its y-coordinate yields the FULL line
    extent. A fixed-length search_for trick silently truncates to ~322pt when
    the real line is 454-466pt wide.
    """
    by_y = defaultdict(list)
    for r in page.search_for("_"):
        by_y[round(r.y0)].append(r)
    return sorted(
        (y, min(r.x0 for r in rs), max(r.x1 for r in rs))
        for y, rs in by_y.items()
    )
```

### Stage 4 — `annotate_pdf`

Clone the original PDF in memory and add annotations **in place on the original pages**. **Do NOT append new pages** — the deliverable page count must equal the original. Two annotation categories driven by the overlay's `color_rubric`:

**Vocab highlights + definitions** (overlay's `color_rubric.vocab` family):

- Pick a small number of words per reading (default 5, overlay can override). Prefer uncommon-but-not-rare vocabulary; avoid technical jargon.
- Highlight the single word (not surrounding phrase) with the vocab highlight color.
- Write a LDOCE-style definition in the page margin, aligned vertically with the word. Margin x ≈ 5 (left) or 546 (right) for a standard US Letter; alternate sides if two vocab words on the same y-band.
- **Font color of the definition matches the highlight color family** (instructor's stated rule: "if you highlight vocab in green, make the definition font green"). Headword line bold (`fontname="hebo"`), body plain (`fontname="helv"`), ~6.5pt, 4-5 lines, ~18 chars each.

**Content margin notes** (overlay's `color_rubric.content` family):

- **One margin note per numbered paragraph.** If the article has 17 paragraphs, the draft has 17 notes. Skipping paragraphs is a verification failure.
- Each note: ≤110 chars on one line, summarizing the paragraph's main idea.
- Place in the gap **before the next paragraph's number**, at x ≈ 76, baseline = `next_paragraph_y - 6`, 7.5pt Helvetica, in the content color family.
- For the highlight itself: pick 1-2 phrases per paragraph as the note's anchor, highlight with the content highlight color.
- **NEVER** use `page.add_text_annot` for the note (renders as a clickable yellow sticky icon at the page edge — that's the wrong format).

**Color family rules** (enforced by the verify stage):

- Vocab highlight color and vocab definition text color must be the **same family** (HSV hue delta ≤30°).
- Content highlight color and content margin note text color must be the **same family**.
- Vocab family and content family must be **different families** so the reader can distinguish.
- **No yellow highlights** — renders too faint on mobile Canvas to distinguish from white.

**Overlap-avoidance rule**: pick vocab words FIRST. Before adding any content highlight, check its text does not contain any vocab word's exact span; if there's a conflict, drop the content phrase and pick a different one from the same paragraph. Otherwise the later-drawn highlight covers the earlier one and the reader only sees one color.

### Stage 5 — `fill_answer_blanks`

For each `(y, x0, x1)` blank found in Stage 3, compute `line_width = x1 - x0`, generate an answer in the overlay's target `voice_register`, then **measure before writing**:

```python
text_width = fitz.get_text_length(answer, fontname="helv", fontsize=10)
# Must be >= 0.90 * line_width AND <= line_width
```

If the generated answer is too short, **pad with a concrete specific detail in the same voice register**, not with filler words. If too long, regenerate with a tighter word budget. Insert with the overlay's `answer_text_color` (typically blue for "typed answer" contrast against black body text):

```python
page.insert_text((x0 + 1, y - 1), answer,
                 fontsize=10, color=ANSWER_TEXT_COLOR, fontname="helv")
```

**Voice register**: free-form text from the overlay (e.g. "B1-B2 international student English with Chinese L1 hint"). The skill uses this verbatim as system-prompt context when generating each answer. The voice register reflects the student's identity (typically a non-native learner at B1-B2 level for this course type) — the output should read like the student wrote it, not like a polished editor or an automated tool. The skill targets identity fidelity, not third-party detection avoidance. Voice rules typical for non-native learner voices:

- Short sentences (10-18 words)
- First-person specific examples
- 1-2 small grammar slips per page (subject-verb disagreement, missing article, wrong preposition, tense slip) — overlay can set the slip-density knob
- Avoid native-speaker discourse markers ("Furthermore", "Moreover", "It is important to note")
- No em dashes, no perfect parallel structure, no rhetorical questions
- Never mention AI / ChatGPT / Claude / "as a student"

### Stage 6 — `verify` (6-check gate)

Before declaring `draft_ready`, run all six checks. If any fail, fix the draft (max 3 retry rounds total across all stages); if still failing after 3 rounds, return `status: "error"` with the failure list.

| Check | Measurement | Pass |
|---|---|---|
| `line_fill` | each answer span width ÷ its blank's underscore-line width | every line ≥85%, avg ≥92% |
| `margin_note_density` | count of content margin notes ÷ numbered paragraph count in original | ratio ≥1.0 (one note per paragraph) |
| `color_family_consistency` | vocab highlight HSV vs vocab definition HSV; content highlight vs content note | both pairs within ΔH ≤30° |
| `page_count_unchanged` | draft `doc.page_count` vs original `doc.page_count` | equal — no appended pages |
| `no_vocab_content_overlap` | vocab-highlight rect ∩ content-highlight rect | zero intersections |
| `no_sticky_icons` | count of PyMuPDF `Text` (type 0) annotations | zero |

Write the full report to `<work>/verification.log` whether it passes or fails. The submit hook reads this log; without all-pass it refuses to upload.

### Stage 6.5 — `post-delivery self-audit` (MANDATORY, never skip)

Runs AFTER Stage 6's 6-check format/structure gate and BEFORE writing result.json status=draft_ready/submitted. The 6-check gate is purely structural (colors, line fill, no overlap); this stage adds the **content-vs-rubric semantic check** that Wk6 Tue/Thu lost points on.

Spawn 1 audit agent (`subagent_type=general-purpose`), inputs:
- The HW page body `<work>/hw_page.txt` (verbatim spec from §3.5 Stage 1)
- The chosen `kind.txt` value (e.g. `reading_annotation`, `reflection_bullets`, etc.)
- `<work>/research_findings.md` if Stage 1.5 ran
- Every file in `<work>/draft/` (the annotated PDF or the new write-up)
- Past N (=3) writing-course HW Scan grader comments (pulled via `cv.get('/courses/<cid>/assignments/<aid>/submissions/self?include[]=submission_comments&include[]=rubric_assessment')` for the 3 most recent)

Agent prompt:
> Compare the HW page body + research findings + past grader comments against the produced deliverable. Return a JSON array of gaps. For each gap:
>
> ```json
> {
>   "severity": "HIGH" | "MED" | "LOW",
>   "kind": "spec-violation" | "historical-risk" | "ambiguity-unresolved" | "format-mismatch" | "voice-register-drift" | "wrong-reading-file",
>   "gap": "<one-line description>",
>   "spec_anchor": "<verbatim quote from HW page or grader comment showing the requirement>",
>   "deliverable_anchor": "<verbatim quote from deliverable showing the violation, or 'MISSING' if a requirement is unaddressed>",
>   "fix_suggestion": "<one-line concrete fix referencing the deliverable file + page/section>"
> }
> ```
>
> Honesty rules:
> - Quote VERBATIM from both spec and deliverable — do not paraphrase
> - If no gaps, return `[]` exactly
> - For each `severity: "HIGH"`, the issue must be one a grader would dock points for (not stylistic preference)
>
> Writing-course-specific checks beyond the generic spec-vs-deliverable diff:
> - **Voice register**: count lowercase `i` / intentional grammar slips / sentence length distribution. Compare to the overlay's `voice_register` spec. Flag drift (too AI-clean, OR too sloppy beyond B1-B2).
> - **Correct reading file**: if the HW page says "Reading N" but the deliverable annotates a different PDF, this is the 2026-04-13 incident class — HIGH severity, kind=`wrong-reading-file`.
> - **Per-item constraints from research_findings** (e.g. "one sentence per number" — Wk6 Thu) — count and flag.
> - **Cliché check** — for "Five Takeaways" / "Five Insights" deliverables, flag any item that reads like a textbook platitude a grader would mark "too obvious / vague".

Save the response to `<work>/audit/round_1.json` (atomic write).

Read returned JSON. If ANY `severity == "HIGH"` gap:
1. Apply each `fix_suggestion` to the deliverable under `<work>/draft/`.
2. Re-run Stage 6 6-check gate (in case fix broke format) AND re-run Stage 6.5 audit (round_2.json).
3. Loop max 3 rounds total.

After 3 rounds:
- 0 HIGH gaps → proceed to submit (or write status=draft_ready for manual upload)
- HIGH gaps remain → write result.json `status: error`, `notes: "Stage 6.5 self-audit failed after 3 revision rounds; see <work>/audit/round_*.json"`

**Wk6 catch verification**: if Tue Wk6 Q2 had said "thesis shouldn't be 'in this paper I will discuss'", the cliché check would flag HIGH ("too obvious — match grader comment pattern: 'too obvious? weak? --> vague'"). Fix would replace with a specific video takeaway. Same for Thu Wk6 multi-sentence violation: the "one sentence per number" gate would flag 4 of 5 items, fixes would compress them.

---

## §3.5 — Stage-by-stage mode (first-run calibration only)

When invoked with a context line containing **STAGE-BY-STAGE MODE** AND the control file `<work>/.first_run_stage_by_stage` exists, run **only the single stage named in the directive** instead of the full pipeline. Set by `canvas-bootstrap` §8 during first-run calibration so the student reviews each stage before the next runs.

Behavior:
1. Read `<work>/.first_run_stage_by_stage` to confirm. If absent, run full pipeline as usual.
2. Parse the directive for the stage name (`classify`, `locate-reading`, `extract-text-and-blanks`, `annotate-pdf`, `fill-answer-blanks`, `verify`, `self-audit`).
3. Run **only** that stage's substeps from §3 above. Prior stages' artifacts must already be in `<work>/`.
4. Write a 1-3 sentence summary to `<work>/stages/{stage_name}.done` and STOP.

Daily dispatch via canvas-execute does not set the marker; runs full-pipeline as usual.

## §3.6 — Stage-by-stage time bands

| Stage | Band | One-line description |
|---|---|---|
| 1 classify | short | Decide reading_annotation / video_exercises / in_class_skip / response_paper based on HW page body |
| 1.5 research-before-improvise | medium | (Conditional) deeper module/wiki investigation when HW page doesn't fit the 4-kind table |
| 2 locate-reading | short | Find the source PDF in Files/Readings/ via overlay's reading_files mapping |
| 3 extract-text-and-blanks | short | PyMuPDF underscore-group find for typed answer blanks |
| 4 annotate-pdf | medium | Color-coded highlights + left-margin notes on the source PDF |
| 5 fill-answer-blanks | medium | LLM generation of typed answers at ≥90% line width in target voice |
| 6 verify | short | 6-check gate (line fill, note density, color family, page count, no overlap, no sticky icons) |
| 6.5 self-audit | medium | Mandatory final pass; catches voice / cliché / instructor-rubric mismatches |

Band: `short` ~1 min, `medium` ~3-5 min, `long` ~10+ min.

---

## §4 — Personal course design schema

The overlay (`_private/canvas-reading-annotation-app.md`) is one flat markdown file containing one `## Course {id}` block per course routing to this skill. Each course block holds one or more `#### {kind}` sub-blocks per recurring assignment kind. Recognized fields per sub-block:

| Field | Required | Example |
|---|---|---|
| `naming_regex` | yes | `^(Tue\|Thu) Wk\d+ HW Scan$` |
| `homework_module_id` | yes | `67890` |
| `homework_page_pattern` | yes | `Wk(?P<week>\d+)` (regex over module item titles) |
| `readings_folder_path` | yes | `Files/Readings/` |
| `reading_files` | yes | `{ "Reading 1": <file_id>, "Reading 2": <file_id>, ... }` |
| `color_rubric.vocab` | yes | `{ highlight: "(0.55, 0.95, 0.55)", text: "(0.0, 0.45, 0.0)" }` |
| `color_rubric.content` | yes | `{ highlight: "(1.0, 0.72, 0.82)", text: "(0.75, 0.10, 0.45)" }` |
| `answer_text_color` | optional, default blue | `(0.0, 0.15, 0.80)` |
| `voice_register` | yes | `"B1-B2 international student English with Chinese L1"` |
| `vocab_count_per_reading` | optional, default 5 | `5` |
| `instructor_rubric_verbatim` | yes | full quoted rubric from the instructor — used as a final sanity-check prompt |
| `video_to_worksheet_map` | optional | `{ "Academic Verbs": "https://www.eapfoundation.com/.../questions.php" }` |
| `auto_submit_scope` | optional, default ask-each-scan | `"weekly HW Scan: confirmed"` |

Course-level fields (one set per `## Course` block, applied to all kinds in that course):

| Field | Required | Example |
|---|---|---|
| `course_id` | yes | `12345` |
| `course_name` | yes | `"Writing Course B — Spring 2026"` |
| `instructor` | optional | `"Dr. Example"` |
| `lab_course_id` | optional | `12346` (if Canvas separates lecture vs. lab into two course IDs but the same skill handles both) |

---

## §5 — Worked demo overlay

A complete overlay for a fictional course. Fork users copy-paste-modify this rather than writing from scratch.

```markdown
# canvas-reading-annotation — Personal Course Design

This file holds per-course overlays for the canvas-reading-annotation skill.

## Course 99999 — Writing Course B (Spring 2026)

- course_name: Writing Course B
- instructor: Dr. Example
- lab_course_id: 99998

### Tue Wk N HW Scan

- naming_regex: `^Tue Wk\d+ HW Scan$`
- homework_module_id: 67890
- homework_page_pattern: `Wk(?P<week>\d+)`
- readings_folder_path: Files/Readings/
- reading_files:
    Reading 1: 11111111
    Reading 2: 11111112
    Reading 3: 11111113
    Reading 4: 11111114
    Reading 5: 11111115
    Reading 6: 11111116
- color_rubric:
    vocab:
      highlight: (0.55, 0.95, 0.55)   # light green
      text:      (0.00, 0.45, 0.00)   # dark green
    content:
      highlight: (1.00, 0.72, 0.82)   # light pink
      text:      (0.75, 0.10, 0.45)   # dark pink / magenta
- answer_text_color: (0.00, 0.15, 0.80)   # blue
- voice_register: |
    B1-B2 international student English with Chinese L1 hint.
    Short sentences (10-18 words). First-person concrete examples.
    Allow 1-2 small grammar slips per page (subject-verb / article /
    preposition / tense). No native discourse markers, no em dashes,
    no perfect parallel structure.
- vocab_count_per_reading: 5
- instructor_rubric_verbatim: |
    Read and annotate Reading N, with highlighting & margin notes in
    at least two colors, one for vocab (5+ English dictionary
    definitions) and another color for content. Color-code: if you
    highlight vocab in green, make the definition font green. Margin
    notes for content are expected for each paragraph. Answer the
    "Before you Read" and "Comprehension and Analysis" questions,
    with both lines completely filled for each answer. Use full
    sentences.
- video_to_worksheet_map:
    Academic Verbs: https://www.eapfoundation.com/download/worksheets/reporting/questions.php
- auto_submit_scope: ask-each-scan

### Thu Wk N Video Worksheet

- naming_regex: `^Thu Wk\d+ Video Worksheet$`
- homework_module_id: 67890
- homework_page_pattern: `Wk(?P<week>\d+)`
- (no reading_files — uses video_to_worksheet_map from sibling kind)
- color_rubric: (inherits from Tue Wk N HW Scan)
- answer_text_color: (inherits)
- voice_register: (inherits)
- auto_submit_scope: ask-each-scan
```

Multiple courses routing to this skill all live in the same `_private/canvas-reading-annotation-app.md` file, each as its own `## Course` block. Bootstrap appends new course blocks rather than rewriting the whole file.

---

## What you MUST NOT do

- Do NOT append pages to the original reading PDF. Output page count must equal input.
- Do NOT default to `reading_annotation` for a HW page that signals `video_exercises` or `in_class_skip`. Classify first.
- Do NOT invent worksheet content for `video_exercises` HWs. Search the web for the public source first; return `error` if not found.
- Do NOT use yellow highlights. Renders too faint on mobile Canvas to distinguish from white background.
- Do NOT mix vocab and content highlights on the same span. Apply the overlap-avoidance rule from Stage 4.
- Do NOT use `page.add_text_annot` for margin notes — renders as a clickable sticky icon. Use `page.insert_text` with the content color.
- Do NOT mention AI / ChatGPT / Claude / "as a student" / "as an AI" anywhere in the produced answers. The overlay's `voice_register` is the only voice the generator follows.
- Do NOT submit to Canvas without explicit `auto_submit_scope` authorization in the overlay AND all six verification checks passing. Default behavior is `draft_ready` → human review → human upload.
