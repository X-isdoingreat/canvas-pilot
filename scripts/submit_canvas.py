# SPDX-License-Identifier: AGPL-3.0-or-later
"""Generic Canvas submitter — upload one or more files to a Canvas assignment.

Reads course id and assignment ids from arguments (or from SECRETS.md by name
if you want to invoke by symbolic key in the future). Specific course/assignment
IDs live in SECRETS.md, NOT here, to keep the script committable without leaking
identifiers.

Usage examples:

    # Single file submit:
    python -m scripts.submit_canvas \\
        --course-id <course_id> \\
        --assignment-id <assignment_id> \\
        --file path/to/draft.bundle

    # Multiple files (assignments are submitted independently):
    python -m scripts.submit_canvas \\
        --batch \\
        <course_id>:<asg1_id>:path/to/p1.py \\
        <course_id>:<asg2_id>:path/to/p2.pdf

The script verifies each upload and prints SUCCESS/FAIL per item.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src import canvas_submit_origin as cso


def submit_one(course_id: str, assignment_id: str, file_path: Path) -> dict:
    """Returns {label, status, ...details}. status in (OK, missing, upload-fail,
    submit-fail, verify-fail, already-submitted).

    Submit path goes through `cso.upload_and_submit_files_with_view`,
    which runs a pre-gate (re-reads assignment + submission) and a
    post-verify (re-reads submission) around `cv.submit_files`. If the
    pre-gate sees `workflow_state == "submitted"` we abort with
    `already-submitted` instead of stacking another attempt on top."""
    label = f"{course_id}:{assignment_id} ({file_path.name})"
    result = {"label": label, "course_id": course_id, "assignment_id": assignment_id,
              "file": str(file_path)}

    if not file_path.exists():
        result["status"] = "missing"
        return result

    print(f"\n=== {label} ===")
    print(f"  draft: {file_path} ({file_path.stat().st_size} bytes)")

    try:
        verify = cso.upload_and_submit_files_with_view(
            course_id, assignment_id, [file_path]
        )
    except cso.AlreadySubmitted as e:
        result["status"] = "already-submitted"
        result["existing_attempt"] = e.submission.get("attempt")
        result["existing_submitted_at"] = e.submission.get("submitted_at")
        print(f"  pre-gate: already submitted "
              f"(attempt={e.submission.get('attempt')}, "
              f"at={e.submission.get('submitted_at')})")
        return result
    except RuntimeError as e:
        # upload_submission_file returned no id for at least one file.
        result["status"] = "upload-fail"
        result["error"] = str(e)
        return result
    except Exception as e:
        result["status"] = "submit-fail"
        result["error"] = str(e)
        return result

    attachments = verify.get("attachments") or []
    print(f"  verify: workflow={verify.get('workflow_state')} "
          f"attempt={verify.get('attempt')} at={verify.get('submitted_at')}")
    for att in attachments:
        print(f"    attachment: {att.get('display_name')} ({att.get('size')} bytes)")
    if verify.get("workflow_state") in ("submitted", "graded"):
        result["status"] = "OK"
        result["attempt"] = verify.get("attempt")
        result["submitted_at"] = verify.get("submitted_at")
        result["attachments"] = [a.get("display_name") for a in attachments]
    else:
        result["status"] = "verify-fail"
        result["state"] = verify.get("workflow_state")

    return result


def main():
    p = argparse.ArgumentParser(description="Upload + submit a file to a Canvas assignment.")
    p.add_argument("--course-id", help="Canvas course id (single submission mode)")
    p.add_argument("--assignment-id", help="Canvas assignment id (single submission mode)")
    p.add_argument("--file", help="Path to file to upload (single submission mode)")
    p.add_argument("--batch", action="store_true",
                   help="Batch mode: pass multiple <course>:<asg>:<path> tuples as positional args")
    p.add_argument("items", nargs="*", help="Batch items (only with --batch)")
    args = p.parse_args()

    if args.batch:
        if not args.items:
            p.error("--batch requires at least one <course>:<asg>:<path> item")
        results = []
        for item in args.items:
            parts = item.split(":", 2)
            if len(parts) != 3:
                print(f"SKIP malformed item: {item}")
                continue
            course_id, assignment_id, file_str = parts
            results.append(submit_one(course_id, assignment_id, Path(file_str)))
    else:
        if not (args.course_id and args.assignment_id and args.file):
            p.error("non-batch mode requires --course-id, --assignment-id, and --file")
        results = [submit_one(args.course_id, args.assignment_id, Path(args.file))]

    print("\n\n=== SUMMARY ===")
    n_ok = 0
    for r in results:
        marker = "OK" if r["status"] == "OK" else "!!"
        print(f"  {marker} {r['label']}: {r['status']}")
        if r["status"] != "OK" and "error" in r:
            print(f"      {r['error']}")
        if r["status"] == "OK":
            n_ok += 1

    print(f"\n{n_ok}/{len(results)} succeeded")
    sys.exit(0 if n_ok == len(results) else 1)


if __name__ == "__main__":
    main()
