# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path

import pytest

from scripts import canvas_cron
from scripts.cron_base import CronInstance, Schedule, configured_canvas_origin
from scripts.cron_template_autonomous_submit_pending import (
    AutonomousSubmitPending,
    SPEC as AUTONOMOUS_SPEC,
)
from scripts.cron_template_scan_pending import ScanPending, SPEC as SCAN_SPEC


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PATHS = (
    ROOT / "scripts" / "cron_base.py",
    ROOT / "scripts" / "canvas_cron.py",
    ROOT / "scripts" / "cron_registry.py",
    ROOT / "scripts" / "cron_template_autonomous_submit_pending.py",
    ROOT / "scripts" / "cron_template_scan_pending.py",
    ROOT / ".agents" / "skills" / "canvas-cron" / "SKILL.md",
)


def _instance(
    *,
    name: str = "codex_cron_test",
    template: str = "scan_pending",
    course_id: str = "42",
    receipt: str | None = None,
) -> CronInstance:
    return CronInstance(
        name=name,
        template=template,
        course_id=course_id,
        schedule=Schedule(1, "09:00", "2030-01-01"),
        params={},
        recipient="local-test@example.invalid",
        created_at="2030-01-01T00:00:00Z",
        authorization_receipt=receipt,
    )


def test_runtime_contains_no_legacy_agent_launcher_or_text() -> None:
    text = "\n".join(path.read_text(encoding="utf-8") for path in RUNTIME_PATHS)
    assert "claude" not in text.lower()
    assert re.search(r"\bCC\b", text) is None
    assert "from src.codex_runner import run_codex" in text


def test_autonomous_fire_fails_before_probe_without_signed_receipt(monkeypatch) -> None:
    template = AutonomousSubmitPending(AUTONOMOUS_SPEC)
    monkeypatch.setattr(template, "log", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        template,
        "_cookie_check",
        lambda *_args, **_kwargs: pytest.fail("probe must not run before authority"),
    )

    assert template.run(
        _instance(template="autonomous_submit_pending"),
        dry_run=True,
    ) == 1


def test_signed_automation_receipt_is_exactly_bound(monkeypatch, tmp_path: Path) -> None:
    import scripts.cron_base as cron_base
    from src.authorization import AuthorizationDenied, create_authorization_receipt

    key_path = tmp_path / "authorization.key"
    receipt_path = tmp_path / "_private" / "receipt.json"
    monkeypatch.setenv("CANVAS_AUTHORIZATION_KEY_PATH", str(key_path))
    monkeypatch.setenv("CANVAS_BASE", "https://canvas.test.invalid/api/v1")
    monkeypatch.setattr(cron_base, "ROOT", tmp_path)
    create_authorization_receipt(
        canvas_origin=configured_canvas_origin(),
        course_id="42",
        target_type="automation_template",
        target_id="autonomous_submit_pending",
        actions=["assignment.submit_text"],
        session_id="cron-delegation:test",
        expires_at=dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1),
        authority_reference={"approval_id": "unit-test-authority"},
        output_path=receipt_path,
    )
    template = AutonomousSubmitPending(AUTONOMOUS_SPEC)
    receipt = template.validate_runtime_authorization(
        _instance(
            template="autonomous_submit_pending",
            receipt=str(receipt_path),
        )
    )
    assert receipt["target_type"] == "automation_template"
    assert receipt["target_id"] == "autonomous_submit_pending"

    with pytest.raises(AuthorizationDenied, match="course"):
        template.validate_runtime_authorization(
            _instance(
                template="autonomous_submit_pending",
                course_id="different-course",
                receipt=str(receipt_path),
            )
        )


