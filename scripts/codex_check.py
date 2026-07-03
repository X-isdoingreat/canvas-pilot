# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_RE = re.compile(
    r"[U]CI|[x]ianzh|tao\.for|gmail|@[u]ci|胡|[献]之",
    re.IGNORECASE,
)


def run(args: list[str]) -> None:
    print("+", " ".join(args))
    cp = subprocess.run(args, cwd=ROOT, text=True)
    if cp.returncode != 0:
        raise SystemExit(cp.returncode)


def ast_check(paths: list[Path]) -> None:
    for base in paths:
        for path in base.rglob("*.py") if base.is_dir() else [base]:
            rel = path.relative_to(ROOT)
            print(f"AST {rel}")
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def privacy_check(paths: list[Path]) -> None:
    hits: list[str] = []
    for base in paths:
        if not base.exists():
            continue
        files = base.rglob("*") if base.is_dir() else [base]
        for path in files:
            if not path.is_file():
                continue
            rel = path.relative_to(ROOT).as_posix()
            if rel.endswith("CODEX_REGRESSION.md"):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for match in PRIVATE_RE.finditer(text):
                hits.append(f"{rel}: {match.group(0)}")
    if hits:
        print("Private marker hits:")
        for hit in hits:
            print("-", hit)
        raise SystemExit(1)


def command_count_check() -> None:
    data = json.loads((ROOT / ".codex" / "hooks.json").read_text(encoding="utf-8"))
    count = 0
    for entries in (data.get("hooks") or {}).values():
        for entry in entries:
            for hook in entry.get("hooks") or []:
                if "command" in hook:
                    count += 1
    print(f"hooks.json command count: {count}")
    if count != 4:
        raise SystemExit("Expected exactly 4 command hooks")


def require_text(path: Path, pattern: str, label: str) -> None:
    if not path.exists():
        raise SystemExit(f"Missing required file: {path.relative_to(ROOT)}")
    text = path.read_text(encoding="utf-8", errors="ignore")
    print(f"CHECK {path.relative_to(ROOT)}: {label}")
    if not re.search(pattern, text, re.IGNORECASE | re.MULTILINE):
        raise SystemExit(f"Missing {label} in {path.relative_to(ROOT)}")


def require_all_text(path: Path, labels: dict[str, str]) -> None:
    for label, pattern in labels.items():
        require_text(path, pattern, label)


def check_b2() -> None:
    run([sys.executable, "tests/codex_hooks/run_hook_tests.py"])
    ast_check([ROOT / "src", ROOT / ".codex" / "hooks", ROOT / "tests" / "codex_hooks"])
    privacy_check([
        ROOT / "AGENTS.md",
        ROOT / "docs",
        ROOT / ".agents",
        ROOT / ".codex",
        ROOT / "tests" / "codex_hooks",
    ])
    command_count_check()


def check_b3() -> None:
    skill = ROOT / ".agents" / "skills" / "canvas-bootstrap" / "SKILL.md"
    require_text(skill, r"^name:\s*canvas-bootstrap", "bootstrap frontmatter")
    require_text(skill, r"routes.*empty|routes.*commented|first", "empty routes first-run")
    require_text(skill, r"courses\.yaml", "courses.yaml route config")
    require_text(skill, r"bucket_recurring", "recurring pattern helper")
    require_text(skill, r"min_freq=3", "min_freq=3")
    require_text(skill, r"UNFILLED_SKELETON", "skeleton sentinel")
    require_text(skill, r"STOP if you are Codex", "dispatch stop guard")
    require_text(skill, r"deferred_to_next_run=true", "deferred retry result")
    require_text(skill, r"cross-course|different courses|one skill maps to one course", "cross-course rejection")
    require_text(skill, r"\.agents/skills/canvas-", "Codex-side generated skill path")
    require_text(skill, r"Do not write `?\.claude|Do not write \.claude", "no Claude driver writes")
    run([sys.executable, "tests/codex_bootstrap/run_bootstrap_tests.py"])
    ast_check([ROOT / "tests" / "codex_bootstrap"])
    privacy_check([
        ROOT / "AGENTS.md",
        ROOT / "docs",
        ROOT / ".agents",
        ROOT / "tests" / "codex_bootstrap",
    ])


