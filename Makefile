# DAZZLE Development Makefile
#
# Usage: make <target>
# Run 'make help' to see all available targets

.PHONY: help install dev-install lint format type-check security test test-fast test-integration test-all coverage clean build vscode-build examples ci pre-commit

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
	@echo "  test-integration Run integration tests only"
	@echo "  coverage         Run tests with coverage report"
	@echo ""
	@echo "Build:"
	@echo "  build            Build Python package (sdist + wheel)"
	@echo "  vscode-build     Build VS Code extension"
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
	codespell --skip '*.json,*.vsix,package-lock.json,*.min.js' --ignore-words-list 'doubleclick' src/ tests/ docs/ examples/

# =============================================================================
# Testing
# =============================================================================

test:
	pytest tests/ -v

test-fast:
	pytest tests/ -x -q --ignore=tests/integration/ -m "not slow"

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

vscode-build:
	cd extensions/vscode && npm ci && npm run compile && npm run package
	@echo ""
	@echo "VS Code extension: extensions/vscode/*.vsix"

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
	rm -rf extensions/vscode/out/ extensions/vscode/*.vsix
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo "Cleaned build artifacts"

update-deps:
	pre-commit autoupdate
	pip list --outdated
