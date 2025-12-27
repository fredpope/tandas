#!/bin/bash
set -e

echo "🚀 Installing Tanda - AI Test Orchestration Layer (inspired by Beads)"
echo "   For Playwright + Vite projects"

# Step 1: Install official Beads CLI
echo "📦 Installing Beads (transient execution engine)..."
curl -fsSL https://raw.githubusercontent.com/steveyegge/beads/main/scripts/install.sh | bash

# Step 2: Initialize Beads
echo "🔧 Initializing Beads for execution tasks..."
bd init --quiet || echo "Beads already initialized"

# Step 3: Install td CLI (our persistent tanda layer)
echo "📦 Installing td CLI (persistent test registry)..."
# For v0.1, we'll use a simple Python script (no compile needed)
mkdir -p ~/.local/bin
curl -fsSL https://get.tanda.dev/td.py -o ~/.local/bin/td
chmod +x ~/.local/bin/td

# Ensure ~/.local/bin in PATH (common on Linux/macOS)
if ! echo $PATH | grep -q ~/.local/bin; then
  echo "export PATH=\"\$PATH:~/.local/bin\"" >> ~/.bashrc
  echo "export PATH=\"\$PATH:~/.local/bin\"" >> ~/.zshrc
  export PATH="$PATH:~/.local/bin"
fi

# Step 4: Initialize Tanda in current dir (if in a git repo)
if git rev-parse --git-dir > /dev/null 2>&1; then
  echo "🔧 Initializing Tanda persistent registry..."
  td init --quiet

  # Auto-discover existing Playwright tests
  echo "🔍 Auto-importing existing Playwright tests..."
  find tests -name "*.spec.ts" -o -name "*.test.ts" | while read file; do
    name=$(basename "$file" .ts)
    td create "$name" --file "$file" --status active || true
  done

  # Add AGENTS.md
  if [ ! -f AGENTS.md ]; then
    curl -fsSL https://get.tanda.dev/AGENTS.md -o AGENTS.md
    echo "📝 Created AGENTS.md with full agent instructions"
  fi

  echo "✅ Tanda installed! Run 'td list' to see your tests, 'bd ready' for execution."
  echo "   Tell your agent: 'Orchestrate tests using Tanda (td) + Beads (bd)'"
else
  echo "⚠️  Not in a git repo. Run 'git init' first, then re-run installer."
fi

echo "🌟 Tanda is open source: https://github.com/yourusername/tanda"