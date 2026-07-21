# Security Policy

Canvas Pilot is a local-first framework: it stores nothing on remote services,
and all credentials / cookies / drafts stay in gitignored paths on your machine.
The most likely "security" issue here is an **accidental leak of private data
into a tracked file** — a school name, course ID, email, cookie, or JWT slipping
past `.gitignore` or the leak-check hook.

## Reporting

Please do **not** open a public issue for anything sensitive.

- **Preferred:** email **X_isdoingreat@proton.me** with details and, if
  relevant, the commit / file / line.
- Alternatively, use GitHub's private vulnerability reporting
  (the repo **Security** tab → **Report a vulnerability**) if enabled.
- You can also DM [@X_isdoingreat](https://x.com/X_isdoingreat) on X to flag
  that a report is incoming.

Include enough to reproduce, and please allow a reasonable window for a fix
before any public disclosure.

## Scope and expectations

This is a single-maintainer personal framework, not a funded project — there is
no SLA. Reports are handled on a best-effort basis. Active leak /
credential-exposure paths take priority over everything else.

## If you find leaked data in git history

If you discover personal or school data committed in a past revision, report it
privately as above — do not amplify it. Any history-rewriting fix (a forced
re-anonymization, for example) will be coordinated through that report.
