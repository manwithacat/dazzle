#!/usr/bin/env bash
# Local CI concordance runner — mirrors the blocking *core* of
# `.github/workflows/ci.yml` so "green here" predicts GitHub green.
#
# Tiers (see docs/contributing/local-ci-concordance.md):
#   tier0 / ship-fast  — ~2–3 min, no DB; what `/ship` runs by default
#   tier1 / ci-core    — lint + type + full non-e2e tests + security + docs
#                        mirrors python-tests + lint + type-check + security-tests + docs
#
# Usage:
#   bash scripts/ci_local.sh tier0
#   bash scripts/ci_local.sh tier1
#   bash scripts/ci_local.sh sync-type    # uv sync CI type-check extras (3.12)
#   bash scripts/ci_local.sh sync-test    # uv sync CI python-tests extras (3.12)
#   bash scripts/ci_local.sh type-check   # mypy with CI-equivalent env when possible
#
# Extras lists are copied from ci.yml / setup-dazzle — change those sources first,
# then update the constants below (keep the three in lockstep).

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Match Makefile / [tool.uv]: uv-managed Python only. Prefer a real uv binary
# over pyenv shims (repo `.python-version` is for uv + Heroku, not pyenv).
export UV_MANAGED_PYTHON="${UV_MANAGED_PYTHON:-1}"
export PYENV_VERSION="${PYENV_VERSION:-system}"
if [ -x "${HOME}/.local/bin/uv" ]; then
  UV="${UV:-${HOME}/.local/bin/uv}"
else
  UV="${UV:-uv}"
fi

# ── CI extras (from .github/workflows/ci.yml + setup-dazzle/action.yml) ──────
# type-check job:
EXTRAS_TYPE="dev,llm,mcp,mobile,postgres,pitch,i18n,viewport,perf,lsp"
# python-tests job:
EXTRAS_TEST="dev,llm,mcp,mobile,postgres,perf,saml,lsp,test-full"
# lint job (subset; tier1 uses TYPE for one sync rather than three):
# EXTRAS_LINT="dev,llm,mcp,postgres,perf"
# security-tests job:
# EXTRAS_SECURITY="dev,mobile,postgres,perf"

CI_PYTHON="${CI_LOCAL_PYTHON:-3.12}"

_log() { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }
_ok()  { printf '\033[1;32mOK\033[0m %s\n' "$*"; }
_die() { printf '\033[1;31mFAIL\033[0m %s\n' "$*" >&2; exit 1; }

_uv_extra_flags() {
  local extras="$1" flags="" e
  IFS=',' read -ra _parts <<< "$extras"
  for e in "${_parts[@]}"; do
    [ -n "$e" ] && flags="$flags --extra $e"
  done
  # shellcheck disable=SC2086
  echo $flags
}

_run_uv() {
  # Prefer repo .venv tools when present; fall back to `uv run`.
  if [ -x "$ROOT/.venv/bin/python" ]; then
    # shellcheck disable=SC2086
    PATH="$ROOT/.venv/bin:$PATH" "$@"
  else
    "$UV" run "$@"
  fi
}

cmd_sync_type() {
  _log "uv sync --python ${CI_PYTHON} --frozen (type-check extras)"
  # shellcheck disable=SC2046
  "$UV" sync --python "$CI_PYTHON" --frozen $(_uv_extra_flags "$EXTRAS_TYPE")
  _ok "type-check extras synced (Python ${CI_PYTHON})"
}

cmd_sync_test() {
  _log "uv sync --python ${CI_PYTHON} --frozen (python-tests extras)"
  # shellcheck disable=SC2046
  "$UV" sync --python "$CI_PYTHON" --frozen $(_uv_extra_flags "$EXTRAS_TEST")
  _ok "python-tests extras synced (Python ${CI_PYTHON})"
}

cmd_type_check() {
  # Prefer CI-matching mypy: frozen 3.12 + type extras. If the operator has
  # already synced, this is fast; if not, we still run mypy on whatever is
  # active but warn (matches the historical ship footgun).
  local pyver
  pyver="$(_run_uv python -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo "?")"
  if [ "$pyver" != "$CI_PYTHON" ] && [ "$pyver" != "3.12" ]; then
    printf 'WARN: active Python is %s; CI type-check is %s. Run: make sync-ci-type\n' "$pyver" "$CI_PYTHON" >&2
  fi
  _log "mypy src/dazzle  (CI command; extras should match type-check job)"
  _run_uv mypy src/dazzle
  _ok "mypy clean"
}

cmd_build_dist() {
  _log "python scripts/build_dist.py  (CI builds gitignored dist/ before tests)"
  _run_uv python scripts/build_dist.py
  _ok "asset bundles built"
}

cmd_ruff_fix() {
  _log "ruff check --fix + format  (local mutates; CI is check-only)"
  _run_uv ruff check src/ tests/ --fix
  _run_uv ruff format src/ tests/
  _ok "ruff fix + format"
}

cmd_ruff_check() {
  _log "ruff check + format --check  (CI lint job)"
  _run_uv ruff check src/ tests/
  _run_uv ruff format --check src/ tests/
  _ok "ruff check + format --check"
}

cmd_gates() {
  _log "pytest tests/unit -m gate  (ship-fast structural gates, no DB)"
  _run_uv pytest tests/unit -m gate -q --tb=line
  _ok "gate suite"
}

