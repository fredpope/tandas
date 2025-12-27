#!/usr/bin/env python3
"""
td - Tandas CLI: Persistent test registry for AI-orchestrated test suites.

Tandas are eternal records of tests. Unlike Beads (transient execution tasks),
tandas are never closed - they track the living history of your test suite.

Statuses: active | flaky | deprecated (never "closed")
"""

import argparse
import hashlib
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from textwrap import dedent
from typing import List, Optional

from lib.generator import (
    GenerationConfigError,
    build_context,
    get_provider,
    load_ai_config,
)
from lib.generator import PROVIDERS  # noqa: E402
from lib.providers.base import GenerationProviderError

TANDA_DIR = Path(".tandas")
ISSUES_FILE = TANDA_DIR / "issues.jsonl"
DB_FILE = TANDA_DIR / "db.sqlite"
TRACE_INBOX_FILE = TANDA_DIR / "trace_inbox.jsonl"
VERSION = "0.2.0"

# ANSI colors
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

DAEMON_SOCKET = TANDA_DIR / "td.sock"
DAEMON_PID_FILE = TANDA_DIR / "daemon.pid"
DAEMON_BIN_ENV = "TD_DAEMON_BIN"
DEFAULT_DAEMON_BIN = "td-daemon"


def now_iso() -> str:
    """Return current timestamp in ISO format."""
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def generate_id(title: str) -> str:
    """Generate a unique tanda ID from title."""
    hash_val = hashlib.sha1(f"{title}{now_iso()}".encode()).hexdigest()[:8]
    return f"td-{hash_val}"


def init_db(conn: sqlite3.Connection):
    """Initialize SQLite schema with full tanda structure."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tandas (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            file TEXT,
            covers TEXT,  -- JSON array
            depends_on TEXT,  -- JSON array of tanda IDs
            notes TEXT,  -- JSON array of note objects
            run_history TEXT,  -- JSON array of run results
            flakiness_score REAL DEFAULT 0.0,  -- Computed from run_history
            last_run_at TEXT,  -- Timestamp of last test run
            last_run_result TEXT,  -- pass/fail/skip
            created_at TEXT,
            updated_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_status ON tandas(status);
        CREATE INDEX IF NOT EXISTS idx_file ON tandas(file);
        CREATE INDEX IF NOT EXISTS idx_flakiness ON tandas(flakiness_score);
        CREATE INDEX IF NOT EXISTS idx_last_run ON tandas(last_run_at);
    """)
    conn.commit()


def get_db() -> sqlite3.Connection:
    """Get database connection, initializing if needed."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def ensure_initialized():
    """Ensure .tandas directory exists."""
    if not TANDA_DIR.exists():
        print(f"{RED}Error: Tandas not initialized. Run 'td init' first.{RESET}")
        sys.exit(1)


def load_all_from_jsonl() -> dict:
    """Load all tandas from JSONL file (source of truth)."""
    tandas = {}
    if ISSUES_FILE.exists():
        with open(ISSUES_FILE) as f:
            for line in f:
                line = line.strip()
                if line:
                    data = json.loads(line)
                    tandas[data["id"]] = data
    return tandas


def append_to_jsonl(tanda: dict):
    """Append a tanda record to JSONL file."""
    with open(ISSUES_FILE, "a") as f:
        f.write(json.dumps(tanda) + "\n")


def rewrite_jsonl(tandas: dict):
    """Rewrite entire JSONL file (for updates)."""
    with open(ISSUES_FILE, "w") as f:
        for tanda in tandas.values():
            f.write(json.dumps(tanda) + "\n")


def calculate_flakiness(run_history: list) -> float:
    """Calculate flakiness score from run history (0.0 to 1.0)."""
    if not run_history:
        return 0.0
    # Only consider recent runs (last 10)
    recent = run_history[-10:]
    failures = sum(1 for r in recent if r.get("result") == "fail")
    return round(failures / len(recent), 2)


def sync_to_sqlite(tandas: dict):
    """Sync all tandas to SQLite cache."""
    conn = get_db()
    conn.execute("DELETE FROM tandas")
    for t in tandas.values():
        run_history = t.get("run_history", [])
        flakiness = calculate_flakiness(run_history)
        last_run = run_history[-1] if run_history else {}

        conn.execute("""
            INSERT INTO tandas (id, title, status, file, covers, depends_on, notes,
                               run_history, flakiness_score, last_run_at, last_run_result,
                               created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            t["id"],
            t["title"],
            t.get("status", "active"),
            t.get("file"),
            json.dumps(t.get("covers", [])),
            json.dumps(t.get("depends_on", [])),
            json.dumps(t.get("notes", [])) if isinstance(t.get("notes"), list) else t.get("notes", ""),
            json.dumps(run_history),
            flakiness,
            last_run.get("ts"),
            last_run.get("result"),
            t.get("created_at"),
            t.get("updated_at"),
        ))
    conn.commit()
    conn.close()


def daemon_call(method: str, params: Optional[dict] = None, timeout: float = 2.0, quiet: bool = True):
    """Call the Go daemon via Unix socket if it is running."""
    if not DAEMON_SOCKET.exists():
        return None

    payload = ""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect(str(DAEMON_SOCKET))
            request = {
                "method": method,
                "params": params or {},
                "id": int(time.time() * 1000),
            }
            sock.sendall((json.dumps(request) + "\n").encode())
            with sock.makefile("r") as response:
                payload = response.readline()
    except (FileNotFoundError, ConnectionRefusedError, socket.timeout, OSError) as exc:
        if not quiet:
            print(f"{YELLOW}Daemon communication failed: {exc}{RESET}")
        return None
    except json.JSONDecodeError:
        if not quiet:
            print(f"{YELLOW}Daemon sent invalid JSON response.{RESET}")
        return None

    if not payload:
        return None

    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        if not quiet:
            print(f"{YELLOW}Daemon response parse error.{RESET}")
        return None

    if data.get("error"):
        if not quiet:
            print(f"{YELLOW}Daemon error: {data['error']}{RESET}")
        return None

    return data.get("result")


