# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read-only Canvas scanner and Codex route planner input.

Product usage::

    python -m src.router --scan-json

``--scan-json`` is the only state-producing scan path.  It writes an enriched,
complete ``scan.json`` plus ``assignments.json`` atomically and exits nonzero
when any configured course cannot be listed.  ``--dry-run`` is a manual debug
view and deliberately writes no approval/execution state.

The historical ``--run`` dispatcher is permanently fail-closed: legacy skill
dispatch is disabled.  Assignment work must go through canvas-scan, explicit
user approval, and canvas-execute.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

from .routes import (
    configured_skill_for,
    matches_override,
    normalize_routes,
    resolve_skill as resolve_canonical_skill,
    resolve_route,
)
from .scan_service import (
    bucket_for,
    collect_candidates,
    enrich_candidates,
    is_actionable_assignment,
    scan_product,
    write_product_outputs,
)


ROOT = Path(__file__).resolve().parent.parent
TODAY = dt.date.today().isoformat()
RUN_DIR = ROOT / "runs" / TODAY

EXIT_OK = 0
EXIT_FATAL = 2
EXIT_INCOMPLETE = 3
EXIT_EXECUTION_DISABLED = 4


def _round_s(value: float) -> float:
    return round(value, 3)


class ScanTiming:
    """Structured timing and diagnostic evidence for one scanner invocation."""

    def __init__(self, command: str, auth_mode: str | None = None) -> None:
        self.started = time.perf_counter()
        self.data: dict[str, Any] = {
            "generated_at": dt.datetime.now(
                ZoneInfo("America/Los_Angeles")
            ).isoformat(),
            "command": command,
            "auth_mode": auth_mode or os.environ.get("CANVAS_AUTH", "cookie"),
            "phases": [],
            "courses": [],
            "items": [],
        }

    @staticmethod
    def elapsed(start: float) -> float:
        return _round_s(time.perf_counter() - start)

    def phase(self, name: str, start: float, **fields: Any) -> None:
        entry = {"name": name, "elapsed_s": self.elapsed(start)}
        entry.update(fields)
        self.data["phases"].append(entry)

    def course(self, **fields: Any) -> None:
        self.data["courses"].append(fields)

    def item(self, **fields: Any) -> None:
        self.data["items"].append(fields)

    def mark_error(self, code: str, detail: str, **fields: Any) -> None:
        error = {"code": code, "detail": detail}
        error.update(fields)
        self.data["error"] = error

    def write(self, run_dir: Path = RUN_DIR) -> Path:
        from .scan_service import atomic_write_json

        self.data["total_s"] = self.elapsed(self.started)
        out = run_dir / "scan_timing.json"
        atomic_write_json(out, self.data)
        return out


def _load_routes(path: Path | None = None) -> dict[str, Any]:
    config_path = path or (ROOT / "courses.yaml")
    if not config_path.exists():
        raise FileNotFoundError(f"missing route config: {config_path}")
    parsed = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(parsed, dict):
        raise ValueError("courses.yaml root must be a mapping")
    # Validate both object routes and shorthand strings before any Canvas call.
    normalize_routes(parsed)
    return parsed


def _load_client():
    # Lazy import lets `--help` and the `--run` safety refusal work even when
    # Canvas auth is not configured on a clean install.
    from . import canvas_client

    return canvas_client


# Compatibility helpers retained for callers/tests that used the old module.
# They now delegate to the canonical route/scan service rather than maintaining
# another implementation.
def _is_pending(assignment: dict, window_days: int) -> bool:
    return is_actionable_assignment(assignment, window_days)


def _matches_override(assignment: dict, match_spec: dict) -> bool:
    return matches_override(assignment, match_spec)


def _resolve_skill(route: dict, assignment: dict) -> str:
    return resolve_canonical_skill(route, assignment)


def _bucket(hours_left: float | None, live_state: str = "unknown") -> str:
    return bucket_for(hours_left, live_state)


def _enrich(
    pending: list[dict],
    course_errors: list[dict],
    timing: ScanTiming | None = None,
    *,
    client=None,
) -> dict[str, Any]:
    current = dt.datetime.now(dt.timezone.utc)
    if course_errors:
        return {
            "complete": False,
            "generated_at": current.astimezone(
                ZoneInfo("America/Los_Angeles")
            ).isoformat(),
            "now_utc": current.isoformat(),
            "items": [],
            "course_errors": course_errors,
            "diagnostics": {
                "partial_candidate_count": len(pending),
                "approval_ready": False,
            },
        }
    cv = client or _load_client()
    return {
        "complete": True,
        "generated_at": current.astimezone(
            ZoneInfo("America/Los_Angeles")
        ).isoformat(),
        "now_utc": current.isoformat(),
        "items": enrich_candidates(pending, cv, now=current, timing=timing),
        "course_errors": [],
    }


def _scan_with_errors(
    timing: ScanTiming | None = None,
    *,
    config: dict[str, Any] | None = None,
    client=None,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, str]]]:
    cfg = config if config is not None else _load_routes()
    cv = client or _load_client()
    pending, errors = collect_candidates(cfg, cv, timing=timing)
    return cfg, pending, errors


