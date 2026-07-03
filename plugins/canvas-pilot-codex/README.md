# Canvas Pilot Codex Plugin

Public-safe Codex plugin package for Canvas Pilot.

Packaging mode: manifest-only. This package declares the public-safe repo
skills that belong in the sidecar, while the repo-local `.agents/skills/**`
directories remain the source of truth for the skill payloads.

Declared skills:

- canvas-bootstrap
- canvas-setup
- canvas-scan
- canvas-execute
- canvas-skip
- cc-sync-runner
- cc-sync-execute-loop

Do not package private Claude course skills.

