# GitHub Metadata Update Checklist

This checklist records the public GitHub search-entry update. The local
environment did not have `gh`, `GH_TOKEN`, or `GITHUB_TOKEN`, but the repo was
updated through the GitHub API using the local Git credential manager.

## Current Public Repository

- Repository: `X-isdoingreat/canvas-pilot`
- URL: `https://github.com/X-isdoingreat/canvas-pilot`
- Stars observed: `80`
- Forks observed: `9`
- Description:

```text
Local-first Canvas LMS AI agent that learns each course's recurring assignment workflow and reuses it through scan -> approval -> execute with student review.
```

- Topics:

```text
canvas-lms
canvas-api
canvas-agent
ai-agent
ai-agents
student-tools
assignment-planner
homework-planning
homework-workflows
course-workflows
assignment-workflows
human-in-the-loop
workflow-automation
local-first
privacy-first
python
playwright
claude-code
codex
mcp-alternative
```

## Applied Metadata

Repository name:

```text
canvas-pilot
```

Description:

```text
Local-first Canvas LMS AI agent that learns each course's recurring assignment workflow and reuses it through scan -> approval -> execute with student review.
```

Topics:

```text
canvas-lms
canvas-api
canvas-agent
ai-agent
ai-agents
student-tools
assignment-planner
homework-planning
homework-workflows
course-workflows
assignment-workflows
human-in-the-loop
workflow-automation
local-first
privacy-first
python
playwright
claude-code
codex
mcp-alternative
```

Homepage:

```text
https://x.com/X_isdoingreat
```

## Manual GitHub UI Fallback

1. Open:

```text
https://github.com/X-isdoingreat/canvas-pilot/settings
```

2. Confirm `Settings > General > Repository name` is `canvas-pilot`.
3. Open the repository:

```text
https://github.com/X-isdoingreat/canvas-pilot
```

4. In the right sidebar `About` panel, click the edit/gear control.
5. Set the description to the recommended description above.
6. Set homepage to `https://x.com/X_isdoingreat` unless a stronger project page
   exists.
7. Replace topics with the applied topic list above. Remove old topics that
   are no longer in the target list.
8. Confirm the repository resolves at:

```text
https://github.com/X-isdoingreat/canvas-pilot
```

## Local Follow-Up After Rename

After the remote rename is complete, the local public remote should point at the
new URL:

```powershell
git remote get-url public
git remote set-url public https://github.com/X-isdoingreat/canvas-pilot.git
git remote -v
git ls-remote public HEAD
rg -n "Canvas_pilot_public|github\.com/X-isdoingreat/Canvas_pilot_public|github\.com/X-isdoingreat/Canvas_pilot\.git" README.md CONTRIBUTING.md docs articles scripts .gitattributes --glob '!.claude/**'
```

Review every `rg` hit. Update public-facing clone links to the new public URL.
Historical notes may keep old names only when clearly marked as historical. Do
not edit `.claude/` as part of this cleanup.

## API Verification

Read the public repo metadata after the change:

```powershell
$expectedTopics = @(
  'canvas-lms',
  'canvas-api',
  'canvas-agent',
  'ai-agent',
  'ai-agents',
  'student-tools',
  'assignment-planner',
  'homework-planning',
  'homework-workflows',
  'course-workflows',
  'assignment-workflows',
  'human-in-the-loop',
  'workflow-automation',
  'local-first',
  'privacy-first',
  'python',
  'playwright',
  'claude-code',
  'codex',
  'mcp-alternative'
)
$headers = @{
  'User-Agent' = 'Codex-Canvas-Research'
  'Accept' = 'application/vnd.github+json'
}
$r = Invoke-RestMethod -Headers $headers -Uri 'https://api.github.com/repos/X-isdoingreat/canvas-pilot' -TimeoutSec 20
$r.full_name
$r.description
$r.homepage
$r.topics
Compare-Object -ReferenceObject ($expectedTopics | Sort-Object) -DifferenceObject (@($r.topics) | Sort-Object)
```

Expected:

- `full_name` is `X-isdoingreat/canvas-pilot`
- description contains `Canvas LMS AI agent`, `recurring assignment workflow`,
  and `scan -> approval -> execute`
- `Compare-Object` prints no differences, proving all expected topics are
  present and old topics were removed
