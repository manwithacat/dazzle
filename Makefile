# DAZZLE Development Makefile
#
# Usage: make <target>
# Run 'make help' to see all available targets

.PHONY: help install dev-install lint format type-check security test test-fast test-integration test-all coverage clean build examples ci pre-commit

# Default target
help:
	@echo "DAZZLE Development Commands"
	@echo "============================"
	@echo ""
	@echo "Setup:"
	@echo "  install          Install DAZZLE in development mode"
	@echo "  dev-install      Install with all dev dependencies + pre-commit hooks"
	@echo ""
	@echo "Code Quality:"
	@echo "  lint             Run ruff linter"
	@echo "  format           Run ruff formatter"
	@echo "  type-check       Run mypy type checker"
	@echo "  security         Run bandit + pip-audit security checks"
	@echo "  spell            Run codespell spell checker"
	@echo ""
	@echo "Testing:"
	@echo "  test             Run all tests"
	@echo "  test-fast        Run fast tests only (no integration/slow)"
	@echo "  test-ux-preflight  UX cycle gate (~5s): lints + snapshots + card-safety + mypy(ui)"
	@echo "  test-ux-deep     Preflight + mypy across core/cli/mcp/back (~15s warm) — use before ship"
	@echo "  test-integration Run integration tests only"
	@echo "  coverage         Run tests with coverage report"
	@echo ""
	@echo "Build:"
	@echo "  build            Build Python package (sdist + wheel)"
	@echo "  examples         Validate and build example projects"
	@echo ""
	@echo "CI/CD:"
	@echo "  ci               Run all CI checks locally"
	@echo "  pre-commit       Run pre-commit on all files"
	@echo ""
	@echo "Maintenance:"
	@echo "  clean            Remove build artifacts"
	@echo "  update-deps      Update pre-commit hooks and check for outdated packages"

# =============================================================================
# Setup
# =============================================================================

install:
	pip install -e ".[dev,llm]"

dev-install:
	pip install -e ".[dev,llm]"
	pip install pygls || true
	pre-commit install
	pre-commit install --hook-type pre-push
	@echo ""
	@echo "Development environment ready!"
	@echo "Pre-commit hooks installed for commit and push."

# =============================================================================
# Code Quality
# =============================================================================

lint:
	ruff check src/ tests/

format:
	ruff format src/ tests/

format-check:
	ruff format --check src/ tests/

type-check:
	mypy src/dazzle --ignore-missing-imports

security:
	@echo "=== Bandit Security Check ==="
	bandit -c pyproject.toml -r src/
	@echo ""
	@echo "=== Dependency Vulnerability Scan ==="
	pip-audit --strict --desc on || true

spell:
	codespell --skip '*.json,*.min.js' --ignore-words-list 'doubleclick' src/ tests/ docs/ examples/

# =============================================================================
# Testing
# =============================================================================

test:
	pytest tests/ -v

test-fast:
	pytest tests/ -x -q --ignore=tests/integration/ -m "not slow"

# Fast infrastructure-drift gate used by /ux-cycle (cycles 312 + 314).
# Runs the 4 horizontal-discipline lints + snapshot tests + card-safety invariants
# + mypy on the UI subtree. Budget <6s. Catches the drift class that accumulated
# for ~40 cycles before cycle 311 surfaced 9 red tests in the full suite, AND
# the hypothesized 4th class (type-error drift in dazzle_ui/) that cycle 313 flagged.
test-ux-preflight:
	pytest tests/unit/test_template_orphan_scan.py \
	       tests/unit/test_page_route_coverage.py \
	       tests/unit/test_canonical_pointer_lint.py \
	       tests/unit/test_template_none_safety.py \
	       tests/unit/test_daisyui_python_lint.py \
	       tests/unit/test_external_resource_lint.py \
	       tests/unit/test_ir_field_reader_parity.py \
	       tests/unit/test_dom_snapshots.py \
	       tests/unit/test_card_safety_invariants.py \
	       -q
	mypy src/dazzle_ui/ --ignore-missing-imports
	@# Non-blocking dist/ drift warning (cycle 319, silent-drift class 3).
	@# Cycle 317 gap doc flagged dist/ accumulating across ~20 cycles; this
	@# surfaces it on every preflight but doesn't fail the cycle — runs
	@# that legitimately regenerate dist/ in-flight shouldn't be blocked.
	@if [ -n "$$(git status --porcelain dist/ 2>/dev/null)" ]; then \
		echo ""; \
		echo "[WARN] dist/ has uncommitted changes (silent-drift class 3):"; \
		git status --short dist/ | sed 's/^/  /'; \
		echo "  Rebuild + commit before /ship to keep the wheel fresh."; \
	fi

# Deeper drift audit for cycles touching framework Python beyond src/dazzle_ui/
# (cycle 320). Superset of test-ux-preflight plus mypy across core + cli +
# mcp + dazzle_back. Takes ~7s — not part of the per-cron-tick preflight,
# but recommended before /ship or after any cross-subtree edit. Complements
# /ship's own mypy which only runs on push.
test-ux-deep: test-ux-preflight
	mypy src/dazzle/core src/dazzle/cli src/dazzle/mcp src/dazzle_back/ \
	     --ignore-missing-imports --exclude 'eject'

test-integration:
	pytest tests/integration/ -v

test-all:
	pytest tests/ -v --cov=src/dazzle --cov-report=term-missing

coverage:
	pytest tests/ -v --cov=src/dazzle --cov-report=html --cov-report=term-missing
	@echo ""
	@echo "Coverage report: htmlcov/index.html"

# =============================================================================
# Build
# =============================================================================

build:
	python -m build
	twine check dist/*
	@echo ""
	@echo "Build artifacts in dist/"

examples:
	@echo "=== Validating Example Projects ==="
	@for dir in examples/*/; do \
		if [ -f "$${dir}dazzle.toml" ]; then \
			echo "Validating $${dir}..."; \
			cd "$${dir}" && dazzle validate && cd - > /dev/null || exit 1; \
		fi \
	done
	@echo ""
	@echo "=== Building simple_task Example ==="
	cd examples/simple_task && dazzle build --stack micro
	@echo ""
	@echo "All examples validated!"

# =============================================================================
# CI/CD
# =============================================================================

ci: lint format-check type-check security test-all examples
	@echo ""
	@echo "=== All CI Checks Passed! ==="

pre-commit:
	pre-commit run --all-files

# =============================================================================
# Maintenance
# =============================================================================

clean:
	rm -rf build/ dist/ *.egg-info
	rm -rf .pytest_cache/ .mypy_cache/ .ruff_cache/
	rm -rf htmlcov/ .coverage coverage.xml
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo "Cleaned build artifacts"

update-deps:
	pre-commit autoupdate
	pip list --outdated
