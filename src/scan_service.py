# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read-only, enriched Canvas assignment scanning for the Codex product path."""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from .routes import has_lockdown_browser, normalize_routes, resolve_route


PT = ZoneInfo("America/Los_Angeles")
DONE_LIVE_STATES = {"submitted", "graded", "pending_review"}


class IncompleteScanError(RuntimeError):
    """One or more configured courses could not be scanned."""

    def __init__(self, payload: dict[str, Any]):
        super().__init__("one or more configured courses failed to scan")
        self.payload = payload


def _parse_time(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _utc_now(value: dt.datetime | None) -> dt.datetime:
    if value is None:
        return dt.datetime.now(dt.timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=dt.timezone.utc)
    return value.astimezone(dt.timezone.utc)


def normalize_live_state(value: Any) -> str:
    if value in {"unsubmitted", "submitted", "graded", "pending_review"}:
        return str(value)
    return "unknown"


def is_actionable_assignment(
    assignment: Mapping[str, Any],
    window_days: int,
    *,
    now: dt.datetime | None = None,
) -> bool:
    """Whether an assignment belongs in the actionable scan candidate set.

    Future work is bounded by ``window_days``.  Overdue work remains visible
    while Canvas has not marked it complete and its lock time has not passed;
    this fixes the old one-hour cutoff that silently erased actionable late
    work.
    """

    current = _utc_now(now)
    embedded = assignment.get("submission") or {}
    if normalize_live_state(embedded.get("workflow_state")) in DONE_LIVE_STATES:
        return False

    lock_at = _parse_time(assignment.get("lock_at"))
    if lock_at is not None and lock_at < current:
        return False
    due = _parse_time(assignment.get("due_at"))
    if due is None:
        # Canvas permits no-due assignments.  They belong in the explicit
        # unknown bucket rather than disappearing from the approval surface.
        return True
    if due > current + dt.timedelta(days=window_days):
        return False
    return True


def bucket_for(hours_left: float | None, live_state: str = "unknown") -> str:
    if hours_left is None:
        return "unknown"
    if hours_left <= 0:
        # Only a confirmed not-submitted state earns the overdue label.  A
        # failed live-state lookup must remain loud but uncertain.
        return "overdue" if live_state == "unsubmitted" else "urgent"
    if hours_left <= 72:
        return "urgent"
    if hours_left <= 168:
        return "soon"
    return "later"


def _base_item(
    course_id: str,
    route: Mapping[str, Any],
    assignment: Mapping[str, Any],
) -> dict[str, Any]:
    decision = resolve_route(route, assignment)
    item = {
        "course_id": course_id,
        "course_name": route["name"],
        "skill": decision.skill,
        "configured_skill": decision.configured_skill,
        "assignment_id": str(assignment.get("id")),
        "name": assignment.get("name"),
        "due_at": assignment.get("due_at"),
        "lock_at": assignment.get("lock_at"),
        "html_url": assignment.get("html_url"),
        "submission_types": list(assignment.get("submission_types") or []),
        "points_possible": assignment.get("points_possible"),
        "quiz_id": assignment.get("quiz_id"),
    }
    if decision.reason_code:
        item["skip_reason_code"] = decision.reason_code
    embedded = assignment.get("submission") or {}
    item["embedded_live_state"] = normalize_live_state(
        embedded.get("workflow_state")
    )
    return item


def collect_candidates(
    config: Mapping[str, Any],
    client: Any,
    *,
    now: dt.datetime | None = None,
    timing: Any | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    routes = normalize_routes(config)
    window_days = int(config.get("pending_window_days", 7))
    candidates: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for course_id, route in routes.items():
        started = dt.datetime.now(dt.timezone.utc)
        try:
            assignments = client.list_assignments(course_id)
            if not isinstance(assignments, list):
                raise TypeError("list_assignments returned a non-list payload")
        except Exception as exc:
            errors.append(
                {
                    "course_id": course_id,
                    "course_name": route["name"],
                    "code": "list_assignments_failed",
                    "error": str(exc),
                }
            )
            if timing:
                timing.course(
                    course_id=course_id,
                    course_name=route["name"],
                    status="error",
                    error=str(exc),
                    elapsed_s=round(
                        (
                            dt.datetime.now(dt.timezone.utc) - started
                        ).total_seconds(),
                        3,
                    ),
                )
            continue

        selected = 0
        for assignment in assignments:
            if not isinstance(assignment, Mapping):
                continue
            if not is_actionable_assignment(
                assignment, window_days, now=now
            ):
                continue
            candidates.append(_base_item(course_id, route, assignment))
            selected += 1
        if timing:
            timing.course(
                course_id=course_id,
                course_name=route["name"],
                status="ok",
                assignments_count=len(assignments),
                pending_count=selected,
                elapsed_s=round(
                    (dt.datetime.now(dt.timezone.utc) - started).total_seconds(), 3
                ),
            )
    return candidates, errors


def enrich_candidates(
    candidates: list[dict[str, Any]],
    client: Any,
    *,
    now: dt.datetime | None = None,
    timing: Any | None = None,
) -> list[dict[str, Any]]:
    current = _utc_now(now)
    enriched: list[dict[str, Any]] = []

    for candidate in candidates:
        item = dict(candidate)
        live_state = "unknown"
        try:
            submission = client.get_submission(
                item["course_id"], item["assignment_id"]
            )
            live_state = normalize_live_state(submission.get("workflow_state"))
        except Exception as exc:
            live_state = item.get("embedded_live_state") or "unknown"
            item["live_state_error"] = str(exc)
        item["live_state"] = live_state
        if live_state in DONE_LIVE_STATES:
            continue

        due = _parse_time(item.get("due_at"))
        hours_left = (
            (due - current).total_seconds() / 3600 if due is not None else None
        )
        item["hours_left"] = round(hours_left, 2) if hours_left is not None else None
        item["bucket"] = bucket_for(hours_left, live_state)

        item["ldb_locked"] = False
        if item.get("skill") == "canvas-inside" and item.get("quiz_id"):
            try:
                quiz = client.get_quiz(item["course_id"], item["quiz_id"])
                if has_lockdown_browser(quiz):
                    item["skill"] = "canvas-skip"
                    item["skip_reason_code"] = "lockdown_browser"
                    item["ldb_locked"] = True
            except Exception as exc:
                # An API failure is not evidence that the plugin is active.
                # canvas-inside must recheck before any separately authorized
                # action; the scan records the uncertainty explicitly.
                item["ldb_check_failed"] = True
                item["ldb_check_error"] = str(exc)

        item.pop("embedded_live_state", None)
        enriched.append(item)
        if timing:
            timing.item(
                course_id=item["course_id"],
                assignment_id=item["assignment_id"],
                name=item.get("name"),
                live_state=item["live_state"],
                bucket=item["bucket"],
                skill=item["skill"],
            )

    order = {"overdue": 0, "urgent": 1, "soon": 2, "later": 3, "unknown": 4}
    enriched.sort(
        key=lambda item: (
            order.get(item.get("bucket"), 5),
            item["hours_left"] if item.get("hours_left") is not None else float("inf"),
            item["course_id"],
            item["assignment_id"],
        )
    )
    return enriched


def scan_product(
    config: Mapping[str, Any],
    client: Any,
    *,
    now: dt.datetime | None = None,
    timing: Any | None = None,
) -> dict[str, Any]:
    current = _utc_now(now)
    candidates, course_errors = collect_candidates(
        config, client, now=current, timing=timing
    )
    if course_errors:
        return {
            "complete": False,
            "generated_at": current.astimezone(PT).isoformat(),
            "now_utc": current.isoformat(),
            "items": [],
            "course_errors": course_errors,
            "diagnostics": {
                "partial_candidate_count": len(candidates),
                "approval_ready": False,
            },
        }

    items = enrich_candidates(candidates, client, now=current, timing=timing)
    return {
        "complete": True,
        "generated_at": current.astimezone(PT).isoformat(),
        "now_utc": current.isoformat(),
        "items": items,
        "course_errors": [],
    }


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(
            json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def write_product_outputs(run_dir: Path, payload: Mapping[str, Any]) -> tuple[Path, Path]:
    if payload.get("complete") is not True or payload.get("course_errors"):
        raise IncompleteScanError(dict(payload))
    scan_path = run_dir / "scan.json"
    assignments_path = run_dir / "assignments.json"
    # Each file is independently atomic.  scan.json is written last and is the
    # completion signal; a crash cannot expose a new approval-ready scan that
    # points at a missing assignments snapshot.
    atomic_write_json(assignments_path, payload.get("items") or [])
    atomic_write_json(scan_path, dict(payload))
    return scan_path, assignments_path