def scan() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Read-only compatibility API used by due-alert code.

    Unlike the historical implementation, a failed course cannot silently
    disappear from the returned list.
    """

    cfg, pending, errors = _scan_with_errors()
    if errors:
        detail = "; ".join(
            f"{item['course_id']}: {item['error']}" for item in errors
        )
        raise RuntimeError(f"incomplete Canvas scan: {detail}")
    return cfg, pending


def _classify_connection_error(exc: Exception) -> tuple[str, str]:
    message = str(exc)
    name = type(exc).__name__
    if name == "CanvasSessionExpired":
        return "auth", message
    if isinstance(exc, (FileNotFoundError, ValueError, RuntimeError)):
        return "not_configured", message
    return "unknown", message


def _emit_scan_json(
    *,
    run_dir: Path = RUN_DIR,
    config: dict[str, Any] | None = None,
    client=None,
) -> int:
    timing = ScanTiming(
        "scan-json", getattr(client, "AUTH_MODE", None) if client else None
    )
    try:
        cfg = config if config is not None else _load_routes()
        cv = client or _load_client()
        started = time.perf_counter()
        payload = scan_product(cfg, cv, timing=timing)
        timing.phase(
            "scan_product",
            started,
            complete=payload.get("complete"),
            item_count=len(payload.get("items") or []),
            course_errors_count=len(payload.get("course_errors") or []),
        )
    except Exception as exc:
        code, detail = _classify_connection_error(exc)
        timing.mark_error(code, detail)
        timing_path = timing.write(run_dir)
        print(
            json.dumps({"complete": False, "error": code, "detail": detail}, ensure_ascii=False)
        )
        print(f"Timing -> {timing_path}", file=sys.stderr)
        return EXIT_FATAL

    if payload.get("complete") is not True or payload.get("course_errors"):
        timing.mark_error(
            "course_scan_failed",
            "one or more configured courses could not be listed",
            course_errors=payload.get("course_errors") or [],
        )
        timing_path = timing.write(run_dir)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        print(
            "Incomplete scan: no scan.json or assignments.json was written. "
            "Repair the listed course connection and scan again.",
            file=sys.stderr,
        )
        print(f"Timing -> {timing_path}", file=sys.stderr)
        return EXIT_INCOMPLETE

    try:
        write_started = time.perf_counter()
        scan_path, assignments_path = write_product_outputs(run_dir, payload)
        timing.phase(
            "write_product_outputs",
            write_started,
            scan_path=str(scan_path),
            assignments_path=str(assignments_path),
        )
        timing_path = timing.write(run_dir)
    except Exception as exc:
        timing.mark_error("write_failed", str(exc))
        timing_path = timing.write(run_dir)
        print(
            json.dumps(
                {"complete": False, "error": "write_failed", "detail": str(exc)},
                ensure_ascii=False,
            )
        )
        print(f"Timing -> {timing_path}", file=sys.stderr)
        return EXIT_FATAL

    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"Timing -> {timing_path}")
    return EXIT_OK


def _debug_scan(
    args: argparse.Namespace,
    *,
    run_dir: Path = RUN_DIR,
    config: dict[str, Any] | None = None,
    client=None,
) -> int:
    timing = ScanTiming(
        "dry-run-debug", getattr(client, "AUTH_MODE", None) if client else None
    )
    try:
        cfg, pending, errors = _scan_with_errors(
            timing=timing, config=config, client=client
        )
    except Exception as exc:
        code, detail = _classify_connection_error(exc)
        timing.mark_error(code, detail)
        timing.write(run_dir)
        print(f"Debug scan failed: {detail}", file=sys.stderr)
        return EXIT_FATAL

    if args.only:
        pending = [item for item in pending if item["course_id"] == str(args.only)]
    if args.assignment:
        try:
            course_id, assignment_id = args.assignment.split(":", 1)
        except ValueError:
            timing.mark_error("invalid_filter", "--assignment must be COURSE:ASSIGNMENT")
            timing.write(run_dir)
            print("--assignment must be COURSE:ASSIGNMENT", file=sys.stderr)
            return EXIT_FATAL
        pending = [
            item
            for item in pending
            if item["course_id"] == course_id
            and item["assignment_id"] == assignment_id
        ]

    if errors:
        timing.mark_error(
            "course_scan_failed",
            "debug view is partial",
            course_errors=errors,
        )
        timing.write(run_dir)
        print(json.dumps({"complete": False, "course_errors": errors}, ensure_ascii=False))
        print(
            "Debug scan is incomplete; no product scan state was written.",
            file=sys.stderr,
        )
        return EXIT_INCOMPLETE

    timing.write(run_dir)
    print(f"=== {len(pending)} debug candidate(s) ===")
    for item in pending:
        print(
            f"[{item['skill']}] {item['course_name']} | "
            f"due {item.get('due_at')} | {item.get('name')}"
        )
    print(
        "Debug only: no scan.json, assignments.json, plan, result, or report was written."
    )
    del cfg
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--scan-json",
        action="store_true",
        help="complete enriched product scan; writes scan.json + assignments.json",
    )
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="manual read-only debug listing; writes no product scan state",
    )
    mode.add_argument(
        "--run",
        action="store_true",
        help="disabled legacy execution flag",
    )
    parser.add_argument("--only", help="debug-only course-id filter")
    parser.add_argument("--assignment", help="debug-only COURSE:ASSIGNMENT filter")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.run:
        print(
            "Legacy skill dispatch is disabled. Run canvas-scan, review the "
            "plan, then explicitly approve work for canvas-execute.",
            file=sys.stderr,
        )
        return EXIT_EXECUTION_DISABLED

    if args.scan_json:
        if args.only or args.assignment:
            print(
                "Product --scan-json must cover every configured course; "
                "--only/--assignment are debug-only.",
                file=sys.stderr,
            )
            return EXIT_FATAL
        return _emit_scan_json()

    # No explicit mode remains a safe debug view for backward compatibility.
    return _debug_scan(args)


if __name__ == "__main__":
    raise SystemExit(main())
