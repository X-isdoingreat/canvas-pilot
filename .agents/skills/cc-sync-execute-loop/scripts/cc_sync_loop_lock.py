# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


LOCK_RELATIVE = Path(".codex") / "cc-sync-execute-loop.lock.json"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def lock_path(root: Path) -> Path:
    return root / LOCK_RELATIVE


def load_lock(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"status": "unreadable", "path": str(path)}
    if not isinstance(data, dict):
        return {"status": "invalid", "path": str(path)}
    return data


def write_lock(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def is_fresh_active(data: dict[str, Any] | None, ttl: timedelta, at: datetime) -> bool:
    if not data or data.get("status") != "active":
        return False
    heartbeat = parse_time(data.get("heartbeat_at")) or parse_time(data.get("started_at"))
    if heartbeat is None:
        return False
    return at - heartbeat <= ttl


def output(result: str, **fields: Any) -> None:
    payload = {"result": result, **fields}
    print(json.dumps(payload, indent=2, sort_keys=True))


def claim(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    path = lock_path(root)
    ttl = timedelta(minutes=args.ttl_minutes)
    at = now_utc()
    existing = load_lock(path)

    if is_fresh_active(existing, ttl, at):
        output("locked", lock_path=str(path), lock=existing)
        return 2

    cycle_id = args.cycle_id or str(uuid.uuid4())
    data: dict[str, Any] = {
        "cycle_id": cycle_id,
        "heartbeat_at": iso(at),
        "host": "local",
        "lock_path": str(path),
        "owner": args.owner,
        "pid": None,
        "started_at": iso(at),
        "status": "active",
        "ttl_minutes": args.ttl_minutes,
    }
    if existing and existing.get("status") == "active":
        data["recovered_from"] = existing

    write_lock(path, data)
    output("claimed", lock_path=str(path), lock=data)
    return 0


def heartbeat(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    path = lock_path(root)
    data = load_lock(path)
    if not data or data.get("status") != "active":
        output("no_active_lock", lock_path=str(path), lock=data)
        return 2
    data["host"] = "local"
    data["heartbeat_at"] = iso(now_utc())
    write_lock(path, data)
    output("heartbeat", lock_path=str(path), lock=data)
    return 0


def release(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    path = lock_path(root)
    data = load_lock(path)
    at = now_utc()
    if not data:
        output("no_lock", lock_path=str(path))
        return 0
    data["status"] = args.status
    data["host"] = "local"
    data["ended_at"] = iso(at)
    data["heartbeat_at"] = iso(at)
    if args.note:
        data["note"] = args.note
    write_lock(path, data)
    output("released", lock_path=str(path), lock=data)
    return 0


def status(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    path = lock_path(root)
    data = load_lock(path)
    output("status", lock_path=str(path), lock=data)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage cc-sync execute loop lock state.")
    parser.add_argument("command", choices=["claim", "heartbeat", "release", "status"])
    parser.add_argument("--root", default=".", help="Repository root. Defaults to current directory.")
    parser.add_argument("--ttl-minutes", type=int, default=30, help="Fresh active lock TTL.")
    parser.add_argument("--owner", default="codex", help="Lock owner label.")
    parser.add_argument("--cycle-id", default=None, help="Optional explicit cycle id.")
    parser.add_argument("--status", default="released", help="Release status, such as released or blocked.")
    parser.add_argument("--note", default=None, help="Optional release note.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "claim":
        return claim(args)
    if args.command == "heartbeat":
        return heartbeat(args)
    if args.command == "release":
        return release(args)
    return status(args)


if __name__ == "__main__":
    raise SystemExit(main())
