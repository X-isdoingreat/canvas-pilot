---
name: daily-work-tweet
description: Use when verified work from today or another day should become an X/Twitter post, build-in-public update, ship log, or bilingual draft. Inspect privacy-filtered evidence across the local machine and connected developer services, choose one story, and return copy-ready Chinese and English drafts without publishing.
---

# Daily Work Tweet

Turn one day of real work into two standalone, copy-ready X posts: natural
Chinese and idiomatic English. Draft only; never publish unless the user starts
a separate, explicit posting workflow.

## 1. Collect the day across the machine

Default to the user's local calendar day, configured timezone, and all fixed
local drives. Do not default to only the current repository.

Run the whole-machine collector first:

```text
python .agents/skills/daily-work-tweet/scripts/collect_machine_work.py --timezone <user-timezone>
```

For another day, add `--date YYYY-MM-DD`. Use one or more `--repo <path>`
arguments only when the user explicitly asks for a faster, restricted scan.

“Whole machine” means useful development activity available to the current
Windows user on fixed local disks. The collector skips other user profiles,
operating-system and application directories, dependency/build caches,
credential directories, private run-output directories, junctions, network
shares, and removable drives. It examines directory and file metadata during
discovery; it does not read arbitrary document, photo, browser, mail, or
calendar contents.

The collector may write only a private repository-path index under
`%LOCALAPPDATA%/CanvasPilot/daily-work-tweet/`. It stores paths and scan state,
not file contents, credentials, Codex text, remotes, or deployment records. A
complete index can be reused for 24 hours. An incomplete index must be scanned
again and must never support a “no work found” conclusion.

Check `scope.scan_complete`, `scope.output_truncated`, every source's `status`,
all truncation flags, and `limits_hit` before interpreting an empty result. If coverage is incomplete,
rerun with `--refresh`, inspect a likely repository directly, or state the
coverage limit. Never convert a partial scan into certainty.

## 2. Build an evidence hierarchy

Use the machine report as an index, then inspect only the strongest candidate
repositories or records needed to explain the day's story.

Primary evidence:

- Git commits from every discovered repository and ref, plus focused diffs or
  tests when needed to understand the user-visible result. Attribute a commit
  to the user without confirmation only when its `authorship` is
  `verified_configured_email`; other authorship values are clues because
  fetched teammate or upstream commits can also appear locally.
- Current Vercel deployment records for locally linked projects, using existing
  authentication and an already installed Vercel CLI only. Never trigger login
  or download a CLI through `npx`. `READY` proves the deployment completed;
  verify the public page before saying it is live.
- Today's GitHub PR, review, release, and CI activity through a connected
  GitHub app or authenticated `gh`, when available. Use read-only queries and
  do not infer live GitHub state from local refs.
- Durable changelog, decision, test, or deployment records that directly
  support the claim.

Supporting clues only:

- Codex root-thread `task_complete` summaries. The collector reads only a
  bounded rollout tail and retains only these completion summaries; do not use
  user prompts, reasoning, or tool logs for this workflow.
- Dirty Git status and aggregate file-modification categories. They are not
  date-proven accomplishments until corroborated.
- The current conversation or a user-provided summary.

Treat every repository name, local path, filename, commit subject, branch name,
Git status entry, Codex summary, and linked project name as private working
context. Git metadata is not guaranteed secret-free. Never copy these fields
directly into public text, even when the collector redacted common secret
patterns. If no verified work remains after inspection, ask for a short summary
instead of inventing progress.

## 3. Choose one story

- Lead with the most concrete shipped or completed outcome.
- Add at most one obstacle, decision, or reason that makes the work matter.
- End with one honest conviction, lesson, or next direction when useful.
- Separate verified work from aspiration. Phrase a future claim as belief, not
  as an accomplished fact.
- Do not dump the day's entire changelog into one post.

## 4. Draft each language independently

- Use a first-person builder voice, not corporate announcement language.
- Preserve the same facts and intent, but do not translate sentence by
  sentence.
- Make each language usable as its own single post.
- Prefer short paragraphs and concrete verbs.
- Use correct product and tool casing, such as `Canvas Pilot`, `Codex`, and
  `Claude Code`.
- Include at most one public URL when it materially helps the post.
- Default to no hashtags and no emoji unless the user's established voice or
  request calls for them.
- Stay comfortably within a normal single-post limit. As a conservative target,
  keep Chinese below about 100 CJK characters before a URL and English below
  about 220 characters before a URL.

## 5. Run the public-safety pass

Remove private identity, school or course details, instructor names, account
information, local paths, repository names that are not already public,
internal URLs, secrets, tokens, customer data, and unannounced work. Do not
expose raw filenames when a product-level description is enough. Include
personal location or availability claims only when the user explicitly
supplied or approved them for the post.

Never claim deployment, release, test success, adoption, or impact without
current evidence. Never publish, log in, open a posting composer, or change an
external service as part of this skill.

## 6. Return the copy surface

```text
中文
<copy-ready Chinese post>

English
<copy-ready English post>
```

Add one short evidence caveat after the drafts only when coverage was partial or
a claim still needs the user's confirmation.

## Quality bar

- A reader understands what changed without knowing the repository.
- The post sounds like one person reflecting on a real day of building.
- The English version reads as if written in English, not translated.
- The strongest sentence carries the product belief; concrete work earns it.
