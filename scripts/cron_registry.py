# SPDX-License-Identifier: AGPL-3.0-or-later
"""canvas-cron framework — two registries.

1. **Template registry**: discovers `scripts/cron_template_<name>.py` files at
   import time. Each must export a module-level `template = SomeTemplate(SPEC)`
   instance (`SomeTemplate` subclasses `EmailTemplate` or `AutonomousTemplate`).
   `cron_base.py` and `cron_registry.py` are framework — excluded from discovery.

2. **Instance registry**: source of truth is `_private/cron_instances.yaml`.
   `load_instances()` reads and parses into `CronInstance` objects.
   `save_instances()` writes atomically (tmp + os.replace).
   `add_instance()` / `remove_instance()` mutate yaml in-place.

Both registries are read on every CLI invocation — no caching beyond the
single CLI process. yaml writes are atomic so partial-write corruption is
impossible (worst case: write fails and yaml is unchanged).
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Optional

import yaml

from scripts.cron_base import (
    ROOT, ActionTemplate, CronInstance,
)

SCRIPTS_DIR = ROOT / "scripts"
FRAMEWORK_FILES = {"cron_base.py", "cron_registry.py"}
INSTANCES_YAML = ROOT / "_private" / "cron_instances.yaml"


# ============================================================================
# Template registry
# ============================================================================

def _template_modules() -> list[Path]:
    """Globs scripts/cron_template_*.py."""
    out = []
    for p in sorted(SCRIPTS_DIR.glob("cron_template_*.py")):
        if p.name in FRAMEWORK_FILES:
            continue
        out.append(p)
    return out


def _import_module_from_path(path: Path):
    mod_name = f"scripts.{path.stem}"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


def discover_templates() -> dict[str, ActionTemplate]:
    """Returns {template_name: ActionTemplate instance}. Bad modules logged
    to stderr and skipped — working subset returned."""
    out: dict[str, ActionTemplate] = {}
    for path in _template_modules():
        try:
            module = _import_module_from_path(path)
        except Exception as e:
            print(f"[cron_registry] failed to import {path.name}: "
                  f"{type(e).__name__}: {e}", file=sys.stderr)
            continue
        if module is None:
            print(f"[cron_registry] could not load {path.name} (no spec)",
                  file=sys.stderr)
            continue
        template = getattr(module, "template", None)
        if template is None:
            print(f"[cron_registry] {path.name} has no module-level `template` "
                  f"attribute — skipping", file=sys.stderr)
            continue
        if not isinstance(template, ActionTemplate):
            print(f"[cron_registry] {path.name}.template is not an "
                  f"ActionTemplate instance — skipping", file=sys.stderr)
            continue
        name = template.spec.name
        if name in out:
            print(f"[cron_registry] duplicate template name {name!r} in "
                  f"{path.name} — keeping first", file=sys.stderr)
            continue
        out[name] = template
    return out


def get_template(name: str) -> Optional[ActionTemplate]:
    return discover_templates().get(name)


# ============================================================================
# Instance registry — reads/writes _private/cron_instances.yaml atomically
# ============================================================================

def _empty_yaml_doc() -> dict:
    return {"version": 1, "instances": {}}


def load_instances_doc() -> dict:
    """Returns the raw parsed yaml dict (incl. version + instances). If file
    missing / corrupt, returns an empty doc — caller decides whether that's
    expected (first run) or an error."""
    if not INSTANCES_YAML.exists():
        return _empty_yaml_doc()
    try:
        d = yaml.safe_load(INSTANCES_YAML.read_text(encoding="utf-8")) or {}
        if not isinstance(d, dict):
            return _empty_yaml_doc()
        d.setdefault("version", 1)
        d.setdefault("instances", {})
        return d
    except Exception as e:
        print(f"[cron_registry] failed to parse {INSTANCES_YAML}: "
              f"{type(e).__name__}: {e}", file=sys.stderr)
        return _empty_yaml_doc()


def load_instances() -> dict[str, CronInstance]:
    """Returns {instance_name: CronInstance}."""
    doc = load_instances_doc()
    out: dict[str, CronInstance] = {}
    for name, body in (doc.get("instances") or {}).items():
        if not isinstance(body, dict):
            print(f"[cron_registry] instance {name!r}: malformed entry — skipping",
                  file=sys.stderr)
            continue
        try:
            out[name] = CronInstance.from_yaml_dict(name, body)
        except Exception as e:
            print(f"[cron_registry] instance {name!r}: parse failed — "
                  f"{type(e).__name__}: {e}", file=sys.stderr)
    return out


def get_instance(name: str) -> Optional[CronInstance]:
    return load_instances().get(name)


def save_instances_doc(doc: dict) -> None:
    """Atomic yaml write: tmp + os.replace. Caller is responsible for the
    doc structure ({version, instances}). Best-effort — raises on filesystem
    failure."""
    INSTANCES_YAML.parent.mkdir(parents=True, exist_ok=True)
    tmp = INSTANCES_YAML.with_suffix(".yaml.tmp")
    tmp.write_text(
        yaml.safe_dump(doc, default_flow_style=False, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    os.replace(tmp, INSTANCES_YAML)


def add_instance(inst: CronInstance) -> None:
    """Add or overwrite an instance entry. Atomic yaml write."""
    doc = load_instances_doc()
    doc.setdefault("instances", {})[inst.name] = inst.to_yaml_dict()
    save_instances_doc(doc)


def remove_instance(name: str) -> bool:
    """Remove an instance entry. Returns True if removed, False if not present.
    Atomic yaml write."""
    doc = load_instances_doc()
    instances = doc.setdefault("instances", {})
    if name not in instances:
        return False
    del instances[name]
    save_instances_doc(doc)
    return True


# ============================================================================
# Courses (reads courses.yaml at project root)
# ============================================================================

def load_courses() -> list[dict]:
    """Returns a list of {course_id, name, skill} dicts from courses.yaml routes."""
    from scripts.cron_base import load_courses_yaml
    cfg = load_courses_yaml()
    out = []
    for cid, route in (cfg.get("routes") or {}).items():
        out.append({
            "course_id": str(cid),
            "name": (route or {}).get("name") or f"course {cid}",
            "skill": (route or {}).get("skill") or "?",
        })
    return out
