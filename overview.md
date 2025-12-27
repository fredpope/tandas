Tanda — Technical System Overview
Tanda is an open-source AI orchestration layer designed specifically for end-to-end testing in Playwright-based projects (typically with Vite or similar modern frontend tooling). Its primary goal is to provide a structured, persistent, and agent-friendly way to manage, discover, execute, and evolve a test suite over the long term using AI agents.
Core Philosophy
Testing is fundamentally different from coding in one key way:

Code features are built once and (ideally) completed.
Tests must live indefinitely, run repeatedly, and evolve with the application.

Tanda embraces this reality by combining two complementary systems:

Persistent Test Registry (tandas) — Eternal, version-controlled home for every test and its relationships.
Transient Execution Engine (Beads) — Short-lived, closable tasks for actually running, analyzing, and healing tests.

This hybrid approach gives you the best of both worlds:

Perpetual memory and discoverability for the test suite
Clean compaction and focus for execution runs

Architecture
textproject-root/
├── tests/                      # Existing Playwright .spec.ts files
├── playwright.config.ts
├── vite.config.ts
├── .tandas/                    # Persistent registry (our system)
│   ├── issues.jsonl            # Git-backed storage of all tandas
│   ├── db.sqlite               # Local cache for fast queries
│   └── daemon.log              # Background sync daemon
├── .beads/                     # Installed by Beads (transient execution tasks)
├── td                          # Tanda CLI (symlinked to ~/.local/bin/td)
├── AGENTS.md                   # Complete agent instructions
└── .git/                       # Both .tandas and .beads travel with the repo
Component Breakdown
1. Tanda Registry (.tandas/ + td CLI)

Purpose: The canonical, indefinitely-living source of truth for what tests exist, what they cover, and how they relate.
Storage: Line-delimited JSON (.tandas/issues.jsonl) — identical in spirit to Beads, fully git-mergeable and branchable.
Local Cache: SQLite database for O(1) queries without loading the full file.
Background Daemon: Keeps SQLite in sync with JSONL (similar to Beads).
Key Entity (Tanda):JSON{
  "id": "td-a1b2c3d4",
  "title": "User Login Flow",
  "status": "active",           // active | flaky | deprecated (never closed)
  "file": "tests/login.spec.ts",
  "covers": ["auth", "session-management"],
  "depends_on": ["td-e5f6g7h8"], // e.g., requires DB setup test
  "notes": "Last passed: 2025-12-27\nFlakiness healed: 2025-11-15",
  "created_at": "2025-10-20",
  "updated_at": "2025-12-27"
}
CLI Commands (td):
td init — Initialize registry
td create — Add new test tanda
td list [--active|--flaky] — Query live tests
td dep add/remove — Manage dependencies
td update <id> — Add notes, update status
td ready — Show high-priority, unblocked tandas
td sync — Force daemon sync


2. Execution Layer (Beads)

Purpose: Handle all transient work: building, running suites, analyzing failures, healing selectors, generating new tests.
Why Beads?
Designed for closable, compactable tasks
Excellent dependency graph with blocking, parent/child, discovered-from
Built-in compaction keeps agent context clean
Proven in long-horizon AI coding workflows

Usage Pattern:
Agent creates an epic bead: "Run Regression Suite – 2025-12-27"
Spawns child beads: "Build with Vite", "Execute Login Tests", "Execute Checkout Flow", "Analyze Failures"
On discovery (e.g., missing coverage): create new tanda via td create + generate file
On flakiness: create bug bead → heal → update tanda notes
Close all execution beads → compaction keeps history light


3. AI Agent Workflow (Defined in AGENTS.md)
The agent is instructed to:

Always start with td sync && bd sync
Query the persistent registry: td list --active or td ready
When execution is needed (code change, CI trigger, user request):
Create a new execution epic in Beads
Break into child beads based on tanda groups
Run actual commands (vite build, npx playwright test)
Attach reports, traces, screenshots as bead notes
Update relevant tandas with results or flakiness status

Discover gaps → create new tandas + generate tests
Never close or compact tandas — only execution beads

Development Roadmap
v0.1 (Current)

One-command installer
Basic td CLI (init, create, list, update)
Auto-discovery of existing *.spec.ts files
Beads integration
Comprehensive AGENTS.md

v0.2

Full dependency graph in td (depends_on, blocked_by, covers)
td ready with topological sorting
Background daemon implementation
Rich notes with timestamps and run links

v0.3

td generate — AI-assisted test stub creation
Integration with Playwright trace viewer links
Flakiness detection and automatic healing beads
Git hook triggers (post-merge runs)

v1.0

Multi-agent support (specialized generator/healer agents)
Dashboard/UI for browsing tanda graph
Export to coverage reports / test matrix
Plugin system for Jest/Cypress compatibility

Why This Architecture Wins

Git-native: No external database, full history, branching works naturally
Agent-optimized: Structured data + clear separation of concerns
Self-healing by design: Failures become discoverable work in Beads, updates flow back to tandas
Scales indefinitely: Test suite grows without context bloat
Minimal footprint: Two lightweight CLIs, no servers

Tanda is not just another test runner or generator — it is the operating system for AI-maintained test suites.
Welcome to the future of autonomous testing.