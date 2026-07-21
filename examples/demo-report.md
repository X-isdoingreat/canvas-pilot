# Demo REPORT.md

This is a fake public-safe report. It shows the shape of a Canvas Pilot closeout
without using real courses, assignments, drafts, or identifiers.

## Urgent

No items due within 24 hours remain unsubmitted in this demo.

The two approved scan-plan `urgent` items are listed under `draft_ready`
because execution produced drafts for student review.

## Summary

Run date: 2026-09-17

Approved items: 2

Draft-ready items: 2

Skipped items: 1

## draft_ready

| Course | Assignment | Workflow | Status | Next step |
|---|---|---|---|---|
| Code Course A | Set 3 Problem 1 | code-course workflow | draft_ready | Review bundle and upload manually. |
| Writing Course B | Week 5 Reading Notes | reading-annotation workflow | draft_ready | Review annotated PDF and worksheet. |

## skipped

| Course | Assignment | Workflow | Status | Next step |
|---|---|---|---|---|
| Math Course C | Problem Set 4 | zyBooks-backed workflow | skipped | Awaiting student approval. |

## Verified Facts

- The code-course workflow found the fake external spec and starter archive.
- The reading-annotation workflow found the fake reading and worksheet files.
- Each approved item wrote a fake `result.json` with `status: draft_ready`.
- The unapproved item wrote a fake skipped result so the run still has a
  complete audit trail.

## Judgment Calls

- Math Course C was left unapproved during the approval step, so no draft was
  generated.
- The demo uses fake dates and fake IDs only.
