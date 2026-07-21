---
title: Canvas LMS agents for Codex and Claude Code need workflow memory
description: Canvas access is useful, but recurring coursework needs local workflow memory, approval boundaries, and review-ready reports.
tags: ai, opensource, productivity, agents
canonical_url: https://canvas-pilot.likelyou.com/use-cases/canvas-lms-codex-agent
---

Canvas LMS agents usually start with an access question:

```text
Can the agent read assignments, modules, files, pages, and due dates?
```

That matters. Canvas MCP servers and API clients are useful because they give
an agent something concrete to inspect.

But access is not the whole workflow.

For recurring coursework, the expensive part is often not fetching the Canvas
assignment. It is remembering the course pattern:

- where the real spec usually lives
- what files or readings need to be gathered
- what output format the course expects
- what checks matter before review
- where the student must approve the next step

This is the layer Canvas Pilot is trying to build.

Canvas Pilot is an open-source, local-first Canvas LMS AI agent workflow for
Codex and Claude Code power users. The core loop is:

```text
scan Canvas -> approval plan -> student approval -> approved workflow -> review-ready output -> REPORT.md
```

The scan step does not start doing the work. It writes a plan and stops.

Execution starts only after the student approves selected items. Approved items
then route into course-specific workflows that know how to produce a draft,
run checks, write a result file, and generate a final report for review.

That difference is why I describe Canvas Pilot as a workflow layer above Canvas
access, not just another Canvas API wrapper.

If you are using Codex, Claude Code, or another local agent, the useful product
surface is not only "the agent can see Canvas." The useful surface is:

```text
The agent remembers how this course works every week.
```

The project is intentionally local-first. Credentials, cookies, course
identifiers, assignment inputs, drafts, and real run outputs stay on the user's
machine. The public repo contains the generic framework and public-safe skill
skeletons.

Canvas Pilot is not a silent homework submission service. The default behavior
is draft production and student review.

Canonical pages:

- Canvas LMS Codex agent workflow: https://canvas-pilot.likelyou.com/use-cases/canvas-lms-codex-agent
- Canvas LMS Claude Code agent workflow: https://canvas-pilot.likelyou.com/use-cases/canvas-lms-claude-code-agent
- Canvas MCP workflow layer: https://canvas-pilot.likelyou.com/use-cases/canvas-mcp-workflow-layer
- Open-source Canvas LMS AI agent: https://canvas-pilot.likelyou.com/use-cases/open-source-canvas-lms-ai-agent
- GitHub: https://github.com/X-isdoingreat/canvas-pilot
