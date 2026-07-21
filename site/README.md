# Canvas Pilot site

Static website for `https://canvas-pilot.likelyou.com`.

Deploy as an independent Vercel project:

1. Create a new Vercel project from `https://github.com/X-isdoingreat/canvas-pilot`.
2. Set Root Directory to `site`.
3. Add the custom domain `canvas-pilot.likelyou.com`.
4. In the DNS provider for `likelyou.com`, add:

```text
Type: CNAME
Name: canvas-pilot
Value: cname.vercel-dns.com
TTL: Auto
```

This directory is intentionally separate from the LikelyYou app so Canvas Pilot
has its own search identity, sitemap, robots policy, and llms.txt.

Canonical localized landing pages:

- English: `/install`
- 简体中文: `/zh/install`

Detailed setup and assignment-fit guides remain available at `/setup` and
`/zh/setup`. Vercel rewrites the canonical install URLs to the shared landing
page sources at `/index.html` and `/zh/index.html`.

Run the static site checks from this directory with:

```text
npm test
```
