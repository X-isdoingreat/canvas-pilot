# SPDX-License-Identifier: AGPL-3.0-or-later
"""Submit an assignment only with a target-exact signed receipt.

Single-target examples::

    python -m scripts.submit_canvas \
      --course-id <course> --assignment-id <assignment> \
      --file C:/path/to/draft.pdf \
      --authorization-receipt C:/path/to/mutation_authorization.json

    python -m scripts.submit_canvas \
      --course-id <course> --assignment-id <assignment> \
      --text-file C:/path/to/answer.txt \
      --authorization-receipt C:/path/to/mutation_authorization.json

Batch submission uses ``--batch-manifest``.  JSON fields carry Windows paths
without colon-delimited parsing, and every target must name its own receipt::

    [
      {
        "course_id": "course-a",
        "assignment_id": "assignment-a",
        "files": ["C:/drafts/a.pdf"],
        "authorization_receipt": "C:/receipts/a.json"
      },
      {
        "course_id": "course-b",
        "assignment_id": "assignment-b",
        "text_file": "C:/drafts/b.txt",
        "authorization_receipt": "C:/receipts/b.json"
      }
    ]

Receipt signatures and expiry are enforced again at the Canvas mutation
boundary.  This script additionally checks target/action metadata before it
performs even the authoritative Canvas pre-read.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.authorization import AuthorizationDenied, load_authorization_receipt


_FILE_ACTIONS = frozenset(
    {
        "assignment.upload_init",
        "assignment.upload_blob",
        "assignment.submit_files",
    }
)
_TEXT_ACTIONS = frozenset({"assignment.submit_text"})
_URL_ACTIONS = frozenset({"assignment.submit_url"})
_BATCH_KEYS = frozenset(
    {
        "course_id",
        "assignment_id",
        "authorization_receipt",
        "files",
        "text",
        "text_file",
        "url",
    }
)


class SubmissionInputError(ValueError):
    """Submission input or receipt scope is structurally unsafe."""


def _submission_origin():
    # Keep module import safe in a clean clone that has no Canvas environment.
    # The real client (and therefore auth/session setup) is loaded only for an
    # actual submission call.
    from src import canvas_submit_origin

    return canvas_submit_origin


def _load_receipt(value: Mapping[str, Any] | Path | str) -> dict[str, Any]:
    if isinstance(value, Mapping):
        receipt = dict(value)
    else:
        try:
            receipt = load_authorization_receipt(value)
        except AuthorizationDenied as exc:
            raise SubmissionInputError(str(exc)) from exc
    if not isinstance(receipt.get("receipt_id"), str) or not receipt["receipt_id"].strip():
        raise SubmissionInputError("authorization receipt requires receipt_id")
    return receipt


def _require_receipt_scope(
    value: Mapping[str, Any] | Path | str,
    *,
    course_id: str,
    assignment_id: str,
    required_actions: frozenset[str],
) -> dict[str, Any]:
    receipt = _load_receipt(value)
    if receipt.get("target_type") != "assignment":
        raise SubmissionInputError("submission receipt target_type must be assignment")
    if str(receipt.get("course_id")) != str(course_id):
        raise SubmissionInputError("submission receipt course does not match target")
    if str(receipt.get("target_id")) != str(assignment_id):
        raise SubmissionInputError("submission receipt assignment does not match target")
    actions = receipt.get("actions")
    if not isinstance(actions, list) or any(not isinstance(action, str) for action in actions):
        raise SubmissionInputError("submission receipt actions must be a list of exact names")
    missing = required_actions - set(actions)
    if missing:
        raise SubmissionInputError(
            "submission receipt does not declare required action(s): "
            + ", ".join(sorted(missing))
        )
    return receipt


def _result_from_verify(result: dict[str, Any], verify: Mapping[str, Any]) -> dict[str, Any]:
    attachments = verify.get("attachments") or []
    print(
        f"  verify: workflow={verify.get('workflow_state')} "
        f"attempt={verify.get('attempt')} at={verify.get('submitted_at')}"
    )
    for attachment in attachments:
        if isinstance(attachment, Mapping):
            print(
                f"    attachment: {attachment.get('display_name')} "
                f"({attachment.get('size')} bytes)"
            )
    if verify.get("workflow_state") in {"submitted", "graded"}:
        result.update(
            {
                "status": "OK",
                "attempt": verify.get("attempt"),
                "submitted_at": verify.get("submitted_at"),
                "workflow_state": verify.get("workflow_state"),
                "readback_verified": True,
                "attachments": [
                    attachment.get("display_name")
                    for attachment in attachments
                    if isinstance(attachment, Mapping)
                ],
            }
        )
    else:
        result.update({"status": "verify-fail", "state": verify.get("workflow_state")})
    return result


def _already_submitted(result: dict[str, Any], exc: Any) -> dict[str, Any]:
    result.update(
        {
            "status": "already-submitted",
            "existing_attempt": exc.submission.get("attempt"),
            "existing_submitted_at": exc.submission.get("submitted_at"),
        }
    )
    print(
        "  pre-gate: already submitted "
        f"(attempt={exc.submission.get('attempt')}, "
        f"at={exc.submission.get('submitted_at')})"
    )
    return result


def submit_files_one(
    course_id: str,
    assignment_id: str,
    file_paths: Sequence[Path | str],
    *,
    authorization_receipt: Mapping[str, Any] | Path | str,
    submission_origin=None,
) -> dict[str, Any]:
    """Upload one or more files and pass the exact receipt through every write."""

    receipt = _require_receipt_scope(
        authorization_receipt,
        course_id=course_id,
        assignment_id=assignment_id,
        required_actions=_FILE_ACTIONS,
    )
    paths = [Path(path) for path in file_paths]
    label = f"{course_id}:{assignment_id} ({', '.join(path.name for path in paths)})"
    result: dict[str, Any] = {
        "label": label,
        "course_id": course_id,
        "assignment_id": assignment_id,
        "files": [str(path) for path in paths],
    }
    if not paths or any(not path.is_file() for path in paths):
        result["status"] = "missing"
        return result

    print(f"\n=== {label} ===")
    for path in paths:
        print(f"  draft: {path} ({path.stat().st_size} bytes)")
    origin = submission_origin or _submission_origin()
    try:
        verify = origin.upload_and_submit_files_with_view(
            course_id,
            assignment_id,
            paths,
            authorization_receipt=receipt,
        )
    except origin.AlreadySubmitted as exc:
        return _already_submitted(result, exc)
    except RuntimeError as exc:
        result.update({"status": "upload-fail", "error": str(exc)})
        return result
    except Exception as exc:  # Canvas/network errors become an item result.
        result.update({"status": "submit-fail", "error": str(exc)})
        return result
    return _result_from_verify(result, verify)


def submit_one(
    course_id: str,
    assignment_id: str,
    file_path: Path | str,
    *,
    authorization_receipt: Mapping[str, Any] | Path | str,
    submission_origin=None,
) -> dict[str, Any]:
    """Compatibility wrapper for one file; receipt is deliberately required."""

    return submit_files_one(
        course_id,
        assignment_id,
        [file_path],
        authorization_receipt=authorization_receipt,
        submission_origin=submission_origin,
    )


def submit_text_one(
    course_id: str,
    assignment_id: str,
    body: str,
    *,
    authorization_receipt: Mapping[str, Any] | Path | str,
    submission_origin=None,
) -> dict[str, Any]:
    """Submit a text-entry response and pass the exact receipt to the wrapper."""

    if not isinstance(body, str) or not body.strip():
        raise SubmissionInputError("text submission body must be non-empty")
    receipt = _require_receipt_scope(
        authorization_receipt,
        course_id=course_id,
        assignment_id=assignment_id,
        required_actions=_TEXT_ACTIONS,
    )
    label = f"{course_id}:{assignment_id} (text entry)"
    result: dict[str, Any] = {
        "label": label,
        "course_id": course_id,
        "assignment_id": assignment_id,
        "text_chars": len(body),
    }
    print(f"\n=== {label} ===")
    print(f"  draft: text entry ({len(body)} characters)")
    origin = submission_origin or _submission_origin()
    try:
        verify = origin.submit_text_with_view(
            course_id,
            assignment_id,
            body,
            authorization_receipt=receipt,
        )
    except origin.AlreadySubmitted as exc:
        return _already_submitted(result, exc)
    except Exception as exc:
        result.update({"status": "submit-fail", "error": str(exc)})
        return result
    return _result_from_verify(result, verify)


def submit_url_one(
    course_id: str,
    assignment_id: str,
    url: str,
    *,
    authorization_receipt: Mapping[str, Any] | Path | str,
    submission_origin=None,
) -> dict[str, Any]:
    """Submit one non-empty URL with exact assignment.submit_url authority."""

    if not isinstance(url, str) or not url.strip():
        raise SubmissionInputError("URL submission value must be non-empty")
    receipt = _require_receipt_scope(
        authorization_receipt,
        course_id=course_id,
        assignment_id=assignment_id,
        required_actions=_URL_ACTIONS,
    )
    normalized = url.strip()
    label = f"{course_id}:{assignment_id} (URL entry)"
    result: dict[str, Any] = {
        "label": label,
        "course_id": course_id,
        "assignment_id": assignment_id,
        "url": normalized,
    }
    print(f"\n=== {label} ===")
    origin = submission_origin or _submission_origin()
    try:
        verify = origin.submit_url_with_view(
            course_id,
            assignment_id,
            normalized,
            authorization_receipt=receipt,
        )
    except origin.AlreadySubmitted as exc:
        return _already_submitted(result, exc)
    except Exception as exc:
        result.update({"status": "submit-fail", "error": str(exc)})
        return result
    return _result_from_verify(result, verify)


def _path_from_manifest(base: Path, value: Any, field: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise SubmissionInputError(f"batch {field} must be a non-empty path")
    path = Path(value)
    return path if path.is_absolute() else base / path


def _target_id(value: Any, field: str) -> str:
    if isinstance(value, bool) or value in (None, "") or not str(value).strip():
        raise SubmissionInputError(f"batch item requires {field}")
    return str(value)


def load_batch_manifest(path: Path | str) -> list[dict[str, Any]]:
    """Load a Windows-safe target-to-receipt manifest and reject reuse."""

    manifest_path = Path(path)
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SubmissionInputError(f"batch manifest cannot be loaded: {exc}") from exc
    if not isinstance(payload, list) or not payload:
        raise SubmissionInputError("batch manifest must be a non-empty JSON list")

    jobs: list[dict[str, Any]] = []
    seen_targets: set[tuple[str, str]] = set()
    receipt_targets: dict[str, tuple[str, str]] = {}
    base = manifest_path.parent
    for position, raw in enumerate(payload, start=1):
        if not isinstance(raw, Mapping):
            raise SubmissionInputError(f"batch item {position} must be an object")
        unknown = set(raw) - _BATCH_KEYS
        if unknown:
            raise SubmissionInputError(
                f"batch item {position} has unsupported field(s): {sorted(unknown)}"
            )
        course_id = _target_id(raw.get("course_id"), "course_id")
        assignment_id = _target_id(raw.get("assignment_id"), "assignment_id")
        target = (course_id, assignment_id)
        if target in seen_targets:
            raise SubmissionInputError(f"batch target {target} is duplicated")
        seen_targets.add(target)

        payload_fields = [
            field for field in ("files", "text", "text_file", "url") if field in raw
        ]
        if len(payload_fields) != 1:
            raise SubmissionInputError(
                f"batch item {position} requires exactly one of files, text, text_file, url"
            )
        receipt_path = _path_from_manifest(
            base, raw.get("authorization_receipt"), "authorization_receipt"
        )
        field = payload_fields[0]
        required_actions = (
            _FILE_ACTIONS
            if field == "files"
            else _URL_ACTIONS
            if field == "url"
            else _TEXT_ACTIONS
        )
        receipt = _require_receipt_scope(
            receipt_path,
            course_id=course_id,
            assignment_id=assignment_id,
            required_actions=required_actions,
        )
        receipt_id = receipt["receipt_id"]
        previous_target = receipt_targets.get(receipt_id)
        if previous_target is not None and previous_target != target:
            raise SubmissionInputError(
                "one authorization receipt cannot be reused across different batch targets"
            )
        receipt_targets[receipt_id] = target

        job: dict[str, Any] = {
            "course_id": course_id,
            "assignment_id": assignment_id,
            "authorization_receipt": receipt,
        }
        if field == "files":
            values = raw["files"]
            if not isinstance(values, list) or not values:
                raise SubmissionInputError(f"batch item {position} files must be non-empty list")
            job["files"] = [
                _path_from_manifest(base, value, "files entry") for value in values
            ]
        elif field == "text_file":
            text_path = _path_from_manifest(base, raw["text_file"], "text_file")
            try:
                job["text"] = text_path.read_text(encoding="utf-8")
            except OSError as exc:
                raise SubmissionInputError(f"batch text_file cannot be read: {exc}") from exc
        elif field == "text":
            if not isinstance(raw["text"], str) or not raw["text"].strip():
                raise SubmissionInputError(f"batch item {position} text must be non-empty")
            job["text"] = raw["text"]
        else:
            if not isinstance(raw["url"], str) or not raw["url"].strip():
                raise SubmissionInputError(f"batch item {position} url must be non-empty")
            job["url"] = raw["url"].strip()
        jobs.append(job)
    return jobs


def _run_jobs(jobs: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for job in jobs:
        if "files" in job:
            result = submit_files_one(
                str(job["course_id"]),
                str(job["assignment_id"]),
                job["files"],
                authorization_receipt=job["authorization_receipt"],
            )
        elif "text" in job:
            result = submit_text_one(
                str(job["course_id"]),
                str(job["assignment_id"]),
                str(job["text"]),
                authorization_receipt=job["authorization_receipt"],
            )
        else:
            result = submit_url_one(
                str(job["course_id"]),
                str(job["assignment_id"]),
                str(job["url"]),
                authorization_receipt=job["authorization_receipt"],
            )
        results.append(result)
    return results


def _print_summary(results: Sequence[Mapping[str, Any]]) -> int:
    print("\n\n=== SUMMARY ===")
    succeeded = 0
    for result in results:
        ok = result.get("status") == "OK"
        marker = "OK" if ok else "!!"
        print(f"  {marker} {result.get('label')}: {result.get('status')}")
        if not ok and result.get("error"):
            print(f"      {result['error']}")
        succeeded += int(ok)
    print(f"\n{succeeded}/{len(results)} succeeded")
    return 0 if succeeded == len(results) else 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Submit Canvas work with one exact signed receipt per target"
    )
    parser.add_argument("--batch-manifest", type=Path)
    parser.add_argument("--course-id")
    parser.add_argument("--assignment-id")
    parser.add_argument("--file", action="append", dest="files")
    parser.add_argument("--text")
    parser.add_argument("--text-file", type=Path)
    parser.add_argument("--url")
    parser.add_argument("--authorization-receipt", type=Path)
    args = parser.parse_args(argv)

    try:
        if args.batch_manifest is not None:
            if any(
                value is not None
                for value in (
                    args.course_id,
                    args.assignment_id,
                    args.files,
                    args.text,
                    args.text_file,
                    args.url,
                    args.authorization_receipt,
                )
            ):
                raise SubmissionInputError(
                    "--batch-manifest cannot be combined with single-target arguments"
                )
            jobs = load_batch_manifest(args.batch_manifest)
        else:
            if not (args.course_id and args.assignment_id and args.authorization_receipt):
                raise SubmissionInputError(
                    "single-target mode requires --course-id, --assignment-id, "
                    "and --authorization-receipt"
                )
            payload_count = sum(
                value is not None
                for value in (args.files, args.text, args.text_file, args.url)
            )
            if payload_count != 1:
                raise SubmissionInputError(
                    "single-target mode requires exactly one of --file, --text, --text-file, --url"
                )
            receipt = _load_receipt(args.authorization_receipt)
            job: dict[str, Any] = {
                "course_id": args.course_id,
                "assignment_id": args.assignment_id,
                "authorization_receipt": receipt,
            }
            if args.files is not None:
                job["files"] = [Path(value) for value in args.files]
            elif args.text_file is not None:
                job["text"] = args.text_file.read_text(encoding="utf-8")
            elif args.url is not None:
                job["url"] = args.url
            else:
                job["text"] = args.text
            jobs = [job]
        results = _run_jobs(jobs)
    except (OSError, SubmissionInputError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return _print_summary(results)


if __name__ == "__main__":
    raise SystemExit(main())