def check_b4() -> None:
    skill = ROOT / ".agents" / "skills" / "canvas-scan" / "SKILL.md"
    require_text(skill, r"^name:\s*canvas-scan", "scan frontmatter")
    require_text(skill, r"canvas-bootstrap", "bootstrap handoff")
    require_text(skill, r"routes.*empty|routes.*commented|routes.*None", "empty route handling")
    require_text(skill, r"canvas_client --probe|src\.canvas_client --probe", "auth probe")
    require_text(skill, r"router --dry-run|src\.router --dry-run", "router dry-run")
    require_text(skill, r"assignments\.json", "assignments snapshot")
    require_text(skill, r"plan\.json", "plan output")
    require_text(skill, r"_processed\.json", "cross-day ledger")
    require_text(skill, r"deferred_to_next_run", "deferred re-entry")
    require_text(skill, r"get_submission", "live submission state")
    require_text(skill, r"live_state", "live_state")
    require_text(skill, r"os\.replace|atomic", "atomic plan write")
    require_text(skill, r"MUST NOT execute|must not execute|Do not.*execute", "scan cannot execute")
    require_text(skill, r"MUST NOT write.*result\.json|Do not.*result\.json", "scan writes no result")
    require_text(skill, r"MUST NOT write.*REPORT\.md|Do not.*REPORT\.md", "scan writes no report")
    require_text(skill, r"MUST NOT create.*\.scan_in_progress|Do not.*\.scan_in_progress", "scan creates no marker")
    require_text(skill, r"Due within 3 days|三天内", "three-day table")
    require_text(skill, r"Due within 7 days|七天内", "seven-day table")
    run([sys.executable, "tests/codex_runtime/run_scan_tests.py"])
    ast_check([ROOT / "tests" / "codex_runtime"])
    privacy_check([
        ROOT / "AGENTS.md",
        ROOT / "docs",
        ROOT / ".agents",
        ROOT / "tests" / "codex_runtime",
    ])


def check_b5() -> None:
    skill = ROOT / ".agents" / "skills" / "canvas-execute" / "SKILL.md"
    require_text(skill, r"^name:\s*canvas-execute", "execute frontmatter")
    require_text(skill, r"plan\.json", "plan precondition")
    require_text(skill, r"assignments\.json", "assignments precondition")
    require_text(skill, r"expires_at|expired", "plan expiration")
    require_text(skill, r"approve all", "approve all")
    require_text(skill, r"urgent only", "urgent only")
    require_text(skill, r"range|1-4", "range approval")
    require_text(skill, r"swap", "swap skill")
    require_text(skill, r"defer|cancel", "defer cancel")
    require_text(skill, r"\.scan_in_progress", "execute marker")
    require_text(skill, r"sequential|one at a time", "sequential dispatch")
    require_text(skill, r"Skill tool|Dispatch via the Skill", "skill dispatch")
    require_text(skill, r"result\.json", "result json")
    require_text(skill, r"_processed\.json", "processed ledger")
    require_text(skill, r"deferred_to_next_run", "deferred retry")
    require_text(skill, r"not approved this run", "unapproved placeholder")
    require_text(skill, r"REPORT\.md", "report")
    require_text(skill, r"urgent banner", "urgent banner")
    require_text(skill, r"Error Help Section|debug-help", "error help")
    require_text(skill, r"Delivery Sync|delivery folder", "delivery sync")
    require_text(skill, r"Do not submit|Do not submit to Canvas by default", "no default submit")
    run([sys.executable, "tests/codex_runtime/run_execute_tests.py"])
    ast_check([ROOT / "tests" / "codex_runtime"])
    privacy_check([
        ROOT / "AGENTS.md",
        ROOT / "docs",
        ROOT / ".agents",
        ROOT / "tests" / "codex_runtime",
    ])


def check_b6() -> None:
    require_text(ROOT / "tests" / "codex_runtime" / "README.md", r"fake|fixture|offline|no network", "offline fixture docs")
    require_text(ROOT / "tests" / "codex_runtime" / "README.md", r"CANVAS_TOKEN|token", "token-like auth coverage")
    require_text(ROOT / "tests" / "codex_runtime" / "README.md", r"cookie|login", "cookie-like auth coverage")
    require_text(ROOT / "tests" / "codex_runtime" / "run_all.py", r"run_scan_tests", "scan suite included")
    require_text(ROOT / "tests" / "codex_runtime" / "run_all.py", r"run_execute_tests", "execute suite included")
    run([sys.executable, "tests/codex_runtime/run_all.py"])
    ast_check([ROOT / "tests" / "codex_runtime"])
    privacy_check([
        ROOT / "AGENTS.md",
        ROOT / "docs",
        ROOT / ".agents",
        ROOT / "tests" / "codex_runtime",
    ])


