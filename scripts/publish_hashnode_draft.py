#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Create a Hashnode draft from a Markdown file.

Secrets are read from environment variables or an ignored env file:

  HASHNODE_TOKEN
  HASHNODE_PUBLICATION_ID

The script only creates drafts. It does not publish posts, edit profiles, or
change publication settings.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path


API_URL = "https://gql.hashnode.com"


class HashnodeApiError(RuntimeError):
    """Raised when Hashnode returns a non-usable API response."""


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def split_article_markdown(text: str) -> tuple[dict[str, str], str]:
    """Parse either YAML-ish front matter or the local label block format."""
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end == -1:
            raise ValueError("front matter starts with --- but has no closing ---")
        raw = text[4:end]
        body = text[end + len("\n---\n") :].strip() + "\n"
        meta = parse_colon_lines(raw)
        return meta, body

    marker = "\n---\n"
    if marker not in text:
        return {}, text.strip() + "\n"

    raw, body = text.split(marker, 1)
    meta = parse_label_blocks(raw)
    return meta, body.strip() + "\n"


def parse_colon_lines(text: str) -> dict[str, str]:
    meta: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            raise ValueError(f"invalid metadata line: {line!r}")
        key, value = line.split(":", 1)
        meta[normalize_key(key)] = value.strip()
    return meta


def parse_label_blocks(text: str) -> dict[str, str]:
    meta: dict[str, str] = {}
    current_key: str | None = None
    current_value: list[str] = []

    def flush() -> None:
        nonlocal current_key, current_value
        if current_key:
            meta[current_key] = "\n".join(current_value).strip()
        current_key = None
        current_value = []

    for line in text.splitlines():
        if line.endswith(":") and not line.startswith((" ", "\t")):
            flush()
            current_key = normalize_key(line[:-1])
            current_value = []
        elif current_key is not None:
            current_value.append(line)
    flush()
    return meta


def normalize_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")


def slugify_tag(tag: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", tag.lower()).strip("-")
    return slug or tag.lower()


def build_input(md_path: Path, publication_id: str) -> dict:
    meta, body = split_article_markdown(md_path.read_text(encoding="utf-8"))
    title = meta.get("title")
    if not title:
        raise ValueError("article metadata must include Title")

    subtitle = meta.get("subtitle") or meta.get("description")
    canonical_url = meta.get("canonical_url")
    tags = [
        {"name": tag.strip(), "slug": slugify_tag(tag.strip())}
        for tag in meta.get("tags", "").split(",")
        if tag.strip()
    ]

    draft_input: dict[str, object] = {
        "publicationId": publication_id,
        "title": title,
        "contentMarkdown": body,
    }
    if subtitle:
        draft_input["subtitle"] = subtitle
    if canonical_url:
        draft_input["originalArticleURL"] = canonical_url
    if tags:
        draft_input["tags"] = tags
    return draft_input


def graphql_request(token: str, query: str, variables: dict | None = None) -> dict:
    payload = {"query": query, "variables": variables or {}}
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": token,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "canvas-pilot-publisher",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise HashnodeApiError(f"Hashnode API HTTP {exc.code}: {body[:500]}") from exc

    stripped = raw.lstrip()
    if not stripped.startswith("{"):
        if "GraphQL API is moving to a paid offering" in raw:
            raise HashnodeApiError(
                "Hashnode GraphQL returned the paid API page instead of JSON. "
                "The publication/account needs Hashnode Pro/API access before automation can write."
            )
        raise HashnodeApiError("Hashnode GraphQL returned non-JSON HTML/text.")

    data = json.loads(raw)
    if data.get("errors"):
        raise HashnodeApiError(json.dumps(data["errors"], ensure_ascii=False))
    return data["data"]


def run_check(token: str) -> None:
    data = graphql_request(
        token,
        "query Viewer { me { id username name } }",
    )
    print(json.dumps(data, indent=2, ensure_ascii=False))


def create_draft(token: str, draft_input: dict) -> dict:
    mutation = """
    mutation CreateDraft($input: CreateDraftInput!) {
      createDraft(input: $input) {
        draft {
          id
          title
          slug
          url
        }
      }
    }
    """
    return graphql_request(token, mutation, {"input": draft_input})


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a Hashnode draft from Markdown.")
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env.publishing"),
        help="Ignored env file containing HASHNODE_TOKEN and optional HASHNODE_PUBLICATION_ID",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check", help="Verify token/API access without writing")

    draft_parser = subparsers.add_parser("draft", help="Create a Hashnode draft")
    draft_parser.add_argument("markdown", type=Path, help="Markdown file to convert")
    draft_parser.add_argument(
        "--publication-id",
        help="Hashnode publication ID; defaults to HASHNODE_PUBLICATION_ID",
    )

    args = parser.parse_args()
    load_env_file(args.env_file)

    token = os.environ.get("HASHNODE_TOKEN")
    if not token:
        print("missing HASHNODE_TOKEN", file=sys.stderr)
        return 2

    try:
        if args.command == "check":
            run_check(token)
            return 0

        publication_id = args.publication_id or os.environ.get("HASHNODE_PUBLICATION_ID")
        if not publication_id:
            print("missing --publication-id or HASHNODE_PUBLICATION_ID", file=sys.stderr)
            return 2

        md_path = args.markdown.resolve()
        if not md_path.exists():
            print(f"missing markdown file: {md_path}", file=sys.stderr)
            return 2

        draft_input = build_input(md_path, publication_id)
        result = create_draft(token, draft_input)
        draft = result["createDraft"]["draft"]
        print(json.dumps({
            "id": draft.get("id"),
            "title": draft.get("title"),
            "slug": draft.get("slug"),
            "url": draft.get("url"),
        }, indent=2, ensure_ascii=False))
        return 0
    except (HashnodeApiError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
