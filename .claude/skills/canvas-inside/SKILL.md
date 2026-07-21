---
name: canvas-inside
description: Canvas in-page answering handler — currently scoped to Classic Quizzes (`online_quiz`); see the SKILL's Scope note. Handles open quizzes (MCQ, multi-answer, T/F, matching, short-answer, fill-in-the-blank, multiple-dropdowns, numerical, essay) that the student has authorized for auto-take. The pipeline pre-builds study notes from the course's source readings, runs 4-agent arbitration on each question, then submits answers with deliberate human-ness layers (per-question log-normal timing, non-linear sequence with revisits, page_blurred/page_focused pairs, question_flagged events, optional strategic miss to land in a target percent band). The submission-pattern humanness is implemented as named Python helpers in `src/quiz_pacing.py`, `src/quiz_focus_events.py`, and `src/quiz_strategic_miss.py` — this SKILL.md calls those by name; it does not re-describe them. Three independent enforcement layers prevent bypassing the 4-agent arbitration. Invoked by canvas-execute when an assignment's routing skill is `quiz`. Before doing anything, this skill loads `_private/canvas-inside-app.md` which encodes school/instructor-specific behavior (course whitelist, instructor's framework primer, expected canonical knowledge, auto-take authorization, paced-submission defaults). Without the overlay the skill stops and asks the user to author one.
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - WebFetch
  - WebSearch
  - Skill
---

# canvas-inside

## §1 — Identity & contract

> **Scope (honest).** This is the "answer it directly inside Canvas" handler. **Currently implemented:** Canvas **Classic Quizzes** (`submission_types: ["online_quiz"]` with a `quiz_id`), including quizzes that mix MCQ / true-false / multiple-answer / matching with fill-in-the-blank types (short-answer, fill-in-multiple-blanks, multiple-dropdowns, numerical). **Not yet implemented** — the skill returns `skipped` with a clear note instead of faking them: **New Quizzes** (LTI `external_tool`, no `quiz_id`; Canvas exposes no student-submission API for these — would need browser automation) and **`online_text_entry`** assignments (typed answers in a box). The broad name reflects the intended scope; these gaps get built when a real case shows up.

**What this skill handles**: assignments whose deliverable is a sequence of answers submitted to a Canvas online quiz inside its time window. The quiz typically lives in a course module, references course readings (PDFs, lecture notes, syllabus), and is open for a fixed number of attempts. Question types covered: `multiple_choice_question`, `multiple_answers_question`, `true_false_question`, `matching_question`, `short_answer_question`, `fill_in_multiple_blanks_question`, `multiple_dropdowns_question`, `numerical_question`, `essay_question`.

**Trigger**: invoked by `canvas-execute` when an assignment's routing skill in `courses.yaml` is `quiz` AND the assignment has a non-null `quiz_id` AND the assignment's course is on the overlay's `whitelisted_course_ids` list.

**Success criterion**: writes a `result.json` with `kind: "quiz"`, `status: "submitted"` (or `"graded"` if Canvas has returned a grade), `agent_passes_count >= 4`, `kept_score / points_possible / attempts_used / allowed_attempts / scoring_policy` populated, and a `human_ness_diagnostics` block. The three enforcement layers (§2) all check different parts of this contract.

**Failure statuses**:
- `status: "skipped"` if the assignment is not a classic quiz (no `quiz_id`), is `locked_for_user`, is a 1-question video-lecture quiz that requires watching a video the skill can't watch, or the course is not on the whitelist.
- `status: "draft_ready"` if any safety gate fires (autorun off, outside human-hours window, per-cron rate limit hit) — study_notes.md is still produced so the student has the most valuable preparation work to review.
- `status: "error"` if overlay missing, readings cannot be located after 4-layer hunt, Canvas /complete API fails, or any enforcement layer fires after a serious bug.

**Three independent enforcement layers** (the price of getting a `submitted` status):

| Layer | Where | What it blocks |
|---|---|---|
| **Layer 1** | `src/canvas_client.py:_require_canonical_arbitration_evidence` | `complete_quiz_submission` and `answer_quiz_questions` raise `QuizArbitrationEvidenceMissing` unless the work_dir contains `final_answers.json` with `arbitration_notes.unanimous_count` AND `agent_passes/` with ≥4 distinct JSON files |
| **Layer 2** | `.claude/hooks/check-router-complete.py` Stop hook (retake gate) | A quiz `result.json` with `status=submitted, kept_score/points_possible < 0.95, attempts_used < allowed_attempts, scoring_policy=keep_highest` blocks session Stop. Must run §10 retake-with-feedback OR write `degraded_method_user_consent` (verbatim user quote ≥10 chars) |
| **Layer 3** | `.claude/hooks/_lib.py:_validate_quiz_submitted_schema` (called by check-result-schema) | A quiz `result.json` with `status=submitted` requires numeric `kept_score / points_possible / attempts_used / allowed_attempts / scoring_policy` AND (`agent_passes_count >= 4` OR `degraded_method_user_consent`) AND `human_ness_diagnostics.views_paired_with_answers == true` (the anti-bulk-emit invariant) |
| schema | `.claude/hooks/check-no-runner-script.py` PreToolUse(Write\|Edit) | Writing any `runs/**/_*.py`, `runs/**/run.py`, or `runs/**/run_*.py` is blocked at write-time — prevents one-off bypass scripts |

**The single legitimate path** to `status: submitted` is: §3-§7 (overlay → safety gates → classify → resolve quiz_id → readings → study_notes → 4-agent arbitration writing `final_answers.json` + `agent_passes/`) → §8 (paced submission with humanness) → §9 (complete) → §10 (retake if score < 0.95 and policy allows). The override (`CANVAS_QUIZ_DEGRADED_OK` env + `degraded_method_user_consent` field with verbatim user quote) is intentionally awkward and leaves an audit trail.

**Explicitly does NOT handle**:
- 1-question video-lecture micro-quizzes that require watching the video → `status: skipped` with a clear note
- Quiz from a course not on overlay's whitelist → `status: skipped`
- Take-home exams with PDF attachments → `canvas-zybooks` or manual
- In-class paper-and-pencil quizzes → not on Canvas

**Agent stops at can't-do, not shouldn't-do** — this skill serves the student. Behavioral policies set by course staff (prohibitions on AI tools, on cooperation, on outside tutors, on paraphrasing) are between the student and the staff; the skill does not gate on such rules. The skill does the work regardless; whether to use the output is the student's call. The skill only stops on **intrinsic can't-do**:

1. **Physically impossible / the agent genuinely can't do it** — in-person attendance, printing paper artifacts, in-person signing, Lockdown-Browser-locked quizzes, Respondus monitor proctoring.
2. **Must be the student personally** — academic honesty contract signature, ID proof, in-person peer review, interview-style.
3. **Input missing and unobtainable** — spec cannot be located anywhere; a required material file cannot be fetched and the student cannot supply it.
4. **Verification fails after retries** — sub-agent-designed checklist still fails after 3 retry rounds.

**YuJa-style soft-stop** — for resources the agent physically can't reach but where a fetched substitute may exist (linked videos, password-protected pages, third-party site logins), the skill does not hard-stop. It offers the student a chance to supply the link:

> "This week's HW references a YuJa video. I can't log into YuJa myself. If you send me the video URL, I'll try transcript / scraping; otherwise I'll skip this step and do the rest of the work I can do."

Student declines → skip that step and continue with the work that can be done. Student supplies → agent attempts fetch (transcript / OCR / scraping, whichever the platform supports).

---

## §2 — Stage 0: load overlay + safety gates

First action every run is to read `_private/canvas-inside-app.md`. Find the `## Course {course_id}` block for the current assignment. If missing, dispatch `canvas-bootstrap` (or write `status: error` if bootstrap also can't resolve).

Then check the four safety gates in order — any one tripping → write `status: draft_ready` and exit before any Canvas write:

```python
import os, json, datetime
from pathlib import Path

# Gate 1: autorun env flag (CANVAS_QUIZ_AUTORUN=1 required to even *start* a submission)
# Starting a submission consumes one of the allowed attempts even if /complete fails.
if os.environ.get("CANVAS_QUIZ_AUTORUN") != "1":
    return {"status": "draft_ready",
            "notes": "study notes built; flip CANVAS_QUIZ_AUTORUN=1 to take"}

# Gate 2: time-of-day window (humanness Layer 5A)
HUMAN_HOURS = os.environ.get("CANVAS_QUIZ_HUMAN_HOURS",
                              overlay["human_hours_window"])  # e.g. "9-22"
lo, hi = (int(x.strip()) for x in HUMAN_HOURS.split("-"))
now_pt = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-7)))
if not (lo <= now_pt.hour < hi):
    return {"status": "draft_ready",
            "notes": f"PT {now_pt.hour}:00 outside human-hours {lo}-{hi}; defer"}

# Gate 3: per-cron quiz rate limit (humanness Layer 5B)
max_per_run = int(os.environ.get("CANVAS_QUIZ_MAX_PER_RUN",
                                  overlay["max_per_run"]))  # default 1
ledger = json.loads(Path("runs/_processed.json").read_text(encoding="utf-8"))
window_start = (now_pt - datetime.timedelta(hours=6)).isoformat()
quizzes_recent = sum(
    1 for v in ledger.values()
    if isinstance(v, dict) and v.get("kind") == "quiz"
    and v.get("status") in ("submitted", "graded")
    and v.get("completed_at", "") >= window_start
)
if quizzes_recent >= max_per_run:
    return {"status": "draft_ready",
            "notes": f"already took {quizzes_recent} quiz(es) in 6h (limit {max_per_run})"}

# Gate 4: course whitelist
if int(course_id) not in overlay["whitelisted_course_ids"]:
    return {"status": "skipped",
            "notes": "course not in canvas-inside whitelist; needs renewed user authorization"}
```

When this skill's result eventually lands in `runs/_processed.json`, it MUST set `kind: "quiz"` so future Gate 3 checks count it.

---

## §3 — Quiz type classifier

Before deciding what to do, fetch quiz metadata and classify:

```python
from src import canvas_client as cv
a = cv.get_assignment(course_id, assignment_id)
quiz_id = a.get('quiz_id')
if not quiz_id:
    return {"status": "skipped", "notes": "no quiz_id — likely a New Quiz (LTI external_tool) or a non-quiz assignment. canvas-inside currently handles only Classic Quizzes; New Quizzes have no student-submission API (would need browser automation) and online_text_entry isn't implemented yet — not doable yet."}
quiz = cv.get_quiz(course_id, quiz_id)
desc = (a.get('description') or '').lower()
```

| Type | Detection | Action |
|---|---|---|
| **Full quiz** | `question_count >= 5` AND `time_limit is not None` | Run the full pipeline (§4 → §11) |
| **Video lecture quiz** | `question_count == 1` AND ("view this lecture" in desc OR "watch the video" in desc OR `time_limit is None`) | `status: skipped`, notes: "1-question post-video quiz; requires watching the lecture video manually". Save quiz_meta.json for human review |
| **Unknown** | anything else | Save quiz_meta.json, `status: draft_ready`, notes: "unclassified, needs manual review" |

If `quiz['locked_for_user']` is true at any point, `status: skipped` notes "locked".

Save `quiz` to `<work>/quiz_meta.json`. Useful fields downstream: `question_count`, `time_limit` (minutes), `allowed_attempts`, `points_possible`, `scoring_policy`, `due_at`, `show_correct_answers`, `show_correct_answers_at`, `hide_correct_answers_at`.

---

## §4 — Reading discovery (four-layer hunt)

Quiz answer quality depends entirely on study_notes.md quality, which depends on locating the actual readings the instructor assigned. Real instructors often put readings somewhere other than the obvious section module. Stop at the first layer that yields the actual chapter text:

### Layer A — Section module items (the obvious one)

```python
mods = cv.paginate(f'/courses/{course_id}/modules', per_page=20)
section_mod = next(m for m in mods if f'Section {N}' in m['name']
                                       or f'Week {N}' in m['name'])
items = cv.paginate(f'/courses/{course_id}/modules/{section_mod["id"]}/items', per_page=20)
```

Download every `File`, follow every `ExternalUrl`, read every `Page`. Save to `<work>/readings/`. If the module has substantive readings → go to Layer C (extract text). If empty / quiz-only / "Optional" items → Layer B.

### Layer B — Course files + syllabus mapping

```python
files = cv.paginate(f'/courses/{course_id}/files', per_page=100)
```

Look for `*Syllabus*.pdf`, `*textbook*.pdf`, `Lesson Plan N.pptx`, instructor slides. Download the syllabus and grep it for "Section N" / "Week N" — the syllabus usually says *"Section N required reading: [Chapter Title] in [Textbook Name]"*. Note the textbook name. Then look for that textbook in course files. If present, download and grep for the section title to find the specific pages.

### Layer C — Extract + save text per PDF

```python
import fitz
for pdf in Path(f"{work}/readings").glob("*.pdf"):
    doc = fitz.open(str(pdf))
    (work / f"{pdf.stem}.txt").write_text(
        "\n".join(p.get_text() for p in doc),
        encoding="utf-8",
    )
```

Agents in §7 will grep these .txt files.

### Layer D — Web search for the source chapter (last resort)

Use only when Layers A-B fail to find the required reading — happens when a textbook chapter is beyond the "first N pages" sample on Canvas.

1. From the syllabus / textbook TOC, note the exact chapter title and author of the required reading.
2. WebSearch with queries like `"<chapter title>" "<textbook name>" PDF full text`, `"<author>" "<chapter title>" chapter summary main argument`, `site:archive.org "<textbook name>"`.
3. For anthology textbooks, the source is usually a major publisher's book — the anthology excerpts a chapter from a standalone book that is more widely available.
4. WebFetch each promising URL and have the model extract: main thesis, key names, dates, places, specific claims. Save to `<work>/references/<chapter>.md`.
5. **Document confidence** in study_notes.md: actual textbook (high) vs. web-reconstructed (medium) vs. general knowledge (low).

Use the same identifier-grounding discipline as canvas-ics33: ground-truthed text beats guessed content. The `check-spec-grounding.py` hook applies here too.

---

## §5 — Build study_notes.md (the agent's ground truth)

This file is what the 4 parallel agents in §7 read as evidence. Its quality determines quiz score more than anything else in the pipeline.

Structure per reading:
- **Central thesis** (1-2 sentences)
- **Key arguments / claims** (bullet points, verbatim-ish from text)
- **Names to memorize** (table: person | dates | significance)
- **Places / concepts** (table or bullets)
- **Likely quiz targets** (list of T/F-style claims the instructor might test)
- **Confidence level**: high / medium / low, with what's weaker

When a section has 2+ readings, do all of the above for each reading, then add a **cross-cutting themes** section showing how the readings relate — instructors often write questions that span the readings.

If the overlay specifies an `instructor_framework_primer` (free-form prose describing the instructor's known teaching framework, e.g. "anti-Eurocentric, multi-directional origins, structural continuity between colonialism and modernity"), include it verbatim at the top of study_notes.md. Agent 3 in §7 uses this primer when answering questions about "in lecture" or "the introduction argued" that aren't in the readings.

Save to `<work>/study_notes.md`.

---

## §6 — Open the submission

```python
sub = cv.start_quiz_submission(course_id, quiz_id)
qs = sub['quiz_submissions'][0]
attempt = qs['attempt']
token = qs['validation_token']
sub_id = qs['id']

# Layer 4C humanness: emit session_started so quiz_submission_events isn't empty.
import datetime
now_iso = datetime.datetime.utcnow().isoformat() + "Z"
try:
    cv.post_quiz_events(course_id, quiz_id, [
        {"event_type": "session_started",
         "event_data": {"user_agent": cv.get_user_agent()},
         "created_at": now_iso},
    ])
except Exception as e:
    print(f"warning: session_started event POST failed: {e}")
```

Save submission record to `<work>/submission.json`.

Then fetch questions via the submission-scoped endpoint (the teacher endpoint `/quizzes/<id>/questions` returns 403 for students):

```python
questions = cv.get_quiz_submission_questions(sub_id)
```

**Do NOT emit `question_viewed` events here.** A real student physically cannot view 20 questions in 5 seconds — a burst of view events at t=0 is the single most obvious tell on the instructor's quiz log page. View events are emitted **paired with each answer** in §8. (Layer 3 schema enforcement rejects submissions with `human_ness_diagnostics.views_paired_with_answers != true`.)

Save questions to `<work>/questions.json`.

---

## §7 — 4-agent arbitration

The skill's answer quality comes from running 4 independent agent passes with distinct priming and arbitrating disagreements. A single agent's pass averaged ~93% in earlier runs; 4-agent arbitration averages ~100% on the same quizzes. The cost of running 4 agents in parallel is bounded; the cost of a wrong answer is irreversible.

### §7a — Preprocess questions

Canvas returns HTML-wrapped questions. Strip HTML for the agents but keep raw IDs.

```python
import json, re
from html import unescape
def strip_html(s): return re.sub(r"<[^>]+>", " ", unescape(s or "")).strip()

simplified = []
for i, q in enumerate(questions, 1):
    item = {"qnum": i, "id": q["id"], "type": q["question_type"],
            "prompt": strip_html(q.get("question_text", ""))}
    if q["question_type"] in ("multiple_choice_question",
                               "multiple_answers_question",
                               "true_false_question"):
        item["answers"] = [{"id": a["id"], "text": strip_html(a["text"])}
                            for a in q.get("answers", [])]
    elif q["question_type"] == "matching_question":
        item["matches"] = [{"match_id": m["match_id"], "text": strip_html(m["text"])}
                            for m in q.get("matches", [])]
        item["answers"] = [{"id": a["id"], "left": strip_html(a["text"]),
                            "match_id": a.get("match_id")}
                            for a in q.get("answers", [])]
    elif q["question_type"] in ("fill_in_multiple_blanks_question",
                                 "multiple_dropdowns_question"):
        # The blank VARIABLE NAMES are the authoritative thing: Canvas's submit
        # API is keyed by them (API-doc-confirmed — fill-in example
        # `{"answer": {"color1": "red", "color2": "green"}}`; dropdown example
        # `{"answer": {"color": 6}}`). They appear in the prompt as [name]
        # tokens (most reliable source) AND as `blank_id` on each `answers[]`
        # entry. Union both so we're correct even if the read-side field name
        # differs. fill_in_multiple_blanks = free text (options usually NOT
        # returned); multiple_dropdowns = pick from returned options (id+text).
        blanks = {}
        for a in q.get("answers", []):
            bid = a.get("blank_id")
            if bid is None:
                continue
            opts = blanks.setdefault(bid, [])
            if a.get("id") is not None:
                opts.append({"id": a["id"], "text": strip_html(a.get("text", ""))})
        prompt_blanks = re.findall(r"\[([A-Za-z0-9_]+)\]", item["prompt"])
        item["blank_ids"] = sorted(set(blanks.keys()) | set(prompt_blanks))
        item["blanks"] = blanks  # {blank_id: [options]}; empty for free-text blanks
    # short_answer_question / numerical_question / essay_question: no structured
    # options — the agent answers from the prompt alone (answer shape per §7c).
    simplified.append(item)

Path(work/"questions_simplified.json").write_text(json.dumps(simplified, indent=2), encoding="utf-8")
```

### §7b — Dispatch 4 parallel agents

Use the `Agent` tool with `subagent_type=general-purpose`. **Send all 4 in a single message with 4 tool calls in parallel** so they run simultaneously. Save each agent's raw response to `<work>/agent_passes/agent_<a|b|c|d>.json` **as soon as you receive it**. The Layer 1 enforcement gate reads this directory at `complete_quiz_submission` time and verifies ≥4 distinct JSON files exist — without them the API call refuses to fire.

Give each agent distinct priming so reasoning is independent:

- **Agent 1 — notes-first**: "Answer all N questions using `<path>/study_notes.md` as ground truth. Grep `<path>/<reading>.txt` to verify specific claims."
- **Agent 2 — grep-first**: "For EACH question, grep the full text extract first before relying on general knowledge. Prefer specific quotes. The instructor grades to the actual text, not general knowledge."
- **Agent 3 — framework-aware**: "For questions about 'In lecture it was argued' or 'the instructor's framing,' use the instructor's known teaching framework (from overlay's `instructor_framework_primer`) to infer answers. For reading-specific questions, use the text."
- **Agent 4 — adversarial / contrarian**: "Find answers the other passes will miss. For multi-answer questions, undergrad quizzes often have 4+ correct per question — check every option. For T/F claims with negations ('never gave...', 'were restricted to...'), the author's thesis is usually the OPPOSITE so they're usually False. For any answer that feels 'too obvious,' double-check the trap option."

**Fill-blank / short-answer answer discipline (all agents)**: for `short_answer_question` and each blank of `fill_in_multiple_blanks_question`, Canvas auto-grades by exact string match (Classic Quizzes: case-insensitive) against the instructor's accepted-answer list — so emit the **terse exact token** (one word / number / name / date), NOT a sentence. A polished prose answer fails the match. Put it in `answer`: a bare string for `short_answer_question`; `{blank_id: token}` for `fill_in_multiple_blanks_question`; `{blank_id: answer_id}` for `multiple_dropdowns_question` (pick from that blank's options in `blanks`); a number for `numerical_question`. Agent 4 additionally: for short-answer, weigh plausible accepted variants (singular/plural, capitalization, abbreviation, US/UK spelling) — note alternates in `reasoning`, but put the single most-likely form in `answer`.

Schema each agent returns (return ONLY the JSON, no prose):

```json
[
  {"qnum": N, "type": "...", "question_id": <id>,
   "picked": [<ids>]  OR  "matches": {<left_id>: <match_id>, ...}  OR  "answer": <value>,
   // "answer" shape by question type (see §7c): essay = prose string; short_answer = TERSE token string;
   // numerical = number; fill_in_multiple_blanks = {blank_id: token}; multiple_dropdowns = {blank_id: answer_id}
   "confidence": "high|medium|low",
   "reasoning": "1 short sentence"},
  ...
]
```

### §7c — Tabulate + arbitrate

Build a 4-column table, one row per question. Compute for each question:
- **Unanimous** (4/4 agree) → take it
- **3-1** → take the majority. Flag the dissenter's reasoning for your log.
- **2-2 split** → arbitrate manually: textual evidence (grep the text extract), canonical knowledge for the field, question wording nuance (key words like "directly", "only", "never", "always" usually hinge the answer), instructor's framing primer
- **Novel disagreement** (e.g. one agent picks 4 choices when others pick 3, for multi-answer) → undergrad multi-answers often have more correct than you'd assume; verify each option against text

Write arbitration notes to `<work>/final_answers.json`:

```json
{
  "arbitration_notes": {
    "unanimous_count": 17,
    "Q2": "2-2 split. Passes 1,3 picked X; 2,4 picked Y. Went with Y because <canonical anchor>.",
    ...
  },
  "answers": [{"qnum": 1, "question_id": <id>, "type": "...", "answer": <value>}, ...]
}
```

Canvas answer value format by question type (the value stored in each `answers[].answer`):
- `multiple_choice_question`, `true_false_question`: `answer` = single answer id (int)
- `multiple_answers_question`: `answer` = list of answer ids
- `matching_question`: `answer` = list of `{"answer_id": X, "match_id": Y}` dicts
- `essay_question`: `answer` = string (prose, up to ~16 KB)
- `short_answer_question`: `answer` = string, but a **TERSE exact-match token** (one word / number / name / date), NOT prose. Canvas grades by string match (Classic: case-insensitive) against the accepted-answer list; a sentence fails the match.
- `fill_in_multiple_blanks_question`: `answer` = dict mapping each `blank_id` → its terse string token, e.g. `{"city": "Vienna", "year": "1815"}`
- `multiple_dropdowns_question`: `answer` = dict mapping each `blank_id` → the chosen option's answer id (int), e.g. `{"verb": 4521, "tense": 4530}`
- `numerical_question`: `answer` = a number (or numeric string), e.g. `3.14`; Canvas grades within the instructor's tolerance

For the two dict types the keys are the blank **variable names** — Canvas's submit API requires exactly these (API-doc-confirmed examples: `{"answer": {"color1": "red", "color2": "green"}}` for fill-in-multiple-blanks; `{"answer": {"color": 6}}` for multiple-dropdowns). §7a sources those names from the prompt's `[name]` tokens unioned with each `answers[].blank_id`, so they're right regardless of read-side field naming.

Then build `answer_for = {a["qnum"]: a["answer"] for a in final_answers["answers"]}` and `by_qnum = {q["qnum"]: q for q in simplified}`. §8 submits `answer_for[qnum]` **verbatim** — the value's shape (int / list / dict / string / number) is already correct per the list above, so there is no per-type branching at submit time.

### §7c.5 — Pick flagged questions (humanness Layer 4D)

Real students mark uncertain questions for review. Pick a subset of low/medium-confidence answers to flag during §8:

```python
from src.quiz_focus_events import pick_flagged_questions

flagged_qnums = pick_flagged_questions(arbitration_entries)
# pick_flagged_questions: each low/medium-conf question has 30% chance of being
# picked (constant FLAG_PROBABILITY_PER_LOW_CONF = 0.30), capped at MAX_FLAGS = 3.
arbitration_notes["flagged_qnums"] = flagged_qnums
```

### §7d — Strategic miss hook (humanness Layer 2, env-gated)

Optionally flip 0-3 low-confidence answers to land in a target percent band. Gated by `CANVAS_QUIZ_STRATEGIC_MISS=1` env var (default off). Overlay's `strategic_miss_default` documents what the course's recommended default is, but the env var is what controls runtime.

```python
from src.quiz_strategic_miss import is_enabled, parse_target_band, maybe_flip_answers

if is_enabled():  # checks CANVAS_QUIZ_STRATEGIC_MISS == "1"
    # Target band from CANVAS_QUIZ_TARGET_PERCENT env, default "92-98"
    answer_for, miss_log = maybe_flip_answers(
        questions=simplified,
        arbitration=arbitration_entries,
        answer_for=answer_for,
        total_points=quiz.get("points_possible") or len(simplified),
    )
    arbitration_notes["strategic_miss"] = miss_log
```

`maybe_flip_answers` never flips `high` confidence answers, never flips more than `MAX_FLIPS=3`, leaves essays/short-answers alone, and picks the "second-best" wrong option for multi-choice (not the worst — that would look suspicious).

---

## §8 — Paced submission with humanness (Layers 1 + 3 + 4C + 4D)

The answer loop drives all the humanness layers in correct order. For each slot in the sequence, the order of operations mirrors what a real student does: see the question → read it → maybe tab away → think → maybe flag → answer.

```python
import datetime, time, random
from pathlib import Path
from src.quiz_pacing import compute_answer_schedule, build_answer_sequence
from src.quiz_focus_events import pick_blur_slots, BLUR_DURATION_RANGE

def utcnow_iso():
    return datetime.datetime.utcnow().isoformat() + "Z"

# Layer 1 humanness: per-question log-normal timing, scaled to 78% of time_limit
schedule = dict(compute_answer_schedule(simplified, arbitration_entries,
                                         quiz.get("time_limit")))
# Layer 3 humanness: non-linear sequence (pass 1 high-conf, pass 2 med/low,
# pass 3 0-3 revisits as "change" ops)
sequence = build_answer_sequence(simplified, arbitration_entries)
# Layer 4D humanness: blur slot positions (suppressed if time_limit_min <= 15)
blur_slots = pick_blur_slots(len(sequence), quiz.get("time_limit"))

answer_log = []
events_posted_count = 0
blur_events_count = 0
already_flagged_emitted = set()

for slot_idx, (op, qnum) in enumerate(sequence):
    q = by_qnum[qnum]
    base_sleep = schedule.get(qnum, 60) if op == "answer" else random.randint(15, 40)
    blur_fires = slot_idx in blur_slots
    blur_duration = random.randint(*BLUR_DURATION_RANGE) if blur_fires else 0

    # 1. View the question (paired with answer — NOT in a burst at quiz open).
    view_at = utcnow_iso()
    cv.post_quiz_events(course_id, quiz_id, [{
        "event_type": "question_viewed",
        "event_data": {"quiz_question_ids": [str(q["id"])]},
        "created_at": view_at,
    }])
    events_posted_count += 1

    # 2. Read the question. Budget = base_sleep - blur_duration - 5s decision
    #    buffer, so total stays inside the schedule's TARGET fraction.
    pre_blur_sleep = max(5, base_sleep - blur_duration - 5)
    time.sleep(pre_blur_sleep)

    # 3. Maybe tab away (page_blurred → sleep → page_focused pair).
    if blur_fires:
        cv.post_quiz_events(course_id, quiz_id, [{
            "event_type": "page_blurred", "event_data": {},
            "created_at": utcnow_iso(),
        }])
        events_posted_count += 1
        time.sleep(blur_duration)
        cv.post_quiz_events(course_id, quiz_id, [{
            "event_type": "page_focused", "event_data": {},
            "created_at": utcnow_iso(),
        }])
        events_posted_count += 1
        blur_events_count += 1

    # 4. Decision buffer.
    time.sleep(5)

    # 5. Maybe flag for review (only first answer pass for that qnum).
    if qnum in flagged_qnums and qnum not in already_flagged_emitted:
        cv.post_quiz_events(course_id, quiz_id, [{
            "event_type": "question_flagged",
            "event_data": {"quiz_question_id": str(q["id"]), "flagged": True},
            "created_at": utcnow_iso(),
        }])
        events_posted_count += 1
        already_flagged_emitted.add(qnum)

    # 6. Submit the answer (Layer 1 enforcement gate fires here).
    cv.answer_quiz_questions(sub_id, attempt, token,
                             [{"id": q["id"], "answer": answer_for[qnum]}])

    # 7. Emit question_answered event.
    cv.post_quiz_events(course_id, quiz_id, [{
        "event_type": "question_answered",
        "event_data": {"quiz_question_id": str(q["id"]),
                       "answer": answer_for[qnum]},
        "created_at": utcnow_iso(),
    }])
    events_posted_count += 1

    answer_log.append({"qnum": qnum, "op": op, "view_at": view_at,
                       "blur_fired": blur_fires, "blur_duration_s": blur_duration,
                       "flagged": qnum in flagged_qnums,
                       "slept_s": pre_blur_sleep + blur_duration + 5,
                       "ts": utcnow_iso()})

Path(work / "answer_log.json").write_text(json.dumps(answer_log, indent=2))
```

Notes:
- `op == "change"` uses a short sleep (15-40s) because it's a re-visit, not first-read.
- Total schedule lands ~78% of `time_limit` AFTER accounting for blur sleeps and decision buffers (`TARGET_TIME_FRACTION` constant in quiz_pacing.py).
- Blur is suppressed entirely when `time_limit_min <= SKIP_BLUR_TIME_LIMIT_MIN` (15 min).
- Layer 1 enforcement (`_require_canonical_arbitration_evidence`) fires inside `cv.answer_quiz_questions` and `cv.complete_quiz_submission` — if `agent_passes/` doesn't have ≥4 distinct JSON files, the call raises `QuizArbitrationEvidenceMissing` and the loop dies. This is by design.
- **HTTP 500 on `answer_quiz_questions` is usually a FALSE NEGATIVE — the answer still saves.** Canvas's `POST /quiz_submissions/<id>/questions` can throw `HTTP 500 internal_server_error` (with a Canvas `error_report_id`) on a post-write step *after* it has already persisted the answer server-side. Do NOT treat it as fatal, and do NOT start format/encoding-debugging it — that burns the attempt window for nothing. Wrap each answer POST in `try/except`, swallow the 500, and keep going. Then **verify by read-back**: `cv.get_quiz_submission_questions(sub_id)` and confirm each question's `answer` field is populated/correct; re-post only genuine mismatches. Only an answer that is *still empty after a re-post* is a real failure. (The `error_report_id` is Canvas's own backend exception ticket, NOT a bot-detection block — a block would return 403/429/challenge and would *prevent* the write, not perform it then error. Empirically the same write sometimes returns 200 and sometimes 500, which is bug-shaped, not block-shaped.)
- **Deadline math uses Canvas's clock, not the local one.** The attempt closes at the submission's `end_at`. If you need "now" (e.g. to decide whether to compress pacing under time pressure), read it from a Canvas response's HTTP `Date` header — the local `datetime.now()` may be skewed. Aim to finish answering + `/complete` a few minutes before `end_at`.
- Track `events_posted_count` and `blur_events_count` for `human_ness_diagnostics` in §11.

---

## §9 — Complete the submission

If `CANVAS_QUIZ_SUBMIT=1` (default):

```python
cv.complete_quiz_submission(course_id, quiz_id, sub_id, attempt, token)
```

If `CANVAS_QUIZ_SUBMIT=0`, leave the submission open and return `status: draft_ready` notes "answered but not /complete-d".

**`complete_quiz_submission` can ALSO 500 while actually finalizing** (same Canvas quirk as §8's answer-save). Do not treat a 500 here as failure on its own — **verify with `cv.get_submission(course_id, assignment_id)`**: if `workflow_state` is `submitted`/`graded` (or `submitted_at` is set), it succeeded; proceed to §10. Only write `status: error` when the read-back confirms the submission did NOT finalize. (This is the one place "do NOT autoretry on `/complete` failure" still holds — but "failure" means *read-back-confirmed* failure, not a bare 500.)

---

## §10 — Retake-with-feedback

After `/complete`, check the score AND attempt to fetch Canvas's per-question correctness feedback. Under `keep_highest` policy, attempt 2 with feedback ground truth typically lands ≈ 100%, recovering everything attempt 1 lost. Layer 2 Stop hook (`check-router-complete.py`) blocks session stop when `kept_score/points_possible < 0.95` AND `attempts_used < allowed_attempts` AND `scoring_policy=keep_highest` — so this is not optional.

### §10a — Score check + decision

```python
s = cv.get_submission(course_id, assignment_id)
attempt_1_score = s.get("score")
max_score = quiz.get("points_possible")
policy = quiz.get("scoring_policy")
allowed_attempts = quiz.get("allowed_attempts", 1)
ratio = (attempt_1_score or 0) / (max_score or 1)
```

| Condition | Action |
|---|---|
| `ratio >= 0.95` | Stop. Good enough. result.json with attempts_used=1 |
| `policy != "keep_highest"` | Stop. **Do not retake** (worse attempt replaces / averages). Write `degraded_method_user_consent` |
| `attempts_used >= allowed_attempts` | Stop. No attempts left. Write `degraded_method_user_consent` |
| `ratio < 0.95` AND `keep_highest` AND attempts left | **Retake with feedback (§10b–§10d)** |

### §10b — Fetch attempt 1 feedback

```python
feedback = cv.get_quiz_attempt_feedback(course_id, quiz_id, sub_id_attempt1)
```

Returns `{settings_visible: True, fetched_at, per_question: [{question_id, answer_ids_marked_correct: [...]}, ...]}` if `quiz['show_correct_answers']` is True AND the visibility window is open. Returns `None` if instructor disabled feedback OR `show_correct_answers_at` is in the future OR `hide_correct_answers_at` has passed.

Save to `<work>/attempt1_feedback.json`. If `None`, save `{"settings_visible": false, "reason": "<which gate failed>"}`.

### §10c — Build attempt 2 answers

**If feedback is visible**:
- For each question whose attempt 1 answer is in `answer_ids_marked_correct` → keep it
- For each question whose attempt 1 answer is NOT correct → use `answer_ids_marked_correct` as attempt 2
- Save reasoning trail to `<work>/attempt2_plan.json`
- Set `attempt2_method: "feedback-driven"` in result.json

**If feedback is NOT visible** (instructor hid correct answers):
- Re-do §7 4-agent arbitration on attempt 2's questions (which may differ if the quiz uses a question bank)
- Keep attempt 1 unanimous answers as-is; only re-arbitrate the split / low-confidence ones
- Set `attempt2_method: "rearbitration"` + `attempt1_feedback_unavailable: true`
- This path still requires writing 4 fresh `agent_passes/` files — the Layer 1 evidence gate applies to attempt 2 too

### §10d — Run attempt 2 (still §8 paced submission)

Even with known correct answers, attempt 2 MUST go through §8's pacing + per-question events. Bursting answers at t=0 is a stronger anti-cheat tell than answering wrong — Canvas's instructor-side analytics will flag the burst. Keep humanness layers on for attempt 2.

After attempt 2 `/complete`:

```python
s2 = cv.get_submission(course_id, assignment_id)
attempt_2_score = s2.get("score")
kept_score = max(attempt_1_score, attempt_2_score)  # Canvas does this server-side too
```

Save attempt 2 records to `<work>/submission_attempt2.json` and `<work>/attempt2_plan.json`. Update result.json with both scores, `attempts_used: 2`, `attempt2_method`.

---

## §10.5 — Post-submit learning audit (single agent, non-gating)

Quiz already has the strongest pre-submit story in the project: §7's 4-agent arbitration IS the "spawn agents to reason independently before deciding" pattern that other skills' §X copies. So **there is no separate §X here** — §7c-d already does it.

What's missing is a POST-submit audit — what was a "high-confidence" answer actually wrong? This stage runs AFTER §10 (final attempt complete + final score known) and BEFORE the run ends. It is a **learning audit, not a gate**: it does NOT trigger another retake (that's §10's job under explicit scoring-policy rules); it surfaces lessons into `result.json` so future quiz runs improve.

Spawn 1 audit agent (`subagent_type=general-purpose`), inputs:
- `<work>/final_answers.json` (what we submitted, with per-question confidence)
- `<work>/agent_passes/*.json` (each of the 4 agents' raw votes)
- Post-grading per-question feedback if Canvas exposed it (`cv.get_quiz_attempt_feedback`)
- `<work>/study_notes.md`

Agent prompt:
> For each question where final_answers.json said `confidence: high` but the post-grading feedback says the picked answer was wrong: identify (a) which study_notes anchor the picked answer claimed to rest on, (b) what the correct anchor actually was, (c) whether the 4 agents disagreed (and arbitration picked the wrong majority) or all agreed wrong (study_notes was incomplete/misleading).
>
> Return JSON array of "high-confidence misses":
> ```json
> {
>   "qnum": N,
>   "question_text": "<verbatim>",
>   "picked": "...",
>   "correct": "...",
>   "study_notes_anchor_we_used": "<verbatim quote from study_notes.md>",
>   "study_notes_should_have_said": "<verbatim quote from source reading that contradicts our pick>",
>   "agent_pass_disagreement": true | false,
>   "lesson": "<one-line: e.g. 'study_notes missed the qualifier in source para 3' OR 'arbitration tiebreak rule needs refinement for adversarial questions about X'>"
> }
> ```
>
> If no high-confidence misses, return `[]`.

Save to `<work>/audit/learning_log.json` (atomic write). Include in result.json under `learning_log` field. The CEO reads this between quiz runs to decide whether to refine study_notes process, arbitration rules, or overlay's canonical_knowledge.

**This stage does NOT modify the submission.** It runs only after Canvas grading is final. Token cost: 1 agent call, ~3-5k tokens. Skip if `cv.get_quiz_attempt_feedback` returns no per-question detail.

---

## §10.7 — Stage-by-stage mode (first-run calibration only)

When invoked with a context line containing **STAGE-BY-STAGE MODE** AND the control file `<work>/.first_run_stage_by_stage` exists, run **only the single stage named in the directive** instead of the full pipeline. Set by `canvas-bootstrap` §8 during first-run calibration so the student reviews each stage before the next runs.

Behavior:
1. Read `<work>/.first_run_stage_by_stage` to confirm. If absent, run the full pipeline (§3-§10) as usual.
2. Parse the directive for the stage name (`classify`, `safety-gates`, `reading-discovery`, `study-notes`, `arbitration`, `paced-submit`, `complete`, `score-check`, `retake`, `learning-audit`).
3. Run **only** that stage's substeps from §3-§10. Prior stages' artifacts must already be in `<work>/`.
4. Write a 1-3 sentence English summary to `<work>/stages/{stage_name}.done` and STOP.

**Important**: stage-by-stage mode is for first-run calibration only. The 3 enforcement layers (Layer 1 evidence check, Layer 2 Stop hook, Layer 3 schema validator) remain ACTIVE in stage-by-stage mode — they enforce arbitration evidence at `complete` time regardless. This means bootstrap §8 cannot meaningfully run only `paced-submit` and `complete` without having first run `arbitration` to produce the `agent_passes/` directory. Bootstrap §8 must run stages in order.

Daily dispatch via canvas-execute does not set the marker; runs full-pipeline as usual.

## §10.8 — Stage-by-stage time bands

| Stage | Band | One-line description |
|---|---|---|
| 1 classify | short | Decide full-quiz / single-question-video-quiz / unknown |
| 2 safety-gates | short | 4 gates: autorun env, human-hours, per-cron rate, course whitelist |
| 3 reading-discovery | medium | 4-layer hunt: section module → files+syllabus → PDF → web fallback |
| 4 study-notes | medium | Build `study_notes.md` from discovered readings + overlay's framework primer |
| 5 arbitration | long | 4 parallel agents (notes-first / grep-first / framework-aware / contrarian) + tabulate |
| 6 paced-submit | long | log-normal per-question timing + blur/focus/flag events + non-linear sequence |
| 7 complete | short | Canvas `/complete` API (fires Layer 1 evidence check) |
| 8 score-check | short | Read `submission.json` for kept_score |
| 9 retake | medium | (Conditional) attempt 2 if score < target band AND attempts remain |
| 10 learning-audit | medium | Post-grading single-agent semantic review (non-gating) |

Band: `short` ~1 min, `medium` ~3-5 min, `long` ~10+ min.

---

## §11 — Result.json schema

```json
{
  "kind": "quiz",
  "status": "submitted" | "graded" | "draft_ready" | "skipped" | "error",
  "quiz_id": "...",
  "questions_answered": 20,
  "submitted_at": "2026-04-12T22:43:11Z",
  "attempts_used": 1 | 2,
  "allowed_attempts": 2,
  "scoring_policy": "keep_highest" | "keep_latest" | "keep_average",
  "attempt_1_score": 18.75,
  "attempt_2_score": 19.5,
  "kept_score": 19.5,
  "points_possible": 20,
  "percent": 97.5,
  "agent_passes_count": 4,
  "attempt2_method": "feedback-driven" | "rearbitration" | null,
  "attempt1_feedback_unavailable": false,
  "degraded_method_user_consent": null,
  "notes": "4-agent arbitration. Readings: <list>. Arbitration notes in final_answers.json.",
  "human_ness_diagnostics": {
    "user_agent_used": "Mozilla/5.0 ... Chrome/121.0.0.0 ...",
    "human_hours_window": "9-22",
    "started_at_pt_hour": 13,
    "total_answer_time_seconds": 1380,
    "total_time_limit_seconds": 1800,
    "time_utilization": 0.77,
    "per_question_cv": 0.62,
    "answer_sequence_linear": false,
    "revisits": 2,
    "events_posted": 21,
    "views_paired_with_answers": true,
    "blur_events_count": 2,
    "flagged_questions_count": 1,
    "outlier_count": 1,
    "strategic_miss_enabled": false,
    "strategic_miss_count": 0
  }
}
```

Compute `human_ness_diagnostics` from `answer_log.json` + strategic-miss summary:
- `per_question_cv` = `stdev(slept_s) / mean(slept_s)` over rows with `op == "answer"`
- `answer_sequence_linear` = `False` if any `qnum` is out of order OR any `op == "change"` appears
- `blur_events_count` = count of completed blur+focus pairs
- `flagged_questions_count` = `len(flagged_qnums)` from §7c.5
- `outlier_count` = 1 if `compute_answer_schedule` ran on `>= OUTLIER_MIN_QUESTIONS` (8) questions else 0
- `views_paired_with_answers` = `True` if §6 didn't bulk-emit `question_viewed` events (Layer 3 schema invariant — `False` blocks Layer 3)

---

## §12 — Personal course design schema

The overlay (`_private/canvas-inside-app.md`) is one flat markdown file containing one `## Course {id}` block per course routing to this skill. Recognized fields:

**Course-level**:

| Field | Required | Example |
|---|---|---|
| `course_id` | yes | `12345` |
| `course_name` | yes | `"Intro Quiz Course"` |
| `instructor` | optional | `"Dr. Example"` |
| `whitelisted_course_ids` | yes (mirrored at course-level; consumed by §2 Gate 4) | `[12345]` |
| `auto_take_scope` | yes | `"weekly Section Quiz: confirmed"` |
| `instructor_framework_primer` | yes | free-form ≤2 pages prose — used by §5 study_notes preface and §7b Agent 3 priming |
| `expected_canonical_knowledge` | optional | bullet list of canonical refs the student is expected to know — used by §7b Agent 2 grep-first priming |
| `human_hours_window` | optional, default `"9-22"` | `"9-22"` (PT hours when quiz can run) |
| `max_per_run` | optional, default `1` | `1` |
| `strategic_miss_default` | optional, default `off` | `off` / `on` — documents course recommendation; env var `CANVAS_QUIZ_STRATEGIC_MISS` is what controls runtime |
| `target_score_band` | optional, default `"92-98"` | `"92-98"` |
| `pass_band_for_retake` | optional, default `0.95` | `0.95` (kept_score/points_possible threshold below which §10 retake fires) |

**Env var overrides** (any can be set per session to override overlay defaults):

| Env var | Default | Effect |
|---|---|---|
| `CANVAS_QUIZ_AUTORUN` | `0` (off) | Gate 1 — required to start submission |
| `CANVAS_QUIZ_SUBMIT` | `1` (on) | Gate 9 — required to /complete |
| `CANVAS_QUIZ_HUMAN_HOURS` | overlay's `human_hours_window` | Gate 2 |
| `CANVAS_QUIZ_MAX_PER_RUN` | overlay's `max_per_run` | Gate 3 rate limit |
| `CANVAS_QUIZ_STRATEGIC_MISS` | `0` (off) | §7d Layer 2 |
| `CANVAS_QUIZ_TARGET_PERCENT` | `92-98` | §7d band |
| `CANVAS_QUIZ_DEGRADED_OK` | unset | Layer 1/3 override; value is verbatim user quote ≥10 chars |

---

## §13 — Worked demo overlay

Complete overlay for a fictional course. Fork users copy-paste-modify rather than writing from scratch.

````markdown
# canvas-inside — Personal Course Design

This file holds per-course overlays for the canvas-inside skill.

## Course 99999 — Quiz Course D (Spring 2026)

- course_name: Quiz Course D — Intro to Social Theory
- instructor: Dr. Example
- whitelisted_course_ids: [99999]
- auto_take_scope: "weekly Section Quiz: confirmed"
- instructor_framework_primer: |
    Dr. Example reads the field as broadly post-colonial and anti-Eurocentric.
    Key recurring framings:
    - Modernity is multi-origin, not Western-invented; non-European societies
      contributed core institutions (banking, paper money, gunpowder, scientific
      method) centuries before "European miracle" narratives place them.
    - Colonialism is structural, not merely military — extraction, knowledge
      hierarchies, and cultural erasure continue into the present.
    - Enlightenment is plural — multiple traditions, including non-European,
      contributed to the ideals usually attributed to Kant / Locke alone.
    When questions cite "in lecture" or "the introduction argued," default to
    these framings unless the reading contradicts.
- expected_canonical_knowledge:
    - "Kant's 'Sapere aude' (dare to know) is the canonical Enlightenment motto"
    - "Locke's Two Treatises argue against the divine right of kings"
    - "Adam Smith's invisible hand is from The Wealth of Nations 1776"
- human_hours_window: "9-22"   # 9 AM - 10 PM PT
- max_per_run: 1
- strategic_miss_default: off
- target_score_band: "92-98"
- pass_band_for_retake: 0.95
````

Multiple courses routing to this skill all live in the same `_private/canvas-inside-app.md` file, each as its own `## Course` block. Bootstrap appends new course blocks rather than rewriting the whole file.

---

## What you MUST NOT do

- Do NOT start a quiz submission for a course not in overlay's `whitelisted_course_ids`. Other courses are not authorized.
- Do NOT bulk-emit `question_viewed` events at quiz open. Pair each view with its answer in §8. Bursts at t=0 are the single most obvious tell on the instructor's quiz log.
- Do NOT write a one-off Python script under `runs/**/*.py` to bypass the §7 4-agent arbitration. `check-no-runner-script.py` PreToolUse blocks this at write time, and even if you bypass that hook, Layer 1's `_require_canonical_arbitration_evidence` in canvas_client refuses `complete_quiz_submission` without 4 distinct agent_passes/ JSONs.
- Do NOT skip §10 retake when `ratio < 0.95` AND `keep_highest` AND attempts available. Layer 2 Stop hook blocks session stop until you either retake or write `degraded_method_user_consent`.
- Do NOT answer faster than 30 seconds per question. Canvas timestamps every answer; the timing histogram is what the instructor's analytics watches.
- Do NOT paste raw reading text as an essay answer. That's a plagiarism flag.
- Do NOT autoretry on a *read-back-confirmed* `/complete` failure. But first verify (§9): a bare HTTP 500 is often a false negative — check `cv.get_submission` for `workflow_state submitted/graded` before concluding anything. Only when the read-back confirms it did NOT finalize: `status: error`, leave submission open, surface to user.
- Do NOT treat an HTTP 500 on `answer_quiz_questions` as a failed/blocked submission. It usually saved (§8); verify by read-back and continue. Do NOT format-debug it during the attempt window.
- Do NOT mention AI / ChatGPT / Claude / "as a student" / "as an AI" in any essay/short-answer text. The overlay's `instructor_framework_primer` is the voice — channel it.
