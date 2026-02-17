set shell := ["bash", "-uc"]
set dotenv-load := true

alias pre-commit := hooks
alias upgrade := update

# Show available recipes
default:
    @just --list

# ============================================================================
# Development
# ============================================================================

[doc('Run the software pilot CLI with provided arguments')]
[group('dev')]
run *args:
    uv run software-pilot {{ args }}

[doc('Install project dependencies')]
[group('dev')]
install:
    uv sync

[doc('Install project in editable mode with all dependencies')]
[group('dev')]
install-dev:
    uv sync --extra dev

[doc('Update pre-commit hooks and dependencies')]
[group('qa')]
update:
    uv run pre-commit autoupdate
    uv sync --upgrade

# ============================================================================
# Testing & Quality Assurance
# ============================================================================

[doc('Run all tests with pytest')]
[group('test')]
test *pytest_args:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ ! -d tests ]; then
        echo "No tests directory found. Create tests/ to add tests."
        exit 1
    fi
    # Use direct python path to avoid uv run issues with pytest
    if [ -f .venv/bin/python ]; then
        .venv/bin/python -m pytest tests/ -v --tb=short {{ pytest_args }}
    else
        uv run python -m pytest tests/ -v --tb=short {{ pytest_args }}
    fi

[doc('Run tests with coverage report')]
[group('test')]
test-cov:
    #!/usr/bin/env bash
    if [ -d tests ]; then
        uv run pytest tests/ --cov=src/software_pilot --cov-report=html --cov-report=term
    else
        echo "No tests directory found. Create tests/ to add tests."
        exit 1
    fi

[doc('Serve the HTML coverage report')]
[group('test')]
serve-coverage:
    @echo "Serving coverage report at http://localhost:8080"
    uv run python -m http.server 8080 -d htmlcov

[doc('Install pre-commit hooks')]
[group('qa')]
install-hooks:
    uv run pre-commit install

[doc('Run pre-commit hooks on all files')]
[group('qa')]
hooks *args:
    uv run pre-commit run --all-files {{ args }}

[doc('Run pre-commit hooks on staged files')]
[group('qa')]
hooks-staged *args:
    uv run pre-commit run {{ args }}

[doc('Run security checks with bandit')]
[group('qa')]
security:
    @echo "Running bandit security checks..."
    uv run bandit -r src/ -ll || true

[doc('Run all quality checks (pre-commits, security)')]
[group('qa')]
check: hooks security

# ============================================================================
# Build & Release
# ============================================================================

[doc('Build the Python package distribution')]
[group('build')]
build:
    uv build

[doc('Clean build artifacts')]
[group('build')]
clean:
    @echo "Cleaning build artifacts..."
    rm -rf dist/ build/ *.egg-info htmlcov/ .coverage .pytest_cache/ .ruff_cache/ .mypy_cache/
    find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

[doc('Clean and rebuild package')]
[group('build')]
rebuild: clean build