def check_b7() -> None:
    require_text(ROOT / ".codex" / "hooks" / "post_tool_guard.py", r"spec_grounding|references", "spec grounding hook")
    require_text(ROOT / ".codex" / "hooks" / "post_tool_guard.py", r"identifier_grounding|ungrounded", "identifier grounding hook")
    require_text(ROOT / ".codex" / "hooks" / "pre_tool_guard.py", r"submit|upload|verification\.log|PASS|FAIL", "pre-submit gate")
    require_text(ROOT / "tests" / "codex_hooks" / "run_advanced_hook_tests.py", r"spec_grounding|identifier_grounding|pre_submit|negative|positive", "advanced hook tests")
    run([sys.executable, "tests/codex_hooks/run_hook_tests.py"])
    run([sys.executable, "tests/codex_hooks/run_advanced_hook_tests.py"])
    ast_check([ROOT / ".codex" / "hooks", ROOT / "tests" / "codex_hooks"])
    privacy_check([
        ROOT / "AGENTS.md",
        ROOT / "docs",
        ROOT / ".agents",
        ROOT / ".codex",
        ROOT / "tests" / "codex_hooks",
    ])


def check_b8() -> None:
    doc = ROOT / "docs" / "CODEX_ONBOARDING.md"
    require_text(doc, r"CANVAS_TOKEN", "token setup")
    require_text(doc, r"CANVAS_BASE", "base setup")
    require_text(doc, r"API Token Path", "API token path")
    require_text(doc, r"Cookie Path", "cookie path")
    require_text(doc, r"canvas_login --auto", "cookie login")
    require_text(doc, r"--probe", "probe verification")
    require_text(doc, r"cookie.*quiz|quiz.*cookie", "cookie quiz path")
    require_text(doc, r"fail closed", "fail closed")
    require_text(doc, r"skip|manual", "skip/manual")
    run([sys.executable, "tests/codex_runtime/run_onboarding_tests.py"])
    ast_check([ROOT / "tests" / "codex_runtime"])
    privacy_check([
        ROOT / "AGENTS.md",
        ROOT / "docs",
        ROOT / ".agents",
        ROOT / "tests" / "codex_runtime",
    ])


def check_b9() -> None:
    require_text(ROOT / "plugins" / "canvas-pilot-codex" / ".codex-plugin" / "plugin.json", r"name|version|skills", "plugin manifest")
    require_text(ROOT / "plugins" / "canvas-pilot-codex" / "README.md", r"canvas-bootstrap|canvas-scan|canvas-execute|canvas-skip", "plugin skills")
    require_text(ROOT / "scripts" / "codex_plugin_check.py", r"drift|canvas-pilot-codex", "plugin drift check")
    run([sys.executable, "tests/codex_runtime/run_plugin_tests.py"])
    ast_check([ROOT / "scripts" / "codex_plugin_check.py", ROOT / "tests" / "codex_runtime"])
    privacy_check([
        ROOT / "AGENTS.md",
        ROOT / "docs",
        ROOT / ".agents",
        ROOT / "plugins",
        ROOT / "tests" / "codex_runtime",
    ])


def check_b10() -> None:
    require_text(ROOT / "docs" / "CODEX_AUTOMATION.md", r"codex exec|--batch B|non-interactive", "codex exec docs")
    require_text(ROOT / ".github" / "workflows" / "codex.yml", r"permissions:", "ci permissions")
    require_text(ROOT / ".github" / "workflows" / "codex.yml", r"contents:\s*read", "contents read")
    require_text(ROOT / ".github" / "workflows" / "codex.yml", r"pull-requests:\s*write", "pull request write")
    require_text(ROOT / "docs" / "CODEX_AUTOMATION.md", r"Never commit|\.cookies|CANVAS_TOKEN", "no committed auth docs")
    run([sys.executable, "tests/codex_runtime/run_automation_tests.py"])
    ast_check([ROOT / "tests" / "codex_runtime"])
    privacy_check([
        ROOT / "AGENTS.md",
        ROOT / "docs",
        ROOT / ".agents",
        ROOT / ".github",
        ROOT / "tests" / "codex_runtime",
    ])


