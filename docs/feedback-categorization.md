# Feedback categorization protocol

This doc is the single source of truth for how Canvas Pilot turns student
draft feedback into changes — both to the current draft AND, when the
feedback represents a recurring preference or workflow shift, to the
relevant per-course overlay so the next dispatch honors it automatically.

It is referenced from:

- `.claude/skills/canvas-bootstrap/SKILL.md` §8 (stage-by-stage co-author
  loop — categorize feedback between stages during the first-run
  calibration).
- `CLAUDE.md` "Feedback writeback (permanent)" section (permanent CC
  session rule — any session, any time the user gives feedback on a
  draft).
- `.claude/skills/canvas-generic/SKILL.md` Stage 11 (write-back hook for
  the canvas-generic learnings overlay).

---

## The three categories

When the student gives feedback on a draft (a single message that may
contain multiple discrete pieces), each piece falls into exactly one of:

### 1. `one_off`

The feedback applies **only** to the current draft. It does not describe
a pattern the student wants for future assignments of the same kind.

Examples:
- "fix the typo in paragraph 2"
- "this week the topic should be X not Y"
- "the data point on page 3 is wrong, it should be 47%"
- "I want to remove the sentence starting 'However, recent...'"

**Action**: apply to the current draft. Do NOT touch the overlay.

### 2. `recurring_pattern`

The feedback describes a stylistic, formatting, voice, or content
preference that will apply to **every same-cluster assignment from now
on**.

Examples:
- "voice is too formal, write more like a B1-B2 international student"
- "use MLA citations not APA"
- "vocabulary annotations should be green, not yellow"
- "always include a thesis sentence as the second paragraph"
- "never use the phrase 'in conclusion'"

**Action**: apply to the current draft AND propose a specific overlay
edit (see "Overlay edit format" below). Write back after user confirms.

### 3. `workflow_change`

The feedback describes a change to **how the skill runs**, not what the
output looks like. A stage should be added, removed, reordered, or
parameterized differently.

Examples:
- "don't write the outline first, just start drafting"
- "always run the spell-check stage twice"
- "skip the figure-caption stage — this cluster never has figures"
- "do verification before humanize, not after"

**Action**: apply to the current draft (re-run from the changed stage if
necessary) AND propose a workflow edit in the overlay's `**Workflow**
(numbered steps)` field. Write back after user confirms.

---

## Two invocation modes

### Mode A — Sub-agent D (heavy, used by bootstrap §8 + canvas-generic Stage 11)

Used when the full categorization context is available (overlay v1
text, workflow list, draft text). Spawns a dedicated general-purpose
agent via the Agent tool with the prompt template below.

**Prompt template** (fill in the bracketed variables):

```
You are a feedback categorizer. You don't see the broader Canvas Pilot
conversation, so here is the full context.

Cluster: [cluster.norm_name] in [course_name]
Generic skill: [skill_id]
Assignment: [target_assignment.name]

Overlay v1 (current):
---
[overlay_v1_text_for_this_cluster_or_learnings_block]
---

Workflow (numbered steps from overlay; "n/a" if canvas-generic with no fixed workflow):
---
[workflow_numbered_or_na]
---

Draft produced by per-course skill:
---
[draft_text_or_summary]
---

Student's feedback (verbatim, freeform):
---
[student_feedback_verbatim]
---

Your task: parse the student's feedback into discrete pieces. For each piece
decide ONE of three categories:

- "one_off": applies only to the current draft (typo, this week's specific
  topic choice, weird one-time request) — fix in draft, do NOT touch overlay.
- "recurring_pattern": will likely apply to every same-cluster assignment in
  the future (voice register adjustment, instructor's specific formatting
  rule, color preference, register too formal / too casual / wrong slip
  density) — fix in draft AND propose an overlay edit.
- "workflow_change": the student wants a new step added / step reordered /
  step removed in the workflow itself — fix in draft AND propose a workflow
  list edit in overlay.

For each piece, return:
{
  "feedback_piece": "<verbatim quote of student's text>",
  "category": "one_off" | "recurring_pattern" | "workflow_change",
  "justification": "<one sentence why this category>",
  "suggested_overlay_change": "<one-line proposed edit if recurring_pattern or workflow_change; null if one_off>"
}

