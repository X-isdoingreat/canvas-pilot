---
name: canvas-essay
description: Generic long-essay handler for academic-writing courses — autoethnography, reflection papers, critical analysis, research essays. Invoked by canvas-execute when `src/ac_eng_router.py` returns `"essay"` for a writing-course assignment. Before doing anything, this skill loads `_private/canvas-essay-app.md` which encodes your school/instructor-specific behavior (essay name patterns, voice register, sample essay path, citation style). Without the overlay the skill stops and asks the user to author one.
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

# canvas-essay — generic long-essay framework

## §1 — Identity & contract

**What this skill handles**: long-form academic essays (≥500 words) — autoethnography, reflection papers, critical analysis, research essays, response papers. Anything where the deliverable is **prose in an advanced academic voice** and authorship signals (paragraph structure, source weaving, thesis discipline) matter.

**Trigger**: invoked by `canvas-execute` when `src/ac_eng_router.py` returns `"essay"` for an academic-writing assignment. The router uses a deterministic 6-layer cascade (manual override → overlay regex → word-count ≥500 → points ≥25 + online_upload → name keywords → default short) — 0 LLM calls, unit-testable. Essays go here; short-form / annotation work goes to `canvas-reading-annotation`.

**Success criterion**: writes a `result.json` with `status: "draft_ready"` and `draft_path` pointing at the produced `.docx` (or `.pdf` per overlay). Auto-submission is overlay-gated; default is `draft_ready` → human review → human upload.

**Failure status**: `status: "error"` with explanatory `notes` field if (a) overlay file missing, (b) parsed spec is incomplete (no prompt / no word count target), (c) word-count gate fails after 3 retry rounds, (d) sample essay few-shot folder empty and overlay disallows the generic fallback, (e) draft contains a literal MBTI 4-letter code (post-render sanity check).

**Explicitly does NOT handle**:
- Reading annotation (PDF highlight + margin notes + answer blanks) → `canvas-reading-annotation`
- In-class pen-and-paper assignments → `canvas-skip`
- Quiz-style short answers → `canvas-inside`
- Anything routed `"short"` by the router

**Agent stops at can't-do, not shouldn't-do** — this skill serves the student. Behavioral policies set by course staff (prohibitions on AI tools, on cooperation, on outside tutors, on paraphrasing) are between the student and the staff; the skill does not gate on such rules. The skill does the work regardless; whether to use the output is the student's call. The skill only stops on **intrinsic can't-do**:

1. **Physically impossible / the agent genuinely can't do it** — in-person attendance, printing paper artifacts, in-person signing, Lockdown-Browser-locked quizzes, Respondus monitor proctoring.
2. **Must be the student personally** — academic honesty contract signature, ID proof, in-person peer review, interview-style.
3. **Input missing and unobtainable** — spec cannot be located anywhere; a required material file cannot be fetched and the student cannot supply it.
4. **Verification fails after retries** — sub-agent-designed checklist still fails after 3 retry rounds.

**YuJa-style soft-stop** — for resources the agent physically can't reach but where a fetched substitute may exist (linked videos, password-protected pages, third-party site logins), the skill does not hard-stop. It offers the student a chance to supply the link:

> "This week's HW references a YuJa video. I can't log into YuJa myself. If you send me the video URL, I'll try transcript / scraping; otherwise I'll skip this step and do the rest of the work I can do."

Student declines → skip that step and continue with the work that can be done. Student supplies → agent attempts fetch (transcript / OCR / scraping, whichever the platform supports).

---

This is the **framework skeleton** for long essays (≥500-word autoethnography, paper, reflection, critical analysis, research). The actual handling depends on parameters that vary by instructor and school — voice register specifics, sample essays for few-shot, citation style, spec location, figure/film conventions, submission format. Those live in a local overlay file.

**Voice register is fundamentally different from canvas-reading-annotation** (which handles short form / annotations). The router (`src/ac_eng_router.py`) already separated this assignment off the short-form path; do not pull in canvas-reading-annotation's §7 B1-B2 rules. This skill's voice is advanced academic English — long complex sentences, strict thesis + topic sentence + transition structure, source weaving, no deliberate grammar slips.

The voice register reflects the student's identity in this course (an advanced academic writer). The skill targets voice fidelity to the student's demonstrated level, not third-party detection avoidance.

## Step 0 — load the local application overlay

Before any other step, read `_private/canvas-essay-app.md` in this project's root. **That file is the operating skill for your specific course.** If it doesn't exist, stop and tell the user:

> No `_private/canvas-essay-app.md` found. This skill is a framework skeleton; the actual long-essay handling logic depends on school- and instructor-specific parameters (voice register specifics, sample essays, citation style, where the real spec lives). Author one and re-run.