def check_b11() -> None:
    today = "2026-05-07"
    run_dir = ROOT / "runs" / "codex" / today
    revised = run_dir / "REVISED_CC_SYNC_PLAN.md"
    gaps = run_dir / "CAPABILITY_GAPS.md"
    proposed = run_dir / "PROPOSED_BATCHES.md"
    skill_specs = run_dir / "NEW_SKILL_SPECS.md"
    review = run_dir / "CC_SYNC_REVIEW.md"
    setup_skill = ROOT / ".agents" / "skills" / "canvas-setup" / "SKILL.md"
    loop_skill = ROOT / ".agents" / "skills" / "cc-sync-execute-loop" / "SKILL.md"
    lock_helper = ROOT / ".agents" / "skills" / "cc-sync-execute-loop" / "scripts" / "cc_sync_loop_lock.py"

    ast_check([
        ROOT / "scripts" / "codex_cc_sync_plan.py",
        ROOT / "scripts" / "codex_check.py",
        ROOT / "tests" / "codex_runtime",
        ROOT / "tests" / "codex_hooks",
        ROOT / "tests" / "codex_bootstrap",
        lock_helper,
    ])

    require_all_text(gaps, {
        "reviewed schema source field": r"Source:\s*(current-git|untracked|baseline-drift|codex-side)",
        "reviewed schema surface field": r"Surface:\s*",
        "reviewed schema public sync field": r"Public sync:\s*(yes|no|redacted|manual-review)",
        "reviewed schema codex status field": r"Codex status:\s*",
        "reviewed schema verification target field": r"Verification target:\s*",
        "reviewed schema new skill needed field": r"New skill needed:\s*(yes|no)|cc-sync-execute-loop",
        "supporting runtime detection": r"supporting-runtime|src/canvas_client\.py|src/quiz_pacing\.py",
        "path-based privacy classification": r"Path-Based Public/Private Classification|path-based private",
        "source labels": r"current-git.*untracked.*baseline-drift|baseline-drift.*current-git.*untracked",
        "execute-loop capability gap": r"Approved Execution Loop Split|cc-sync-execute-loop",
    })
    require_all_text(revised, {
        "canvas setup classification": r"canvas-setup.*setup/onboarding|Deterministic first-run setup",
        "execute loop split": r"cc-sync-execute-loop|Same-dialog execute loop",
        "no baseline update during planning": r"Do not update `runs/codex/cc_sync_baseline\.json`",
    })
    require_all_text(proposed, {
        "B11 batch": r"B11 Sync Planner Hardening",
        "B11 A1": r"B11-A1",
        "B11 A9 execute loop": r"B11-A9|cc-sync-execute-loop",
        "private quiz fail closed": r"quiz.*fail-closed|fail-closed.*quiz",
    })
    require_all_text(skill_specs, {
        "setup skill spec": r"\.agents/skills/canvas-setup/SKILL\.md",
        "execute loop skill spec": r"\.agents/skills/cc-sync-execute-loop/SKILL\.md",
        "missing approval blocks": r"missing approval blocks|approval.*blocks",
    })
    require_all_text(review, {
        "local audit disclosure": r"Subagent reviewers were not launched|local main-thread audit",
        "supporting runtime blocker": r"Supporting runtime/test changes represented:\s*no",
        "execute loop represented": r"Execution-loop split represented:\s*yes",
    })

    require_all_text(setup_skill, {
        "setup frontmatter": r"^name:\s*canvas-setup",
        "setup skeleton or runtime state matrix": r"PLANNED_SKILL_SKELETON v1|Setup State Matrix",
        "setup onboarding trigger": r"\.env|Canvas base URL|setup",
        "setup bootstrap handoff": r"canvas-bootstrap",
        "setup no scan": r"Do not scan|no `assignments\.json`",
        "setup no execute": r"Do not execute|no `result\.json`",
        "setup no manual env edit": r"Avoid telling the student to edit `?\.env",
    })
    require_all_text(loop_skill, {
        "execute loop frontmatter": r"^name:\s*cc-sync-execute-loop",
        "one-shot mode": r"One-Shot Tick",
        "same-dialog mode": r"Same-Dialog Persistent Loop",
        "ten minute sleep": r"Start-Sleep -Seconds 600|10 minutes",
        "lock path": r"cc-sync-execute-loop\.lock\.json",
        "missing approval hard stop": r"execution approval is missing|approval.*missing",
        "no raw review": r"does not audit raw|Do not use for raw plan review",
    })
    require_all_text(lock_helper, {
        "lock claim": r"def claim\(",
        "lock heartbeat": r"def heartbeat\(",
        "lock release": r"def release\(",
        "lock status": r"def status\(",
        "stale lock ttl": r"ttl_minutes|recovered_from",
    })

    run([sys.executable, "C:\\Users\\32247\\.codex\\skills\\.system\\skill-creator\\scripts\\quick_validate.py", str(loop_skill.parent)])
    run([sys.executable, str(lock_helper), "status", "--root", "."])

    require_text(ROOT / "docs" / "CODEX_BATCHES.md", r"\.agents/skills/cc-sync-execute-loop/\*\*", "B11 allows execute loop skill")
    require_text(ROOT / "docs" / "CODEX_PARITY_MATRIX.md", r"P30.*P31.*P32.*P33.*P34.*P35.*P36.*P37|P37", "B11 parity ids")

    check_b4()
    check_b5()
    check_b7()
    check_b8()

    privacy_check([
        ROOT / "AGENTS.md",
        ROOT / "docs",
        ROOT / ".agents",
        ROOT / "plugins",
        ROOT / "tests" / "codex_runtime",
        ROOT / "tests" / "codex_hooks",
        ROOT / "tests" / "codex_bootstrap",
        run_dir,
    ])