cmd_unit_full() {
  _log "pytest -n auto --dist loadgroup -m 'not e2e'  (CI python-tests shape)"
  # COVERAGE optional — CI only measures on 3.12; local default is no cov for speed.
  if [ "${CI_LOCAL_COVERAGE:-0}" = "1" ]; then
    _run_uv env COVERAGE_CORE=sysmon pytest -n auto --dist loadgroup \
      --cov=src/dazzle --cov-report=term-missing -m "not e2e"
  else
    _run_uv pytest -n auto --dist loadgroup -m "not e2e" -q --tb=line
  fi
  _ok "full non-e2e suite"
}

cmd_security() {
  _log "bandit (CI: medium severity on src/) + pip-audit hard-fail"
  # setup-dazzle venv has no pip; match CI (`uv pip install bandit[toml]`).
  "$UV" pip install 'bandit[toml]' pip-audit
  # lint job scans all of src/; security-tests also scans http/runtime.
  # Full-tree medium is the stricter of the two local mirrors.
  _run_uv bandit -c pyproject.toml -r src/ --severity-level medium
  # Freeze snapshot (same rationale as ci.yml — editable dazzle-dsl breaks pip-audit).
  "$UV" pip freeze --exclude-editable > /tmp/dazzle-audit-reqs.txt
  # MAL-2026-4750: same ignore as CI (fastapi/fastar false positive).
  _run_uv pip-audit --strict --desc --no-deps --disable-pip \
    --ignore-vuln MAL-2026-4750 \
    -r /tmp/dazzle-audit-reqs.txt
  _ok "bandit + pip-audit"
}

cmd_lint_extras() {
  _log "CSS clip + raw-ramp + coverage --fail-on-uncovered  (CI lint job)"
  _run_uv python scripts/css_clip_check.py
  _run_uv python scripts/css_raw_ramp_check.py
  _run_uv python -m dazzle coverage --fail-on-uncovered
  _ok "lint extras"
}

cmd_security_cli() {
  _log "JWT fuzz + shapes RBAC matrix  (CI security-tests unique gates)"
  _run_uv pytest tests/unit/test_jwt_fuzzing.py -q --tb=line
  (
    cd fixtures/shapes_validation
    _run_uv python -m dazzle rbac matrix --format json > /tmp/rbac-matrix.json
    python3 -c "
import json, sys
matrix = json.load(open('/tmp/rbac-matrix.json'))
cells = matrix['cells']
unprotected = [c for c in cells if c['decision'] == 'PERMIT_UNPROTECTED']
if unprotected:
    for c in unprotected[:5]:
        print(f\"FAIL: {c['role']} / {c['entity']} / {c['operation']} is UNPROTECTED\")
    sys.exit(1)
print(f\"RBAC matrix OK: {len(cells)} cells, 0 unprotected\")
"
  )
  _ok "security CLI gates"
}

cmd_docs() {
  _log "mkdocs build --strict  (docs.yml; /ship also runs this)"
  if [ -f requirements-docs.txt ]; then
    "$UV" run --with-requirements requirements-docs.txt mkdocs build --strict
  else
    _run_uv mkdocs build --strict
  fi
  _ok "docs build"
}

cmd_tier0() {
  _log "TIER 0 / ship-fast  (ruff fix, mypy, gate suite, docs)"
  cmd_ruff_fix
  cmd_type_check
  cmd_gates
  cmd_docs
  _ok "tier0 complete — not full CI; run 'make ci-core' before a release tag"
}

cmd_tier1() {
  _log "TIER 1 / ci-core  (mirrors CI lint + type-check + python-tests + security + docs)"
  # Prefer one frozen 3.12 test sync (superset of lint/security needs for collection).
  if [ "${CI_LOCAL_SKIP_SYNC:-0}" != "1" ]; then
    cmd_sync_test
    # Type extras are a strict superset for mypy (pitch/i18n/viewport).
    cmd_sync_type
  else
    printf 'WARN: CI_LOCAL_SKIP_SYNC=1 — using current .venv (concordance not guaranteed)\n' >&2
  fi
  cmd_build_dist
  cmd_ruff_check
  cmd_type_check
  cmd_lint_extras
  cmd_security
  cmd_security_cli
  cmd_unit_full
  cmd_docs
  _ok "tier1 / ci-core complete — still missing Postgres/e2e/walks (Tier 2; see docs)"
}

usage() {
  cat <<'EOF'
Usage: bash scripts/ci_local.sh <command>

Commands:
  tier0 | ship-fast     Fast pre-ship (ruff fix, mypy, -m gate, mkdocs)
  tier1 | ci-core       CI core mirror (sync, build_dist, lint, type, unit, security, docs)
  sync-type             uv sync --frozen with CI type-check extras (Python 3.12)
  sync-test             uv sync --frozen with CI python-tests extras (Python 3.12)
  type-check            mypy src/dazzle only
  help

Environment:
  CI_LOCAL_PYTHON=3.12       Python for frozen sync (default 3.12)
  CI_LOCAL_SKIP_SYNC=1       tier1 skips uv sync (use current venv)
  CI_LOCAL_COVERAGE=1        tier1 unit step enables coverage

See docs/contributing/local-ci-concordance.md
EOF
}

main() {
  local cmd="${1:-help}"
  case "$cmd" in
    tier0|ship-fast) cmd_tier0 ;;
    tier1|ci-core)   cmd_tier1 ;;
    sync-type|sync-ci-type) cmd_sync_type ;;
    sync-test|sync-ci-test) cmd_sync_test ;;
    type-check|type-check-ci) cmd_type_check ;;
    help|-h|--help)  usage ;;
    *) _die "unknown command: $cmd (try: help)" ;;
  esac
}

main "$@"
