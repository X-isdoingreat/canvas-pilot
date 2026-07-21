# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / ".agents" / "skills" / "daily-work-tweet" / "SKILL.md"
SCRIPTS = SKILL.parent / "scripts"
COLLECTOR = SCRIPTS / "collect_machine_work.py"
REQUESTED_DAY = "2026-07-17"
REQUESTED_TIMEZONE = "America/Los_Angeles"


def run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    return completed.stdout


def commit(repository: Path, message: str, timestamp: str) -> None:
    environment = os.environ.copy()
    environment.update({"GIT_AUTHOR_DATE": timestamp, "GIT_COMMITTER_DATE": timestamp})
    run(["git", "commit", "--quiet", "-m", message], cwd=repository, env=environment)


def create_repository(root: Path, name: str, *, commit_work: bool) -> Path:
    repository = root / name
    repository.mkdir()
    run(["git", "init", "--quiet"], cwd=repository)
    run(["git", "config", "user.name", "Public Test Builder"], cwd=repository)
    run(["git", "config", "user.email", "builder@example.invalid"], cwd=repository)
    (repository / "work.py").write_text("print('verified work')\n", encoding="utf-8")
    if commit_work:
        run(["git", "add", "work.py"], cwd=repository)
        commit(repository, "ship verified test work", "2026-07-17T12:00:00-07:00")
    return repository


def collect(scan_root: Path) -> dict[str, object]:
    output = run(
        [
            sys.executable,
            "-X",
            "utf8",
            str(COLLECTOR),
            "--scan-root",
            str(scan_root),
            "--date",
            REQUESTED_DAY,
            "--timezone",
            REQUESTED_TIMEZONE,
            "--no-cache",
            "--no-codex",
            "--no-vercel",
            "--compact",
        ],
        cwd=ROOT,
    )
    return json.loads(output)


def collect_restricted(repository: Path) -> dict[str, object]:
    output = run(
        [
            sys.executable,
            "-X",
            "utf8",
            str(COLLECTOR),
            "--repo",
            str(repository),
            "--date",
            REQUESTED_DAY,
            "--timezone",
            REQUESTED_TIMEZONE,
            "--no-codex",
            "--no-vercel",
            "--compact",
        ],
        cwd=ROOT,
    )
    return json.loads(output)


def test_machine_discovery_and_evidence_limits() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        scan_root = Path(temporary)
        active = create_repository(scan_root, "active-repository", commit_work=False)
        for index in range(20):
            (active / f"draft-{index}.py").write_text(f"value = {index}\n", encoding="utf-8")
        run(["git", "add", "."], cwd=active)
        commit(active, "baseline", "2026-07-16T12:00:00-07:00")
        (active / "work.py").write_text("print('verified work shipped')\n", encoding="utf-8")
        run(["git", "add", "work.py"], cwd=active)
        commit(active, "ship verified test work", "2026-07-17T12:00:00-07:00")
        inactive = create_repository(scan_root, "inactive-repository", commit_work=False)
        (inactive / "work.py").unlink()
        for index in range(20):
            (active / f"draft-{index}.py").write_text(f"value = {index + 1}\n", encoding="utf-8")

        document = scan_root / "notes.md"
        document.write_text("metadata signal only\n", encoding="utf-8")
        noon = datetime(2026, 7, 17, 19, 0, tzinfo=timezone.utc).timestamp()
        os.utime(document, (noon, noon))

        payload = collect(scan_root)
        scope = payload["scope"]
        git = payload["sources"]["git"]
        repositories = git["active_repositories"]

        assert scope["mode"] == "machine"
        assert scope["scan_complete"] is True
        assert scope["modified_file_metadata_signals"]["document"] >= 1
        assert git["repositories_considered"] == 2
        assert git["active_repositories_found"] == 1
        assert len(repositories) == 1
        assert repositories[0]["commits"][0]["subject"] == "ship verified test work"
        assert repositories[0]["commits"][0]["authorship"] == "verified_configured_email"
        tree = repositories[0]["working_tree"]
        assert tree["status_count"] == 20
        assert len(tree["status"]) == 12
        assert tree["status_truncated"] is True


def test_incomplete_cache_is_never_reused() -> None:
    sys.path.insert(0, str(SCRIPTS))
    import collect_machine_work as collector

    current = datetime.now(timezone.utc).isoformat(timespec="seconds")
    incomplete = {
        "version": collector.CACHE_VERSION,
        "updated_at_utc": current,
        "scan_complete": False,
    }
    complete = {**incomplete, "scan_complete": True}
    assert collector.cache_usable(incomplete, 24, refresh=False) is False
    assert collector.cache_usable(complete, 24, refresh=False) is True
    assert collector.cache_usable(complete, 24, refresh=True) is False

    with tempfile.TemporaryDirectory() as temporary:
        cache_path = Path(temporary) / "index.json"
        discovery = collector.DiscoveryResult(
            directories_scanned=25,
            denied_or_unreadable=2,
            complete=True,
        )
        collector.write_cache(cache_path, discovery)
        cached = collector.load_cache(cache_path)
        assert cached is not None
        assert cached["directories_scanned"] == 25
        assert cached["denied_or_unreadable"] == 2


