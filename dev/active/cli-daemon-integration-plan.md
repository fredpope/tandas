# CLI ↔ Daemon Integration Test Plan

## Goals
- Exercise the `td daemon` command family end-to-end without requiring real AI providers.
- Verify SQLite/JSONL synchronization when daemon socket is present or absent.
- Catch regressions in Unix socket RPC handling before shipping v0.3.

## Proposed Coverage
1. **Status Flow**
   - Start with clean repo, `td init`, `td daemon status` should report "not running" (covered by pytest).
   - Once Go binary is installed, `td daemon start` + `status` should show PID + interval (manual for now).

2. **Sync Loop Validation (Go)**
   - Go tests (added) keep JSONL↔DB flow correct.
   - Next iteration: spin up daemon in tests using temp dir + short interval, then call `cmd_sync` to assert socket import is used.

3. **Trace + Run History (future)**
   - When Playwright traces land, extend tests to drop trace files in watched dir and assert daemon attaches run links.

## Tooling Needs
- Lightweight harness to build td-daemon inside tests (skip if Go missing).
- Pytest marker (e.g., `@pytest.mark.daemon`) to gate slow integration tests.

## Open Questions
- How to stub AI provider calls for integration tests (maybe `TD_GENERATE_FAKE=1`).
- Should daemon integration tests run in CI (requires Go install + fsnotify support).

## Next Steps
1. Add pytest fixture that optionally builds/runs td-daemon in background (skips if Go missing).
2. Write test: start daemon, mutate `.tandas/issues.jsonl`, ensure CLI sees socket import.
3. Expand watchers coverage after Playwright/trace features exist.
