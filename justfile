set shell := ["bash", "-uc"]
set dotenv-load := true

# variables

gwy_root := justfile_directory()
git_root := gwy_root

# aliases

alias pre-commit := hooks
alias prek := hooks
alias upgrade := update

# Show available recipes
default:
    @just --list

# ============================================================================
# Development
# ============================================================================

[doc('Set up the development environment by checking dependencies, installing Python packages, and configuring pre-commit hooks')]
[group('development')]
dev-setup:
    #!/usr/bin/env bash
    set -euo pipefail
    echo -e "Setting up development environment\n"

    # check for required system dependencies
    echo "Checking system dependencies..."
    missing_deps=()

    if ! command -v uv &> /dev/null; then
        missing_deps+=("uv (install from: https://docs.astral.sh/uv/getting-started/installation/)")
    fi
    if ! command -v just &> /dev/null; then
        missing_deps+=("just (install from: https://github.com/casey/just#installation/)")
    fi

    # report missing dependencies
    if [[ ${#missing_deps[@]} -gt 0 ]]; then
        echo -e "\n\e[31m✗  Missing required system dependencies:\e[0m"
        for dep in "${missing_deps[@]}"; do
            echo "  - ${dep}"
        done
        echo -e "\n\e[33mInstall commands (run as needed for your system):\e[0m"
        echo -e "  Ubuntu/Debian:"
        echo "    sudo apt update"
        echo "    sudo apt install -y docker.io docker-compose-v2 python3-dev libpq-dev postgresql-client"
        echo "    curl -LsSf https://astral.sh/uv/install.sh | sh"
        echo "    curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to ~/.local/bin"
        echo -e "  RHEL/Fedora:"
        echo "    sudo dnf install -y docker docker-compose-plugin python3-devel postgresql-devel postgresql"
        echo "    curl -LsSf https://astral.sh/uv/install.sh | sh"
        echo "    curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to ~/.local/bin"
        echo ""
        exit 1
    fi

    echo -e "\e[32m✓  All system dependencies found\e[0m\n"

    # install python dependencies
    echo "Installing Python dependencies..."
    uv sync --dev --frozen

    # install pre-commit hooks
    echo "Installing pre-commit hooks..."
    uv run prek install -f
    uv run prek install-hooks

    echo -e "\n\e[32m✓  Development environment setup complete\e[0m"

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
    uv run prek autoupdate
    uv sync --upgrade

# ============================================================================
# Testing & Quality Assurance
# ============================================================================

[doc('Runs GitHub Actions locally using gh act. e.g. `just gact -j qa-test-and-lint`, `just gact -l`')]
[group('development')]
[group('qa')]
gact *args:
    @echo "Running GitHub Actions locally for {{ git_root }}"
    cd "{{ git_root }}" && \
        gh act \
            --rm \
            --workflows "{{ git_root }}/.github/workflows" \
            {{ args }}

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
    uv run prek install

[doc('Run pre-commit hooks on all files')]
[group('qa')]
hooks *args:
    #!/usr/bin/env bash
    args=({{ args }})
    if [ ${#args[@]} -eq 0 ]; then
        uv run prek run --all-files
    else
        uv run prek run ${args[@]}
    fi

[doc('Run pre-commit hooks on staged files')]
[group('qa')]
hooks-staged *args:
    uv run prek run {{ args }}

[doc('Run security checks with bandit')]
[group('qa')]
security:
    @echo "Running bandit security checks..."
    uv run bandit -r src/ -ll

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
