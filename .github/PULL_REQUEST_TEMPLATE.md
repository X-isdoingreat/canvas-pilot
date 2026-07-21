<!--
Thanks for contributing to Canvas Pilot. Keep PRs scoped to one concern.
Describe the change from the student's side, not just the diff.
-->

## What this changes

A short description — what's different for the *student* / user after this PR.

## Checklist

- [ ] PR is scoped to a single concern.
- [ ] `git add` named explicit paths — no `git add -A`, `git add .`, or `git add -f`.
- [ ] No personal/school-identifying data in the diff (course IDs, file IDs,
      instructor/school names, emails, cookies, JWTs, real drafts).
- [ ] If I touched a hook or the public/private boundary, I confirmed
      `check-public-leak.py` still blocks the bad cases.
- [ ] No school-/instructor-specific solving logic in tracked files (that belongs
      in a local `_private/` overlay).
- [ ] Ran the relevant test runner(s) — note which below.
- [ ] I agree my contribution is licensed under AGPL-3.0-or-later.

## Tests run

```
e.g. python tests/codex_runtime/run_all.py
```
