# SPDX-License-Identifier: AGPL-3.0-or-later
"""canvas-cron framework — ActionTemplate ABC + CronInstance dataclass +
EmailTemplate / AutonomousTemplate subclasses + shared helpers.

This is the SHARED INFRASTRUCTURE for canvas-cron. Templates are course-agnostic
Python modules at `scripts/cron_template_<name>.py`. User-created cron instances
(course_id + schedule + params) live in `_private/cron_instances.yaml`. The
canvas-cron skill is the only entry point — students never write Python files
or edit yaml by hand.

Two kinds (CEO requirement: structural separation):

  EmailTemplate       — exec <10s. Reads Canvas, sends email via
                        src/gws_email.send_email. NO submit capability.
                        Adding submit to an email template requires promoting
                        it to AutonomousTemplate (different install gate).

  ScanTemplate        — runs a fresh Codex session in scan-only mode. It may
                        read Canvas and write the daily plan, but it never
                        receives mutation authority.

  AutonomousTemplate — runs a fresh Codex session with a signed durable
                        automation receipt. The receipt is validated against
                        the exact Canvas origin, course, template, and allowed
                        mutation actions before every fire.
                        Has consecutive_failures ledger + N=1/[REPEATED 2]
                        /[PAUSED] escalation + Sunday heartbeat. Auto-submits
                        to Canvas — install flow requires the user to type
                        `授权` keyword before this template gets registered.

Cookie health check (CEO 5/16 evening): ActionTemplate.run() invokes
`_cookie_check` BEFORE pre_run. If Canvas session is dead (cookies expired,
browser not authenticated) the template sends a single wake-up email to
`instance.recipient` telling the user to run `python -m src.canvas_login`,
then aborts without launching Codex. Scan/autonomous fires return non-zero so
Task Scheduler records the failed auth gate. In dry_run=True
mode the cookie probe is SKIPPED entirely (saves 5s × N gates during install
flow — cookies will be enforced on the first real OS-triggered fire).

ROOT calc: `Path(__file__).resolve().parent.parent` from scripts/cron_base.py
→ project root (depth 2). An assert fails loud if the file ever moves.
"""
from __future__ import annotations

import abc
import dataclasses
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Literal, Mapping, Optional
from zoneinfo import ZoneInfo

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
assert (ROOT / "courses.yaml").exists() or (ROOT / "SECRETS.md").exists(), (
    f"ROOT misresolved in cron_base.py: {ROOT} — expected project root with "
    f"courses.yaml or SECRETS.md. Did this file move?"
)

PT = ZoneInfo("America/Los_Angeles")
RUNS = ROOT / "runs"


def configured_canvas_origin() -> str:
    """Read the configured Canvas web origin without starting an auth backend."""
    values: dict[str, str] = {}
    env_path = ROOT / ".env"
    if env_path.is_file():
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    web_base = os.environ.get("CANVAS_WEB_BASE") or values.get("CANVAS_WEB_BASE")
    api_base = os.environ.get("CANVAS_BASE") or values.get("CANVAS_BASE")
    candidate = (web_base or api_base or "").rstrip("/")
    if candidate.endswith("/api/v1"):
        candidate = candidate[: -len("/api/v1")]
    if not candidate:
        raise RuntimeError("CANVAS_BASE is not configured")
    from src.authorization import canonical_canvas_origin

    return canonical_canvas_origin(candidate)


# ============================================================================
# Dataclasses
# ============================================================================

@dataclasses.dataclass(frozen=True)
class Schedule:
    """Calendar trigger for Windows Task Scheduler. start_boundary is local PT date."""
    days_interval: int
    time_hh_mm: str
    start_boundary: str  # ISO date "YYYY-MM-DD"


@dataclasses.dataclass(frozen=True)
class ParamSpec:
    """One row of a template's param_schema. Used by canvas_cron.py create
    for CLI validation and by canvas-cron skill for AskUserQuestion driving."""
    key: str
    type: Literal["int", "str", "bool"]
    default: object
    prompt: str
    description: str = ""


