# Canvas Pilot: the workflow layer above Canvas MCP

Canvas Pilot is built on a simple product belief: the valuable part of student workflow automation is not only seeing Canvas. It is learning what repeats in each course and turning that pattern into a local, review-first workflow.

The public preview is strongest for AI power users. If you already know how to use Codex, Claude Code, or similar local agents, Canvas Pilot can remove a large amount of repeated Canvas orchestration. If you do not already work that way, the current version will feel hard.

## Access is not memory

Canvas MCP servers are useful because they give an agent access to Canvas. The agent can list assignments, read modules, fetch files, and inspect course pages. That solves the access problem.

It does not solve the repeated-workflow problem. A course often has a durable shape that does not live in one assignment description. One course may publish the real spec on an external site. Another may always require the same reading annotation format. A third may use the same problem-source and PDF delivery pattern every week.

If an agent has to rediscover that structure every time, the user is still paying the coordination cost. Canvas Pilot treats that repeated structure as the product surface.

## The workflow shape

Canvas Pilot uses a fixed boundary:

```text
scan Canvas -> approval plan -> student approval -> approved workflow -> review-ready output -> REPORT.md
```

The scan step does not begin assignment work. It writes a plan and stops.

Execution happens only after the student approves selected items. Approved items then route into course-specific workflows that know how to find the real spec, gather inputs, produce a draft, run checks, and report what happened.

That boundary matters because the product is not "let an agent silently do anything it can reach." The product is "turn repeated course patterns into local workflows the student can inspect."

## Why this is for AI power users first

Canvas Pilot is not a no-code consumer product yet. It is for people who already know how to run local agents, review generated plans, inspect files, and decide what should or should not be submitted.

For that audience, the upside is high. Recurring coursework can feel close to a one-command workflow:

```text
scan canvas
review the approval plan
approve selected work
inspect REPORT.md and final drafts
submit or withhold after review
```

The product can remove the repeated low-value work: digging through Canvas, finding the same external spec source, re-explaining the same course pattern, rebuilding the same draft workflow, and checking the same output constraints.

If someone is not already comfortable with local agent tooling, this public preview will feel rough. That is an honest product boundary, not something to hide.

## Why local-first matters

Coursework data is sensitive. Credentials, school-specific course identifiers, assignment inputs, drafts, cookies, and private overlays should not become part of a hosted multi-tenant service by default.

Canvas Pilot keeps those files on the user's machine. The public repo ships the generic framework. The user's real courses live in local, gitignored configuration and run directories.

That also makes the public repo safer to inspect. The open-source project can show the workflow structure without publishing private course data or real student drafts.

## What Canvas Pilot is not

Canvas Pilot is not a silent homework service. The default mode is draft production and student review, not automatic submission.

It is also not trying to win by having the longest list of Canvas API endpoints. Canvas MCP can be part of the access layer. Canvas Pilot's value is in what happens after Canvas is visible to the agent: approval, routing, course memory, verification, result files, and a run report.

The strongest long-term use case is repeated, structured coursework where the pattern is stable enough to become a workflow. That is the product category: not one prompt that writes, but course patterns that persist.

## What the public preview proves

The current public preview proves the shape of the system:

- scan Canvas assignments into an approval plan
- stop before execution until the student approves work
- route approved items into recurring course workflows
- produce review-ready drafts and per-assignment result files
- write a run report for student review
- keep private course data, runs, drafts, and credentials local

Canvas Pilot is the workflow layer above Canvas access. Canvas MCP can supply part of the input layer. The product value is the recurring workflow memory above it.

GitHub: https://github.com/X-isdoingreat/canvas-pilot

Website: https://canvas-pilot.likelyou.com/
