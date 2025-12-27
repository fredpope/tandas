# Tandas

**AI-orchestrated test suite management for Playwright projects**

Tandas is an open-source orchestration layer that provides persistent, structured management for end-to-end test suites. It combines a **persistent test registry** with **transient execution tasks** (via [Beads](https://github.com/steveyegge/beads)) to give AI agents and developers a powerful system for managing, discovering, and evolving tests over time.

## Why Tandas?

Testing is fundamentally different from coding:

- **Code features** are built once and completed
- **Tests** must live indefinitely, run repeatedly, and evolve with your application

Tandas embraces this by separating concerns:

| Component | Purpose | Lifecycle |
|-----------|---------|-----------|
| **Tandas** (`td`) | Test registry - what tests exist, what they cover, how they relate | Permanent |
| **Beads** (`bd`) | Execution tasks - running, analyzing, healing tests | Transient |

## Features

- **Persistent Registry** - Git-backed JSONL storage for test metadata
- **Dependency Graph** - Track test dependencies with topological ordering
- **Flakiness Detection** - Automatic tracking of test stability
- **Run History** - Full history of test executions with traces
- **AI-Optimized** - Structured data designed for agent workflows
- **Background Daemon** - Auto-sync between JSONL and SQLite cache

## Installation

### Quick Start

Install everything with a single command:

```bash
curl -fsSL https://raw.githubusercontent.com/fredpope/tandas/main/install.sh | bash
```

After the installer finishes (it installs Beads, copies `td`, and runs
`td init`/`td quickstart`), you can start using `td` right away. If you prefer
to set things up manually instead, follow the steps below:

```bash
# Clone the repository
git clone https://github.com/fredpope/tandas.git
cd tanda

# Make td.py executable
chmod +x td.py

# Initialize in your project (if you didn't run the installer)
./td.py init

# Scaffold provider config & env instructions
./td.py quickstart
# Fill in .tandas/env.example with your API keys, then:
source .tandas/env.example

# Discover existing tests
./td.py discover

# Link Playwright traces (optional)
./td.py trace scan --dir test-results
./td.py trace link td-abc123 test-results/trace.zip --result fail
```

### Quickstart Setup

`td quickstart` writes `.tandas/config.yaml`, `.tandas/env.example`, and `tanda.json` so
you can wire up providers immediately. Customize the generated files, export the
API keys (or source `.tandas/env.example`), and then run `td generate <id>` to
draft a spec with your chosen provider.

### System-wide Installation

```bash
# Copy to local bin
cp td.py ~/.local/bin/td
chmod +x ~/.local/bin/td

# Ensure ~/.local/bin is in your PATH
echo 'export PATH="$PATH:$HOME/.local/bin"' >> ~/.zshrc
```

### Building the Daemon (Optional)

The Go daemon provides background sync and file watching:

```bash
cd daemon
go mod tidy
go build -o td-daemon ./cmd/td-daemon

# Install
cp td-daemon ~/.local/bin/
```

### Managing the Daemon

After building the binary, control it directly from the CLI:

```bash
td daemon start            # Launch daemon in .tandas
td daemon status           # Check PID/interval/socket
td daemon stop             # Gracefully stop the daemon
```

If the binary is not on your `PATH`, set the `TD_DAEMON_BIN` environment
variable or pass `--bin /path/to/td-daemon` on each command.

## Usage

### Basic Commands

```bash
# Initialize registry
td init

# Create a new test record
td create "Login Flow" --file tests/login.spec.ts --covers auth,session

# Auto-discover test files
td discover

# List all tests
td list
td list --flaky          # Show only flaky tests
td list --active         # Show only active tests

# View test details
td show td-abc123

# Update a test
td update td-abc123 --status flaky --note "Timing issue on CI"

# Record a test run
td update td-abc123 --run-result pass --run-duration 2.3s
```

### Dependency Management

```bash
# Add dependency (A depends on B)
td dep add td-checkout td-auth

# Remove dependency
td dep remove td-checkout td-auth

# Show dependencies
td dep show td-checkout
```

### Ready Queue (Topologically Sorted)

```bash
# Show tests in execution order
td ready
```

Output:
```
Ready (in execution order):
  1. td-abc123: DB Setup
  2. td-def456: Auth Tests (after: td-abc123)
  3. td-ghi789: Checkout Flow (after: td-def456)

Blocked (waiting on flaky):
  td-xyz: Payment Tests
    waiting on: td-def456
```

### Sync with Git

```bash
td sync    # Sync JSONL <-> SQLite and stage for git
```

### AI-Assisted Test Generation

Configure providers in `.tandas/config.yaml`, then ask Tandas to draft a Playwright
spec using your preferred model:

```yaml
ai:
  default_provider: claude
  providers:
    claude:
      api_key: ${ANTHROPIC_API_KEY}
      model: claude-sonnet-4-20250514
    openai:
      api_key: ${OPENAI_API_KEY}
      model: gpt-4o
```

```bash
td generate td-abc123 --provider openai --output tests/generated/auth.spec.ts
```

> `td generate` requires [PyYAML](https://pyyaml.org/) to parse `config.yaml`.

### Trace Management

Tandas records Playwright traces so you can revisit failures:

```bash
td trace scan --dir test-results --ext .zip        # queue new traces
td trace list                                       # pending traces
td trace link td-abc123 test-results/login.zip --result fail
```

When the Go daemon is running, it watches `test-results/` and automatically
adds new trace files to `.tandas/trace_inbox.jsonl`.

## Architecture

```
project-root/
├── tests/                      # Your Playwright test files
├── playwright.config.ts
├── .tandas/                    # Tandas registry
│   ├── issues.jsonl            # Git-tracked source of truth
│   ├── db.sqlite               # Local SQLite cache
│   ├── td.sock                 # Daemon socket (if running)
│   ├── daemon.pid              # Daemon PID file
│   └── trace_inbox.jsonl       # Trace files discovered via scan/daemon
├── .beads/                     # Beads execution tasks
└── td.py                       # CLI (or symlink to ~/.local/bin/td)
```

### Tandas Entity Structure

```json
{
  "id": "td-a1b2c3d4",
  "title": "User Login Flow",
  "status": "active",
  "file": "tests/login.spec.ts",
  "covers": ["auth", "session-management"],
  "depends_on": ["td-e5f6g7h8"],
  "notes": [
    {"ts": "2025-12-27T10:00:00", "type": "note", "text": "Fixed timing issue"}
  ],
  "run_history": [
    {"ts": "2025-12-27T10:05:00", "result": "pass", "duration": "2.3s"}
  ],
  "created_at": "2025-10-20T00:00:00",
  "updated_at": "2025-12-27T10:05:00"
}
```

### Status Values

| Status | Meaning |
|--------|---------|
| `active` | Test is healthy and running |
| `flaky` | Test has intermittent failures (auto-detected at 20%+ failure rate) |
| `deprecated` | Test is no longer relevant |

Note: Tandas are **never closed** - they represent permanent records of tests.

## Integration with Beads

Tandas works alongside [Beads](https://github.com/steveyegge/beads) for execution:

```bash
# Start a test run (in Beads)
bd create "Run Regression Suite $(date)" -t epic

# Query active tests (in Tandas)
td list --active

# After running, record results (in Tandas)
td update td-abc123 --run-result pass --run-duration 1.5s

# Close the execution task (in Beads)
bd close 123
```

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.

### Requirements

- Python 3.8+
- Go 1.21+ (for daemon, optional)
- SQLite 3
- PyYAML (optional, required for `td generate` config parsing)

### Running Tests

```bash
# Python CLI tests
python -m pytest tests/

# Go daemon tests
cd daemon && go test ./...
```

## Roadmap

- [x] v0.1 - Basic CLI (init, create, list, update, discover)
- [x] v0.2 - Dependency graph, topological ready, Go daemon
- [ ] v0.3 - AI test generation, Playwright traces, git hooks
- [ ] v1.0 - Multi-agent support, dashboard UI, plugin system

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions are welcome! Please read our [Contributing Guidelines](CONTRIBUTING.md) and [Code of Conduct](CODE_OF_CONDUCT.md) first.