Return a JSON array of all pieces. Return ONLY the JSON array, no preamble.
```

**Malformed-output handling**: if the JSON parse fails, do not retry
silently. Tell the student "feedback categorizer returned malformed
output; the safer move is for you to edit `_private/canvas-<skill>-app.md`
directly". Do not write any overlay edit.

### Mode B — Inline (light, used by CLAUDE.md permanent rule)

Used in everyday review sessions where invoking a separate agent for
every piece of feedback would be expensive and slow. Claude judges the
feedback shape itself.

**Self-classification heuristic** (apply in this order):

1. **Skip asking when the feedback is clearly `one_off`**:
   - feedback mentions specific draft content ("paragraph 2", "the sentence about X")
   - feedback corrects a specific data point ("the number is wrong")
   - feedback removes / changes a one-time phrase
   - feedback is content-specific ("this week's topic should be Y")
   - just apply it to the current draft and continue

2. **Ask when the feedback looks like `recurring_pattern`**:
   - feedback names a style/voice/format property ("too formal", "use MLA")
   - feedback mentions a color, font, citation style, paragraph structure
   - feedback prescribes a general rule ("always X" / "never Y")
   - apply to current draft, then append the one-line question:
     > 顺便：'<paraphrased feedback>' 这条要不要也写进 skill 下次自动这样？

3. **Ask when the feedback looks like `workflow_change`**:
   - feedback names a stage / step / phase
   - feedback says "skip X" / "always do Y first" / "don't do Z"
   - apply to current draft, then append same one-line question.

4. **When in doubt, ask**. Missing a recurring preference is worse than
   asking once. But don't ask the same kind of question twice in one
   session — if user said "yes write it in" earlier this session, don't
   re-ask for related preferences.

**On confirmation**: when user replies yes, propose a specific overlay
edit (see "Overlay edit format" below). Show the diff. Confirm before
writing back to disk.

**On declination**: when user replies no, do nothing (the feedback was
already applied to the current draft). Do not mark the user as
"declined recurring" for this session — they might say yes to a
similar question later.

---

## Overlay edit format

When proposing a write-back, render the change as a unified-diff-style
preview the user can scan in one glance. The diff is over the relevant
section of `_private/canvas-<framework>-app.md`.

**Example for `recurring_pattern`**:

```
我要把这条写进 _private/canvas-essay-app.md, course 12345, Long Essay block:

  - voice_register: "B2, academic tone, source-weaving paragraph structure"
+   - voice_register: "B1-B2, source-weaving paragraph structure, no contractions"

要不要？
```

**Example for `workflow_change`**:

```
我要改 _private/canvas-reading-annotation-app.md, course 12345, Weekly Reading Annotation block:

  **Workflow** (numbered steps):
   1. classify (reading_annotation / video_exercises)
   2. locate_reading
   3. extract_text_and_blanks
-  4. annotate_pdf (colors + margin notes)
-  5. fill_answer_blanks
+  4. fill_answer_blanks
+  5. annotate_pdf (colors + margin notes)
   6. verify

要不要？(交换了 step 4 和 5 — 先填空再批注)
```

After user confirms, run the actual edit via the Edit tool. Re-apply the
behavioral-rule residue guard (`_assert_no_behavioral_rule_residue` from
canvas-bootstrap §7.1.5) before writing.

---

## File path resolution

Categorization writes back to one of:

| Framework | Overlay file path |
|---|---|
| `canvas-ics33` | `_private/canvas-ics33-app.md` |
| `canvas-reading-annotation` | `_private/canvas-reading-annotation-app.md` |
| `canvas-essay` | `_private/canvas-essay-app.md` |
| `canvas-zybooks` | `_private/canvas-zybooks-app.md` |
| `canvas-inside` | `_private/canvas-inside-app.md` |
| `canvas-generic` | `_private/canvas-generic-<course_id>-<cluster_slug>.md` |

**Critical**: for `canvas-generic`, the filename includes the cluster
slug. Both bootstrap (which creates the empty learnings file) and
Layer 2 writeback (which appends user preferences) MUST compute
`cluster_slug` the same way, or the writeback will create a sibling
file the next dispatch never reads.

Use `src/overlay_utils.py:cluster_filename_slug(cluster_norm)`:

```python
def cluster_filename_slug(cluster_norm: str) -> str:
    """Deterministic filename slug from a normalized cluster name.

    Input: output of src.recurring_patterns.normalize() (e.g. "Tue Wk<N> HW Scan")
    Output: filesystem-safe slug (e.g. "tue-wk-hw-scan")
    """
    import re
    s = cluster_norm.lower()
    s = re.sub(r'<n>', '', s)
    s = re.sub(r'[^a-z0-9]+', '-', s)
    s = re.sub(r'-+', '-', s).strip('-')
    return s or 'cluster'
```

For the 5 specific skills, the overlay file is single-per-framework
(multi-course inside), so no slug is needed — the writeback locates the
correct course block by `course_id`.