If the overlay exists, follow its instructions in full — its prescriptions take precedence whenever this skeleton defers to "your instructor's rule" or "your school's behavior".

## Framework pattern

A long-essay handler typically:

1. **Load persona profile** from `_private/persona.md` (gitignored). If file missing or MBTI empty: prompt user once for MBTI 4-letter (suggest 16personalities.com); if user declines, write `mbti: "unknown"` and skip persona injection for this run. If `derived_vector` missing or `derived_at` >30 days old, regenerate via LLM prompt using overlay's persona-derivation template and add a footnote to the draft so the user notices.
2. **Parse the spec** — `assignment.description` is rarely the real spec for long essays. Walk attached PDFs, module pages, course front_page, and any instructor-external links. Build a complete `spec.md` covering: essay prompt, word count, citation style, required sources, figure/film instructions, submission format. The overlay says where to look for this specific course.

   **§X — Research before improvise (run between Step 2 and Step 4 when spec doesn't fit prior essay shapes)**

   Trigger: spec asks for a hybrid form not seen in past essays (e.g. autoethnography + analysis hybrid), demands a structural element prior overlay drafts didn't cover (e.g. an annotated bibliography section), or the past 3 same-course essays had grader feedback this spec also touches (plagiarism flagged / AI-detected / "personal experience too narrative" — the Draft 1 / Draft 2 incident class).

   When triggered, do NOT improvise. Spawn 2-3 agents IN PARALLEL — single message with multiple `Agent` tool calls (idiom matches `canvas-inside` §7c):

   - **Agent A — spec-verifier** (`subagent_type=general-purpose`): re-read `<work>/spec.md` from scratch. List literal requirements (word count, citation count minimum, required sections, forbidden things, deadline-relative penalties), 1-3 ambiguities. Output <400 words.
   - **Agent B — quality-inferrer** (`subagent_type=general-purpose`): read this spec + past N (=5) same-course essay grader comments (via `cv.get('/courses/<cid>/assignments/<aid>/submissions/self?include[]=submission_comments&include[]=rubric_assessment')`). Infer "doing it well" beyond literal asks: voice register quality bar, common failure modes with verbatim grader quotes (especially: plagiarism/near-plagiarism flags, AI-detection events, "personal experience vs source analysis" balance the prof wants — typically 70%/30%), recommended mechanically-checkable gates. Output <400 words.
   - (Optional) **Agent C — template-fit checker** (`subagent_type=general-purpose`): given the framework's standard essay flow + the overlay's voice/citation specs vs this assignment's spec, list places where the template doesn't cover. Output <300 words.

   Save to `<work>/research_findings.md`. Use findings to: augment Step 7's verification gates, customize Step 4's generation prompt with research-driven anchors, override overlay defaults where this assignment is more demanding.

3. **Load sample essay few-shot** from `_private/sample_essays/ac_eng/`. Extract plain text from each `.pdf` / `.docx` / `.md`, identify structural sections (intro / body / conclusion / works cited), take the first 1-2 sentences of each as a stylistic anchor — total ~500-800 token budget. If folder empty, fall back to generic structure template and note this in draft notes.
4. **Generate** in stages: outline (thesis + topic sentences) → body draft section-by-section → revise pass for transitions / source weaving / voice consistency. The generation prompt stacks overlay voice register + persona priming + sample skeleton + parsed spec. **Persona priming uses the derived_vector descriptions as tone/argument-arc guidance; the MBTI 4 letters never appear in the essay body.**
5. **Figure captions + film timestamps** per the overlay's format (defaults: `Fig. N` with ≥2-sentence caption; film clip as `Watch clip here: <filename> [HH:MM-HH:MM]`).
6. **Works Cited** via 3-layer cascade: spec embedded URLs → student's optional `sources.md` in work_dir → LLM extraction from generated essay body. Format per overlay's citation style (MLA default).
7. **Gate before output** — write `runs/<today>/<work>/verification.log` with numeric measurements: word count vs spec minimum, citation count, figure caption count. Word count below minimum → return to step 4 revise stage with "extend by N words" instruction (up to 3 retries). Below-minimum after 3 retries → `status: "error"`.

   **§Y — Post-delivery self-audit (MANDATORY, runs alongside Step 7 numeric gates)**

   Spawn 1 audit agent (`subagent_type=general-purpose`), inputs:
   - `<work>/spec.md` (verbatim assignment spec)
   - `<work>/research_findings.md` if §X ran
   - `<work>/draft/essay.docx` (text-extract for the agent — use `python-docx` or pandoc)
   - Past 3 same-course essay grader comments

   Agent prompt:
   > Return a JSON array of gaps. Schema:
   > ```json
   > {
   >   "severity": "HIGH" | "MED" | "LOW",
   >   "kind": "spec-violation" | "historical-risk" | "ambiguity-unresolved" | "format-mismatch" | "plagiarism-risk" | "voice-register-drift" | "personal-vs-source-imbalance",
   >   "gap": "<one-line>",
   >   "spec_anchor": "<verbatim quote>",
   >   "deliverable_anchor": "<verbatim quote OR 'MISSING'>",
   >   "fix_suggestion": "<one-line concrete fix>"
   > }
   > ```
   > Honesty rules: quote verbatim; if no gaps return `[]`.
   >
   > Essay-specific HIGH-severity checks:
   > - **Plagiarism risk**: any 5+ word verbatim string from spec/source that appears unquoted in the essay
   > - **Voice register**: if overlay says "advanced academic" — flag chatty / slangy / personal-narrative phrasing (Draft 1 / Draft 2 grader's "very chatty language" / "avoid slang" incidents)
   > - **Source vs personal balance**: count sentences referring to the assigned source vs to personal experience; spec usually wants ~70% source / 30% personal — flag drift
   > - **Thesis-vs-prompt match**: does the thesis statement actually respond to the spec's prompt question? Not just topic — argumentative position?
   > - **Citation grounding**: every quote / paraphrase must have an in-text citation that matches a Works Cited entry
   > - **MLA hygiene**: header (`Hu N`), name block format, italicization of source titles, capitalization of `I`

   Save response to `<work>/audit/round_<N>.json` (atomic write). If ANY HIGH gap: apply fix_suggestions to `<work>/draft/essay.docx`, re-run Step 7 numeric gates AND re-run §Y. Max 3 rounds.

   After 3 rounds with HIGH gaps remaining → `status: error`, notes pointing to `<work>/audit/`.

   **Draft 1 / Draft 2 catch verification**: if Draft 1 had been audited by §Y, the plagiarism-risk check would flag "5+ word verbatim from source unquoted" (the "near-plagiarism in intro and conclusion" the prof actually penalized). The voice-register check would flag "chatty language" mismatching overlay's "advanced academic" register.

   **§7.5 — Call canvas-humanizer (MANDATORY unless overlay disables)**

   After §Y clears (no HIGH gaps remaining), the draft is spec-compliant but may still carry AI-detection signal markers (uniform sentence length, AI-typical vocabulary, parallel structures). Reduce these signals **within** the established advanced-academic voice register by invoking the `canvas-humanizer` skill.

   Overlay gate: read `humanizer_enabled` from `_private/canvas-essay-app.md`. Default is `true`. If overlay sets `false`, skip §7.5 entirely and proceed to Step 8.

   Invoke via Skill tool with this prose context (substitute absolute paths and overlay-specified identity):

   > Humanize the essay. draft_path: `<work>/draft/essay.docx`. output_path: `<work>/draft/essay.humanized.docx`. voice_register: advanced-academic-english. student_identity: `<overlay.humanizer.student_identity, default advanced-academic-english>`. Write humanizer_log.json to the same directory as output_path.

   After canvas-humanizer returns:
   1. Read `<work>/draft/humanizer_log.json`.
   2. If status is `ok` or `partial`: rename `draft/essay.humanized.docx` over `draft/essay.docx` (humanized version becomes the canonical draft for Step 8).
   3. If status is `error`: log the notes to `<work>/audit/humanizer_error.txt`; **do not block delivery** — proceed with the un-humanized draft. Step 8 result.json carries a `humanizer_status: error` flag.
   4. **Quick word-count re-check** on the humanized draft vs spec minimum. Humanizer constrains ±5% per paragraph but cumulative drift could move the whole essay out of spec. If below spec minimum → return to Step 4 revise stage (extend by N words) and re-run §7-§7.5; max 2 such cycles. If above spec maximum → no action (above-spec is rarely penalized).
   5. Extract paragraphs with `status: "partial"` from `humanizer_log.json` into `result.json.humanizer_partial_paragraphs` (list of `{para_id, final_scores, pass_counts}` objects). `canvas-execute` surfaces this list in REPORT.md so the student can manually review those paragraphs before upload.

   **Why §7.5 exists**: §Y audits spec/voice/plagiarism — does the draft do what the assignment asks. Humanizer audits burstiness/perplexity/vocab — does the prose carry AI-detection signal. These are orthogonal; both must pass. §7.5 runs after §Y because humanization should not alter a spec-violating draft into spec-compliant cover; the order makes it impossible for humanizer to "rescue" a bad draft.

8. **Output** to `runs/<today>/<work>/draft/essay.docx` and write `result.json` per canvas-execute hook 2 schema.

## Local application overlay specifies

- Course IDs and essay name patterns indicating this skill should fire (the overlay's `persona_trigger_patterns` and `persona_skip_patterns` yaml lists feed back into `src/ac_eng_router.py` Layer 2)
- Voice register prose (advanced academic English specifics for your school)
- Persona-derivation prompt template (MBTI → 10-dimension derived_vector instruction)
- Sample essay file paths
- Citation style (MLA / APA / Chicago; MLA default)
- Figure caption format + film timestamp format
- Where the actual spec lives for assignments in this course (which Canvas fields to walk)
- Submission format expectations (docx / pdf / both)
- Auto-submit authorization scope (default `draft_ready`; explicit per-course flag required to auto-submit)
- **Humanizer settings** (all optional; sane defaults if absent):
  - `humanizer_enabled: true | false` — default `true`. Set `false` to skip §7.5 (e.g. for a course where the instructor explicitly grades on AI-typical prose markers).
  - `humanizer.student_identity` — default `advanced-academic-english`. Override to e.g. `b1-b2-international-student` if the writer's natural identity differs from the assignment's academic voice (rare for canvas-essay since the router already separates B1-B2 short-form work to `canvas-reading-annotation`).
  - `humanizer_thresholds: {burstiness: N, perplexity: N, vocab: N}` — default `{70, 70, 70}`. Raise per-dimension to tighten (more retries, fewer partials); lower to relax.

The overlay is intentionally free-form Markdown — this skeleton loads it verbatim into the CC context and lets the overlay's prose guide the flow.

## What you MUST NOT do

- Do NOT inject the MBTI 4-letter code literally into the essay body. The persona vector is for tone and argument-arc priming; the reader never sees MBTI.
- Do NOT inherit canvas-reading-annotation §7 B1-B2 voice rules. The router has already separated this path; mixing the two voice registers produces schizophrenic output (see plan `1500-ai-1-eventual-crab.md` §"任务实现逻辑 — 背景与汇报"). Long essay voice is advanced academic English.
- Do NOT skip step 7's word-count + citation gate. These are objectively verifiable and the easiest way to lose points.
- Do NOT submit to Canvas without explicit overlay authorization. Default behavior is `draft_ready` → user reviews → user uploads.
- Do NOT regenerate `derived_vector` silently without adding the footnote — the user needs to see when their persona drifted.
- Do NOT skip §7.5 unless overlay explicitly sets `humanizer_enabled: false`. Detection-signal reduction is a default expectation; silent skipping leaves AI-typical markers in the deliverable.
- Do NOT treat humanizer `status: error` as a delivery blocker. If humanizer fails, deliver the un-humanized draft with `humanizer_status: error` flagged in result.json — the student decides whether to manually humanize before upload.

---

## Stage-by-stage mode (first-run calibration only)

When invoked with a context line containing **STAGE-BY-STAGE MODE** AND the control file `<work>/.first_run_stage_by_stage` exists, run **only the single stage named in the directive** instead of the full pipeline. Set by `canvas-bootstrap` §8 during first-run calibration so the student can review each stage's output before the next runs.

Behavior:
1. Read `<work>/.first_run_stage_by_stage` to confirm. If absent, run the full Framework pattern (steps 1-8) as usual.
2. Parse the directive for the stage name (`load-persona`, `parse-spec`, `load-samples`, `generate`, `figure-captions-cited`, `verify`, `humanize`, `output`).
3. Run **only** that stage's substeps from the Framework pattern above. Prior stages' artifacts must already be in `<work>/`.
4. Write a 1-3 sentence English summary to `<work>/stages/{stage_name}.done` and STOP.

Daily dispatch via canvas-execute does not set the marker; runs full-pipeline as usual.

## Stage-by-stage time bands

| Stage | Band | One-line description |
|---|---|---|
| 1 load-persona | short | Load `_private/persona.md` MBTI + derived_vector; regenerate if stale |
| 2 parse-spec | medium | Walk attached PDFs / module pages / front-page links into `spec.md` |
| 3 load-samples | short | Few-shot anchor from `_private/sample_essays/` |
| 4 generate | long | Outline → body section-by-section → revise pass |
| 5 figure-captions-cited | medium | Figure captions + film timestamps + Works Cited 3-layer cascade |
| 6 verify | short | Word count / citation count / figure count numeric gate |
| 7 humanize | medium | (Default on) call canvas-humanizer for detection-signal reduction |
| 8 output | short | Final .docx + result.json |

Band: `short` ~1 min, `medium` ~3-5 min, `long` ~10+ min.