@dataclasses.dataclass(frozen=True)
class TemplateSpec:
    name: str                              # filesystem-discovered, matches cron_template_<name>.py
    kind: Literal["email", "scan", "autonomous"]
    description: str                       # one-line shown by list-templates
    param_schema: list[ParamSpec]          # tunable knobs (course_id/schedule/recipient are common, not in schema)
    execution_time_limit: str              # ISO 8601 duration "PT5M" / "PT45M"


@dataclasses.dataclass(frozen=True)
class CronInstance:
    """One user-created cron instance. Stored in _private/cron_instances.yaml."""
    name: str
    template: str
    course_id: str
    schedule: Schedule
    params: dict
    recipient: str
    created_at: str
    authorized_at: Optional[str] = None              # autonomous only
    authorized_for_course_id: Optional[str] = None   # tamper detect
    authorization_receipt: Optional[str] = None      # signed durable authority

    @property
    def task_name(self) -> str:
        """Windows Task Scheduler task name. Derived, never user-supplied."""
        return f"CanvasCron_{self.name}"

    def to_yaml_dict(self) -> dict:
        d = {
            "template": self.template,
            "course_id": self.course_id,
            "schedule": {
                "days_interval": self.schedule.days_interval,
                "time_hh_mm": self.schedule.time_hh_mm,
                "start_boundary": self.schedule.start_boundary,
            },
            "params": dict(self.params),
            "recipient": self.recipient,
            "created_at": self.created_at,
        }
        if self.authorized_at is not None:
            d["authorized_at"] = self.authorized_at
        if self.authorized_for_course_id is not None:
            d["authorized_for_course_id"] = self.authorized_for_course_id
        if self.authorization_receipt is not None:
            d["authorization_receipt"] = self.authorization_receipt
        return d

    @classmethod
    def from_yaml_dict(cls, name: str, d: dict) -> "CronInstance":
        s = d.get("schedule") or {}
        return cls(
            name=name,
            template=d["template"],
            course_id=str(d["course_id"]),
            schedule=Schedule(
                days_interval=int(s.get("days_interval", 1)),
                time_hh_mm=str(s.get("time_hh_mm", "09:00")),
                start_boundary=str(s.get("start_boundary", "")),
            ),
            params=dict(d.get("params") or {}),
            recipient=str(d.get("recipient", "")),
            created_at=str(d.get("created_at", "")),
            authorized_at=d.get("authorized_at"),
            authorized_for_course_id=d.get("authorized_for_course_id"),
            authorization_receipt=d.get("authorization_receipt"),
        )


# ============================================================================
# ActionTemplate ABC + run() orchestration
# ============================================================================

