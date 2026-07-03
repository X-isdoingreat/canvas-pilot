# Canvas Pilot vs Canvas MCP Servers

Canvas Pilot and Canvas MCP servers solve different layers of the same problem.
They can work together, but they are not the same product.

## Short Version

Canvas MCP servers let an agent access Canvas.

Canvas Pilot learns the recurring assignment workflow of each course, stops for
student approval, and then runs the approved work through course-specific
pipelines that produce review-ready drafts, result files, and a run report.

Canvas MCP can supply the Canvas access layer; Canvas Pilot adds the
course-memory, approval, verification, and weekly reuse layer above it.

## Layer Comparison

| Question | Canvas MCP server | Canvas Pilot |
|---|---|---|
| What is it? | A tool server that exposes Canvas API actions to an agent. | A local student workflow system built around recurring course patterns. |
| What does it remember? | Usually credentials, available tools, and the current Canvas data it can query. | The durable pattern of a course: where specs live, how work is verified, what output format is expected, and what needs student approval. |
| What happens next week? | The agent usually asks Canvas again and reasons from the current prompt/context. | The course workflow is reused, then adjusted only when the course pattern changes. |
| Where is the approval boundary? | Depends on the host agent and prompt discipline. | `scan canvas` writes a plan and stops; execution happens only after approval. |
| What is the output? | Tool responses, summaries, fetched files, or ad hoc generated content depending on the agent. | A run directory with per-assignment `result.json`, review-ready drafts, and `REPORT.md`. |
| What is private? | Depends on the server and host configuration. | Course overlays, runs, drafts, cookies, credentials, and real identifiers stay local and gitignored. |

## Why Canvas Pilot Exists

A Canvas API tool can answer "what assignments are due?" A general agent can
try to draft one assignment after reading the current Canvas context. That is
useful, but it is still a one-off interaction.

Most student workloads are repetitive. One code course might always publish the
real spec on an external course site. One writing course might always require
the same reading-annotation format. One math course might always use the same
problem-source and PDF delivery pattern. Canvas Pilot treats those repeated
shapes as the product surface.

The first run for a course is a calibration pass. After that, the course has a
local workflow: how to find the real spec, which inputs matter, what a valid
draft looks like, what verification checks must pass, and when the student must
review or approve the next action.

## Where Canvas MCP Fits

Canvas MCP can be a strong access layer for Canvas Pilot. A mature MCP server
can provide tools for assignments, modules, files, submissions, grades, pages,
and quizzes. Canvas Pilot can use that kind of access, but it still needs the
workflow layer above it:

- decide which assignments matter today
- group them by urgency
- map each item to a course workflow
- stop for approval before work begins
- run the workflow in a repeatable way
- write `result.json` and `REPORT.md`
- keep private course data out of public files

## What Canvas Pilot Is Not

Canvas Pilot is not trying to win by having the largest list of Canvas API
tools. It is also not a multi-tenant Canvas service.

The project is local-first. It is designed for a student who wants an agent to
handle the boring orchestration while preserving review, approval, and local
privacy boundaries.

## Practical Difference

With a Canvas MCP server, a useful prompt might be:

```text
Check my Canvas assignments and help me understand what is due.
```

With Canvas Pilot, the intended workflow is:

```text
scan canvas
review the approval plan
approve selected work
inspect REPORT.md and final drafts
```

The difference is not whether an agent can write text. The difference is
whether each course becomes a durable workflow that can be reused every week.
