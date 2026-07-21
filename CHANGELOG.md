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

- `daily-work-tweet`, an evidence-gathering Codex skill that indexes one local day's work
  across fixed disks, Git repositories, Codex completion summaries, linked
  Vercel projects, and available GitHub evidence, then turns the strongest
  verified story into private-safe Chinese and English X drafts.
- A complete Codex-native Canvas runtime: setup/login recovery, enriched scan,
  deterministic approval, sequential execute, course drafting skills,
  humanizer workflows, `canvas-submit`, and disabled-first scan/email/submit
  cron templates.
- Shared run-state, direct Codex runner, stable route/work-directory helpers,
  and target-exact mutation authorization/usage primitives with isolated
  Canvas integration coverage.
- `canvas-skill-opportunity`, a read-only first-run advisor that discovers
  recurring Canvas work, inspects representative real specs and sanitized
  retry/feedback-policy evidence, writes a private local recommendation, and
  stops for the student's numbered choice.
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

- Codex is now the sole primary driver; `.claude/` remains frozen legacy
  history rather than an active runtime dependency.
- Codex hooks now use canonical `[features].hooks = true`, with fresh child
  sessions explicitly launched using `--enable hooks`.

- The redesigned bilingual landing pages are now the canonical `/install` and
  `/zh/install` experiences. The previous long-form setup and assignment-fit
  guides remain available at `/setup` and `/zh/setup`, with route-contract
  validation preventing old static install files from shadowing the landing
  pages again.
- The public home page now leads with the repetitive-homework value proposition,
  previews an expandable first-run prompt before copying it to an Agent, and
  exposes a localized Chinese `/zh` page with matching hero proportions. Its
  workflow comparison now shows the same four weekly steps completed manually
  or automated together as one Skill. A below-fold How it works series reserves
  empty video slots with Quiz first, without pretending unpublished videos are
  playable.
- Public-site GitHub links now open in a separate browser tab and retain the
  Canvas Pilot page, with `noopener` and `noreferrer` isolation.
- Fresh-clone setup now asks which school the user accesses Canvas through
  after download, resolves the school's official Canvas login URL (asking for
  the URL only when ambiguous, never guessing), completes browser
  authentication, and immediately runs opportunity analysis before
  `canvas-bootstrap`. The English and Chinese prompts stop for a numbered
  choice before route creation or homework scanning.
- First-skill selection now uses qualitative agent judgment instead of fixed
  0-100 scoring. It broadly favors code, objective quizzes, quantitative and
  structured document work, treats a continuous prose unit around 200 words as
  a strong demoter, and promotes quizzes with a useful feedback-and-retry loop.
- SSO password capture and persistence are now disabled by default. Explicit
  opt-in requires DPAPI or Fernet, base64 writes are refused, and credential
  cleanup failures stop setup instead of being silently ignored.
- The humanizer skill family was genericized (school/identity specifics removed)
  and is now published in the public repo.
- Renamed the in-page quiz skill `canvas-quiz` → `canvas-inside`.
- Adopted AGPL-3.0-or-later as the project license; public Python files carry an
  SPDX header.

### Security

- Canvas writes require short-lived HMAC receipts bound to one origin, Codex
  session, target, and exact action set, plus replay-aware usage accounting,
  terminal consumption, and authoritative Canvas read-back.
- Execute now archives pre-existing approved results and binds prepared result
  slots to the current plan digest before dispatch, preventing a valid result
  from an earlier run from being accepted as current evidence.
- Public-snapshot boundaries now ignore transient Codex locks and export-ignore
  tracked local dated notes in addition to the existing PII audit.

### Fixed

- Retrying a previously failed assignment now re-dispatches its course skill
  against the current real specification instead of silently reusing the old
  `result.json` from the stable work directory.
