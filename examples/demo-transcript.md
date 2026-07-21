# Demo Transcript

This is a fake public-safe transcript. It demonstrates the interaction shape
without connecting to a real Canvas account.

```text
User:
scan canvas

Canvas Pilot:
URGENT
1. Code Course A - Set 3 Problem 1 - code-course workflow
   matched remembered pattern: Set N points to external spec + starter bundle + test command
2. Writing Course B - Week 5 Reading Notes - reading-annotation workflow
   matched remembered pattern: Week N reading notes require module PDF + worksheet + annotation draft

SOON
3. Math Course C - Problem Set 4 - zyBooks-backed workflow
   matched remembered pattern: Problem Set N uses Canvas exercise list + external problem text + PDF draft

plan.json written with all three items unapproved.
No workflows run until the student approves items from this plan.

Reply with: approve all / approve 1,2 / urgent only / cancel

User:
approve 1,2

Canvas Pilot:
canvas-execute reads plan.json and processes the approved draft workflows for
items 1 and 2.

1. Code Course A - draft_ready
   - spec found
   - tests passed
   - bundle created

2. Writing Course B - draft_ready
   - reading found
   - worksheet filled
   - PDF checks passed

REPORT.md written with draft_ready and skipped sections.
result.json written for all three items: two draft_ready, one skipped because it was not approved.
Drafts are ready for student review; nothing was submitted automatically.
```
