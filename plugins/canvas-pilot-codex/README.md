# Canvas Pilot Codex Plugin

Public-safe Codex plugin package for Canvas Pilot.

Packaging mode: manifest-only. This package declares the public-safe repo
skills that belong in the sidecar, while the repo-local `.agents/skills/**`
directories remain the source of truth for the skill payloads.

Declared skills:

- canvas-bootstrap
- canvas-setup
- canvas-skill-opportunity
- canvas-scan
- canvas-execute
- canvas-skip
- cc-sync-runner
- cc-sync-execute-loop

`canvas-skill-opportunity` is a read-only first-run advisor: it inspects
representative recurring-work specs and sanitized Canvas feedback-policy facts,
makes a qualitative recommendation, and stops for the user's numbered choice.
It does not start attempts, solve work, retain raw answers or exact grades,
submit anything, or create routes before that choice.

Do not package private Claude course skills.