def check_b12() -> None:
    setup_skill = ROOT / ".agents" / "skills" / "canvas-setup" / "SKILL.md"
    require_all_text(setup_skill, {
        "setup frontmatter": r"^name:\s*canvas-setup",
        "runtime ready no skeleton wording": r"Setup State Matrix",
        "missing env state": r"missing-env",
        "incomplete config state": r"incomplete-canvas-config",
        "empty routes state": r"auth-configured-empty-routes",
        "complete state": r"\|\s*complete\s*\|",
        "bootstrap handoff": r"canvas-bootstrap",
        "scan next action only": r"next user action is `canvas-scan`",
        "no assignment scan": r"Do not scan assignments",
        "no execute": r"Do not execute assignments",
        "no run artifacts": r"Do not write `assignments\.json`, `plan\.json`, `result\.json`, or `REPORT\.md`",
        "no manual env edit": r"Do not tell the student to edit `?\.env",
        "claude read-only": r"Keep `?\.claude",
    })
    text = setup_skill.read_text(encoding="utf-8", errors="ignore")
    if "PLANNED_SKILL_SKELETON v1" in text:
        raise SystemExit("canvas-setup is still marked as a planned skeleton")

    run([sys.executable, "tests/codex_runtime/run_setup_tests.py"])
    ast_check([
        ROOT / "scripts" / "codex_check.py",
        ROOT / "tests" / "codex_runtime",
    ])
    check_b4()
    check_b8()
    privacy_check([
        ROOT / "AGENTS.md",
        ROOT / "docs",
        ROOT / ".agents",
        ROOT / "tests" / "codex_runtime",
        ROOT / "runs" / "codex" / "2026-05-07",
    ])


def check_b13() -> None:
    require_all_text(ROOT / ".codex" / "hooks" / "post_tool_guard.py", {
        "runner script guard": r"runner_script_issue|runner script blocked",
        "runner script runs scope": r"rel\.startswith\(\"runs/\"\)",
        "normal artifact path collector": r"referenced_paths",
    })
    require_all_text(ROOT / ".codex" / "hooks" / "stop_guard.py", {
        "session id marker": r"CODEX_SESSION_ID|session_id",
        "other session pass": r"marker_session.*!=.*current_session",
    })
    require_all_text(ROOT / ".codex" / "hooks" / "pre_tool_guard.py", {
        "quiz live patterns": r"QUIZ_LIVE_PATTERNS",
        "quiz fail closed": r"Refuse live quiz action",
        "verification log remains": r"verification\.log",
    })
    require_all_text(ROOT / "tests" / "codex_hooks" / "run_advanced_hook_tests.py", {
        "runner blocked fixture": r"test_runner_script_blocked_under_runs",
        "runner allowed fixture": r"test_normal_run_artifact_allowed",
        "other session fixture": r"test_stop_marker_other_session_passes",
        "matching session fixture": r"test_stop_marker_matching_session_blocks",
        "quiz fail closed fixture": r"test_quiz_live_action_fails_closed",
    })
    run([sys.executable, "tests/codex_hooks/run_hook_tests.py"])
    run([sys.executable, "tests/codex_hooks/run_advanced_hook_tests.py"])
    ast_check([
        ROOT / ".codex" / "hooks",
        ROOT / "tests" / "codex_hooks",
        ROOT / "scripts" / "codex_check.py",
    ])
    check_b7()
    privacy_check([
        ROOT / "AGENTS.md",
        ROOT / "docs",
        ROOT / ".codex",
        ROOT / "tests" / "codex_hooks",
        ROOT / "runs" / "codex" / "2026-05-07",
    ])