def daemon_running() -> bool:
    """Return True if the daemon responds to ping."""
    return daemon_call("ping") == "pong"


def wait_for_daemon(timeout: float = 5.0) -> bool:
    """Wait for the daemon socket to become available."""
    start = time.time()
    while time.time() - start < timeout:
        if daemon_running():
            return True
        time.sleep(0.2)
    return False


def resolve_daemon_binary(explicit: Optional[str] = None) -> Optional[str]:
    """Locate the td-daemon binary, honoring overrides via args or env."""

    def _resolve(candidate: Optional[str]) -> Optional[str]:
        if not candidate:
            return None
        expanded = os.path.expanduser(candidate)
        path_obj = Path(expanded)
        if path_obj.exists() and path_obj.is_file():
            return str(path_obj)
        found = shutil.which(expanded)
        if found:
            return found
        return None

    for option in (explicit, os.environ.get(DAEMON_BIN_ENV)):
        resolved = _resolve(option)
        if resolved:
            return resolved

    resolved_default = _resolve(DEFAULT_DAEMON_BIN)
    if resolved_default:
        return resolved_default

    local_build = Path("daemon/td-daemon")
    if local_build.exists() and local_build.is_file():
        return str(local_build)

    return None


def sync_cache_from_json(tandas: Optional[dict] = None) -> dict:
    """Ensure the SQLite cache matches JSON, using the daemon if available."""
    if tandas is None:
        tandas = load_all_from_jsonl()

    if not daemon_call("import"):
        sync_to_sqlite(tandas)

    return tandas


def write_template(path: Path, content: str, *, force: bool = False) -> bool:
    """Write template content if file missing or force requested."""
    if path.exists() and not force:
        print(f"{YELLOW}{path} already exists. Use --force to overwrite.{RESET}")
        return False

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n")
    return True


def normalize_trace_path(path: str) -> str:
    base = Path.cwd().resolve()
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = (base / candidate).resolve()
    try:
        return str(candidate.relative_to(base))
    except ValueError:
        return str(candidate)


def load_trace_inbox() -> list:
    entries = []
    if TRACE_INBOX_FILE.exists():
        with open(TRACE_INBOX_FILE) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries


def write_trace_inbox(entries: list):
    TRACE_INBOX_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TRACE_INBOX_FILE, "w") as fh:
        for entry in entries:
            fh.write(json.dumps(entry) + "\n")


def append_trace_inbox_entry(entry: dict):
    TRACE_INBOX_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry.setdefault("status", "pending")
    with open(TRACE_INBOX_FILE, "a") as fh:
        fh.write(json.dumps(entry) + "\n")


def update_trace_entry(path: str, **updates) -> bool:
    path = normalize_trace_path(path)
    entries = load_trace_inbox()
    updated = False
    for entry in entries:
        if entry.get("path") == path and entry.get("status", "pending") == "pending":
            entry.update(updates)
            updated = True
    if updated:
        write_trace_inbox(entries)
    return updated


def status_color(status: str) -> str:
    """Return colored status string."""
    colors = {
        "active": GREEN,
        "flaky": YELLOW,
        "deprecated": RED,
    }
    return f"{colors.get(status, '')}{status}{RESET}"


# =============================================================================
# Commands
# =============================================================================

def cmd_init(args):
    """Initialize Tandas registry in current directory."""
    if TANDA_DIR.exists():
        print(f"Tandas already initialized in {TANDA_DIR}/")
        return

    TANDA_DIR.mkdir(exist_ok=True)
    ISSUES_FILE.touch()

    # Initialize SQLite
    conn = get_db()
    conn.close()

    # Add to git if in a repo
    if Path(".git").exists():
        subprocess.run(["git", "add", str(TANDA_DIR)], capture_output=True)

    print(f"{GREEN}Tandas initialized in {TANDA_DIR}/{RESET}")
    print(f"  Registry: {ISSUES_FILE}")
    print(f"  Cache:    {DB_FILE}")
    print(f"\nNext: Run 'td discover' to import existing tests")


def cmd_create(args):
    """Create a new tanda (test record)."""
    ensure_initialized()

    tanda_id = generate_id(args.title)
    now = now_iso()

    # Parse covers as comma-separated list
    covers = []
    if args.covers:
        covers = [c.strip() for c in args.covers.split(",")]

    tanda = {
        "id": tanda_id,
        "title": args.title,
        "status": args.status,
        "file": args.file,
        "covers": covers,
        "depends_on": [],
        "notes": [],
        "run_history": [],
        "created_at": now,
        "updated_at": now,
    }

    append_to_jsonl(tanda)

    # Update SQLite cache
    tandas = load_all_from_jsonl()
    sync_cache_from_json(tandas)

    print(f"{GREEN}Created tanda {BOLD}{tanda_id}{RESET}")
    print(f"  Title:  {tanda['title']}")
    print(f"  Status: {status_color(tanda['status'])}")
    if tanda["file"]:
        print(f"  File:   {tanda['file']}")
    if covers:
        print(f"  Covers: {', '.join(covers)}")