class ActionTemplate(abc.ABC):
    """Abstract base. Each concrete template subclasses EmailTemplate or
    AutonomousTemplate (not this class directly).
    """
    spec: TemplateSpec

    def __init__(self, spec: TemplateSpec) -> None:
        self.spec = spec
        self._dry_run_active = False

    # ----- per-instance derived paths -----
    def log_path(self, inst: CronInstance) -> Path:
        return RUNS / f"_{inst.name}_log.txt"

    def ledger_path(self, inst: CronInstance) -> Path:
        return RUNS / f"_{inst.name}_ledger.json"

    def lock_path(self, inst: CronInstance) -> Path:
        return RUNS / f"_{inst.name}.lock"

    # ----- abstract -----
    @abc.abstractmethod
    def pre_run(self, inst: CronInstance, dry_run: bool) -> Optional[str]:
        """Return None to proceed, or string reason to abort silently."""

    @abc.abstractmethod
    def classify(self, inst: CronInstance) -> dict:
        """Read Canvas state, return classification dict. Pure read."""

    @abc.abstractmethod
    def act_dry(self, inst: CronInstance, classification: dict) -> dict:
        """Log what would happen. No side effects."""

    @abc.abstractmethod
    def act_real(self, inst: CronInstance, classification: dict) -> dict:
        """Actually do the work. Return result summary."""

    def verify(self, inst: CronInstance, result: dict) -> dict:
        """Post-action verification (autonomous: Canvas readback; email: noop).
        Default = noop; AutonomousTemplate overrides."""
        return {}

    def validate_runtime_authorization(self, inst: CronInstance) -> Mapping[str, Any] | None:
        """Validate any authority needed by this template.

        Read-only templates need no receipt. Autonomous templates override
        this and fail closed before any Canvas probe or Codex launch.
        """
        return None

    def result_exit_code(
        self,
        inst: CronInstance,
        result: dict,
        verification: dict,
    ) -> int:
        """Translate action and verification evidence into the process code."""
        try:
            return int(result.get("exit_code", 0))
        except (TypeError, ValueError):
            return 1

    @property
    def canvas_probe_failure_is_error(self) -> bool:
        """Whether a failed Canvas auth/probe must reach Task Scheduler."""
        return self.spec.kind in {"scan", "autonomous"}

    # ----- helpers -----
    def log(self, inst: CronInstance, msg: str) -> None:
        ts = dt.datetime.now(PT).strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] {msg}"
        print(line, flush=True)
        if self._dry_run_active:
            return
        try:
            lp = self.log_path(inst)
            lp.parent.mkdir(parents=True, exist_ok=True)
            with lp.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

    def load_ledger(self, inst: CronInstance) -> dict:
        p = self.ledger_path(inst)
        readme = {"__readme__": "Do not delete — escalation/dedup state. See canvas-cron SKILL.md."}
        if not p.exists():
            return readme
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            d.setdefault("__readme__", readme["__readme__"])
            return d
        except Exception:
            return readme

    def save_ledger_atomic(self, inst: CronInstance, ledger: dict) -> None:
        ledger.setdefault("__readme__", "Do not delete — escalation/dedup state. See canvas-cron SKILL.md.")
        p = self.ledger_path(inst)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(ledger, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, p)

    def acquire_lock(self, inst: CronInstance) -> bool:
        lp = self.lock_path(inst)
        if lp.exists():
            try:
                payload = json.loads(lp.read_text(encoding="utf-8"))
                pid, started_at = payload.get("pid"), payload.get("started_at")
            except Exception:
                pid, started_at = None, None
            started = _parse_iso(started_at) if started_at else None
            if started and (dt.datetime.now(dt.timezone.utc) - started).total_seconds() > 5400:
                self.log(inst, f"stale lock (started {started_at}, pid={pid}) — taking over")
            else:
                self.log(inst, f"lock held by pid={pid} started_at={started_at} — silent exit")
                return False
        lp.parent.mkdir(parents=True, exist_ok=True)
        lp.write_text(json.dumps({
            "pid": os.getpid(),
            "started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }), encoding="utf-8")
        return True

    def release_lock(self, inst: CronInstance) -> None:
        try:
            lp = self.lock_path(inst)
            if lp.exists():
                lp.unlink()
        except Exception as e:
            self.log(inst, f"warning: release_lock failed: {e}")

    def send_email(self, subject: str, body: str, recipient: str,
                    inst: Optional[CronInstance] = None) -> bool:
        from src.gws_email import send_email as _send
        logger = (lambda m: self.log(inst, m)) if inst is not None else (
            lambda m: print(m, file=sys.stderr, flush=True)
        )
        return _send(subject, body, recipient, log=logger)

    # ----- Canvas session health gate (all template kinds) -----
    def _cookie_check(self, inst: CronInstance, dry_run: bool) -> Optional[str]:
        """Probe Canvas session WITHOUT launching Chrome. If dead and not
        dry-run, email the user a wake-up and abort this fire. In dry-run
        mode, SKIP the probe entirely (no 5s latency in install gate flow).
        """
        if dry_run:
            self.log(inst, "cookie probe skipped (dry-run); enforced at real fire")
            return None
        try:
            from src.canvas_client import session_alive
            ok = session_alive(timeout_s=5)
        except Exception as e:
            self.log(inst, f"cookie probe transient error: {e} — skipping fire")
            return f"cookie probe failed: {e}"
        if ok:
            return None
        # Cookie is dead — send wake-up email, abort fire
        subject = f"[Canvas cron] Cookie expired — please login (instance={inst.name})"
        body = (
            f"Canvas session cookie 已失效（可能 24h 过期，或浏览器没 authenticate）。\n"
            f"  instance:  {inst.name}\n"
            f"  template:  {inst.template}\n"
            f"  course_id: {inst.course_id}\n\n"
            f"这次 cron 触发没有 dispatch / 发提醒，只发本封邮件。\n\n"
            f"修复：在 Codex session 跑一次 `python -m src.canvas_login` 重登 Canvas。\n"
            f"下次到点 cron 会自动重试。\n"
        )
        self.send_email(subject, body, inst.recipient, inst=inst)
        self.log(inst, "cookie expired — sent wake-up email, aborting fire")
        return "cookie expired — emailed user"

    # ----- top-level entry called by canvas_cron.py fire -----
    def run(self, inst: CronInstance, dry_run: bool = False, force: bool = False) -> int:
        self._dry_run_active = dry_run
        try:
            self.log(inst, f"=== {inst.name} start "
                           f"(template={inst.template} dry_run={dry_run} force={force}) ===")

            # Legacy timestamp fields are retained only for migration/readback.
            # They never grant authority. A course mismatch is still evidence
            # of hand-editing and therefore fails closed.
            if (inst.authorized_for_course_id is not None
                    and inst.authorized_for_course_id != inst.course_id):
                self.log(inst, "legacy authorization course mismatch; refusing fire")
                return 1

            try:
                self.validate_runtime_authorization(inst)
            except Exception as exc:
                self.log(inst, f"authorization denied: {type(exc).__name__}: {exc}")
                return 1

            # Canvas auth health is checked only for a real fire. A scan or
            # autonomous fire must surface probe failure as non-zero.
            abort = self._cookie_check(inst, dry_run)
            if abort is not None:
                return 1 if self.canvas_probe_failure_is_error else 0

            abort = self.pre_run(inst, dry_run)
            if abort is not None:
                self.log(inst, f"pre_run abort: {abort}")
                return 0
            if not dry_run and not self.acquire_lock(inst):
                return 0

            try:
                classification = self.classify(inst)
                if dry_run:
                    self.act_dry(inst, classification)
                    self.log(inst, f"=== {inst.name} dry-run done ===")
                    return 0

                result = self.act_real(inst, classification)
                verification = self.verify(inst, result)
                exit_code = self.result_exit_code(inst, result, verification)
                if exit_code == 0:
                    self.log(inst, f"=== {inst.name} done ===")
                else:
                    self.log(inst, f"=== {inst.name} failed (exit={exit_code}) ===")
                return exit_code
            finally:
                if not dry_run:
                    self.release_lock(inst)
        except Exception as e:
            import traceback
            self.log(inst, f"FATAL: {type(e).__name__}: {e}")
            self.log(inst, traceback.format_exc())
            return 1
        finally:
            self._dry_run_active = False


class EmailTemplate(ActionTemplate):
    """Email-only kind. No agent subprocess. Concrete subclasses override
    pre_run / classify / act_dry / act_real."""
    pass


class CodexTemplate(ActionTemplate):
    """Shared fresh-Codex launcher for scan and autonomous templates."""

    CODEX_TIMEOUT_S = 30 * 60
    DEFAULT_ENV_VAR = "CANVAS_CRON_RUN"

    def logs_dir(self, inst: CronInstance) -> Path:
        return RUNS / f"_{inst.name}_logs"

    def env_var_name(self, inst: CronInstance) -> str:
        return inst.params.get("env_var_name") or self.DEFAULT_ENV_VAR

    def build_codex_prompt(self, inst: CronInstance, targets: list[dict]) -> str:
        raise NotImplementedError(
            f"{type(self).__name__} must implement build_codex_prompt()"
        )

    def fire_codex_session(
        self,
        inst: CronInstance,
        targets: list[dict],
        dry_run: bool,
    ) -> tuple[int, Path]:
        ts = dt.datetime.now(PT).strftime("%Y-%m-%d-%H%M%S")
        out_log = self.logs_dir(inst) / f"codex-{ts}.jsonl"
        prompt = self.build_codex_prompt(inst, targets)
        if dry_run:
            self.log(inst, f"  [dry-run] would start Codex -> {out_log}")
            self.log(inst, f"  [dry-run] prompt preview: {prompt[:300]}...")
            return (0, out_log)

        self.logs_dir(inst).mkdir(parents=True, exist_ok=True)
        env = {
            self.env_var_name(inst): "1",
            "CANVAS_CRON_TEMPLATE": inst.template,
            "CANVAS_CRON_COURSE_ID": inst.course_id,
        }
        if inst.authorization_receipt:
            env["CANVAS_CRON_AUTHORIZATION_RECEIPT"] = str(
                self.authorization_receipt_path(inst)
            )
            env["CANVAS_ENFORCE_MUTATION_AUTH"] = "1"

        self.log(inst, f"  starting fresh Codex session, log {out_log}")
        try:
            from src.codex_runner import run_codex

            result = run_codex(
                prompt,
                cwd=ROOT,
                log_path=out_log,
                timeout_s=self.CODEX_TIMEOUT_S,
                sandbox="workspace-write",
                network_access=True,
                env=env,
            )
        except Exception as exc:
            self.log(inst, f"  Codex launcher exception: {type(exc).__name__}: {exc}")
            return (1, out_log)
        if result.timed_out:
            self.log(inst, f"  Codex timed out after {self.CODEX_TIMEOUT_S}s")
        self.log(inst, f"  Codex exited {result.returncode}")
        return (result.returncode, result.log_path)

    def authorization_receipt_path(self, inst: CronInstance) -> Path:
        if not inst.authorization_receipt:
            raise PermissionError("no signed authorization receipt is configured")
        path = Path(inst.authorization_receipt)
        if not path.is_absolute():
            path = ROOT / path
        resolved = path.resolve()
        private_dir = (ROOT / "_private").resolve()
        try:
            resolved.relative_to(private_dir)
        except ValueError as exc:
            raise PermissionError(
                "durable cron authorization receipt must remain under _private/"
            ) from exc
        return resolved


class ScanTemplate(CodexTemplate):
    """Codex template class that has no Canvas mutation authority."""

    DEFAULT_ENV_VAR = "CANVAS_CRON_SCAN_ONLY"


class AutonomousTemplate(CodexTemplate):
    """Autonomous kind with signed authority, verification, and escalation.

    Required spec.default-params... actually spec.param_schema MUST include
    these keys (concrete template lists them):
      - max_items_per_run: int
      - pause_after_n_failures: int

    Required spec metadata (concrete sets these on RoutineSpec.default_params
    or hardcoded as class consts):
      - env_var_name: passed to the Codex subprocess environment

    Concrete subclasses MUST override:
      - build_codex_prompt(inst, targets) -> str
      - classify(inst) -> dict including a "targets" list
    """
    EVENTUAL_CONSISTENCY_WAIT_S = 90
    DEFAULT_ENV_VAR = "CANVAS_CRON_AUTO_RUN"

    def heartbeat_path(self, inst: CronInstance) -> Path:
        return RUNS / f"_{inst.name}_heartbeat.json"

    def validate_runtime_authorization(self, inst: CronInstance) -> Mapping[str, Any]:
        """Validate durable automation authority against every exact action."""
        from src.authorization import (
            AuthorizationDenied,
            load_authorization_receipt,
            validate_authorization_receipt,
        )

        path = self.authorization_receipt_path(inst)
        canvas_origin = configured_canvas_origin()
        receipt = load_authorization_receipt(path)
        actions = receipt.get("actions")
        if not isinstance(actions, list) or not actions:
            raise AuthorizationDenied("automation receipt has no exact actions")
        for action in actions:
            validate_authorization_receipt(
                receipt,
                canvas_origin=canvas_origin,
                course_id=inst.course_id,
                target_type="automation_template",
                target_id=inst.template,
                action=action,
                session_id=None,
            )
        return receipt

    def result_exit_code(
        self,
        inst: CronInstance,
        result: dict,
        verification: dict,
    ) -> int:
        child_code = super().result_exit_code(inst, result, verification)
        if child_code != 0:
            return child_code
        targets = result.get("targets") or []
        if not targets:
            return 0
        if not isinstance(verification, dict):
            return 1
        for target in targets:
            if verification.get(str(target.get("id"))) not in {"submitted", "graded"}:
                return 1
        return 0

    def heartbeat_body(self, inst: CronInstance, classification: dict) -> str:
        return (
            f"{inst.name} ({inst.template}) heartbeat — alive.\n\n"
            f"Classification this run:\n  {classification!r}\n"
        )

    def post_codex_verify(self, inst: CronInstance, targets: list[dict],
                          get_state: Callable[[dict], str]) -> dict[str, str]:
        self.log(inst, f"  waiting {self.EVENTUAL_CONSISTENCY_WAIT_S}s "
                       f"for Canvas eventual consistency")
        time.sleep(self.EVENTUAL_CONSISTENCY_WAIT_S)
        out: dict[str, str] = {}
        for t in targets:
            try:
                out[t["id"]] = get_state(t)
            except Exception as e:
                self.log(inst, f"  post-Codex verify({t.get('id')}) failed: {e}")
                out[t["id"]] = "error"
        return out

    def email_failure(self, inst: CronInstance, item: dict, ledger: dict,
                      post_state: str, codex_log: Path, body_extras: str = "") -> None:
        pause_n = inst.params.get("pause_after_n_failures", 3)
        key = f"{item['course_id']}:{item['id']}:cron_failure"
        entry = ledger.get(key, {"consecutive_failures": 0})
        n = entry.get("consecutive_failures", 0) + 1
        prefix = inst.name.upper().replace("_", " ")
        if n >= pause_n:
            subject = f"[{prefix} PAUSED — manual fix needed] {item['name']}"
            tail = (
                f"\n⚠️ N={n} consecutive failures. Cron will stop auto-attempting this "
                f"item until a different one succeeds or you manually reset "
                f"{self.ledger_path(inst).name}.\n"
            )
        elif n == 2:
            subject = f"[{prefix} REPEATED 2] {item['name']} still failing"
            tail = "\nSecond consecutive failure. One more and cron will pause auto-attempts.\n"
        else:
            subject = f"[{prefix}] {item['name']} auto-dispatch failed"
            tail = ""
        due_pt = _parse_iso(item.get("due_at"))
        due_str = due_pt.astimezone(PT).strftime("%Y-%m-%d %H:%M PT") if due_pt else "?"
        body = (
            f"Cron auto-dispatch failed:\n\n"
            f"  instance:   {inst.name}\n"
            f"  course:     {item.get('course_name')}\n"
            f"  name:       {item.get('name')}\n"
            f"  due:        {due_str}\n"
            f"  pts:        {item.get('points_possible')}\n"
            f"  link:       {item.get('html_url')}\n"
            f"  post_state: {post_state}\n"
            f"  Codex log:  {codex_log}\n"
            f"{body_extras}{tail}"
        )
        ok = self.send_email(subject, body, inst.recipient, inst=inst)
        self.log(inst, f"  failure email N={n} -> {'OK' if ok else 'FAILED'}: {item['name']}")
        if ok:
            ledger[key] = {
                "course_name": item.get("course_name"),
                "assignment_name": item["name"],
                "consecutive_failures": n,
                "last_attempt_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "last_post_state": post_state,
                "last_codex_log": str(codex_log),
            }

    def reset_failure_counter(self, item: dict, ledger: dict, inst: CronInstance) -> None:
        key = f"{item['course_id']}:{item['id']}:cron_failure"
        if key in ledger:
            self.log(inst, f"  reset failure counter for {item['name']}")
            del ledger[key]

    def is_paused(self, item: dict, ledger: dict, inst: CronInstance) -> bool:
        pause_n = inst.params.get("pause_after_n_failures", 3)
        key = f"{item['course_id']}:{item['id']}:cron_failure"
        entry = ledger.get(key, {})
        return entry.get("consecutive_failures", 0) >= pause_n

    def maybe_send_heartbeat(self, inst: CronInstance, now_pt: dt.datetime,
                              classification: dict, dry_run: bool) -> None:
        if now_pt.weekday() != 6:  # Sunday only
            return
        hp = self.heartbeat_path(inst)
        sunday_iso = now_pt.date().isoformat()
        if hp.exists():
            try:
                last = json.loads(hp.read_text(encoding="utf-8"))
                if last.get("last_sunday") == sunday_iso:
                    self.log(inst, f"  heartbeat already sent today ({sunday_iso})")
                    return
            except Exception:
                pass
        subject = f"[{inst.name} cron heartbeat] {sunday_iso} — still alive"
        body = self.heartbeat_body(inst, classification)
        if dry_run:
            self.log(inst, f"  [dry-run] would send heartbeat: subj={subject!r}")
            return
        ok = self.send_email(subject, body, inst.recipient, inst=inst)
        self.log(inst, f"  heartbeat email -> {'OK' if ok else 'FAILED'}")
        if ok:
            hp.write_text(json.dumps({
                "last_sunday": sunday_iso,
                "sent_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            }), encoding="utf-8")


# ============================================================================
# Module-level helpers
# ============================================================================

def _parse_iso(s: Optional[str]) -> Optional[dt.datetime]:
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def check_manual_session_active() -> Optional[str]:
    """Conflict-detect: if a manual canvas-scan session is mid-flight, abort cron."""
    today_dir = RUNS / dt.date.today().isoformat()
    marker = today_dir / ".scan_in_progress"
    if marker.exists():
        return "manual session marker .scan_in_progress active"
    plan = today_dir / "plan.json"
    if plan.exists():
        age_s = time.time() - plan.stat().st_mtime
        if age_s < 30 * 60:
            return f"plan.json written {int(age_s)}s ago — user may be reviewing"
    return None


def check_tz_window(now_pt: dt.datetime, window: tuple[int, int]) -> bool:
    """True if now_pt.hour is within [window[0], window[1]] inclusive."""
    return window[0] <= now_pt.hour <= window[1]


def load_courses_yaml() -> dict:
    """Load courses.yaml from project root. Returns the full parsed dict."""
    import yaml
    return yaml.safe_load((ROOT / "courses.yaml").read_text(encoding="utf-8")) or {}


def course_name_for(course_id: str) -> str:
    """Look up the human name for a course_id from courses.yaml routes.
    Returns '<course_id>' if not found."""
    cfg = load_courses_yaml()
    route = (cfg.get("routes") or {}).get(course_id) or (cfg.get("routes") or {}).get(int(course_id) if course_id.isdigit() else course_id)
    if route:
        return route.get("name") or course_id
    return course_id
