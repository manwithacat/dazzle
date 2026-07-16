# Local CI concordance

A green laptop is not automatically a green GitHub Actions badge. This page
defines **tiers** so agents and humans know what "passed" means, and points at
the single runner that keeps command strings aligned with CI.

| Artifact | Role |
|----------|------|
| [`scripts/ci_local.sh`](https://github.com/manwithacat/dazzle/blob/main/scripts/ci_local.sh) | Source of truth for local gate *commands* and extras lists |
| [`Makefile`](https://github.com/manwithacat/dazzle/blob/main/Makefile) targets `ci-fast` / `ci-core` / `sync-ci-type` / `sync-ci-test` / `type-check-ci` | Thin wrappers |
| [`.github/workflows/ci.yml`](https://github.com/manwithacat/dazzle/blob/main/.github/workflows/ci.yml) | Server-side jobs |
| [`.github/actions/setup-dazzle`](https://github.com/manwithacat/dazzle/blob/main/.github/actions/setup-dazzle) | Frozen `uv sync` + extras |

When you change a CI command or extras list, update `scripts/ci_local.sh` in the
**same** change (constants at the top of the script cite the CI jobs).

---

## Tiers

### Preflight — `make preflight-surface` (`scripts/ci_local.sh preflight-surface`)

**Mandatory first step of every ship path** (also invoked automatically by
Tier 0 and Tier 1). Exists to kill the pattern where feature unit tests pass
locally while GitHub stays red on unpaid structural/artifact debt.

| What it runs | CI failure class it blocks |
|--------------|----------------------------|
| `scripts/preflight_surface.py` → curated gate modules | See table below |

| Module | Debt class | Typical fix |
|--------|------------|-------------|
| `test_api_surface_drift` | MCP/IR/public API baselines | `dazzle inspect api <lens> --write` |
| `test_docs_drift` | AGENTS MCP table, cli.md groups, generated refs | edit docs + `dazzle docs generate` |
| `test_deferred_imports_ratchet_1438` | function-level `dazzle.*` import growth | hoist import or raise baseline with justification |
| `test_import_contracts` | layer edges (`core ↛ page/api_kb`) | relocate code |
| `test_no_bare_except_pass` | silent `except Exception` | log with `exc_info=True` or narrow type |
| `test_ux_catalogue` | stale catalogue CSS | `python scripts/gen_ux_catalogue.py` |
| `test_complexity_ratchet` | cyclomatic/MI regressions | refactor or `dazzle fitness code --write-baseline` |
| `test_hm_package_suite_gate` | HM gallery stale-dist | `cd packages/hatchi-maxchi && python site/build_site.py` |

**Non-zero exit → do not ship.** The script prints a remediation playbook.

Standalone use mid-change:

```bash
make preflight-surface
```

### Tier 0 — `make ci-fast` (`scripts/ci_local.sh tier0`)

**Default for `/ship`.** Budget ~2–3 minutes, no Postgres. **Always runs
preflight-surface first.**

| Step | Mirrors |
|------|---------|
| `preflight-surface` | Structural debt cluster (see above) |
| `ruff check --fix` + `ruff format` | CI `lint` (local mutates; CI is check-only) |
| `mypy src/dazzle` | CI `type-check` **command** (extras may still differ) |
| `pytest tests/unit -m gate` | Full gate suite (superset of preflight modules) |
| `mkdocs build --strict` | `docs.yml` build |

Does **not** include full unit matrix, security hard-fail, multi-version Python,
or service-backed jobs.

### Tier 1 — `make ci-core` (`scripts/ci_local.sh tier1`)

**Required before release tags** (`/ship minor`, `/ship major`, or any bump of
`pyproject.toml` version). Closer to GitHub core jobs. **Always runs
preflight-surface first** (after sync, before the long unit matrix).

| Step | Mirrors |
|------|---------|
| `uv sync --frozen` with CI python-tests then type-check extras, **Python 3.12** | `setup-dazzle` |
| `preflight-surface` | Structural debt cluster |
| `python scripts/build_dist.py` | CI builds gitignored `dist/` before tests |
| `ruff check` + `ruff format --check` | `lint` |
| `mypy src/dazzle` after type extras | `type-check` |
| CSS clip + raw-ramp + `dazzle coverage --fail-on-uncovered` | `lint` extras |
| bandit (medium, all of `src/`) + pip-audit hard-fail | `lint` + `security-tests` |
| JWT fuzz + shapes RBAC matrix | `security-tests` unique gates |
| `pytest -n auto --dist loadgroup -m "not e2e"` | `python-tests` (single local version) |
| `mkdocs build --strict` | `docs.yml` |

Environment knobs:

- `CI_LOCAL_SKIP_SYNC=1` — skip frozen sync (uses current `.venv`; concordance not guaranteed)
- `CI_LOCAL_COVERAGE=1` — enable coverage on the unit step
- `CI_LOCAL_PYTHON=3.12` — override sync Python (default 3.12)

### Tier 2 — still GitHub-only (not in `ci_local.sh` yet)

These routinely fail after a Tier-0-only ship:

- **Python matrix** 3.12 / 3.13 / 3.14
- **postgres-tests** (service container)
- **e2e-runtime**, **e2e-smoke** (example validate loop is partially make-able)
- **interaction-walks** / viewport (Playwright + Postgres)
- **guide-walks** (12-app matrix)
- **contracts-gate** (`ux verify --contracts --managed` on support_tickets)
- **homebrew-validation** (macOS)

See `ci.yml` job names for the authoritative list.

---

## Extras cheatsheet (must match CI)

Copied into `scripts/ci_local.sh` — do not invent a third list.

| Job | Extras |
|-----|--------|
| type-check | `dev,llm,mcp,mobile,postgres,pitch,i18n,viewport,perf,lsp` |
| python-tests | `dev,llm,mcp,mobile,postgres,perf,saml,lsp,test-full` |
| lint | `dev,llm,mcp,postgres,perf` |
| security-tests | `dev,mobile,postgres,perf` |
| setup-dazzle default | `dev,llm,mcp,mobile,postgres,perf,saml,lsp` |

Install type-check env only:

```bash
make sync-ci-type
make type-check-ci
```

---

## Agent skills

| Skill | Default tier |
|-------|----------------|
| `/ship` | Tier 0 (`make ci-fast`); **Tier 1** for minor/major or version bumps |
| `/check` | Opportunistic per changed files; prefer full unit when Python changed; `make ci-core` when asked for release-grade |

---

## Why concordance breaks

1. **Extras** — thin local venv → mypy lies (`warn_return_any` / unused ignores).
2. **Tier 0 is intentional subset** — gate suite ≠ full `python-tests`.
3. **No Postgres / Playwright** locally unless you add services.
4. **OS** — macOS vs `ubuntu-latest`.
5. **Three legacy "CI" paths** — prefer `ci-fast` / `ci-core` over old `make ci`
   (soft pip-audit, no frozen extras).
6. **Unpaid surface debt** — MCP/CLI/IR changes without regenerating baselines
   and docs. This is what `preflight-surface` exists to catch **before** push.
   Stacking feature commits on a red tip multiplies the same failures across
   every matrix cell.

---

## Quick recipes

```bash
# Mid-change: only structural debt (fast fail)
make preflight-surface

# Everyday push confidence (includes preflight)
make ci-fast

# Before tagging a release
make ci-core

# Only re-type after deps change
make type-check-ci

# Skip sync when debugging a single test (you accept drift)
CI_LOCAL_SKIP_SYNC=1 bash scripts/ci_local.sh tier1
```