def cmd_list(args):
    """List tandas with optional filtering."""
    ensure_initialized()

    conn = get_db()

    # Build query based on filters
    query = "SELECT * FROM tandas WHERE 1=1"
    params = []

    if args.active:
        query += " AND status = 'active'"
    elif args.flaky:
        query += " AND status = 'flaky'"
    elif args.deprecated:
        query += " AND status = 'deprecated'"
    elif args.status:
        query += " AND status = ?"
        params.append(args.status)

    if args.covers:
        query += " AND covers LIKE ?"
        params.append(f'%"{args.covers}"%')

    query += " ORDER BY updated_at DESC"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    if not rows:
        print(f"{YELLOW}No tandas found.{RESET}")
        if not args.active and not args.flaky:
            print("Run 'td discover' to import existing tests.")
        return

    print(f"{BOLD}{'ID':<14} {'Status':<12} {'Title':<30} {'File'}{RESET}")
    print("-" * 80)

    for row in rows:
        status_str = status_color(row["status"])
        title = row["title"][:28] + ".." if len(row["title"]) > 30 else row["title"]
        file_str = row["file"] or ""
        print(f"{row['id']:<14} {status_str:<21} {title:<30} {file_str}")

    print(f"\n{len(rows)} tanda(s)")


def cmd_show(args):
    """Show detailed view of a single tanda."""
    ensure_initialized()

    tandas = load_all_from_jsonl()

    # Find by ID or partial match
    tanda = None
    for tid, t in tandas.items():
        if tid == args.id or tid.endswith(args.id):
            tanda = t
            break

    if not tanda:
        print(f"{RED}Tandas '{args.id}' not found.{RESET}")
        sys.exit(1)

    print(f"{BOLD}{tanda['id']}{RESET}")
    print(f"  Title:      {tanda['title']}")
    print(f"  Status:     {status_color(tanda['status'])}")
    print(f"  File:       {tanda.get('file') or '(none)'}")
    print(f"  Covers:     {', '.join(tanda.get('covers', [])) or '(none)'}")
    print(f"  Depends on: {', '.join(tanda.get('depends_on', [])) or '(none)'}")
    print(f"  Created:    {tanda.get('created_at', 'unknown')}")
    print(f"  Updated:    {tanda.get('updated_at', 'unknown')}")

    # Display run history summary
    run_history = tanda.get("run_history", [])
    if run_history:
        flakiness = calculate_flakiness(run_history)
        last_run = run_history[-1]
        result_color = GREEN if last_run.get("result") == "pass" else RED if last_run.get("result") == "fail" else YELLOW
        print(f"\n{BOLD}Run History:{RESET}")
        print(f"  Total runs:  {len(run_history)}")
        print(f"  Last result: {result_color}{last_run.get('result')}{RESET} ({last_run.get('ts', 'unknown')})")
        if last_run.get("duration"):
            print(f"  Duration:    {last_run['duration']}")
        if flakiness > 0:
            print(f"  Flakiness:   {YELLOW}{flakiness * 100:.0f}%{RESET}")
        if last_run.get("trace"):
            print(f"  Trace:       {last_run['trace']}")

    # Display notes
    notes = tanda.get("notes", [])
    if notes:
        print(f"\n{BOLD}Notes:{RESET}")
        # Handle both old string format and new array format
        if isinstance(notes, str):
            print(f"  {notes.replace(chr(10), chr(10) + '  ')}")
        else:
            for note in notes[-5:]:  # Show last 5 notes
                ts = note.get("ts", "")[:10]  # Date only
                text = note.get("text", str(note))
                print(f"  [{ts}] {text}")


def cmd_update(args):
    """Update a tanda's status, notes, or other fields."""
    ensure_initialized()

    tandas = load_all_from_jsonl()

    # Find tanda
    tanda_id = None
    for tid in tandas:
        if tid == args.id or tid.endswith(args.id):
            tanda_id = tid
            break

    if not tanda_id:
        print(f"{RED}Tandas '{args.id}' not found.{RESET}")
        sys.exit(1)

    tanda = tandas[tanda_id]
    updated = False

    if args.status:
        if args.status not in ("active", "flaky", "deprecated"):
            print(f"{RED}Invalid status. Use: active, flaky, deprecated{RESET}")
            sys.exit(1)
        tanda["status"] = args.status
        updated = True

    if args.note:
        timestamp = now_iso()
        notes = tanda.get("notes", [])
        # Migrate string notes to array format
        if isinstance(notes, str):
            notes = [{"ts": timestamp, "type": "note", "text": notes}] if notes else []
        notes.append({"ts": timestamp, "type": "note", "text": args.note})
        tanda["notes"] = notes
        updated = True

    if args.run_result:
        timestamp = now_iso()
        run_history = tanda.get("run_history", [])
        run_entry = {
            "ts": timestamp,
            "result": args.run_result,
        }
        if args.run_duration:
            run_entry["duration"] = args.run_duration
        if args.run_trace:
            run_entry["trace"] = args.run_trace
        run_history.append(run_entry)
        tanda["run_history"] = run_history

        # Auto-update status based on flakiness
        flakiness = calculate_flakiness(run_history)
        if flakiness >= 0.2 and tanda.get("status") == "active":
            tanda["status"] = "flaky"
            print(f"{YELLOW}Auto-marked as flaky (score: {flakiness}){RESET}")
        elif flakiness == 0.0 and tanda.get("status") == "flaky" and len(run_history) >= 3:
            tanda["status"] = "active"
            print(f"{GREEN}Auto-marked as active (3+ consecutive passes){RESET}")

        updated = True

    if args.file:
        tanda["file"] = args.file
        updated = True

    if args.covers:
        covers = [c.strip() for c in args.covers.split(",")]
        tanda["covers"] = covers
        updated = True

    if args.add_dep:
        deps = tanda.get("depends_on", [])
        if args.add_dep not in deps:
            deps.append(args.add_dep)
            tanda["depends_on"] = deps
            updated = True

    if args.remove_dep:
        deps = tanda.get("depends_on", [])
        if args.remove_dep in deps:
            deps.remove(args.remove_dep)
            tanda["depends_on"] = deps
            updated = True

    if updated:
        tanda["updated_at"] = now_iso()
        tandas[tanda_id] = tanda
        rewrite_jsonl(tandas)
        sync_cache_from_json(tandas)
        print(f"{GREEN}Updated {tanda_id}{RESET}")
        cmd_show(argparse.Namespace(id=tanda_id))
    else:
        print("No updates specified. Use --status, --note, --file, --covers, --add-dep, or --remove-dep")


