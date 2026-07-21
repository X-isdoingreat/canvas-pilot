# SPDX-License-Identifier: AGPL-3.0-or-later
"""Skill base class with the standard lifecycle.

Each skill subclasses Skill and implements draft(). The lifecycle:
    read_requirements() -> requirements.md
    plan()              -> plan.md
    draft()             -> draft/ (skill-specific)
    verify()            -> verify.log
    finalize()          -> mark complete or submit
"""
from __future__ import annotations

import json
import re
import traceback
from html import unescape
from pathlib import Path

from .. import canvas_client as cv


def slugify(s: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_\- ]", "", s or "")
    return re.sub(r"\s+", "_", s).strip("_")[:60] or "untitled"


def html_to_text(html: str | None) -> str:
    if not html:
        return ""
    txt = re.sub(r"<br\s*/?>", "\n", html)
    txt = re.sub(r"</p>", "\n\n", txt)
    txt = re.sub(r"<[^>]+>", "", txt)
    return unescape(txt).strip()


class Skill:
    name: str = "base"

    def __init__(self, item: dict, run_dir: Path):
        self.item = item
        self.run_dir = run_dir
        course_slug = slugify(item["course_name"])
        asg_slug = slugify(item["name"])
        self.work_dir = run_dir / f"{course_slug}__{asg_slug}"
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.assignment: dict | None = None

    # ---- helpers ----
    def log(self, msg: str):
        print(f"  [{self.name}] {msg}")

    def write(self, name: str, content: str) -> Path:
        p = self.work_dir / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return p

    # ---- lifecycle ----
    def fetch_assignment(self) -> dict:
        a = cv.get_assignment(self.item["course_id"], self.item["assignment_id"])
        self.assignment = a
        (self.work_dir / "assignment.json").write_text(
            json.dumps(a, indent=2, default=str), encoding="utf-8"
        )
        return a

    def download_attachments(self) -> list[Path]:
        a = self.assignment or self.fetch_assignment()
        files: list[Path] = []
        for fid in cv.extract_file_ids(a.get("description")):
            try:
                meta = cv.get_file(fid)
                url = meta.get("url")
                fname = meta.get("display_name") or f"file_{fid}"
                if url:
                    dest = self.work_dir / "attachments" / fname
                    cv.download_file(url, dest)
                    files.append(dest)
                    self.log(f"downloaded {fname}")
            except Exception as e:
                self.log(f"attachment {fid} failed: {e}")
        return files

    def read_requirements(self) -> str:
        a = self.assignment or self.fetch_assignment()
        body = html_to_text(a.get("description"))
        req = (
            f"# {a.get('name')}\n\n"
            f"- course: {self.item['course_name']}\n"
            f"- due: {a.get('due_at')}\n"
            f"- points: {a.get('points_possible')}\n"
            f"- submission_types: {a.get('submission_types')}\n"
            f"- url: {a.get('html_url')}\n\n"
            f"## Description\n\n{body}\n"
        )
        self.write("requirements.md", req)
        return body

    def plan(self) -> str:
        return ""

    def draft(self) -> dict:
        raise NotImplementedError

    def verify(self) -> str:
        return ""

    def run(self) -> dict:
        try:
            self.fetch_assignment()
            self.read_requirements()
            self.download_attachments()
            plan = self.plan()
            if plan:
                self.write("plan.md", plan)
            result = self.draft()
            v = self.verify()
            if v:
                self.write("verify.log", v)
            return result
        except Exception as e:
            traceback.print_exc()
            return {"status": "error", "message": str(e)}
