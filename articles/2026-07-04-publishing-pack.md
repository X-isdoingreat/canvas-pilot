# Canvas Pilot publishing pack - 2026-07-04

Use public identity only: `X_isdoingreat`, `@X_isdoingreat`, `X_isdoingreat@proton.me`.

Primary links:

- Website: https://canvas-pilot.likelyou.com/
- GitHub: https://github.com/X-isdoingreat/canvas-pilot
- Release: https://github.com/X-isdoingreat/canvas-pilot/releases/tag/public-preview-2026-07-04
- Comparison: https://canvas-pilot.likelyou.com/compare/canvas-mcp
- Use case page: https://canvas-pilot.likelyou.com/use-cases/canvas-lms-ai-agent

## Positioning to preserve

Canvas Pilot is the local workflow layer above Canvas MCP/API access. Canvas MCP can let an agent see Canvas; Canvas Pilot learns recurring course patterns and turns them into scan -> approval -> execute workflows.

The ceiling is strongest for AI power users. If someone already knows how to use Codex or Claude Code, this can remove repeated Canvas orchestration and make recurring coursework feel close to a one-command workflow. If someone does not know how to operate local AI agents, the current public preview will feel hard.

Avoid leading with "one-click homework submission for everyone." A safer public phrase is:

```text
One-command workflows for recurring Canvas coursework.
```

## Hashnode article

Title:

```text
Canvas Pilot: the workflow layer above Canvas MCP
```

Subtitle:

```text
Canvas access is not the same as recurring coursework workflow memory.
```

Tags:

```text
ai, opensource, canvas, agents, productivity
```

Body:

````markdown
Canvas Pilot is built on a simple product belief: the valuable part of student workflow automation is not only seeing Canvas. It is learning what repeats in each course and turning that pattern into a local, review-first workflow.

Canvas MCP servers are useful because they give an agent access to Canvas. The agent can list assignments, read modules, fetch files, and inspect course pages. That solves the access problem.

It does not solve the repeated-workflow problem.

A course often has a durable shape that does not live in one assignment description. One course may publish the real spec on an external site. Another may always require the same reading annotation format. A third may use the same problem-source and PDF delivery pattern every week.

If an agent has to rediscover that structure every time, the user is still paying the coordination cost. Canvas Pilot treats that repeated structure as the product surface.

## The workflow

Canvas Pilot uses a fixed boundary:

```text
scan Canvas -> approval plan -> student approval -> approved workflow -> review-ready output -> REPORT.md
```

The scan step does not begin assignment work. It writes a plan and stops.

Execution happens only after the student approves selected items. Approved items then route into course-specific workflows that know how to find the real spec, gather inputs, produce a draft, run checks, and report what happened.

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

If someone is not already comfortable with local agent tooling, this public preview will feel rough. That is an honest product boundary.

## Why local-first matters

Coursework data is sensitive. Credentials, school-specific course identifiers, assignment inputs, drafts, cookies, and private overlays should not become part of a hosted multi-tenant service by default.

Canvas Pilot keeps those files on the user's machine. The public repo ships the generic framework. The user's real courses live in local, gitignored configuration and run directories.

## What Canvas Pilot is not

Canvas Pilot is not a silent homework service. The default mode is draft production and student review, not automatic submission.

It is also not trying to win by having the longest list of Canvas API endpoints. Canvas MCP can be part of the access layer. Canvas Pilot's value is in what happens after Canvas is visible to the agent: approval, routing, course memory, verification, result files, and a run report.

GitHub: https://github.com/X-isdoingreat/canvas-pilot

Website: https://canvas-pilot.likelyou.com/
````

## DEV article

Title:

```text
I built a local-first Canvas LMS agent workflow for Codex and Claude Code users
```

Tags:

```text
ai, opensource, python, productivity
```

Body:

````markdown
I have been building Canvas Pilot, a local-first Canvas LMS AI agent for recurring coursework workflows.

The main idea is not "another Canvas API wrapper." Canvas MCP servers and Canvas API clients can help an agent see Canvas. Canvas Pilot is the workflow layer above that:

