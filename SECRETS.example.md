# SECRETS.example.md — template for SECRETS.md

> Copy this to `SECRETS.md` and fill in the real values. `SECRETS.md` is
> gitignored. This template is committed to document the schema only.
>
> For each new quarter, update `SECRETS.md` with the new course IDs, file
> IDs, etc. — skills should not require code changes.

---

## Identity

| Field | Value |
|---|---|
| Real name | <your name> |
| School email | <you>@<your-school>.edu |
| Canvas user_id | <int from /api/v1/users/self> |
| zyBooks user_id | <int from zyBooks JWT payload> |
| Discord user id | <copy from Discord with Developer Mode on> |
| Discord DM channel id | <create via POST /users/@me/channels with recipient_id> |
| Discord bot username | <your bot's name> |
| Discord bot id | <bot's snowflake> |

## Canvas

- Host: `<your school's canvas host, e.g. canvas.<your-school>.edu>`
- API base: `https://<host>/api/v1`

### Active courses (current quarter)

| course_id | name | instructor | skill (default) |
|---|---|---|---|
| <id> | <full course name> | <instructor> | <ac_english/code_py/quiz/zybooks/mixed_unsupported> |

### Skipped courses (training, archived)

- <id> <reason>

## Code course (the course routed to code_py)

- Instructor's external site: `https://<external spec site>`
- Schedule, project specs, exercise specs URLs

### Project IDs and assignment IDs

| Assignment | assignment_id | spec URL |
|---|---|---|

## Document / writing course

- Instructor email
- Module IDs
- File folder IDs (Readings, Examples, etc.)
- File ID table for the readings/articles
- Voice rules (B1-B2 / academic / etc.)
- In-class skip rules

## Quiz course

- Question count, time limit, attempts
- Standing authorization scope

## zyBooks math course

- Instructor
- zyBook code (URL-encode the `&`)
- zyBooks zybook_id
- zyBooks user_id
- Assignment kinds and how to handle them
- Week → zyBook section mapping
- Canvas assignment ids (HW + Exam)

## zyBooks API (if applicable)

- Auth scheme
- Base URL(s)
- Endpoints used
- Write API limitations

## Time-sensitive

- Timezone, DST switch dates
- Current quarter
- Note about UTC vs PT

## Notes for skill authors

- Always read SECRETS.md before hardcoding identifiers in a SKILL.md
- SECRETS.md is the "data" half; SKILL.md is the "logic" half
