# Usage Examples

Quick recipes for using Tandas (`td`) across different stacks. Each example assumes
you have already run `td init` and (optionally) `td quickstart`.

## Playwright / Vite (TypeScript)
```bash
# Discover *.spec.ts and *.test.ts files under tests/
td discover --dir tests

# Generate a new test using OpenAI
source .tandas/env.example
td generate td-login --provider openai --output tests/generated/login.spec.ts

# Link a Playwright trace produced under test-results/
td trace scan --dir test-results
td trace link td-login test-results/login-trace.zip --result fail
```

## Jest (TypeScript or JavaScript)
```bash
# Discover Jest tests
find src -name "*.test.ts" -o -name "*.test.js" | xargs -I{} td create "{}" --file {}

# Generate a Jest test skeleton
source .tandas/env.example
td generate td-cart --provider claude --output src/__tests__/cart.test.ts

# Include a failing run trace/log
mkdir -p jest-results
cp ./artifacts/trace.zip jest-results/cart-trace.zip
td trace link td-cart jest-results/cart-trace.zip --result fail --note "CI failure on Chrome"
```

## Python (pytest)
```bash
# Manually register pytest files
find tests -name "test_*.py" | xargs -I{} td create "{}" --file {}

# Use td generate to draft a Playwright-style test and adapt as needed
source .tandas/env.example
td generate td-api --provider gemini --output tests/generated/test_api.py

# Link pytest logs or traces
mkdir -p test-results
cp /tmp/pytest-trace.zip test-results/api-trace.zip
td trace link td-api test-results/api-trace.zip --result fail --note "Timeout on staging"
```

## Continuous Integration (generic)
```bash
# Sync registry to SQLite before running jobs
td sync

# Start daemon in CI to watch test-results/
td daemon start --interval 2s &

# After tests finish, queue traces and stop daemon
td trace scan --dir test-results
td daemon stop

# Commit .tandas/issues.jsonl and .beads/issues.jsonl together
git add .tandas/issues.jsonl .beads/issues.jsonl
```