def find_tanda(tandas: dict, id_or_partial: str) -> tuple:
    """Find a tanda by full or partial ID. Returns (id, tanda) or (None, None)."""
    for tid, t in tandas.items():
        if tid == id_or_partial or tid.endswith(id_or_partial):
            return tid, t
    return None, None


def compute_blocked_by(tandas: dict, tanda_id: str) -> list:
    """Compute which tandas are blocked by (depend on) this tanda."""
    blocked_by = []
    for tid, t in tandas.items():
        if tanda_id in t.get("depends_on", []):
            blocked_by.append(tid)
    return blocked_by


def cmd_dep(args):
    """Manage tanda dependencies."""
    ensure_initialized()

    tandas = load_all_from_jsonl()

    if args.dep_command == "add":
        # Add dependency: A depends on B
        tanda_id, tanda = find_tanda(tandas, args.id)
        if not tanda:
            print(f"{RED}Tandas '{args.id}' not found.{RESET}")
            sys.exit(1)

        dep_id, dep_tanda = find_tanda(tandas, args.dependency)
        if not dep_tanda:
            print(f"{RED}Dependency tanda '{args.dependency}' not found.{RESET}")
            sys.exit(1)

        if dep_id == tanda_id:
            print(f"{RED}Cannot add self-dependency.{RESET}")
            sys.exit(1)

        deps = tanda.get("depends_on", [])
        if dep_id in deps:
            print(f"{YELLOW}{tanda_id} already depends on {dep_id}{RESET}")
            return

        deps.append(dep_id)
        tanda["depends_on"] = deps
        tanda["updated_at"] = now_iso()
        tandas[tanda_id] = tanda
        rewrite_jsonl(tandas)
        sync_cache_from_json(tandas)

        print(f"{GREEN}Added dependency: {tanda_id} → {dep_id}{RESET}")
        print(f"  {tanda['title']} now depends on {dep_tanda['title']}")

    elif args.dep_command == "remove":
        tanda_id, tanda = find_tanda(tandas, args.id)
        if not tanda:
            print(f"{RED}Tandas '{args.id}' not found.{RESET}")
            sys.exit(1)

        dep_id, _ = find_tanda(tandas, args.dependency)
        if not dep_id:
            # Try exact match in case tanda was deleted
            dep_id = args.dependency

        deps = tanda.get("depends_on", [])
        if dep_id not in deps:
            print(f"{YELLOW}{tanda_id} does not depend on {dep_id}{RESET}")
            return

        deps.remove(dep_id)
        tanda["depends_on"] = deps
        tanda["updated_at"] = now_iso()
        tandas[tanda_id] = tanda
        rewrite_jsonl(tandas)
        sync_cache_from_json(tandas)

        print(f"{GREEN}Removed dependency: {tanda_id} → {dep_id}{RESET}")

    elif args.dep_command == "show":
        tanda_id, tanda = find_tanda(tandas, args.id)
        if not tanda:
            print(f"{RED}Tandas '{args.id}' not found.{RESET}")
            sys.exit(1)

        depends_on = tanda.get("depends_on", [])
        blocked_by = compute_blocked_by(tandas, tanda_id)

        print(f"{BOLD}{tanda_id}: {tanda['title']}{RESET}")
        print(f"  Status: {status_color(tanda['status'])}")

        if depends_on:
            print(f"\n{BOLD}Depends on ({len(depends_on)}):{RESET}")
            for dep_id in depends_on:
                dep_tanda = tandas.get(dep_id)
                if dep_tanda:
                    status = status_color(dep_tanda['status'])
                    print(f"  → {dep_id}: {dep_tanda['title']} [{status}]")
                else:
                    print(f"  → {dep_id}: {RED}(not found){RESET}")
        else:
            print(f"\n{BOLD}Depends on:{RESET} (none)")

        if blocked_by:
            print(f"\n{BOLD}Blocked by / Depended on by ({len(blocked_by)}):{RESET}")
            for blocker_id in blocked_by:
                blocker = tandas.get(blocker_id)
                if blocker:
                    status = status_color(blocker['status'])
                    print(f"  ← {blocker_id}: {blocker['title']} [{status}]")
        else:
            print(f"\n{BOLD}Blocked by:{RESET} (none)")

    else:
        print("Usage: td dep <add|remove|show> ...")