def test_explicit_repo_does_not_pull_in_current_working_directory() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        repository = create_repository(Path(temporary), "only-this-repository", commit_work=True)
        payload = collect_restricted(repository)
        git = payload["sources"]["git"]
        assert payload["scope"]["mode"] == "explicit_repositories"
        assert git["repositories_considered"] == 1
        assert git["active_repositories_found"] == 1
        assert git["active_repositories"][0]["repository"] == repository.name


def test_invalid_explicit_repo_fails_closed() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        missing = Path(temporary) / "missing-repository"
        completed = subprocess.run(
            [
                sys.executable,
                "-X",
                "utf8",
                str(COLLECTOR),
                "--repo",
                str(missing),
                "--no-codex",
                "--no-vercel",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=30,
        )
        assert completed.returncode == 2
        assert "existing directory" in completed.stderr


def test_skill_defaults_and_privacy_contract() -> None:
    text = SKILL.read_text(encoding="utf-8")
    collector = COLLECTOR.read_text(encoding="utf-8")
    repo_collector = (SCRIPTS / "collect_daily_work.py").read_text(encoding="utf-8")
    assert "collect_machine_work.py" in text
    assert "Do not default to only the current repository" in text
    assert "all fixed\nlocal drives" in text
    assert "does not read arbitrary document" in text
    assert "Codex root-thread `task_complete` summaries" in text
    assert "Never trigger login" in text
    assert "connected\n  GitHub app" in text
    assert "incomplete index" in text
    assert "Never publish" in text
    assert "verified_configured_email" in text
    assert "npx" in text and "Never trigger login" in text
    assert "core.fsmonitor=false" in repo_collector
    assert "vercel@latest" not in collector
    assert "MAX_OUTPUT_BYTES" in collector


def test_output_is_strictly_bounded() -> None:
    sys.path.insert(0, str(SCRIPTS))
    import collect_machine_work as collector

    repositories = [
        {
            "repository": f"repository-{index}",
            "path": "C:/private/" + ("x" * 2_000),
            "commits": [],
            "working_tree": {"status": []},
        }
        for index in range(300)
    ]
    payload = {
        "scope": {},
        "sources": {
            "git": {
                "active_repositories": repositories,
                "active_repositories_truncated": False,
            },
            "codex": {
                "task_complete_summaries": [
                    {"summary": "y" * 2_000} for _ in range(100)
                ]
            },
        },
    }
    bounded = collector.enforce_output_limit(payload)
    assert collector.serialized_payload_size(bounded) <= collector.MAX_OUTPUT_BYTES
    assert bounded["scope"]["output_truncated"] is True
    assert bounded["scope"]["output_repositories_omitted"] > 0

    payload_with_untrimmed_source = {
        "date": REQUESTED_DAY,
        "timezone": REQUESTED_TIMEZONE,
        "scope": {"mode": "machine", "scan_complete": True, "limits_hit": []},
        "sources": {
            "git": {"status": "ok", "active_repositories": []},
            "codex": {"status": "ok", "task_complete_summaries": []},
            "vercel": {"status": "ok", "unexpected": "z" * 500_000},
        },
    }
    bounded_fallback = collector.enforce_output_limit(payload_with_untrimmed_source)
    assert collector.serialized_payload_size(bounded_fallback) <= collector.MAX_OUTPUT_BYTES
    assert bounded_fallback["scope"]["output_reduced_to_summary_only"] is True
    assert bounded_fallback["sources"]["vercel"]["details_omitted_for_output_limit"] is True


def main() -> int:
    tests = [
        test_machine_discovery_and_evidence_limits,
        test_incomplete_cache_is_never_reused,
        test_explicit_repo_does_not_pull_in_current_working_directory,
        test_invalid_explicit_repo_fails_closed,
        test_skill_defaults_and_privacy_contract,
        test_output_is_strictly_bounded,
    ]
    failures: list[str] = []
    for test in tests:
        try:
            test()
            print(f"PASS {test.__name__}")
        except Exception as exc:
            failures.append(f"{test.__name__}: {exc}")
            print(f"FAIL {test.__name__}: {exc}")
    if failures:
        print("\nFailures:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
