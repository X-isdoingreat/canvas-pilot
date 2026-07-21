# Public / Private Boundary

Canvas Pilot uses one private development repository and publishes a sanitized
snapshot to a public mirror. The public mirror is not a second development
branch and no `upstream` workflow defines the privacy boundary.

## Public-safe

- generic Canvas/runtime/client logic;
- generic setup, scan, approval, execute, submission, cron, and state docs;
- public-safe `.agents/skills/canvas-*` framework skills;
- generic course skill skeletons and humanizer workflows;
- examples containing only synthetic identities and IDs.

Course skills are not private merely because they can produce homework. Their
tracked framework instructions must remain generic. Per-user, per-school,
per-course, and per-quarter behavior belongs in local overlays.

## Private-only

- real identity, school, course/assignment IDs, instructor names, emails, or
  account/session identifiers;
- real specs, readings, answers, drafts, submissions, grades, feedback, and
  incident logs tied to a user;
- `.env`, `SECRETS.md`, `courses.yaml`, `_private/`, `runs/`, `final_drafts/`,
  `.cookies/`, browser/zyBooks state, mutation receipts, signing keys, and
  receipt-usage ledgers;
- machine-specific task files, locks, absolute user paths, and local strategy
  notes not explicitly sanitized.

## Three enforcement layers

1. Tracked framework files are generic and public-safe by construction.
2. Private/runtime paths are gitignored. A tracked file is **not** protected by
   `.gitignore`; any tracked local-only file must also be `export-ignore` or be
   removed from the public candidate.
3. `scripts/push_public_snapshot.py` archives an explicit committed source ref
   with `git archive`, honors `.gitattributes export-ignore`, audits the exact
   archive for configured PII/path violations, and only then can publish one
   squashed commit to the public remote.

## Release rule

- A default dry run against `origin/main` proves only that ref. It does not
  audit uncommitted working-tree changes.
- After the intended change set is committed, run
  `python scripts/push_public_snapshot.py --source HEAD --dry-run` and inspect
  the exact file list/audit result.
- Never commit or push merely to perform validation. Public push is a separate
  external action requiring explicit user authorization.
- Before release, confirm `.claude/` stayed frozen unless legacy maintenance
  was explicitly requested, and confirm transient Codex lock files are ignored.

Codex docs and skills should be public-safe by default. If a workflow needs
private context, put it in user/local config, `SECRETS.md`, `courses.yaml`, or a
gitignored `_private/` overlay—not in tracked instructions.