def cmd_discover(args):
    """Auto-discover and import Playwright test files."""
    ensure_initialized()

    # Find test files
    test_patterns = ["**/*.spec.ts", "**/*.spec.js", "**/*.test.ts", "**/*.test.js"]
    test_files = []

    search_dir = Path(args.dir) if args.dir else Path(".")

    for pattern in test_patterns:
        test_files.extend(search_dir.glob(pattern))

    # Filter out node_modules
    test_files = [f for f in test_files if "node_modules" not in str(f)]

    if not test_files:
        print(f"{YELLOW}No test files found.{RESET}")
        print(f"Searched for: {', '.join(test_patterns)}")
        return

    # Load existing tandas to avoid duplicates
    tandas = load_all_from_jsonl()
    existing_files = {t.get("file") for t in tandas.values()}

    created = 0
    skipped = 0

    for test_file in sorted(test_files):
        file_str = str(test_file)

        if file_str in existing_files:
            skipped += 1
            if args.verbose:
                print(f"  {YELLOW}Skip:{RESET} {file_str} (already registered)")
            continue

        # Generate title from filename
        title = test_file.stem.replace(".spec", "").replace(".test", "")
        title = title.replace("-", " ").replace("_", " ").title()

        tanda_id = generate_id(title)
        now = now_iso()

        tanda = {
            "id": tanda_id,
            "title": title,
            "status": "active",
            "file": file_str,
            "covers": [],
            "depends_on": [],
            "notes": [{"ts": now, "type": "note", "text": "Auto-discovered by td discover"}],
            "run_history": [],
            "created_at": now,
            "updated_at": now,
        }

        append_to_jsonl(tanda)
        created += 1
        print(f"  {GREEN}Created:{RESET} {tanda_id} -> {file_str}")

    # Sync to SQLite
    if created > 0:
        tandas = load_all_from_jsonl()
        sync_cache_from_json(tandas)

    print(f"\n{GREEN}Discovered {created} new test(s){RESET}", end="")
    if skipped > 0:
        print(f", {skipped} already registered", end="")
    print()


def cmd_quickstart(args):
    """Scaffold config/env files so td is ready after init."""
    if not TANDA_DIR.exists():
        print(f"{CYAN}Tandas registry not found. Running 'td init' first...{RESET}")
        cmd_init(argparse.Namespace())

    config_path = TANDA_DIR / "config.yaml"
    env_example_path = TANDA_DIR / "env.example"
    app_config_path = Path("tanda.json")

    config_template = dedent(f"""
        # AI provider configuration for td generate
        ai:
          default_provider: {args.default_provider}
          providers:
            claude:
              api_key: ${{ANTHROPIC_API_KEY}}
              model: claude-sonnet-4-20250514
            openai:
              api_key: ${{OPENAI_API_KEY}}
              model: gpt-4o
            gemini:
              api_key: ${{GEMINI_API_KEY}}
              model: gemini-pro
        """)

    env_template = dedent("""
        # Copy to your shell rc file or run `source .tandas/env.example`
        export ANTHROPIC_API_KEY="sk-ant-..."
        export OPENAI_API_KEY="sk-openai-..."
        export GEMINI_API_KEY="sk-gemini-..."
        """)

    app_template = dedent("""
        {
          "app_url": "http://localhost:3000"
        }
        """)

    created_config = write_template(config_path, config_template, force=args.force)
    created_env = write_template(env_example_path, env_template, force=args.force or args.force_env)

    if not app_config_path.exists() or args.force_app:
        app_config_path.write_text(app_template.strip() + "\n")
        created_app = True
    else:
        created_app = False
        print(f"{YELLOW}{app_config_path} already exists. Skipping.{RESET}")

    print(f"{GREEN if created_config else YELLOW}Config: {config_path}{RESET}")
    print(f"{GREEN if created_env else YELLOW}Env example: {env_example_path}{RESET}")
    print(f"{GREEN if created_app else YELLOW}App config: {app_config_path}{RESET}")

    print("\nNext steps:")
    print("  1. Fill in API keys by editing .tandas/env.example or exporting variables.")
    print("  2. Run 'source .tandas/env.example' (or add to your shell).")
    print("  3. Edit .tandas/config.yaml if you want a different default provider/model.")
    print("  4. Run 'td generate <id>' to draft a test using your provider.")


def cmd_trace(args):
    """Manage trace files and link them to tandas."""
    ensure_initialized()

    command = getattr(args, "trace_command", None)
    if command == "list":
        entries = load_trace_inbox()
        if not args.all:
            entries = [e for e in entries if e.get("status", "pending") == "pending"]

        if not entries:
            print(f"{YELLOW}No trace entries found.{RESET}")
            return

        for entry in entries:
            status = entry.get("status", "pending")
            line = f"[{status}] {entry.get('path')} (source: {entry.get('source', 'unknown')}, ts: {entry.get('ts', 'unknown')})"
            if entry.get("tanda_id"):
                line += f" → {entry['tanda_id']}"
            print(line)
        return

    if command == "scan":
        search_dir = Path(args.dir or "test-results")
        if not search_dir.exists():
            print(f"{YELLOW}Trace directory '{search_dir}' not found.{RESET}")
            return

        extensions = args.ext or [".zip", ".trace.zip"]
        extensions = [ext if ext.startswith(".") else f".{ext}" for ext in extensions]
        existing = {entry.get("path") for entry in load_trace_inbox()}
        discovered = 0

        for ext in extensions:
            for path in search_dir.rglob(f"*{ext}"):
                if not path.is_file():
                    continue
                norm = normalize_trace_path(path)
                if norm in existing:
                    continue
                append_trace_inbox_entry({
                    "path": norm,
                    "ts": now_iso(),
                    "source": args.source or "scan",
                    "status": "pending",
                })
                existing.add(norm)
                discovered += 1

        if discovered:
            print(f"{GREEN}Discovered {discovered} trace file(s). Link them with 'td trace link'.{RESET}")
        else:
            print(f"{YELLOW}No new trace files found (extensions: {', '.join(extensions)}).{RESET}")
        return

    if command == "link":
        tandas = load_all_from_jsonl()
        tanda_id, tanda = find_tanda(tandas, args.id)
        if not tanda:
            print(f"{RED}Tandas '{args.id}' not found.{RESET}")
            sys.exit(1)

        trace_path = normalize_trace_path(args.trace)
        if not Path(trace_path).exists():
            print(f"{YELLOW}Warning: trace path '{trace_path}' not found. Linking anyway.{RESET}")

        run_history = tanda.get("run_history", [])
        entry = {
            "ts": now_iso(),
            "result": args.result,
            "trace": trace_path,
        }
        if args.duration:
            entry["duration"] = args.duration
        run_history.append(entry)
        tanda["run_history"] = run_history

        if args.note:
            notes = tanda.get("notes", [])
            if isinstance(notes, str):
                notes = [{"ts": now_iso(), "type": "note", "text": notes}]
            notes.append({"ts": now_iso(), "type": "trace", "text": args.note})
            tanda["notes"] = notes

        tanda["updated_at"] = now_iso()
        tandas[tanda_id] = tanda
        rewrite_jsonl(tandas)
        sync_cache_from_json(tandas)

        if update_trace_entry(trace_path, status="linked", tanda_id=tanda_id, linked_at=now_iso()):
            print(f"{GREEN}Linked trace {trace_path} to {tanda_id}.{RESET}")
        else:
            print(f"{YELLOW}Trace {trace_path} was not in the inbox; recorded anyway.{RESET}")
        return

    print("Usage: td trace <list|scan|link> ...")


