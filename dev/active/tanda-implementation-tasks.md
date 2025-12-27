# Tandas Implementation Tasks

**Last Updated:** 2025-12-27

## Current Sprint: Documentation & Integration

### Immediate Tasks

- [x] **Create CODE_OF_CONDUCT.md** - Contributor Covenant v2.1
- [x] **Create LICENSE** - MIT License
- [x] **Integrate CLI with daemon** - Python CLI controls Go daemon
- [x] **Test daemon compilation** - `go mod tidy` + `go build ./cmd/td-daemon`
- [x] **Add pytest tests for td.py** - CLI smoke suite in `tests/test_td_cli.py`
- [x] **Kick off Sprint 3** - Provider scaffolding + config file + `td generate`
- [ ] **Implement provider API calls** - Real Claude/OpenAI/Gemini integrations
- [ ] **Add Go daemon tests** - Cover db/rpc/sync packages

### Sprint 1: v0.2 Core (COMPLETE)

- [x] `td dep add/remove/show` command
- [x] Topological sorting in `td ready`
- [x] SQLite schema updates for run_history, flakiness_score
- [x] Notes as structured array

### Sprint 2: Go Daemon (CODE COMPLETE)

- [x] Go project scaffolding (go.mod, structure)
- [x] SQLite operations in Go
- [x] JSONL sync logic
- [x] Unix socket RPC server
- [x] File watcher for auto-sync
- [x] Daemon lifecycle (start/stop/status)
- [x] **Python CLI integration with daemon** - `td daemon start|stop|status`
- [x] Test daemon compilation (requires Go installation)

### Sprint 3: AI Generation (IN PROGRESS)

- [x] Provider abstraction layer (`lib/providers/base.py` + registry)
- [x] Claude provider integration (Anthropic Messages API)
- [x] OpenAI provider integration (Chat Completions API)
- [x] Gemini provider integration (GenerateContent API)
- [x] `td generate` command (provider selection + output path)
- [x] Config file support (`.tandas/config.yaml` loader + env vars)

### Sprint 4: Playwright & Flakiness (NOT STARTED)

- [x] Trace linking (`td trace` CLI + daemon watcher + trace inbox)
- [ ] Run history tracking in daemon
- [ ] Flakiness score calculation in daemon
- [ ] Auto-healing bead creation
- [ ] Git hooks implementation

## Documentation Tasks

- [x] README.md
- [x] CONTRIBUTING.md
- [x] CODE_OF_CONDUCT.md
- [x] LICENSE
- [ ] API documentation (future)

## Testing Tasks

- [x] Add pytest tests for td.py
- [x] Add Go tests for daemon
- [x] Integration tests for CLI-daemon communication (pytest spawns td-daemon when Go present)

## Priority Order

1. Sprint 3: AI Generation
2. Add Go daemon + integration tests
3. Sprint 4: Playwright & Flakiness