def check_b14() -> None:
    skill = ROOT / ".agents" / "skills" / "canvas-bootstrap" / "SKILL.md"
    require_all_text(skill, {
        "main bucket": r"`main`",
        "likely-real bucket": r"`likely-real`",
        "noise bucket": r"`noise`",
        "noise hidden": r"hidden by default|hidden from default mapping",
        "likely-real lower confidence": r"lower-confidence|too little history",
        "cross-course rejection": r"cross-course|different courses|one skill maps to one course",
        "skeleton sentinel": r"UNFILLED_SKELETON",
    })
    require_text(ROOT / "tests" / "codex_bootstrap" / "run_bootstrap_tests.py", r"test_course_triage_buckets", "bootstrap triage fixture")
    run([sys.executable, "tests/codex_bootstrap/run_bootstrap_tests.py"])
    ast_check([
        ROOT / "tests" / "codex_bootstrap",
        ROOT / "scripts" / "codex_check.py",
    ])
    check_b3()
    privacy_check([
        ROOT / "AGENTS.md",
        ROOT / "docs",
        ROOT / ".agents",
        ROOT / "tests" / "codex_bootstrap",
        ROOT / "runs" / "codex" / "2026-05-07",
    ])


def check_b15() -> None:
    manifest = ROOT / "plugins" / "canvas-pilot-codex" / ".codex-plugin" / "plugin.json"
    readme = ROOT / "plugins" / "canvas-pilot-codex" / "README.md"
    checker = ROOT / "scripts" / "codex_plugin_check.py"
    tests = ROOT / "tests" / "codex_runtime" / "run_plugin_tests.py"
    require_text(manifest, r"manifest-only", "manifest-only manifest description")
    require_all_text(readme, {
        "manifest-only readme": r"manifest-only",
        "repo skills source of truth": r"\.agents/skills/\*\*",
        "setup declared": r"canvas-setup",
        "execute loop declared": r"cc-sync-execute-loop",
        "private skills excluded": r"Do not package private Claude course skills",
    })
    require_all_text(checker, {
        "setup required": r"canvas-setup",
        "execute loop required": r"cc-sync-execute-loop",
        "manifest-only check": r"manifest-only",
    })
    require_all_text(tests, {
        "setup plugin test": r"canvas-setup",
        "execute loop plugin test": r"cc-sync-execute-loop",
        "manifest-only test": r"test_manifest_only_mode",
    })
    run([sys.executable, "tests/codex_runtime/run_plugin_tests.py"])
    ast_check([
        checker,
        tests,
        ROOT / "scripts" / "codex_check.py",
    ])
    check_b9()
    privacy_check([
        ROOT / "AGENTS.md",
        ROOT / "docs",
        ROOT / "plugins",
        ROOT / "tests" / "codex_runtime",
        ROOT / "runs" / "codex" / "2026-05-07",
    ])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", default="B2")
    args = parser.parse_args()

    checks = {
        "B2": check_b2,
        "B3": check_b3,
        "B4": check_b4,
        "B5": check_b5,
        "B6": check_b6,
        "B7": check_b7,
        "B8": check_b8,
        "B9": check_b9,
        "B10": check_b10,
        "B11": check_b11,
        "B12": check_b12,
        "B13": check_b13,
        "B14": check_b14,
        "B15": check_b15,
    }
    if args.batch not in checks:
        raise SystemExit(f"Only {', '.join(sorted(checks))} are implemented")
    checks[args.batch]()
    print(f"Codex check {args.batch} PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