- scan Canvas assignments into an approval plan
- stop before execution
- let the student approve selected work
- route approved items into recurring course workflows
- produce review-ready drafts, result files, and REPORT.md
- keep private course data and drafts local

## Why workflow memory matters

Many courses repeat the same assignment shape every week.

One course might always put the real spec on an external site. Another might always require the same reading annotation format. Another might use the same problem-source and PDF delivery workflow.

If an agent has to rediscover that every week, you are still doing the orchestration. Canvas Pilot tries to make the repeated pattern durable.

## The workflow

```text
scan Canvas -> approval plan -> student approval -> approved workflow -> review-ready output -> REPORT.md
```

The scan step does not start doing assignments. It writes a plan and stops. Execution only happens after the user approves selected items.

## Who it is for

This public preview is for AI power users first.

If you already know how to use Codex, Claude Code, or similar local agents, the product can remove a lot of repeated Canvas coordination. It can make recurring coursework feel close to a one-command workflow: scan, approve, execute, review.

If you do not already know how to operate local agent workflows, this version will feel hard. I would rather be honest about that than pretend it is a polished no-code SaaS.

## Local-first boundary

Credentials, cookies, real course identifiers, runs, private overlays, assignment inputs, and drafts stay on the user's machine.

The public repo contains the generic framework and public-safe examples.

GitHub: https://github.com/X-isdoingreat/canvas-pilot

Website: https://canvas-pilot.likelyou.com/
````

## Medium article

Title:

```text
Turning recurring Canvas coursework into local AI workflows
```

Subtitle:

```text
Why Canvas Pilot focuses on repeated course patterns, not just Canvas access.
```

Body:

````markdown
The annoying part of Canvas is not always the assignment itself. It is the repeated coordination around the assignment.

Every week, a student checks what is due, finds where the real instructions live, gathers the same kinds of files, explains the same course pattern to an AI tool, reviews the output, and decides what to submit.

Canvas Pilot is my attempt to turn that repeated coordination into a local workflow.

The product is simple at the surface:

```text
scan Canvas -> approval plan -> student approval -> approved workflow -> review-ready output -> REPORT.md
```

The scan step does not start doing coursework. It writes a plan and stops. The student approves selected work. Only then does Canvas Pilot route the approved items into course-specific workflows.

That is the part I care about: recurring pattern memory.

Canvas MCP servers and Canvas API tools can help an agent access Canvas. They can list assignments, fetch files, inspect modules, and read pages. That is useful, but access is not the same as workflow memory.

A course may always hide the real spec on an external page. Another course may repeat the same reading annotation structure. Another may assign problem sets from the same source every week. If an agent has to rediscover that structure every time, the student is still doing the orchestration.

Canvas Pilot is strongest for AI power users first. If you already know how to operate Codex, Claude Code, or similar local agents, this can remove a large amount of repeated work. Recurring coursework can start to feel close to a one-command workflow: scan, approve, execute, review.

If you do not know how to work with local agents, the current public preview will feel difficult. That is a real boundary.

The project is also local-first. Credentials, cookies, course overlays, real identifiers, runs, assignment inputs, and drafts stay on the user's machine. The public repository contains the generic framework and public-safe examples.

Canvas Pilot is not a silent homework service and not a hosted no-code app. It is a workflow layer for repeated Canvas coursework.

GitHub: https://github.com/X-isdoingreat/canvas-pilot

Website: https://canvas-pilot.likelyou.com/
````

## Hacker News

Title option 1:

```text
Show HN: Canvas Pilot - local AI workflows for recurring Canvas coursework
```

Title option 2:

```text
Show HN: I built a Canvas LMS agent that reuses course-specific workflows
```

URL:

```text
https://github.com/X-isdoingreat/canvas-pilot
```

Comment:

```text
Canvas Pilot is a local-first workflow agent for students whose schools use Canvas LMS.

The main distinction I am trying to make is access vs workflow memory. Canvas MCP/API tools can expose Canvas to an agent. Canvas Pilot sits above that: it scans assignments, writes an approval plan, stops for review, then executes only approved draft-and-review workflows.

The target audience is AI power users first. If you already use Codex or Claude Code locally, the product can remove repeated Canvas orchestration: finding the real spec source, reusing the course pattern, producing review-ready drafts, and writing REPORT.md. If you do not already operate local agents, this public preview will feel rough.

Private course data, credentials, runs, and drafts stay local.
```

## X thread

Post 1:

```text
I built Canvas Pilot: a local-first Canvas LMS AI agent for recurring coursework workflows.

Not another "ask an agent to check Canvas" tool.

It turns repeated course patterns into scan -> approval -> execute workflows.
```

Post 2:

```text
Canvas MCP/API tools solve access:
- list assignments
- fetch files
- read modules
- inspect pages

Canvas Pilot works one layer above that:
- remember course patterns
- stop for approval
- route approved work
- write result.json + REPORT.md
```

Post 3:

```text
The important boundary:

scan Canvas -> approval plan -> student approval -> approved workflow -> review-ready output -> REPORT.md

The scan step does not start doing assignments. It writes a plan and stops.
```

Post 4:

```text
Why this matters:

One course may always put the real spec on an external site.
Another may repeat the same reading annotation format.
Another may use the same problem-source and PDF delivery workflow.

The pattern is the product.
```

Post 5:

```text
This is for AI power users first.

If you already use Codex or Claude Code, recurring coursework can get close to a one-command workflow:

scan -> approve -> execute -> review

If you do not use local agents yet, the public preview will feel hard.
```

Post 6:

```text
Default mode is drafts + review, not silent auto-submit.

Private course overlays, credentials, runs, and drafts stay local.

Repo:
https://github.com/X-isdoingreat/canvas-pilot

Site:
https://canvas-pilot.likelyou.com/
```

## Reddit draft

Title:

```text
I built a local Canvas LMS agent that learns recurring assignment patterns per course
```

Body:

````markdown
I have been building Canvas Pilot, a local-first workflow agent for Canvas LMS.

The distinction I am trying to make is: Canvas MCP/API tools help an agent see Canvas, but Canvas Pilot is meant to remember repeated course patterns.

For example, one course may always put the real spec on an external site, another may have a weekly reading-annotation shape, and another may assign problem sets from the same external exercise source.

The workflow is:

```text
scan Canvas -> approval plan -> student approval -> execute approved workflows -> report
```

Default behavior is draft + review, not silent submission. Private course data, credentials, runs, and drafts stay local.

It is honestly for AI power users first. If you already use Codex or Claude Code, this can remove a lot of repeated Canvas orchestration. If you do not already operate local agents, the public preview will feel rough.

GitHub: https://github.com/X-isdoingreat/canvas-pilot
````

## Posting order tonight

1. Hashnode or DEV first, because longform gives a canonical external URL.
2. Hacker News with the GitHub repo URL and the short comment.
3. X thread with GitHub and website links in the final post.
4. Medium after the technical post is live.
5. Reddit only if you can adapt to the specific subreddit rules; otherwise skip.

After each successful post, add the public URL back into this file and into `7.4.md`.

## Long-term automation idea

This can become a one-command content distribution workflow, but the right
shape is reviewed automation, not blind reposting.

Target command:

```text
publish content
```

Expected behavior:

1. Read the canonical article, README, release notes, comparison page, and
   current site copy.
2. Regenerate Hashnode, DEV, Medium, HN, X, and Reddit variants.
3. Check for private identity, stale repo links, wrong domains, and
   homework-bot framing.
4. Update the website, sitemap, and llms.txt.
5. Publish API-supported targets only after explicit approval.
6. For HN, Reddit, and X, prepare/prefill the post and require manual final
   confirmation unless a safe official API path is configured.
7. Record each successful public URL back into this file.

Good automation outcome: one command keeps the whole public surface current.

Bad automation outcome: one click spams every platform with the same post and
hurts account trust.
