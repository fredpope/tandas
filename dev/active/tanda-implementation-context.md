# Tandas Implementation Context

**Last Updated:** 2025-12-27
**Status:** Active Development - v0.2 Implementation

## Current Implementation State

### Completed Work

#### v0.1 CLI (100% Complete)
- Full `td.py` CLI with commands: init, create, list, show, update, discover, sync, ready, version
- JSONL storage at `.tandas/issues.jsonl`
- SQLite caching at `.tandas/db.sqlite` with WAL mode
- Tandas entity model with covers, depends_on, timestamps
- Colored output, partial ID matching, table formatting

#### v0.2 Features (95% Complete)
- **Dependency Management**: `td dep add/remove/show` commands
- **Topological Sorting**: Kahn's algorithm in `td ready` for dependency-aware ordering
- **Run History Tracking**: `--run-result`, `--run-duration`, `--run-trace` flags
- **Flakiness Detection**: Auto-calculate from run history (20%+ failure = flaky)
- **Notes as Array**: Structured notes with type, timestamp, text fields
- **Daemon Control**: Python CLI `td daemon start|stop|status` commands with socket RPC sync

#### Sprint 3 (60% Complete)
- `lib/providers/*` implements real Claude/OpenAI/Gemini HTTP calls with graceful fallbacks when keys are missing
- `lib/generator.py` handles env expansion and provider registry lookups
- `td generate` CLI command with `--provider/--output/--config`
- `td quickstart` scaffolds `.tandas/config.yaml`, `.tandas/env.example`, and `tanda.json` for API key setup
- README updates documenting quickstart, provider configuration, and PyYAML requirement
- CLI pytest covers `td generate`, `td quickstart`, and daemon status flows
- `dev/active/cli-daemon-integration-plan.md` captures plan for e2e daemon tests

#### Sprint 4 (20% Complete)
- `td trace` command with `scan/list/link` subcommands and trace inbox helpers
- `.tandas/trace_inbox.jsonl` for pending trace files
- Daemon trace watcher monitors `test-results/` and appends new traces automatically
- Quickstart instructions + README detail trace workflow

#### Go Daemon (100% Code Complete, Build Verified)
Go modules are tidy and the daemon now compiles locally:
- `daemon/go.mod` - Module definition
- `daemon/cmd/td-daemon/main.go` - Entry point with cobra CLI
- `daemon/internal/rpc/server.go` - Unix socket RPC server
- `daemon/internal/db/sqlite.go` - SQLite operations
- `daemon/internal/sync/jsonl.go` - JSONL <-> SQLite sync
- `daemon/internal/watch/watcher.go` - File system watcher

#### Documentation (90% Complete)
- ✅ README.md - Full project documentation
- ✅ CONTRIBUTING.md - Contribution guidelines
- ✅ CODE_OF_CONDUCT.md - Contributor Covenant v2.1
- ✅ LICENSE - MIT License

#### Testing (50% Complete)
- ✅ CLI smoke + provider tests via pytest (init/create/dep/ready/generate/quickstart/daemon status)
- ✅ Go daemon unit tests for `internal/db` and `internal/sync` (`go test ./daemon/...`)
- ✅ CLI↔daemon integration test (pytest) spins up td-daemon when Go available and exercises socket-based status/generate flows
- ⏳ Playwright trace automation tests (Sprint 4)

### Key Decisions Made This Session

1. **Daemon Language**: Go binary (not Python) for performance
2. **AI Providers**: Multi-provider support - Claude, OpenAI, Gemini
3. **Flakiness Threshold**: 20% failure rate triggers auto-flaky status
4. **Notes Format**: Array of objects with type/ts/text fields
5. **License**: MIT for open source compatibility

### Files Modified

| File | Changes |
|------|---------|
| `td.py` | Major rewrite - v0.1 to v0.2 with deps, run history, flakiness |
| `daemon/*` | All new - complete Go daemon implementation |
| `README.md` | Created - full project documentation |
| `CONTRIBUTING.md` | Created - contribution guidelines |
| `AGENTS.md` | Cleaned up duplicates (removed @AGENTS.md and trailing-space version) |
| `lib/providers/*` & `lib/generator.py` | Real provider integrations + registry |
| `td.py` | Added `td quickstart`, provider wiring, `td trace`, and daemon command updates |
| `tests/test_td_cli.py` | Generate, quickstart, daemon status, trace workflow coverage |
| `daemon/internal/db/sqlite_test.go` | New Go tests |
| `daemon/internal/sync/jsonl_test.go` | New Go tests |
| `daemon/internal/watch/trace_watcher.go` & `rpc/server.go` | Trace watcher + inbox append |
| `dev/active/cli-daemon-integration-plan.md` | Integration plan |
| `README.md` | Documented providers, quickstart, and trace workflow |

### Blockers

1. **Playwright/trace features**: Sprint 4 items (trace linking, flaky automation) still pending
2. **Provider hardening**: Need retries/rate-limit handling + prompt tuning after field tests

## Next Immediate Steps

1. **Run history + trace automation in daemon** - Convert watcher events into run_history updates
2. **Document provider-specific setup/limits** - Expand README/API docs with per-provider tuning + troubleshooting
3. **Add retries/streaming support** - Improve provider clients for long generations and rate limits
4. **Start flakiness automation** - Auto-mark tandas flaky and open beads when repeated failures detected

## Critical Code Locations

### td.py Key Functions
- `calculate_flakiness()` - Line ~150 - Computes flakiness score
- `topological_sort()` - Line ~180 - Kahn's algorithm implementation
- `cmd_dep()` - Line ~400 - Dependency management commands
- `cmd_ready()` - Line ~500 - Shows tests in execution order

### Daemon Key Files
- `daemon/internal/rpc/server.go` - `StartDaemon()`, `StopDaemon()` functions
- `daemon/internal/db/sqlite.go` - `UpsertTanda()`, `GetAllTandas()` methods
- `daemon/internal/sync/jsonl.go` - `ImportFromJSONL()`, `ExportToJSONL()` methods

## Commands to Verify Work

```bash
# Test CLI
python3 td.py --help
python3 td.py init
python3 td.py create "Test" --file tests/test.spec.ts
python3 td.py list
python3 td.py dep add <id1> <id2>
python3 td.py ready

# Build daemon (requires Go installation)
cd daemon && go mod tidy && go build -o td-daemon ./cmd/td-daemon
```

## Uncommitted Changes

All changes are uncommitted. Files to stage:
- `td.py`
- `lib/` (providers + generator)
- `tests/`
- `daemon/internal/db/sqlite_test.go`
- `daemon/internal/sync/jsonl_test.go`
- `README.md`
- `dev/active/*.md`
- `.tandas/` (generated when running tests/quickstart)
