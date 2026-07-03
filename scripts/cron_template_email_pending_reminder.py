# SPDX-License-Identifier: AGPL-3.0-or-later
"""canvas-cron template: `email_pending_reminder` (kind=email)

Generic reminder template. For a given course_id, lists Canvas assignments that
are still unsubmitted AND due within `threshold_days`, sends one summary email
to `recipient`. Dedup: ledger key `<course_id>:<assignment_id>:reminder:<YYYY-MM-DD>`
ensures at most one alert per assignment per calendar day, even if the cron
fires multiple times.

No CC subprocess. No Canvas state changes. ~5 seconds per run.

This template is COURSE-AGNOSTIC. The user creates instances bound to
specific courses via the canvas-cron skill (which writes to
_private/cron_instances.yaml). To add a new course's reminder, just create
another instance — don't write a new template.
"""
from __future__ import annotations

import datetime as dt
import time
from typing import Optional

from scripts.cron_base import (
    PT, EmailTemplate, CronInstance, ParamSpec, TemplateSpec,
    _parse_iso, course_name_for, load_courses_yaml,
)

ALL_COURSES_SENTINEL = "all"
EMAIL_INTERVAL_S = 60  # seconds between repeat sends in act_real


SPEC = TemplateSpec(
    name="email_pending_reminder",
    kind="email",
    description="Email a summary of pending assignments due within N days (no auto-submit).",
    param_schema=[
        ParamSpec(
            key="threshold_days", type="int", default=3,
            prompt="Email if any assignment is due within how many days?",
            description="A summary email is sent only if there's at least one "
                        "unsubmitted assignment with due_at < now + threshold_days.",
        ),
        ParamSpec(
            key="email_count", type="int", default=1,
            prompt="Send how many copies per cron fire (spaced 60s apart)?",
            description="Repeat the same summary email N times within one fire, "
                        "60s apart. Set to 2 if you sometimes miss a single "
                        "alert. Set to 1 for normal behavior.",
        ),
    ],
    execution_time_limit="PT15M",  # accommodates email_count up to ~10 with 60s spacing
)