def cmd_generate(args):
    """Generate a test skeleton via configured AI providers."""
    ensure_initialized()

    tandas = load_all_from_jsonl()
    tanda_id, tanda = find_tanda(tandas, args.id)
    if not tanda:
        print(f"{RED}Tandas '{args.id}' not found.{RESET}")
        sys.exit(1)

    config_path = Path(args.config) if args.config else TANDA_DIR / "config.yaml"
    try:
        ai_config = load_ai_config(config_path)
    except GenerationConfigError as exc:
        print(f"{RED}{exc}{RESET}")
        sys.exit(1)

    provider_name = args.provider or ai_config.default_provider
    try:
        provider = get_provider(provider_name, ai_config)
    except GenerationConfigError as exc:
        print(f"{RED}{exc}{RESET}")
        sys.exit(1)

    context = build_context(tanda, Path.cwd())
    try:
        generated = provider.generate_test(context)
    except GenerationProviderError as exc:
        print(f"{RED}Generation failed: {exc}{RESET}")
        sys.exit(1)

    if args.output:
        output_path = Path(args.output)
        output_path.write_text(generated)
        print(f"{GREEN}Wrote generated test to {output_path}{RESET}")
    else:
        print(generated)


def cmd_sync(args):
    """Sync JSONL to SQLite cache and optionally to git."""
    ensure_initialized()

    tandas = load_all_from_jsonl()
    sync_cache_from_json(tandas)

    print(f"Synced {len(tandas)} tanda(s) to SQLite cache")

    # Git operations
    if Path(".git").exists():
        result = subprocess.run(
            ["git", "status", "--porcelain", str(TANDA_DIR)],
            capture_output=True,
            text=True
        )

        if result.stdout.strip():
            subprocess.run(["git", "add", str(TANDA_DIR)], capture_output=True)
            print(f"Staged {TANDA_DIR}/ changes for git")


def cmd_daemon(args):
    """Manage the Go daemon lifecycle (start/stop/status)."""
    ensure_initialized()

    action = getattr(args, "daemon_command", None)
    if not action:
        print("Usage: td daemon <start|stop|status>")
        return

    if action == "status":
        status = daemon_call("status", quiet=True)
        if status:
            pid = status.get("pid", "?")
            interval = status.get("interval", "unknown")
            print(f"{GREEN}Daemon running{RESET} (PID: {pid}, interval: {interval})")
            print(f"Socket: {DAEMON_SOCKET}")
            return

        if DAEMON_PID_FILE.exists():
            try:
                pid_text = DAEMON_PID_FILE.read_text().strip()
            except OSError:
                pid_text = "unknown"
            print(f"{YELLOW}Daemon not responding. Last known PID: {pid_text}{RESET}")
        else:
            print(f"{YELLOW}Daemon not running. Use 'td daemon start'.{RESET}")
        return

    binary = resolve_daemon_binary(getattr(args, "bin", None))
    if not binary:
        print(
            f"{RED}td-daemon binary not found. Build it (cd daemon && go build -o td-daemon ./cmd/td-daemon) "
            f"or set {DAEMON_BIN_ENV} to its path.{RESET}"
        )
        sys.exit(1)

    cmd = [binary, action, "--dir", str(TANDA_DIR)]

    if action == "start":
        interval = getattr(args, "interval", "5s") or "5s"
        cmd.extend(["--interval", interval])

    result = subprocess.run(cmd)
    if result.returncode != 0:
        sys.exit(result.returncode)

    if action == "start":
        if wait_for_daemon():
            print(f"{GREEN}Daemon ready on {DAEMON_SOCKET}{RESET}")
        else:
            print(f"{YELLOW}Daemon started but socket not ready. Check logs.{RESET}")

def topological_sort(tandas: dict, filter_status: list = None) -> tuple:
    """
    Topologically sort tandas based on dependencies using Kahn's algorithm.

    Returns:
        (sorted_list, blocked_list) - sorted are ready to run, blocked have unmet deps
    """
    if filter_status is None:
        filter_status = ["active", "flaky"]

    # Filter to relevant tandas
    relevant = {tid: t for tid, t in tandas.items() if t.get("status") in filter_status}

    # Build in-degree map (how many dependencies each tanda has within relevant set)
    in_degree = {}
    for tid, t in relevant.items():
        deps = [d for d in t.get("depends_on", []) if d in relevant]
        in_degree[tid] = len(deps)

    # Find all with zero in-degree (no dependencies or deps outside relevant set)
    queue = [tid for tid, deg in in_degree.items() if deg == 0]
    sorted_list = []

    while queue:
        # Sort queue by status (flaky first) then by updated_at (oldest first)
        queue.sort(key=lambda x: (
            0 if relevant[x].get("status") == "flaky" else 1,
            relevant[x].get("updated_at", "")
        ))

        current = queue.pop(0)
        sorted_list.append(current)

        # Reduce in-degree of dependents
        for tid, t in relevant.items():
            if current in t.get("depends_on", []):
                in_degree[tid] -= 1
                if in_degree[tid] == 0:
                    queue.append(tid)

    # Any remaining with in_degree > 0 are blocked (circular or missing deps)
    blocked = [tid for tid, deg in in_degree.items() if deg > 0 and tid not in sorted_list]

    return sorted_list, blocked


