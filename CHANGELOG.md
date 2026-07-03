# Changelog

All notable changes to Canvas Pilot are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

> **Why this file is hand-written.** The public repo is published as a single
> force-pushed snapshot (`scripts/push_public_snapshot.py` archives the dev repo
> and force-pushes one commit), so its git history does **not** accumulate — you
> can't derive a changelog from `git log` on the public fork. This file is
> therefore a manually maintained record of notable changes; add a line here
> before each snapshot.

## [Unreleased]

### Added

- Community health files: `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1),
  `CONTRIBUTING.md`, and `SECURITY.md`, cross-linked from `README.md`.
- `.github/` templates: bug-report and feature-request issue templates (each
  leading with a privacy warning), an issue `config.yml`, and a pull-request
  template that mirrors the contribution ground rules.
- Continuous integration (`.github/workflows/codex.yml`): runs the offline test
  runners on Python 3.11 and 3.12 for every push and pull request.
- `requirements.txt` is now tracked, so the documented
  `pip install -r requirements.txt` works on a fresh clone.
- README badges (license, Python version).

### Changed

- The humanizer skill family was genericized (school/identity specifics removed)
  and is now published in the public repo.
- Renamed the in-page quiz skill `canvas-quiz` → `canvas-inside`.
- Adopted AGPL-3.0-or-later as the project license; public Python files carry an
  SPDX header.