def test_codex_child_nonzero_is_propagated(monkeypatch, tmp_path: Path) -> None:
    template = ScanPending(SCAN_SPEC)
    monkeypatch.setattr(template, "log", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(template, "_cookie_check", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(template, "pre_run", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(template, "acquire_lock", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(template, "release_lock", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        template,
        "classify",
        lambda _inst: {"today_dir": tmp_path},
    )
    monkeypatch.setattr(
        template,
        "act_real",
        lambda *_args, **_kwargs: {"exit_code": 17, "today_dir": tmp_path},
    )
    monkeypatch.setattr(template, "verify", lambda *_args, **_kwargs: {"ok": True})

    assert template.run(_instance(), dry_run=False) == 17


def test_codex_timeout_code_is_not_rewritten() -> None:
    template = ScanPending(SCAN_SPEC)
    assert template.result_exit_code(
        _instance(),
        {"exit_code": 124},
        {"ok": False, "reason": "timeout"},
    ) == 124


def test_verification_failure_is_nonzero(monkeypatch, tmp_path: Path) -> None:
    template = ScanPending(SCAN_SPEC)
    monkeypatch.setattr(template, "log", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(template, "_cookie_check", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(template, "pre_run", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(template, "acquire_lock", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(template, "release_lock", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(template, "classify", lambda _inst: {"today_dir": tmp_path})
    monkeypatch.setattr(
        template,
        "act_real",
        lambda *_args, **_kwargs: {"exit_code": 0, "today_dir": tmp_path},
    )
    monkeypatch.setattr(
        template,
        "verify",
        lambda *_args, **_kwargs: {"ok": False, "reason": "missing artifacts"},
    )

    assert template.run(_instance(), dry_run=False) == 1


def test_scan_verifier_accepts_fresh_zero_pending_terminal_state(tmp_path: Path) -> None:
    template = ScanPending(SCAN_SPEC)
    (tmp_path / "scan.json").write_text(
        json.dumps({"complete": True, "items": [], "course_errors": []}),
        encoding="utf-8",
    )
    (tmp_path / "assignments.json").write_text("[]", encoding="utf-8")
    verification = template.verify(
        _instance(),
        {"exit_code": 0, "today_dir": tmp_path, "started_at_ns": 0},
    )
    assert verification["ok"] is True
    assert verification["no_pending"] is True
    assert verification["pending_count"] == 0
    assert template.result_exit_code(_instance(), {"exit_code": 0}, verification) == 0


def test_autonomous_post_state_failure_is_nonzero() -> None:
    template = AutonomousSubmitPending(AUTONOMOUS_SPEC)
    code = template.result_exit_code(
        _instance(template="autonomous_submit_pending"),
        {"exit_code": 0, "targets": [{"id": "7"}]},
        {"7": "still_pending"},
    )
    assert code == 1


def test_canvas_probe_failure_is_nonzero_for_scan(monkeypatch) -> None:
    template = ScanPending(SCAN_SPEC)
    monkeypatch.setattr(template, "log", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        template,
        "_cookie_check",
        lambda *_args, **_kwargs: "authentication probe failed",
    )
    monkeypatch.setattr(
        template,
        "pre_run",
        lambda *_args, **_kwargs: pytest.fail("pre_run must not follow failed probe"),
    )
    assert template.run(_instance(), dry_run=False) == 1


def test_scan_template_launches_through_run_codex(monkeypatch, tmp_path: Path) -> None:
    from src.codex_runner import CodexRunResult
    import src.codex_runner as runner

    captured: dict = {}

    def fake_run_codex(prompt: str, **kwargs):
        captured["prompt"] = prompt
        captured.update(kwargs)
        return CodexRunResult(
            returncode=0,
            log_path=Path(kwargs["log_path"]),
            timed_out=False,
            argv=("codex",),
        )

    template = ScanPending(SCAN_SPEC)
    monkeypatch.setattr(template, "logs_dir", lambda _inst: tmp_path / "logs")
    monkeypatch.setattr(template, "log", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(runner, "run_codex", fake_run_codex)

    code, _log = template.fire_codex_session(_instance(), [], dry_run=False)
    assert code == 0
    assert captured["sandbox"] == "workspace-write"
    assert captured["network_access"] is True
    assert captured["env"]["CANVAS_CRON_SCAN_ONLY"] == "1"
    assert "CANVAS_ENFORCE_MUTATION_AUTH" not in captured["env"]


def test_scan_prompt_stops_at_approval_boundary() -> None:
    prompt = ScanPending(SCAN_SPEC).build_codex_prompt(_instance(), [])
    assert "canvas-scan skill exactly once" in prompt
    assert "Do not invoke canvas-execute" in prompt
    assert "Do not create an authorization receipt" in prompt
    assert "Do not upload, submit" in prompt


def test_dry_run_does_not_launch_codex_or_mutate_scheduler(monkeypatch) -> None:
    template = ScanPending(SCAN_SPEC)
    inst = _instance(name="dry_run_no_scheduler")
    monkeypatch.setattr(canvas_cron.cron_registry, "get_instance", lambda _name: inst)
    monkeypatch.setattr(canvas_cron.cron_registry, "get_template", lambda _name: template)
    monkeypatch.setattr(
        template,
        "fire_codex_session",
        lambda *_args, **_kwargs: pytest.fail("dry-run must not launch Codex"),
    )
    monkeypatch.setattr(
        template,
        "send_email",
        lambda *_args, **_kwargs: pytest.fail("dry-run must not send email"),
    )
    monkeypatch.setattr(
        canvas_cron,
        "set_task_enabled",
        lambda *_args, **_kwargs: pytest.fail("dry-run must not mutate scheduler"),
    )
    monkeypatch.setattr(
        canvas_cron,
        "schtasks_create_from_xml",
        lambda *_args, **_kwargs: pytest.fail("dry-run must not create scheduler task"),
    )
    monkeypatch.setattr(
        canvas_cron,
        "schtasks_delete",
        lambda *_args, **_kwargs: pytest.fail("dry-run must not delete scheduler task"),
    )

    code = canvas_cron.cmd_fire(
        argparse.Namespace(
            name=inst.name,
            dry_run=True,
            force=False,
            os_trigger=False,
        )
    )
    assert code == 0
    assert not template.log_path(inst).exists()


def test_dry_run_and_os_trigger_is_rejected_before_scheduler(monkeypatch) -> None:
    template = ScanPending(SCAN_SPEC)
    inst = _instance(name="dry_run_os_conflict")
    monkeypatch.setattr(canvas_cron.cron_registry, "get_instance", lambda _name: inst)
    monkeypatch.setattr(canvas_cron.cron_registry, "get_template", lambda _name: template)
    monkeypatch.setattr(
        canvas_cron,
        "task_exists",
        lambda *_args, **_kwargs: pytest.fail("conflicting flags must not query scheduler"),
    )
    code = canvas_cron.cmd_fire(
        argparse.Namespace(
            name=inst.name,
            dry_run=True,
            force=False,
            os_trigger=True,
        )
    )
    assert code == 1


def test_create_missing_receipt_fails_before_any_scheduler_write(monkeypatch) -> None:
    template = AutonomousSubmitPending(AUTONOMOUS_SPEC)
    monkeypatch.setattr(canvas_cron.cron_registry, "get_template", lambda _name: template)
    monkeypatch.setattr(
        canvas_cron,
        "schtasks_create_from_xml",
        lambda *_args, **_kwargs: pytest.fail("missing authority must fail before scheduler"),
    )
    args = argparse.Namespace(
        name="no_receipt",
        template="autonomous_submit_pending",
        course="42",
        days=1,
        time="19:00",
        start="2030-01-01",
        param=[],
        recipient="local-test@example.invalid",
        authorization_receipt=None,
    )
    assert canvas_cron.cmd_create(args) == 1