def get_blocking_deps(tanda: dict, tandas: dict) -> list:
    """Get list of dependencies that are blocking (flaky or deprecated)."""
    blocking = []
    for dep_id in tanda.get("depends_on", []):
        dep = tandas.get(dep_id)
        if dep and dep.get("status") in ("flaky", "deprecated"):
            blocking.append((dep_id, dep))
    return blocking


def cmd_ready(args):
    """Show high-priority tandas in execution order (dependencies first)."""
    ensure_initialized()

    tandas = load_all_from_jsonl()

    if not tandas:
        print(f"{YELLOW}No tandas found.{RESET}")
        print("Run 'td discover' to import existing tests.")
        return

    # Separate flaky tests (highest priority for healing)
    flaky = {tid: t for tid, t in tandas.items() if t.get("status") == "flaky"}
    active = {tid: t for tid, t in tandas.items() if t.get("status") == "active"}

    # Get topologically sorted active tests
    sorted_ids, blocked_ids = topological_sort(tandas, ["active"])

    # Find tests blocked by flaky dependencies
    blocked_by_flaky = []
    for tid in sorted_ids[:]:  # Copy to avoid modifying during iteration
        blocking = get_blocking_deps(tandas[tid], tandas)
        if blocking:
            blocked_by_flaky.append((tid, blocking))
            sorted_ids.remove(tid)

    # Print results
    if flaky:
        print(f"{BOLD}{YELLOW}⚠ Flaky tests (need healing):{RESET}")
        for tid, t in flaky.items():
            print(f"  {tid}: {t['title']}")
            if t.get("file"):
                print(f"    └─ {t['file']}")
        print()

    if sorted_ids:
        print(f"{BOLD}{GREEN}✓ Ready (in execution order):{RESET}")
        for i, tid in enumerate(sorted_ids, 1):
            t = tandas[tid]
            deps = t.get("depends_on", [])
            dep_info = ""
            if deps:
                resolved = [d for d in deps if d in tandas and tandas[d].get("status") == "active"]
                if resolved:
                    dep_info = f" (after: {', '.join(resolved[:2])}{'...' if len(resolved) > 2 else ''})"
            print(f"  {i}. {tid}: {t['title']}{dep_info}")
        print()

    if blocked_by_flaky:
        print(f"{BOLD}{RED}✗ Blocked (waiting on flaky):{RESET}")
        for tid, blocking in blocked_by_flaky:
            t = tandas[tid]
            blocker_names = [f"{b[0]}" for b in blocking]
            print(f"  {tid}: {t['title']}")
            print(f"    └─ waiting on: {', '.join(blocker_names)}")
        print()

    if blocked_ids:
        print(f"{BOLD}{CYAN}○ Blocked (circular/missing deps):{RESET}")
        for tid in blocked_ids:
            t = tandas[tid]
            print(f"  {tid}: {t['title']}")
        print()

    # Summary
    total = len(flaky) + len(sorted_ids) + len(blocked_by_flaky) + len(blocked_ids)
    if total == 0:
        print(f"{GREEN}No tandas need attention.{RESET}")


