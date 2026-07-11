# DAZZLE Development Makefile
#
# Usage: make <target>
# Run 'make help' to see all available targets

.PHONY: help install dev-install lint format type-check type-check-ci security test test-fast test-integration test-all coverage clean build examples ci ci-fast ci-core sync-ci-type sync-ci-test pre-commit

# Default target
help:
	@echo "DAZZLE Development Commands"
	@echo "============================"
	@echo ""
	@echo "Setup:"
	@echo "  install          Install DAZZLE in development mode"
	@echo "  dev-install      Install with all dev dependencies + pre-commit hooks"
	@echo "  sync-ci-type     uv sync --frozen with CI type-check extras (Python 3.12)"
	@echo "  sync-ci-test     uv sync --frozen with CI python-tests extras (Python 3.12)"
	@echo ""
	@echo "Code Quality:"
	@echo "  lint             Run ruff linter"
	@echo "  format           Run ruff formatter"
	@echo "  type-check       Run mypy type checker (current venv)"
	@echo "  type-check-ci    mypy after CI-matching extras (prefer before release)"
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
	@echo "CI/CD (local concordance — see docs/contributing/local-ci-concordance.md):"
	@echo "  ci-fast          Tier 0: ruff fix + mypy + gate suite + mkdocs (~2–3 min)"
	@echo "  ci-core          Tier 1: CI lint/type/unit/security/docs mirror (no Postgres/e2e)"
	@echo "  ci               Legacy umbrella (lint + format-check + type-check + security + test-all + examples)"
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
	uv run ruff check src/ tests/

format:
	uv run ruff format src/ tests/

format-check:
	uv run ruff format --check src/ tests/

type-check:
	uv run mypy src/dazzle

# CI type-check job uses Python 3.12 + maximal extras (pitch/i18n/viewport/…).
# A thin local venv lies — missing stubs flip warn_return_any / unused-ignores.
type-check-ci: sync-ci-type
	bash scripts/ci_local.sh type-check

sync-ci-type:
	bash scripts/ci_local.sh sync-type

sync-ci-test:
	bash scripts/ci_local.sh sync-test

security:
	@echo "=== Bandit Security Check ==="
	bandit -c pyproject.toml -r src/ --severity-level medium
	@echo ""
	@echo "=== Dependency Vulnerability Scan (soft — use make ci-core for hard-fail) ==="
	pip-audit --strict --desc on || true

spell:
	codespell --skip '*.json,*.min.js' --ignore-words-list 'doubleclick' src/ tests/ docs/ examples/

# =============================================================================
# Testing
# =============================================================================

test:
	uv run pytest tests/ -v

test-fast:
	uv run pytest tests/ -x -q --ignore=tests/integration/ -m "not slow"

# Fast infrastructure-drift gate used by /ux-cycle (cycles 312 + 314).
# Runs the 4 horizontal-discipline lints + snapshot tests + card-safety invariants
# + mypy on the UI subtree. Budget <6s. Catches the drift class that accumulated
# for ~40 cycles before cycle 311 surfaced 9 red tests in the full suite, AND
# the hypothesized 4th class (type-error drift in dazzle_page/) that cycle 313 flagged.
test-ux-preflight:
	@# 5 of 9 prior preflight tests removed during the Jinja retirement
	@# (Phase 4 deletion sweep, v0.67.X): test_template_orphan_scan,
	@# test_page_route_coverage, test_daisyui_python_lint, test_dom_snapshots,
	@# test_card_safety_invariants. Their drift classes are covered by
	@# the typed-runtime gate (test_typed_runtime_no_jinja) which is now
	@# the structural anchor for UI changes. The 4 remaining tests still
	@# guard meaningful invariants (canonical-pointer linkage, template
	@# None-safety, external-resource SRI, IR↔field-reader parity).
	uv run pytest tests/unit/test_canonical_pointer_lint.py \
	       tests/unit/test_template_none_safety.py \
	       tests/unit/test_external_resource_lint.py \
	       tests/unit/test_ir_field_reader_parity.py \
	       tests/unit/test_typed_runtime_no_jinja.py \
	       -q
	@# src/dazzle_page/ merged into src/dazzle/page/ in v0.67.98 (#1055).
	uv run mypy src/dazzle/page/ --ignore-missing-imports
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

# Deeper drift audit for cycles touching framework Python beyond src/dazzle/page/
# (cycle 320). Superset of test-ux-preflight plus mypy across core + cli +
# mcp + dazzle/http. Takes ~7s — not part of the per-cron-tick preflight,
# but recommended before /ship or after any cross-subtree edit. Complements
# /ship's own mypy which only runs on push.
#
# Path note: src/dazzle_http/ → src/dazzle/http/ at v0.67.98 (#1055).
test-ux-deep: test-ux-preflight
	uv run mypy src/dazzle/core src/dazzle/cli src/dazzle/mcp src/dazzle/http/ \
	     --ignore-missing-imports --exclude 'eject'

# On-demand half-finished-internals audit. Not part of preflight — regenerates
# dev_docs/audit-internals.md with two high-noise sections (IR field orphans,
# module import-graph orphans) for loop triage. Real findings from this shape:
# #834 (hot_reload.py). Expected FP rate is high (cycle 328 measured ~83% for
# module orphans); report format supports human skimming, not blocking CI.
audit-internals:
	uv run python tests/unit/audit_internals.py

test-integration:
	uv run pytest tests/integration/ -v

test-all:
	uv run pytest tests/ -v --cov=src/dazzle --cov-report=term-missing

coverage:
	uv run pytest tests/ -v --cov=src/dazzle --cov-report=html --cov-report=term-missing
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

# Tier 0 — what `/ship` runs by default (fast; not full GitHub CI).
ci-fast:
	bash scripts/ci_local.sh tier0

# Tier 1 — mirrors CI lint + type-check + python-tests + security-tests + docs.
# Still omits Postgres services, Playwright walks, guide/contracts matrices.
# Run before tagged releases (especially minor/major).
ci-core:
	bash scripts/ci_local.sh tier1

# Legacy umbrella — broader/sloppier than ci-core (soft pip-audit, no frozen extras).
# Prefer ci-core for concordance; keep for older muscle memory.
ci: lint format-check type-check security test-all examples
	@echo ""
	@echo "=== Legacy make ci finished. Prefer 'make ci-core' for GitHub concordance. ==="

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
