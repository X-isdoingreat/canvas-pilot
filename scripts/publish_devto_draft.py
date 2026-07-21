#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Create or update a DEV/Forem draft from a Markdown file.

Secrets are read from environment variables only:

  DEVTO_API_KEY
  FOREM_API_KEY

The script defaults to draft mode and refuses to publish unless
`--publish` is explicitly passed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


API_BASE = "https://dev.to/api"


def split_front_matter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        raise ValueError("front matter starts with --- but has no closing ---")

    raw = text[4:end]
    body = text[end + len("\n---\n") :]
    meta: dict[str, str] = {}
    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            raise ValueError(f"invalid front matter line: {line!r}")
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip()
    return meta, body.strip() + "\n"


def api_request(method: str, path: str, key: str, payload: dict | None = None) -> dict:
    data = None
    headers = {
        "api-key": key,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "canvas-pilot-publisher",
    }
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        API_BASE + path,
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"DEV API {exc.code}: {body}") from exc


def build_article_payload(md_path: Path, publish: bool) -> dict:
    meta, body = split_front_matter(md_path.read_text(encoding="utf-8"))
    title = meta.get("title")
    if not title:
        raise ValueError("front matter must include title")

    tags = [
        tag.strip()
        for tag in meta.get("tags", "").split(",")
        if tag.strip()
    ]

    article: dict[str, object] = {
        "title": title,
        "body_markdown": body,
        "published": publish,
    }
    if tags:
        article["tags"] = tags
    if meta.get("description"):
        article["description"] = meta["description"]
    if meta.get("canonical_url"):
        article["canonical_url"] = meta["canonical_url"]

    return {"article": article}


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a DEV draft from Markdown.")
    parser.add_argument("markdown", type=Path, help="Markdown file with DEV front matter")
    parser.add_argument("--publish", action="store_true", help="Publish instead of creating a draft")
    args = parser.parse_args()

    key = os.environ.get("DEVTO_API_KEY") or os.environ.get("FOREM_API_KEY")
    if not key:
        print("missing DEVTO_API_KEY or FOREM_API_KEY", file=sys.stderr)
        return 2

    md_path = args.markdown.resolve()
    if not md_path.exists():
        print(f"missing markdown file: {md_path}", file=sys.stderr)
        return 2

    payload = build_article_payload(md_path, publish=args.publish)
    result = api_request("POST", "/articles", key, payload)
    print(json.dumps({
        "id": result.get("id"),
        "url": result.get("url"),
        "published": result.get("published"),
        "title": result.get("title"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
