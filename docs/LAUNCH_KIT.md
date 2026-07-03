# Launch Kit

This is public-safe launch copy for Canvas Pilot. Use the public identity
`X_isdoingreat` only. Do not add real school, course, instructor, assignment, or
private run details.

## One-Line Pitch

Canvas Pilot is a local-first Canvas LMS AI agent that learns recurring
assignment patterns per course, then reuses them through scan -> approval ->
execute to produce review-ready drafts and reports.

## 100-Word Pitch

Canvas Pilot is not another Canvas API wrapper. Canvas MCP servers let an agent
access Canvas; Canvas Pilot adds the workflow layer above that. It scans
upcoming Canvas LMS assignments, learns the recurring pattern of each course,
writes an approval plan, stops for student review, and then executes only
approved draft-and-review workflows. The output is review-ready drafts, per-item result
files, and a run report. Private course overlays, credentials, runs, and drafts
stay local. The goal is to make recurring Canvas assignment planning, drafting,
and review less manual without removing the student's review and approval
boundary.

## GitHub Release Draft

Title:

```text
Canvas Pilot public preview: recurring Canvas course workflows
```

Body:

```markdown
Canvas Pilot is a local-first Canvas LMS AI agent that learns each course's
recurring assignment pattern, writes an approval plan, and executes only
approved draft-and-review workflows.

This public preview focuses on the workflow layer:

- scan Canvas assignments into an approval plan
- stop before execution until the student approves work
- reuse course-specific recurring patterns
- produce review-ready drafts and per-assignment result files
- write a run report for student review
- keep private course data, runs, drafts, and credentials local

The project is different from Canvas MCP servers: MCP exposes Canvas tools to an
agent; Canvas Pilot turns repeated course patterns into reusable student
workflows.
```

## X Thread Draft

Post 1:

```text
I built Canvas Pilot: a local-first Canvas LMS AI agent that learns each course's recurring assignment pattern.

Not just "ask an agent to check Canvas."

It turns repeated weekly coursework into scan -> approval -> execute workflows.
```

Post 2:

```text
Most Canvas tools stop at access:
- list assignments
- fetch files
- check grades
- prepare uploads

Canvas Pilot works one layer above that:
- remember where each course's real specs live
- route repeated assignment shapes
- verify outputs
- write result.json + REPORT.md
```

Post 3:

```text
The important boundary:

scan Canvas -> plan.json -> student approval -> execute approved draft workflows

The agent does not start work during scan. It writes a plan and stops.
```

Post 4:

```text
Why this matters:

One course might always put the real spec on an external site.
Another might repeat the same reading-annotation workflow.
Another might assign problem sets from an external exercise list.

Canvas Pilot treats those repeated patterns as the product.
```

Post 5:

```text
Default mode is drafts + review, not auto-submit.

Private course overlays, credentials, runs, and drafts stay local.

Public repo:
https://github.com/X-isdoingreat/canvas-pilot
```

## HN Title Options

```text
Show HN: Canvas Pilot - a local AI agent that learns recurring Canvas course workflows
```

```text
Show HN: I built a Canvas LMS agent that reuses course-specific assignment patterns
```

```text
Show HN: Canvas Pilot turns repeated Canvas coursework into local approval workflows
```

HN body:

```text
Canvas Pilot is a local-first agent workflow for students whose schools use
Canvas LMS. The core idea is not just API access. Canvas MCP servers can expose
Canvas tools to an agent; Canvas Pilot adds a course-memory/workflow layer on
top.

It scans assignments, writes an approval plan, stops for review, and then
executes only approved draft-and-review workflows. The output is drafts,
result.json files, and REPORT.md. Private course data and drafts stay local.

I am positioning it around recurring course patterns because that is where the
workflow becomes useful week after week.
```

## Reddit Title Options

```text
I built a local Canvas LMS agent that learns recurring assignment patterns per course
```

```text
Canvas Pilot: scan Canvas, approve a plan, reuse course-specific workflows
```

```text
A local-first Canvas LMS workflow agent, not just another API wrapper
```

Reddit body:

```text
I have been building Canvas Pilot, a local-first workflow agent for Canvas LMS.

The distinction I am trying to make is: Canvas MCP/API tools help an agent see
Canvas, but Canvas Pilot is meant to remember repeated course patterns. For
example, one course may always put the real spec on an external site, another
may have a weekly reading-annotation shape, and another may assign problem sets
from an external exercise source.

The workflow is:

scan canvas -> approval plan -> student approves -> execute -> result/report

Default behavior is draft + review, not submission. Private course data,
credentials, runs, and drafts stay local.
```

## Keywords

- Canvas LMS AI agent
- Canvas assignment workflow
- Canvas assignment planner
- Canvas MCP workflow layer
- local-first student tools
- recurring course workflows
- course-specific AI workflows
- scan approval execute
- Codex Canvas
- Claude Code Canvas
- local student workflow tools
- privacy-first Canvas automation
