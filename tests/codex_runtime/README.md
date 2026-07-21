# Codex Runtime Fixtures

Offline fixture suite for Codex Canvas Pilot runtime behavior.

These tests use fake data and static skill assertions. They do not connect to
Canvas and require no network.

## Coverage

- fake scan boundary: `run_scan_tests.py`
- fake execute boundary: `run_execute_tests.py`
- setup state matrix: `run_setup_tests.py`
- API token-like auth path: represented by required `CANVAS_TOKEN` probe text
- cookie-like auth path: represented by required cookie/login recovery text
- no live submission by default

The suite is intentionally offline so Codex can run it inside a sandbox before
any real student account is configured.

