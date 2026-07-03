# Codex Automation

Use automation only after the local batch loop is stable.

## Non-Interactive Command

Bound one run to one batch:

```powershell
codex exec "Run python scripts\codex_check.py --batch B4 and fix only files allowed by B4 until it passes or blocks."
```

Do not use non-interactive automation for live Canvas submission, quiz action,
or cookie capture.

## Batch Rule

Automation must name one batch:

```text
--batch B<N>
```

It must not silently continue to another batch unless the workflow explicitly
uses `$cc-sync-runner` Roadmap Until Blocked mode.

## Auth Rule

CI and non-interactive automation must not use committed auth.

Never commit:

- `.env`
- `.cookies/`
- Canvas cookies
- browser session files

Use fake/offline fixtures in CI.

