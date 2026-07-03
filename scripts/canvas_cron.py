# SPDX-License-Identifier: AGPL-3.0-or-later
"""canvas-cron CLI — the only entry. The canvas-cron skill calls this; OS Task
Scheduler also calls it (via `fire <instance_name>` argument in the generated
task XML).

Subcommands:
  list                          Installed instances (reads cron_instances.yaml).
  list-templates                Available action templates (filesystem).
  list-courses                  Courses from courses.yaml.
  create <name> ...             Build a new instance: write yaml + render XML +
                                schtasks /create (disabled).
  delete <name>                 Remove instance from yaml + schtasks /delete +
                                archive ledger.
  register <name>               Re-render XML + schtasks /create from existing
                                yaml entry (used by change_schedule).
  unregister <name>             schtasks /delete only (keeps yaml entry).
  enable <name>                 PowerShell Enable-ScheduledTask.
  disable <name>                PowerShell Disable-ScheduledTask.
  fire <name> [opts]            Run the instance's template in-proc (what OS
                                Task Scheduler calls). --dry-run, --force,
                                --os-trigger.
  status [<name>]               Instance + Task Scheduler state.
  reconcile [<name>] [--fix]    Diff yaml vs Task Scheduler.

PowerShell preference: `schtasks /change /enable` prompts for password on
Win11 22H2+. We use Enable-ScheduledTask / Disable-ScheduledTask cmdlets
(token-based) for state toggles. `schtasks /create` and `/delete` work
without prompts.

ROOT calc: scripts/canvas_cron.py at depth 2 → parent.parent = project root.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import subprocess
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
assert (ROOT / "courses.yaml").exists() or (ROOT / "SECRETS.md").exists(), (
    f"ROOT misresolved in canvas_cron.py: {ROOT}"
)

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from scripts import cron_registry  # noqa: E402
from scripts.cron_base import (  # noqa: E402
    CronInstance, Schedule, RUNS,
)

TEMPLATE_PATH = ROOT / "scripts" / "cron_templates" / "task.xml.template"
GENERATED_DIR = ROOT / "scripts" / "cron_templates" / "_generated"


# ============================================================================
# Render Task XML + schtasks helpers
# ============================================================================

def get_user_sid() -> str:
    result = subprocess.run(
        ["whoami", "/user"], capture_output=True, text=True, check=True, shell=False,
    )
    for line in result.stdout.splitlines():
        for tok in line.split():
            if tok.startswith("S-1-5-"):
                return tok
    raise RuntimeError(f"Could not parse SID from whoami output:\n{result.stdout}")


def get_python_exe() -> str:
    venv_py = ROOT / ".venv" / "Scripts" / "python.exe"
    if venv_py.exists():
        return str(venv_py)
    return sys.executable


def render_task_xml(inst: CronInstance, exec_time_limit: str, description: str,
                    out_path: Path) -> Path:
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Template not found: {TEMPLATE_PATH}")
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    sid = get_user_sid()
    py_exe = get_python_exe()
    start_boundary = f"{inst.schedule.start_boundary}T{inst.schedule.time_hh_mm}:00"
    subs = {
        "{{USER_SID}}": sid,
        "{{PROJECT_DIR}}": str(ROOT),
        "{{PYTHON_EXE}}": py_exe,
        "{{TASK_NAME}}": inst.task_name,
        "{{DESCRIPTION}}": description,
        "{{START_BOUNDARY}}": start_boundary,
        "{{DAYS_INTERVAL}}": str(inst.schedule.days_interval),
        "{{EXECUTION_TIME_LIMIT}}": exec_time_limit,
        "{{INSTANCE_NAME}}": inst.name,  # CronInstance.name; passed to `canvas_cron.py fire`
    }
    rendered = template
    for k, v in subs.items():
        rendered = rendered.replace(k, v)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(b"\xff\xfe")  # UTF-16 LE BOM
        f.write(rendered.encode("utf-16-le"))
    return out_path


def task_exists(task_name: str) -> bool:
    result = subprocess.run(
        ["schtasks", "/query", "/tn", task_name],
        capture_output=True, text=True, shell=False,
    )
    return result.returncode == 0


def get_task_state(task_name: str) -> dict:
    if not task_exists(task_name):
        return {"state": "NOT_REGISTERED", "last_result": None,
                "last_run": None, "next_run": None}
    ps_cmd = (
        f"$t = Get-ScheduledTask -TaskName '{task_name}' -ErrorAction SilentlyContinue;"
        f" if (-not $t) {{ Write-Output 'NOT_REGISTERED'; exit }};"
        f" $i = Get-ScheduledTaskInfo -TaskName '{task_name}';"
        f" Write-Output \"STATE=$($t.State)\";"
        f" Write-Output \"LAST_RESULT=$($i.LastTaskResult)\";"
        f" Write-Output \"LAST_RUN=$($i.LastRunTime)\";"
        f" Write-Output \"NEXT_RUN=$($i.NextRunTime)\""
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
        capture_output=True, text=True, shell=False,
    )
    out = {"state": "?", "last_result": None, "last_run": None, "next_run": None}
    for line in result.stdout.splitlines():
        line = line.strip()
        if line == "NOT_REGISTERED":
            out["state"] = "NOT_REGISTERED"
            return out
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k == "STATE":
            out["state"] = v
        elif k == "LAST_RESULT":
            out["last_result"] = v
        elif k == "LAST_RUN":
            out["last_run"] = v
        elif k == "NEXT_RUN":
            out["next_run"] = v
    return out


def set_task_enabled(task_name: str, enabled: bool) -> bool:
    cmd = "Enable-ScheduledTask" if enabled else "Disable-ScheduledTask"
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command",
         f"{cmd} -TaskName '{task_name}' | Out-Null"],
        capture_output=True, text=True, shell=False,
    )
    if result.returncode != 0:
        print(f"  {cmd} stderr: {result.stderr}", file=sys.stderr)
        return False
    return True


def schtasks_create_from_xml(task_name: str, xml_path: Path) -> bool:
    # Defensive: delete first in case orphan exists
    subprocess.run(
        ["schtasks", "/delete", "/tn", task_name, "/f"],
        capture_output=True, text=True, shell=False,
    )
    create = subprocess.run(
        ["schtasks", "/create", "/xml", str(xml_path), "/tn", task_name, "/f"],
        capture_output=True, text=True, shell=False,
    )
    if create.returncode != 0:
        print(f"❌ schtasks /create failed (exit {create.returncode}):", file=sys.stderr)
        print(f"   stdout: {create.stdout}", file=sys.stderr)
        print(f"   stderr: {create.stderr}", file=sys.stderr)
        return False
    return True


def schtasks_delete(task_name: str) -> bool:
    if not task_exists(task_name):
        return True
    result = subprocess.run(
        ["schtasks", "/delete", "/tn", task_name, "/f"],
        capture_output=True, text=True, shell=False,
    )
    return result.returncode == 0


# ============================================================================
# Param parsing helpers
# ============================================================================

def _coerce_param_value(spec_type: str, value_str: str):
    if spec_type == "int":
        return int(value_str)
    if spec_type == "bool":
        return value_str.lower() in ("true", "1", "yes", "y")
    return value_str  # str


def _parse_kv_args(kv_args: list[str]) -> dict:
    """--param k=v --param k2=v2 → {k: v, k2: v2}. Both as strings; type
    coercion happens later when we have the param_schema."""
    out = {}
    for arg in (kv_args or []):
        if "=" not in arg:
            raise SystemExit(f"--param expects key=value, got: {arg!r}")
        k, v = arg.split("=", 1)
        out[k.strip()] = v.strip()
    return out


# ============================================================================
# Subcommands
# ============================================================================

def cmd_list(_args) -> int:
    instances = cron_registry.load_instances()
    if not instances:
        print("(no cron instances installed — use `create` via the canvas-cron skill)")
        return 0
    templates = cron_registry.discover_templates()
    print(f"{'instance':<24} {'template':<32} {'kind':<11} {'course':<10} "
          f"{'task_name':<30} {'state':<14} {'next_run'}")
    print("-" * 140)
    for name, inst in instances.items():
        t = templates.get(inst.template)
        kind = t.spec.kind if t else "?"
        st = get_task_state(inst.task_name)
        print(f"{name:<24} {inst.template:<32} {kind:<11} "
              f"{inst.course_id:<10} {inst.task_name:<30} "
              f"{st['state']:<14} {st['next_run']}")
    return 0


def cmd_list_templates(_args) -> int:
    templates = cron_registry.discover_templates()
    if not templates:
        print("(no templates discovered — expected scripts/cron_template_*.py files)")
        return 0
    for name, t in templates.items():
        print(f"=== {name} ===")
        print(f"  kind:        {t.spec.kind}")
        print(f"  description: {t.spec.description}")
        print(f"  exec limit:  {t.spec.execution_time_limit}")
        print(f"  params:")
        if not t.spec.param_schema:
            print(f"    (none)")
        for p in t.spec.param_schema:
            print(f"    - {p.key} ({p.type}, default={p.default!r}): {p.prompt}")
        print()
    return 0


def cmd_list_courses(_args) -> int:
    courses = cron_registry.load_courses()
    if not courses:
        print("(no courses in courses.yaml routes — run canvas-setup first)")
        return 0
    print(f"{'course_id':<12} {'skill':<14} {'name'}")
    print("-" * 70)
    for c in courses:
        print(f"{c['course_id']:<12} {c['skill']:<14} {c['name']}")
    return 0


def cmd_create(args) -> int:
    """Build an instance: validate template+params → check duplicate →
    write yaml → render XML → schtasks /create disabled."""
    template = cron_registry.get_template(args.template)
    if not template:
        print(f"❌ template not found: {args.template}", file=sys.stderr)
        print(f"   Run `list-templates` to see available.", file=sys.stderr)
        return 1
    spec = template.spec
    # 授权 check for autonomous kind
    if spec.kind == "autonomous" and not args.authorized:
        print(f"❌ template '{args.template}' is kind=autonomous; CLI requires "
              f"--authorized flag (the canvas-cron skill obtains 授权 keyword "
              f"from the user before passing this flag).", file=sys.stderr)
        return 1
    # Parse + coerce params
    raw_params = _parse_kv_args(args.param or [])
    schema_keys = {p.key: p for p in spec.param_schema}
    params = {}
    for p in spec.param_schema:
        if p.key in raw_params:
            try:
                params[p.key] = _coerce_param_value(p.type, raw_params.pop(p.key))
            except Exception as e:
                print(f"❌ param {p.key!r}: cannot coerce to {p.type}: {e}", file=sys.stderr)
                return 1
        else:
            params[p.key] = p.default
    if raw_params:
        print(f"❌ unknown params for template {args.template!r}: {list(raw_params)}",
              file=sys.stderr)
        print(f"   Allowed: {list(schema_keys)}", file=sys.stderr)
        return 1
    # Build CronInstance
    now_iso = dt.datetime.now(dt.timezone.utc).astimezone().isoformat()
    inst = CronInstance(
        name=args.name,
        template=args.template,
        course_id=str(args.course),
        schedule=Schedule(
            days_interval=args.days,
            time_hh_mm=args.time,
            start_boundary=args.start,
        ),
        params=params,
        recipient=args.recipient,
        created_at=now_iso,
        authorized_at=(now_iso if args.authorized else None),
        authorized_for_course_id=(str(args.course) if args.authorized else None),
    )
    # Duplicate detection: same template + course_id + schedule
    existing = cron_registry.load_instances()
    for other_name, other in existing.items():
        if other_name == args.name:
            continue
        if (other.template == inst.template
                and other.course_id == inst.course_id
                and other.schedule.days_interval == inst.schedule.days_interval
                and other.schedule.time_hh_mm == inst.schedule.time_hh_mm):
            print(f"❌ duplicate: instance '{other_name}' already covers "
                  f"(template={inst.template}, course={inst.course_id}, "
                  f"schedule={inst.schedule.days_interval}d@{inst.schedule.time_hh_mm}). "
                  f"Delete it first or pick a different time.", file=sys.stderr)
            return 1
    # G1: write yaml atomically
    print(f"→ G1a: writing yaml entry for {inst.name}")
    cron_registry.add_instance(inst)
    # G1b: render XML
    out_xml = GENERATED_DIR / f"{inst.name}.task.xml"
    print(f"→ G1b: rendering {out_xml.relative_to(ROOT)}")
    render_task_xml(
        inst,
        exec_time_limit=spec.execution_time_limit,
        description=f"{spec.description} (instance={inst.name})",
        out_path=out_xml,
    )
    # G2: schtasks /create (disabled)
    print(f"→ G2: schtasks /create /tn '{inst.task_name}'")
    if not schtasks_create_from_xml(inst.task_name, out_xml):
        print(f"   yaml entry kept; retry with `register {inst.name}`")
        return 1
    set_task_enabled(inst.task_name, enabled=False)
    print(f"✅ G2: task '{inst.task_name}' registered (disabled).")
    print(f"   Schedule: every {inst.schedule.days_interval} day(s) at "
          f"{inst.schedule.time_hh_mm} PT, starting {inst.schedule.start_boundary}")
    return 0


def cmd_delete(args) -> int:
    inst = cron_registry.get_instance(args.name)
    if not inst:
        print(f"❌ instance not found: {args.name}", file=sys.stderr)
        return 1
    # 1. Unregister Task Scheduler task
    if task_exists(inst.task_name):
        if not schtasks_delete(inst.task_name):
            print(f"❌ schtasks /delete failed; aborting (yaml unchanged)", file=sys.stderr)
            return 1
    # 2. Delete generated XML
    out_xml = GENERATED_DIR / f"{inst.name}.task.xml"
    if out_xml.exists():
        out_xml.unlink()
    # 3. Archive ledger + log
    ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    for src_path, label in [
        (RUNS / f"_{inst.name}_ledger.json", "ledger"),
        (RUNS / f"_{inst.name}_log.txt", "log"),
        (RUNS / f"_{inst.name}_heartbeat.json", "heartbeat"),
    ]:
        if src_path.exists():
            archived = RUNS / f"_deleted_{ts}_{src_path.name}"
            src_path.rename(archived)
            print(f"   archived {label}: {archived.name}")
    # 4. Remove yaml entry
    cron_registry.remove_instance(args.name)
    print(f"✅ deleted instance '{args.name}' (task + yaml + generated XML).")
    return 0


def cmd_register(args) -> int:
    """Re-render XML + schtasks /create from existing yaml entry. Used by
    change_schedule flow after yaml was edited."""
    inst = cron_registry.get_instance(args.name)
    if not inst:
        print(f"❌ instance not found in yaml: {args.name}", file=sys.stderr)
        return 1
    template = cron_registry.get_template(inst.template)
    if not template:
        print(f"❌ template {inst.template!r} not found", file=sys.stderr)
        return 1
    out_xml = GENERATED_DIR / f"{inst.name}.task.xml"
    print(f"→ rendering {out_xml.relative_to(ROOT)}")
    render_task_xml(
        inst,
        exec_time_limit=template.spec.execution_time_limit,
        description=f"{template.spec.description} (instance={inst.name})",
        out_path=out_xml,
    )
    print(f"→ schtasks /create /tn '{inst.task_name}'")
    if not schtasks_create_from_xml(inst.task_name, out_xml):
        return 1
    set_task_enabled(inst.task_name, enabled=False)
    print(f"✅ '{inst.task_name}' (re-)registered (disabled).")
    return 0


def cmd_unregister(args) -> int:
    inst = cron_registry.get_instance(args.name)
    if not inst:
        print(f"❌ instance not found: {args.name}", file=sys.stderr)
        return 1
    if not task_exists(inst.task_name):
        print(f"(task '{inst.task_name}' was not registered — nothing to do)")
        return 0
    if not schtasks_delete(inst.task_name):
        return 1
    print(f"✅ task '{inst.task_name}' deleted. yaml entry preserved.")
    return 0


def cmd_enable(args) -> int:
    inst = cron_registry.get_instance(args.name)
    if not inst:
        print(f"❌ instance not found: {args.name}", file=sys.stderr)
        return 1
    if not task_exists(inst.task_name):
        print(f"❌ task '{inst.task_name}' not registered. Run `register {args.name}` first.",
              file=sys.stderr)
        return 1
    if set_task_enabled(inst.task_name, enabled=True):
        st = get_task_state(inst.task_name)
        print(f"✅ {inst.task_name}: state={st['state']}, next_run={st['next_run']}")
        return 0
    return 1


def cmd_disable(args) -> int:
    inst = cron_registry.get_instance(args.name)
    if not inst:
        print(f"❌ instance not found: {args.name}", file=sys.stderr)
        return 1
    if set_task_enabled(inst.task_name, enabled=False):
        print(f"✅ {inst.task_name}: disabled.")
        return 0
    return 1


def cmd_fire(args) -> int:
    inst = cron_registry.get_instance(args.name)
    if not inst:
        print(f"❌ instance not found: {args.name}", file=sys.stderr)
        return 1
    template = cron_registry.get_template(inst.template)
    if not template:
        print(f"❌ template {inst.template!r} not found", file=sys.stderr)
        return 1
    if args.os_trigger:
        # G4: prove the OS trigger chain works via real schtasks /run
        if not task_exists(inst.task_name):
            print(f"❌ task '{inst.task_name}' not registered. Run `register` first.",
                  file=sys.stderr)
            return 1
        # schtasks /run refuses to fire a disabled task → enable first.
        # G5 (the final enable) is now implicit: G4 leaves the task enabled
        # if everything passes. If /run or post-verify fails, we re-disable
        # defensively.
        print(f"→ G4a: Enable-ScheduledTask '{inst.task_name}' (so /run will fire)")
        if not set_task_enabled(inst.task_name, enabled=True):
            print(f"❌ G4a: failed to enable task", file=sys.stderr)
            return 1
        print(f"→ G4b: schtasks /run /tn '{inst.task_name}'")
        result = subprocess.run(
            ["schtasks", "/run", "/tn", inst.task_name],
            capture_output=True, text=True, shell=False,
        )
        if result.returncode != 0:
            print(f"❌ schtasks /run failed: {result.stderr}", file=sys.stderr)
            set_task_enabled(inst.task_name, enabled=False)  # roll back
            return 1
        wait_s = 60
        print(f"   waiting {wait_s}s for OS to dispatch + record Last Run Result...")
        time.sleep(wait_s)
        st = get_task_state(inst.task_name)
        last_result = st.get("last_result")
        print(f"   LastTaskResult: {last_result}")
        # 0 / 0x0 = success; 0x41301 (267009) = still running (autonomous kind)
        if last_result in ("0", "0x0", "267009", "0x41301"):
            print(f"✅ G4: OS trigger works (Last Run Result = {last_result}).")
            print(f"   Task left ENABLED — next natural fire is per the schedule.")
            if last_result in ("267009", "0x41301"):
                print(f"   Note: task still running; CC session continues in "
                      f"background up to {template.spec.execution_time_limit}.")
            return 0
        print(f"❌ G4 failed: Last Run Result = {last_result}", file=sys.stderr)
        set_task_enabled(inst.task_name, enabled=False)  # roll back enable
        print(f"   Rolled back: task re-disabled.", file=sys.stderr)
        return 1
    # In-proc fire (what Task Scheduler calls)
    return template.run(inst, dry_run=args.dry_run, force=args.force)


def cmd_status(args) -> int:
    instances = cron_registry.load_instances()
    if args.name:
        if args.name not in instances:
            print(f"❌ instance not found: {args.name}", file=sys.stderr)
            return 1
        targets = {args.name: instances[args.name]}
    else:
        targets = instances
    if not targets:
        print("(no instances installed)")
        return 0
    templates = cron_registry.discover_templates()
    for name, inst in targets.items():
        t = templates.get(inst.template)
        kind = t.spec.kind if t else "?"
        st = get_task_state(inst.task_name)
        print(f"=== {name} ===")
        print(f"  template:    {inst.template} ({kind})")
        print(f"  course_id:   {inst.course_id}")
        print(f"  task_name:   {inst.task_name}")
        print(f"  schedule:    every {inst.schedule.days_interval}d at "
              f"{inst.schedule.time_hh_mm} PT (start {inst.schedule.start_boundary})")
        print(f"  params:      {inst.params}")
        print(f"  recipient:   {inst.recipient}")
        if inst.authorized_at:
            print(f"  authorized:  {inst.authorized_at} for course {inst.authorized_for_course_id}")
        print(f"  task state:  {st['state']}")
        print(f"  last_result: {st['last_result']}")
        print(f"  last_run:    {st['last_run']}")
        print(f"  next_run:    {st['next_run']}")
        print()
    return 0


def cmd_reconcile(args) -> int:
    """Diff yaml instances vs schtasks tasks. Print drifts. With --fix,
    re-render+create from yaml (yaml is source of truth)."""
    instances = cron_registry.load_instances()
    drifts = []
    for name, inst in instances.items():
        if not task_exists(inst.task_name):
            drifts.append((name, "MISSING_TASK", f"yaml has '{name}' but no task '{inst.task_name}'"))
            continue
        # Could also diff days_interval / time_hh_mm from registered XML; punt
        # to v2 — for now just check existence.
    # Also flag tasks named CanvasCron_* without yaml entry
    ps_cmd = (
        "Get-ScheduledTask | Where-Object {$_.TaskName -like 'CanvasCron_*'} | "
        "ForEach-Object { Write-Output $_.TaskName }"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
        capture_output=True, text=True, shell=False,
    )
    yaml_task_names = {i.task_name for i in instances.values()}
    for line in result.stdout.splitlines():
        tn = line.strip()
        if not tn:
            continue
        if tn not in yaml_task_names:
            drifts.append((tn, "ORPHAN_TASK", f"task '{tn}' exists but no yaml entry"))
    if not drifts:
        print("✅ reconcile: no drift")
        return 0
    print(f"⚠️  reconcile: {len(drifts)} drift(s):")
    for d in drifts:
        print(f"  - [{d[1]}] {d[2]}")
    if args.fix:
        print("\nApplying --fix:")
        for name, kind, _msg in drifts:
            if kind == "MISSING_TASK":
                inst = instances[name]
                ns = argparse.Namespace(name=name)
                print(f"  → re-registering '{name}' from yaml")
                cmd_register(ns)
            elif kind == "ORPHAN_TASK":
                print(f"  → deleting orphan task '{name}'")
                schtasks_delete(name)
    return 0 if not drifts else (0 if args.fix else 1)


# ============================================================================
# CLI plumbing
# ============================================================================

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="canvas_cron",
                                  description="Manage Canvas Pilot cron instances.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="Installed instances").set_defaults(fn=cmd_list)
    sub.add_parser("list-templates", help="Available action templates").set_defaults(fn=cmd_list_templates)
    sub.add_parser("list-courses", help="Courses from courses.yaml").set_defaults(fn=cmd_list_courses)

    p_create = sub.add_parser("create", help="Build new instance: yaml + XML + schtasks /create disabled")
    p_create.add_argument("name", help="instance name (yaml key + task name suffix)")
    p_create.add_argument("--template", required=True)
    p_create.add_argument("--course", required=True, help="course_id")
    p_create.add_argument("--days", type=int, required=True)
    p_create.add_argument("--time", required=True, help="HH:MM 24h local PT")
    p_create.add_argument("--start", required=True, help="YYYY-MM-DD start date")
    p_create.add_argument("--param", action="append", help="key=value (repeatable)")
    p_create.add_argument("--recipient", required=True, help="email address")
    p_create.add_argument("--authorized", action="store_true",
                          help="MUST be set for kind=autonomous templates")
    p_create.set_defaults(fn=cmd_create)

    p_del = sub.add_parser("delete", help="Remove yaml entry + task + archive ledger")
    p_del.add_argument("name")
    p_del.set_defaults(fn=cmd_delete)

    p_reg = sub.add_parser("register", help="Re-render XML + schtasks /create from existing yaml")
    p_reg.add_argument("name")
    p_reg.set_defaults(fn=cmd_register)

    p_unreg = sub.add_parser("unregister", help="schtasks /delete (yaml kept)")
    p_unreg.add_argument("name")
    p_unreg.set_defaults(fn=cmd_unregister)

    p_en = sub.add_parser("enable")
    p_en.add_argument("name")
    p_en.set_defaults(fn=cmd_enable)

    p_dis = sub.add_parser("disable")
    p_dis.add_argument("name")
    p_dis.set_defaults(fn=cmd_disable)

    p_fire = sub.add_parser("fire", help="Run instance in-proc (or --os-trigger to test)")
    p_fire.add_argument("name")
    p_fire.add_argument("--dry-run", action="store_true")
    p_fire.add_argument("--force", action="store_true")
    p_fire.add_argument("--os-trigger", action="store_true")
    p_fire.set_defaults(fn=cmd_fire)

    p_stat = sub.add_parser("status")
    p_stat.add_argument("name", nargs="?")
    p_stat.set_defaults(fn=cmd_status)

    p_rec = sub.add_parser("reconcile", help="Diff yaml vs Task Scheduler")
    p_rec.add_argument("name", nargs="?")
    p_rec.add_argument("--fix", action="store_true")
    p_rec.set_defaults(fn=cmd_reconcile)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