class EmailPendingReminder(EmailTemplate):
    """Generic email pending reminder."""

    def pre_run(self, inst: CronInstance, dry_run: bool) -> Optional[str]:
        # No tz window — email reminders are cheap and time-agnostic
        return None

    def _target_courses(self, inst: CronInstance) -> list[tuple[str, str]]:
        """Return [(course_id, course_name)] this instance covers.

        Special: inst.course_id == "all" expands to all routes in courses.yaml.
        Otherwise it's a single course.
        """
        if inst.course_id == ALL_COURSES_SENTINEL:
            cfg = load_courses_yaml()
            out: list[tuple[str, str]] = []
            for cid, route in (cfg.get("routes") or {}).items():
                cid_str = str(cid)
                name = (route or {}).get("name") or f"course {cid_str}"
                out.append((cid_str, name))
            return out
        return [(inst.course_id, course_name_for(inst.course_id))]

    def classify(self, inst: CronInstance) -> dict:
        from src import canvas_client as cv
        threshold_days = int(inst.params.get("threshold_days", 3))
        cutoff = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=threshold_days)
        now_utc = dt.datetime.now(dt.timezone.utc)
        by_course: dict[str, dict] = {}
        total = 0
        for cid, cname in self._target_courses(inst):
            try:
                assignments = cv.list_assignments(cid)
            except Exception as e:
                self.log(inst, f"list_assignments({cid}) failed: {e}")
                by_course[cid] = {"course_name": cname, "pending": []}
                continue
            pending = []
            for a in assignments:
                aid = str(a.get("id"))
                try:
                    sub = cv.get_submission(cid, aid)
                except Exception as e:
                    self.log(inst, f"  get_submission({cid},{aid}) failed: {e}")
                    continue
                state = sub.get("workflow_state")
                if state in ("submitted", "graded"):
                    continue
                due_at = _parse_iso(a.get("due_at"))
                if due_at is None:
                    continue
                if due_at < now_utc:
                    continue
                if due_at > cutoff:
                    continue
                pending.append({
                    "id": aid,
                    "name": a.get("name") or "(unnamed)",
                    "due_at": a.get("due_at"),
                    "points_possible": a.get("points_possible"),
                    "html_url": a.get("html_url"),
                })
            pending.sort(key=lambda x: x.get("due_at") or "")
            by_course[cid] = {"course_name": cname, "pending": pending}
            total += len(pending)
            self.log(inst, f"  {cname}: {len(pending)} pending in next {threshold_days}d")
        return {
            "by_course": by_course,
            "threshold_days": threshold_days,
            "total_pending": total,
        }

    def _format_body(self, inst: CronInstance, classification: dict) -> tuple[str, str]:
        by_course = classification.get("by_course") or {}
        total = classification.get("total_pending", 0)
        threshold = classification.get("threshold_days")
        scope_label = "all courses" if inst.course_id == ALL_COURSES_SENTINEL else (
            next(iter(by_course.values())).get("course_name") if by_course else inst.course_id
        )
        if total == 0:
            return (
                f"[Canvas reminder] {scope_label}: 0 pending in next {threshold} day(s)",
                f"{scope_label}: 0 pending assignments within the next "
                f"{threshold} day(s). All clear.\n",
            )
        subject = f"[Canvas reminder] {scope_label}: {total} pending in next {threshold} day(s)"
        lines = [f"{scope_label}: {total} pending assignment(s) due within "
                 f"the next {threshold} day(s):\n"]
        for cid, cdata in by_course.items():
            pending = cdata.get("pending") or []
            if not pending:
                continue
            if inst.course_id == ALL_COURSES_SENTINEL:
                lines.append(f"--- {cdata.get('course_name')} ({len(pending)}) ---")
            for p in pending:
                due_pt = _parse_iso(p.get("due_at"))
                due_str = due_pt.astimezone(PT).strftime("%Y-%m-%d %H:%M PT") if due_pt else "?"
                lines.append(f"  • {p['name']}")
                lines.append(f"    due:  {due_str}")
                if p.get("points_possible"):
                    lines.append(f"    pts:  {p['points_possible']}")
                if p.get("html_url"):
                    lines.append(f"    link: {p['html_url']}")
                lines.append("")
        return subject, "\n".join(lines)

    def act_dry(self, inst: CronInstance, classification: dict) -> dict:
        total = classification.get("total_pending", 0)
        subject, _body = self._format_body(inst, classification)
        email_count = int(inst.params.get("email_count", 1))
        self.log(inst, f"  [dry-run] would send {email_count} email(s) of: "
                       f"{subject}  ({total} item(s) across "
                       f"{len(classification.get('by_course') or {})} course(s))")
        return {"would_email": True, "n_pending": total, "email_count": email_count}

    def act_real(self, inst: CronInstance, classification: dict) -> dict:
        ledger = self.load_ledger(inst)
        total = classification.get("total_pending", 0)
        if total == 0:
            self.log(inst, "no pending in window — silent skip (no email)")
            self.save_ledger_atomic(inst, ledger)
            return {"emailed": False, "n_pending": 0}
        # Dedup: collect all (course_id, assignment_id) pairs not already alerted today
        today_iso = dt.datetime.now(PT).date().isoformat()
        fresh_keys: list[str] = []
        for cid, cdata in (classification.get("by_course") or {}).items():
            for p in cdata.get("pending") or []:
                key = f"{cid}:{p['id']}:reminder:{today_iso}"
                if key in ledger:
                    continue
                fresh_keys.append(key)
        if not fresh_keys:
            self.log(inst, f"all {total} pending items already alerted today — skip")
            self.save_ledger_atomic(inst, ledger)
            return {"emailed": False, "n_pending": total, "n_fresh": 0}
        subject, body = self._format_body(inst, classification)
        email_count = max(1, int(inst.params.get("email_count", 1)))
        ok_first = False
        for i in range(email_count):
            ok = self.send_email(subject, body, inst.recipient, inst=inst)
            self.log(inst, f"  reminder email {i+1}/{email_count} -> "
                           f"{'OK' if ok else 'FAILED'}: "
                           f"{len(fresh_keys)}/{total} fresh")
            if i == 0 and ok:
                ok_first = True
            if i < email_count - 1:
                time.sleep(EMAIL_INTERVAL_S)
        if ok_first:
            now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
            for key in fresh_keys:
                ledger[key] = {"alerted_at": now_iso}
            self.save_ledger_atomic(inst, ledger)
        return {
            "emailed": ok_first, "n_pending": total,
            "n_fresh": len(fresh_keys), "email_count": email_count,
        }


template = EmailPendingReminder(SPEC)