def cmd_version(args):
    """Show version information."""
    print(f"td (Tandas CLI) v{VERSION}")
    print("Persistent test registry for AI-orchestrated test suites")


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        prog="td",
        description="Tandas: Persistent test registry for AI-orchestrated test suites",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  td init                          Initialize registry
  td create "Login Flow"           Create new tanda
  td create "Auth" --file tests/auth.spec.ts --covers auth,session
  td list --flaky                  Show flaky tests
  td show td-abc123                View tanda details
  td update td-abc123 --status flaky --note "Timing issue"
  td discover                      Auto-import test files
  td ready                         Show what needs attention
  td sync                          Sync to SQLite and git
        """
    )
    parser.add_argument("--version", "-v", action="store_true", help="Show version")

    subparsers = parser.add_subparsers(dest="command", metavar="command")

    # init
    init_p = subparsers.add_parser("init", help="Initialize Tandas registry")
    init_p.set_defaults(func=cmd_init)

    # quickstart
    quick_p = subparsers.add_parser("quickstart", help="Create config/env scaffolding")
    quick_p.add_argument("--default-provider", default="claude", choices=sorted(PROVIDERS.keys()),
                         help="Default provider to set in config (default: claude)")
    quick_p.add_argument("--force", action="store_true", help="Overwrite existing config/env files")
    quick_p.add_argument("--force-env", action="store_true", help="Only overwrite env example")
    quick_p.add_argument("--force-app", action="store_true", help="Overwrite tanda.json template")
    quick_p.set_defaults(func=cmd_quickstart)

    # create
    create_p = subparsers.add_parser("create", help="Create a new tanda")
    create_p.add_argument("title", help="Test title/name")
    create_p.add_argument("--file", "-f", help="Path to test file")
    create_p.add_argument("--status", "-s", default="active",
                          choices=["active", "flaky", "deprecated"],
                          help="Initial status (default: active)")
    create_p.add_argument("--covers", "-c", help="Comma-separated coverage tags")
    create_p.set_defaults(func=cmd_create)

    # list
    list_p = subparsers.add_parser("list", help="List tandas")
    list_p.add_argument("--active", "-a", action="store_true", help="Show only active")
    list_p.add_argument("--flaky", "-f", action="store_true", help="Show only flaky")
    list_p.add_argument("--deprecated", "-d", action="store_true", help="Show only deprecated")
    list_p.add_argument("--status", "-s", help="Filter by status")
    list_p.add_argument("--covers", "-c", help="Filter by coverage tag")
    list_p.set_defaults(func=cmd_list)

    # show
    show_p = subparsers.add_parser("show", help="Show tanda details")
    show_p.add_argument("id", help="Tandas ID (full or partial)")
    show_p.set_defaults(func=cmd_show)

    # update
    update_p = subparsers.add_parser("update", help="Update a tanda")
    update_p.add_argument("id", help="Tandas ID (full or partial)")
    update_p.add_argument("--status", "-s", help="New status: active, flaky, deprecated")
    update_p.add_argument("--note", "-n", help="Add a timestamped note")
    update_p.add_argument("--file", "-f", help="Set file path")
    update_p.add_argument("--covers", "-c", help="Set coverage tags (comma-separated)")
    update_p.add_argument("--add-dep", help="Add dependency on another tanda")
    update_p.add_argument("--remove-dep", help="Remove dependency")
    update_p.add_argument("--run-result", "-r", choices=["pass", "fail", "skip"],
                          help="Record a test run result")
    update_p.add_argument("--run-duration", help="Duration of test run (e.g., '2.3s')")
    update_p.add_argument("--run-trace", help="Path to Playwright trace file")
    update_p.set_defaults(func=cmd_update)

    # dep (dependency management)
    dep_p = subparsers.add_parser("dep", help="Manage dependencies")
    dep_sub = dep_p.add_subparsers(dest="dep_command", metavar="action")

    dep_add = dep_sub.add_parser("add", help="Add dependency (A depends on B)")
    dep_add.add_argument("id", help="Tandas item that will depend on another")
    dep_add.add_argument("dependency", help="Tandas item to depend on")

    dep_remove = dep_sub.add_parser("remove", help="Remove dependency")
    dep_remove.add_argument("id", help="Tandas item to remove dependency from")
    dep_remove.add_argument("dependency", help="Dependency to remove")

    dep_show = dep_sub.add_parser("show", help="Show dependencies for a tanda")
    dep_show.add_argument("id", help="Tandas ID")

    dep_p.set_defaults(func=cmd_dep)

    # discover
    discover_p = subparsers.add_parser("discover", help="Auto-discover test files")
    discover_p.add_argument("--dir", "-d", help="Directory to search (default: current)")
    discover_p.add_argument("--verbose", "-v", action="store_true", help="Show skipped files")
    discover_p.set_defaults(func=cmd_discover)

    # trace
    trace_p = subparsers.add_parser("trace", help="Manage test traces")
    trace_sub = trace_p.add_subparsers(dest="trace_command", metavar="action")

    trace_link = trace_sub.add_parser("link", help="Link a trace file to a tanda")
    trace_link.add_argument("id", help="Tandas ID (full or partial)")
    trace_link.add_argument("trace", help="Path to trace file")
    trace_link.add_argument("--result", choices=["pass", "fail", "skip", "unknown"], default="fail",
                            help="Result to record for the linked run (default: fail)")
    trace_link.add_argument("--duration", help="Duration of the trace/run (optional)")
    trace_link.add_argument("--note", help="Attach a note alongside the trace entry")

    trace_scan = trace_sub.add_parser("scan", help="Scan directory for new traces")
    trace_scan.add_argument("--dir", help="Directory to scan (default: test-results)")
    trace_scan.add_argument("--ext", action="append", help="File extension filter (repeatable)")
    trace_scan.add_argument("--source", default="scan", help="Source label stored in trace inbox")

    trace_list = trace_sub.add_parser("list", help="List pending traces")
    trace_list.add_argument("--all", action="store_true", help="Show linked entries as well")

    trace_p.set_defaults(func=cmd_trace)

    # generate
    generate_p = subparsers.add_parser("generate", help="Generate or plan a test via AI provider")
    generate_p.add_argument("id", help="Tandas ID (full or partial)")
    generate_p.add_argument("--provider", choices=sorted(PROVIDERS.keys()), help="Provider override")
    generate_p.add_argument("--config", help="Path to config.yaml (default: .tandas/config.yaml)")
    generate_p.add_argument("--output", "-o", help="Write output to file instead of stdout")
    generate_p.set_defaults(func=cmd_generate)

    # sync
    sync_p = subparsers.add_parser("sync", help="Sync JSONL to SQLite and git")
    sync_p.set_defaults(func=cmd_sync)

    # daemon
    daemon_p = subparsers.add_parser("daemon", help="Manage the Go daemon")
    daemon_sub = daemon_p.add_subparsers(dest="daemon_command", metavar="action")

    daemon_start = daemon_sub.add_parser("start", help="Start the daemon")
    daemon_start.add_argument("--interval", "-i", default="5s", help="Sync interval (default: 5s)")
    daemon_start.add_argument("--bin", help="Path to td-daemon binary (overrides env)")

    daemon_stop = daemon_sub.add_parser("stop", help="Stop the daemon")
    daemon_stop.add_argument("--bin", help="Path to td-daemon binary (overrides env)")

    daemon_sub.add_parser("status", help="Show daemon status")

    daemon_p.set_defaults(func=cmd_daemon)

    # ready
    ready_p = subparsers.add_parser("ready", help="Show tandas needing attention")
    ready_p.set_defaults(func=cmd_ready)

    # version
    version_p = subparsers.add_parser("version", help="Show version")
    version_p.set_defaults(func=cmd_version)

    args = parser.parse_args()

    if args.version:
        cmd_version(args)
        return

    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
