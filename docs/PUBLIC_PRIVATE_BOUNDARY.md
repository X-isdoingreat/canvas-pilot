# Public / Private Boundary

This repo has a private working copy and a public framework mirror. Codex work must preserve that boundary.

## Public-safe

Public-safe content is generic framework content:

- generic Canvas API client logic
- generic scan/plan/execute workflow docs
- generic result schema docs
- generic setup docs
- generic Codex skill skeletons
- public examples with fake IDs and fake names

## Private-only

Private-only content includes:

- real user identity
- real school identity
- real course names if tied to a user
- real course IDs
- real assignment IDs when tied to a user
- instructor names
- emails
- private incident logs
- real submitted drafts
- `SECRETS.md`
- `runs/`
- `final_drafts/`
- private course-specific skills
- long-term private product strategy docs unless explicitly sanitized

## Remote Rule

- `origin`: private working remote.
- `upstream`: public framework mirror.

Before anything is pushed to `upstream`, verify that it is generic framework content.

## Codex-Specific Rule

Codex docs and skills should be public-safe by default. If a Codex file needs private context, put that context in local/user config or `SECRETS.md`, not in the repo-level instruction file.

