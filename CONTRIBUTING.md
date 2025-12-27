# Contributing to Tandas

Thank you for your interest in contributing to Tandas! This document provides guidelines and information for contributors.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Project Structure](#project-structure)
- [Making Changes](#making-changes)
- [Pull Request Process](#pull-request-process)
- [Coding Standards](#coding-standards)
- [Testing](#testing)
- [Documentation](#documentation)

## Code of Conduct

This project adheres to a [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code. Please report unacceptable behavior to the project maintainers.

## Getting Started

### Prerequisites

- Python 3.8 or higher
- Go 1.21 or higher (for daemon development)
- Git
- SQLite 3

### Fork and Clone

1. Fork the repository on GitHub
2. Clone your fork locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/tanda.git
   cd tanda
   ```
3. Add the upstream remote:
   ```bash
   git remote add upstream https://github.com/ORIGINAL_OWNER/tanda.git
   ```

## Development Setup

### Python CLI

```bash
# Create a virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install development dependencies
pip install -e ".[dev]"

# Or manually install dependencies
pip install pytest black flake8 mypy
```

### Go Daemon

```bash
cd daemon

# Download dependencies
go mod tidy

# Build
go build -o td-daemon ./cmd/td-daemon

# Run tests
go test ./...
```

## Project Structure

```
tanda/
├── td.py                    # Main Python CLI
├── daemon/                  # Go daemon
│   ├── cmd/
│   │   └── td-daemon/
│   │       └── main.go      # Daemon entry point
│   ├── internal/
│   │   ├── db/              # SQLite operations
│   │   ├── rpc/             # Unix socket RPC server
│   │   ├── sync/            # JSONL <-> SQLite sync
│   │   └── watch/           # File system watcher
│   ├── go.mod
│   └── go.sum
├── tests/                   # Test files
├── docs/                    # Documentation
├── AGENTS.md                # AI agent instructions
├── README.md
├── CONTRIBUTING.md
├── CODE_OF_CONDUCT.md
└── LICENSE
```

## Making Changes

### Branching Strategy

- `main` - Stable release branch
- `develop` - Integration branch for features
- `feature/*` - Feature branches
- `fix/*` - Bug fix branches
- `docs/*` - Documentation updates

### Creating a Branch

```bash
# Sync with upstream
git fetch upstream
git checkout main
git merge upstream/main

# Create a feature branch
git checkout -b feature/my-feature
```

### Commit Messages

Follow the [Conventional Commits](https://www.conventionalcommits.org/) specification:

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

Types:
- `feat` - New feature
- `fix` - Bug fix
- `docs` - Documentation only
- `style` - Code style (formatting, semicolons, etc.)
- `refactor` - Code refactoring
- `test` - Adding or updating tests
- `chore` - Maintenance tasks

Examples:
```
feat(cli): add td dep show command
fix(sync): handle empty JSONL files gracefully
docs: update README with daemon build instructions
```

## Pull Request Process

1. **Update your branch** with the latest upstream changes:
   ```bash
   git fetch upstream
   git rebase upstream/main
   ```

2. **Run tests** and ensure they pass:
   ```bash
   # Python
   python -m pytest

   # Go
   cd daemon && go test ./...
   ```

3. **Run linters**:
   ```bash
   # Python
   black td.py
   flake8 td.py
   mypy td.py

   # Go
   cd daemon && go fmt ./... && go vet ./...
   ```

4. **Push your branch**:
   ```bash
   git push origin feature/my-feature
   ```

5. **Open a Pull Request** on GitHub with:
   - Clear title following commit message conventions
   - Description of changes
   - Link to any related issues
   - Screenshots/examples if applicable

6. **Address review feedback** promptly

7. **Squash commits** if requested before merge

## Coding Standards

### Python

- Follow [PEP 8](https://pep8.org/) style guide
- Use [Black](https://black.readthedocs.io/) for formatting
- Use type hints where practical
- Maximum line length: 100 characters
- Use docstrings for public functions

```python
def calculate_flakiness(run_history: list) -> float:
    """
    Calculate flakiness score from run history.

    Args:
        run_history: List of run result dictionaries

    Returns:
        Flakiness score between 0.0 and 1.0
    """
    if not run_history:
        return 0.0
    # ...
```

### Go

- Follow standard Go conventions
- Use `gofmt` for formatting
- Use `golint` for style
- Write godoc comments for exported functions

```go
// CalculateFlakiness computes the flakiness score from run history.
// It considers the last 10 runs and returns a value between 0.0 and 1.0.
func CalculateFlakiness(history []RunResult) float64 {
    // ...
}
```

## Testing

### Python Tests

```bash
# Run all tests
python -m pytest

# Run with coverage
python -m pytest --cov=. --cov-report=html

# Run specific test file
python -m pytest tests/test_cli.py

# Run with verbose output
python -m pytest -v
```

### Go Tests

```bash
cd daemon

# Run all tests
go test ./...

# Run with coverage
go test -cover ./...

# Run specific package
go test ./internal/db/

# Run with race detection
go test -race ./...
```

### Writing Tests

- Test files should be named `test_*.py` (Python) or `*_test.go` (Go)
- Aim for meaningful test coverage, not 100%
- Test edge cases and error conditions
- Use descriptive test names

## Documentation

### Code Documentation

- Document all public functions and classes
- Explain "why" not just "what"
- Keep comments up-to-date with code changes

### User Documentation

- Update README.md for user-facing changes
- Update AGENTS.md for AI workflow changes
- Add examples for new features

### Changelog

For significant changes, add an entry to the changelog (if one exists) or mention it in your PR description.

## Questions?

- Open an issue for bugs or feature requests
- Start a discussion for questions or ideas
- Check existing issues before creating new ones

Thank you for contributing to Tandas!
