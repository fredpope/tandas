#!/usr/bin/env python3
import argparse
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

TANDA_DIR = Path(".tandas")
ISSUES_FILE = TANDA_DIR / "issues.jsonl"
DB_FILE = TANDA_DIR / "db.sqlite"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS issues (
        id TEXT PRIMARY KEY,
        title TEXT,
        status TEXT DEFAULT 'active',
        file TEXT,
        notes TEXT
    )""")
    conn.commit()
    conn.close()

def ensure_dir():
    TANDA_DIR.mkdir(exist_ok=True)
    if not DB_FILE.exists():
        init_db()

def load_issues():
    issues = {}
    if ISSUES_FILE.exists():
        with open(ISSUES_FILE) as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    issues[data['id']] = data
    return issues

def save_issue(issue):
    with open(ISSUES_FILE, "a") as f:
        f.write(json.dumps(issue) + "\n")

def main():
    parser = argparse.ArgumentParser(prog="td", description="Tanda: Persistent test registry")
    sub = parser.add_subparsers(dest="cmd")

    init_p = sub.add_parser("init")
    create_p = sub.add_parser("create")
    create_p.add_argument("title")
    create_p.add_argument("--file")
    create_p.add_argument("--status", default="active")

    list_p = sub.add_parser("list")

    args = parser.parse_args()

    ensure_dir()

    if args.cmd == "init":
        print("Tanda initialized in .tandas/")
        subprocess.run(["git", "add", ".tandas"], cwd=".")

    elif args.cmd == "create":
        import hashlib
        id_hash = hashlib.sha1(args.title.encode()).hexdigest()[:8]
        tid = f"td-{id_hash}"
        issue = {
            "id": tid,
            "title": args.title,
            "status": args.status,
            "file": args.file,
            "notes": ""
        }
        save_issue(issue)
        print(f"Created tanda {tid}: {args.title}")

    elif args.cmd == "list":
        issues = load_issues()
        for issue in issues.values():
            print(f"{issue['id']}: {issue['title']} [{issue['status']}] {issue.get('file','')}")

    else:
        parser.print_help()

if __name__ == "__main__":
    main()