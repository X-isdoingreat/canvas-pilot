# SPDX-License-Identifier: AGPL-3.0-or-later
"""Probe script for the gws-docs PDF annotation path.

Goal: prove we can:
  1. Create a Google Doc
  2. Insert paragraphs and inline annotations beneath each one
  3. Export to PDF via gws drive

Run: python -m src.skills.ac_english_probe
This is a smoke test, not part of the main router.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent.parent / "runs" / "_probe"
OUT.mkdir(parents=True, exist_ok=True)


def gws(*args, input_data=None) -> dict:
    """Run gws CLI, parse JSON if possible."""
    cmd = ["gws", *args]
    print(">>", " ".join(cmd))
    r = subprocess.run(cmd, input=input_data, capture_output=True, text=True)
    if r.returncode != 0:
        print("stderr:", r.stderr)
        raise SystemExit(f"gws failed: {' '.join(cmd)}")
    try:
        return json.loads(r.stdout)
    except Exception:
        return {"raw": r.stdout}


def main():
    # 1. Create document
    doc = gws("docs", "documents", "create", "--title", "Canvas Skill probe")
    doc_id = doc.get("documentId") or doc.get("document_id") or doc.get("id")
    if not doc_id:
        print("create response:", doc)
        raise SystemExit("could not get documentId")
    print("created doc:", doc_id)

    # 2. Append text via the +write helper if it exists
    sample = (
        "This is a probe paragraph one. The writer talk about a topic.\n"
        "Note: main idea is the writer's first claim.\n\n"
        "This is a probe paragraph two. It have another point.\n"
        "Note: the writer give example to support.\n"
    )
    try:
        gws("docs", "+write", doc_id, "--text", sample)
    except SystemExit:
        # fall back to batchUpdate
        body = {"requests": [{
            "insertText": {"location": {"index": 1}, "text": sample}
        }]}
        gws("docs", "documents", "batchUpdate", doc_id,
            "--requests", json.dumps(body["requests"]))

    # 3. Export to PDF via drive
    try:
        # gws drive files export -- this depends on gws version; leave as TODO marker
        out_pdf = OUT / "probe.pdf"
        r = subprocess.run([
            "gws", "drive", "files", "export", doc_id,
            "--mime-type", "application/pdf",
        ], capture_output=True)
        if r.returncode == 0 and r.stdout:
            out_pdf.write_bytes(r.stdout)
            print(f"PDF written: {out_pdf} ({out_pdf.stat().st_size} bytes)")
        else:
            print("export stderr:", r.stderr.decode(errors="ignore")[:500])
            print("(export path may need adjustment for installed gws version)")
    except Exception as e:
        print(f"export failed: {e}")

    print("\nProbe done. doc_id:", doc_id)
    print("If the PDF wasn't produced, the gws docs path is good but drive export needs work.")


if __name__ == "__main__":
    main()
