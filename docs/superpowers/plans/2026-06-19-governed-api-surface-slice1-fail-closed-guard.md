# Governed API Surface — Slice 1: Fail-Closed Auth Guard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refuse to boot a Dazzle app with auth disabled (`enable_auth=False`) in production, unless explicitly acknowledged — closing the `enable_auth=False` → world-writable generated-CRUD hole (#1420 / spec Slice 1).

**Architecture:** A pure guard function decides, from `(enable_auth, is_production, allow_insecure_ack)`, whether the config is a fail-closed violation; it raises `InsecureAuthConfigError` at build time when production + auth-off + not-acknowledged. It is invoked at the top of `DazzleBackendApp._setup_auth`, before any auth/DB state is touched. The dev/prod signal reuses the existing `dazzle.core.environment.is_production()` (`DAZZLE_ENV`, default `development`), so local dev with auth off stays ergonomic. The escape hatch is an explicit, auditable env var.

**Tech Stack:** Python 3.12+, FastAPI runtime (`src/dazzle/http/`), `DAZZLE_ENV` environment convention, pytest.

## Global Constraints

- **Fail-closed by default; escape hatch must be explicit.** Production + `enable_auth=False` raises unless `DAZZLE_ALLOW_INSECURE_NO_AUTH` is set truthy; the acknowledged case logs a loud `warning`.
- **Dev/test stay ergonomic.** `DAZZLE_ENV` defaults to `development`; the guard is a no-op outside production. Do not break the existing suite (which runs with `DAZZLE_ENV` unset).
- **No new dependencies.**
- **Type hints required** (`mypy src/dazzle`); lint/format `ruff check src/ tests/ --fix && ruff format src/ tests/`.
- **Pre-ship:** `pytest tests/ -m "not e2e"`; `/bump patch` → commit → tag → push (clean worktree).
- **ADR-0014:** no `from __future__ import annotations` in FastAPI route files (not touched here, but `server.py` already omits it — keep it that way).

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `src/dazzle/http/runtime/auth/insecure_guard.py` | Pure guard logic + exception + env-ack reader | **Create** |
| `src/dazzle/http/runtime/server.py` | Invoke the guard at the top of `_setup_auth` | Modify (`_setup_auth`, ~line 1458) |
| `tests/unit/test_insecure_auth_guard_1420.py` | Unit (pure fn + env reader) + wiring test | **Create** |
| `CHANGELOG.md` | Security Fixed entry | Modify |

---

### Task 1: Pure fail-closed guard function

**Files:**
- Create: `src/dazzle/http/runtime/auth/insecure_guard.py`
- Test: `tests/unit/test_insecure_auth_guard_1420.py`

**Interfaces:**
- Produces:
  - `class InsecureAuthConfigError(RuntimeError)`
  - `assert_secure_auth_config(enable_auth: bool, *, production: bool, allow_insecure: bool) -> None` — raises `InsecureAuthConfigError` iff `production and not enable_auth and not allow_insecure`; logs a `warning` when `production and not enable_auth and allow_insecure`; returns `None` otherwise.
  - `insecure_ack_from_env() -> bool` — reads `DAZZLE_ALLOW_INSECURE_NO_AUTH` (truthy = `{"1","true","yes"}`, case-insensitive).
  - `INSECURE_ACK_VAR: str = "DAZZLE_ALLOW_INSECURE_NO_AUTH"`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_insecure_auth_guard_1420.py
"""#1420 Slice 1 — fail closed when auth is disabled in production."""

from __future__ import annotations

import pytest

from dazzle.http.runtime.auth.insecure_guard import (
    INSECURE_ACK_VAR,
    InsecureAuthConfigError,
    assert_secure_auth_config,
    insecure_ack_from_env,
)


class TestAssertSecureAuthConfig:
    def test_auth_enabled_is_always_ok(self) -> None:
        # Auth on → never a violation, even in production.
        assert_secure_auth_config(True, production=True, allow_insecure=False)

    def test_dev_with_auth_off_is_ok(self) -> None:
        # Not production → auth-off is the ergonomic local default.
        assert_secure_auth_config(False, production=False, allow_insecure=False)

    def test_prod_auth_off_unacknowledged_raises(self) -> None:
        with pytest.raises(InsecureAuthConfigError) as exc:
            assert_secure_auth_config(False, production=True, allow_insecure=False)
        # Message names the cause and the escape hatch.
        assert INSECURE_ACK_VAR in str(exc.value)

    def test_prod_auth_off_acknowledged_is_ok(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        with caplog.at_level(logging.WARNING):
            assert_secure_auth_config(False, production=True, allow_insecure=True)
        assert any("auth" in r.message.lower() for r in caplog.records)


class TestInsecureAckFromEnv:
    @pytest.mark.parametrize("val,expected", [("1", True), ("true", True), ("YES", True),
                                              ("0", False), ("", False), ("no", False)])
    def test_reads_env_truthy(self, monkeypatch: pytest.MonkeyPatch, val: str, expected: bool) -> None:
        monkeypatch.setenv(INSECURE_ACK_VAR, val)
        assert insecure_ack_from_env() is expected

    def test_unset_is_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(INSECURE_ACK_VAR, raising=False)
        assert insecure_ack_from_env() is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_insecure_auth_guard_1420.py -q`
Expected: FAIL — `ModuleNotFoundError: dazzle.http.runtime.auth.insecure_guard`.

- [ ] **Step 3: Implement the module**

```python
# src/dazzle/http/runtime/auth/insecure_guard.py
"""#1420 Slice 1 — fail-closed guard for auth-disabled production deploys.

`enable_auth=False` makes `_setup_auth` return no auth dependency, so generated
CRUD routes mount with no permit/scope enforcement — world-writable. That is an
ergonomic default for local dev but a critical misconfiguration in production
(a downstream hit it when an auth toggle was accidentally on in prod). This guard
refuses to boot in that case unless the operator explicitly acknowledges it.
"""

import logging
import os

logger = logging.getLogger("dazzle.server")

INSECURE_ACK_VAR = "DAZZLE_ALLOW_INSECURE_NO_AUTH"


class InsecureAuthConfigError(RuntimeError):
    """Raised at build when auth is disabled in production without acknowledgement."""


def assert_secure_auth_config(
    enable_auth: bool, *, production: bool, allow_insecure: bool
) -> None:
    """Fail closed when production runs with auth disabled and unacknowledged."""
    if enable_auth or not production:
        return
    if allow_insecure:
        logger.warning(
            "Dazzle is running in PRODUCTION with auth DISABLED (acknowledged via %s=1). "
            "Generated CRUD routes carry NO permit/scope enforcement and are "
            "unauthenticated. This is intended only for a fully public deployment.",
            INSECURE_ACK_VAR,
        )
        return
    raise InsecureAuthConfigError(
        "Refusing to start: auth is disabled (enable_auth=False) but DAZZLE_ENV=production. "
        "Generated CRUD routes would be world-writable (no permit/scope enforcement). "
        "Enable auth ([auth] enabled=true in dazzle.toml), or set "
        f"{INSECURE_ACK_VAR}=1 to explicitly acknowledge an unauthenticated production deploy."
    )


def insecure_ack_from_env() -> bool:
    """True when DAZZLE_ALLOW_INSECURE_NO_AUTH is set truthy (1/true/yes)."""
    return os.environ.get(INSECURE_ACK_VAR, "").strip().lower() in ("1", "true", "yes")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_insecure_auth_guard_1420.py -q`
Expected: PASS (all tests).

- [ ] **Step 5: Lint + type**

Run: `uv run ruff check src/dazzle/http/runtime/auth/insecure_guard.py tests/unit/test_insecure_auth_guard_1420.py && uv run mypy src/dazzle/http/runtime/auth/insecure_guard.py`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/http/runtime/auth/insecure_guard.py tests/unit/test_insecure_auth_guard_1420.py
git commit -m "feat(auth): fail-closed guard for auth-disabled production (#1420 slice 1)"
```

---

### Task 2: Wire the guard into the boot path

**Files:**
- Modify: `src/dazzle/http/runtime/server.py` (`_setup_auth`, the method starting ~line 1458)
- Test: `tests/unit/test_insecure_auth_guard_1420.py` (append wiring test)

**Interfaces:**
- Consumes: `assert_secure_auth_config`, `insecure_ack_from_env` (Task 1); `dazzle.core.environment.is_production`.
- Produces: `_setup_auth` raises `InsecureAuthConfigError` at build when production + auth-off + unacknowledged, before any auth/DB state is touched.

- [ ] **Step 1: Write the failing wiring test**

```python
# append to tests/unit/test_insecure_auth_guard_1420.py
class TestSetupAuthWiring:
    """The guard runs at the top of _setup_auth, before its enable_auth early-return,
    so it needs no database."""

    def _app(self, *, enable_auth: bool):
        from dazzle.http.runtime.server import DazzleBackendApp
        from tests.unit.test_build_server_config import _appspec  # minimal AppSpec helper

        return DazzleBackendApp(_appspec(), enable_auth=enable_auth)

    def test_prod_auth_off_build_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DAZZLE_ENV", "production")
        monkeypatch.delenv(INSECURE_ACK_VAR, raising=False)
        app = self._app(enable_auth=False)
        with pytest.raises(InsecureAuthConfigError):
            app._setup_auth()

    def test_prod_auth_off_acknowledged_does_not_raise(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DAZZLE_ENV", "production")
        monkeypatch.setenv(INSECURE_ACK_VAR, "1")
        app = self._app(enable_auth=False)
        # Returns (None, None) — the guard allows it; no DB touched on this path.
        assert app._setup_auth() == (None, None)

    def test_dev_auth_off_does_not_raise(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DAZZLE_ENV", "development")
        app = self._app(enable_auth=False)
        assert app._setup_auth() == (None, None)
```

> Implementer note: confirm `_appspec` is importable from `tests/unit/test_build_server_config.py`
> (it is a module-level helper there). If `DazzleBackendApp(_appspec(), enable_auth=False)`
> needs more constructor args in your tree, mirror the construction used in
> `test_build_server_config.py` / `test_social_auth_wiring.py`.

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_insecure_auth_guard_1420.py::TestSetupAuthWiring -q`
Expected: FAIL — `test_prod_auth_off_build_raises` does not raise (guard not wired yet).

- [ ] **Step 3: Wire the guard at the top of `_setup_auth`**

In `src/dazzle/http/runtime/server.py`, `_setup_auth` currently begins:

```python
    def _setup_auth(self) -> tuple[Any, Any]:
        """Initialize auth store, middleware, and social auth.

        Returns (auth_dep, optional_auth_dep) for route generation.
        """
        auth_dep = None
        optional_auth_dep = None
        if not self._enable_auth:
            return auth_dep, optional_auth_dep
```

Insert the guard as the first statements of the method body (before `auth_dep = None`):

```python
        # #1420 Slice 1 — fail closed: auth disabled in production is a critical
        # misconfiguration (generated CRUD would be world-writable). Runs before
        # any auth/DB state is touched.
        from dazzle.http.runtime.auth.insecure_guard import (
            assert_secure_auth_config,
            insecure_ack_from_env,
        )
        from dazzle.core.environment import is_production

        assert_secure_auth_config(
            self._enable_auth,
            production=is_production(),
            allow_insecure=insecure_ack_from_env(),
        )

        auth_dep = None
        optional_auth_dep = None
        if not self._enable_auth:
            return auth_dep, optional_auth_dep
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/unit/test_insecure_auth_guard_1420.py -q`
Expected: PASS (all, including `TestSetupAuthWiring`).

- [ ] **Step 5: Lint + type + no-regression**

Run: `uv run ruff check src/ tests/ --fix && uv run mypy src/dazzle`
Expected: clean.
Run: `uv run pytest tests/unit/test_build_server_config.py tests/unit/test_social_auth_wiring.py -q`
Expected: PASS (guard is a no-op in the default dev env these tests run under).

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/http/runtime/server.py tests/unit/test_insecure_auth_guard_1420.py
git commit -m "feat(auth): wire fail-closed guard into _setup_auth (#1420 slice 1)"
```

---

### Task 3: CHANGELOG + ship

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Add CHANGELOG entry**

Under `## [Unreleased]`, add:

```markdown
### Security
- **Fail closed when auth is disabled in production** (#1420 slice 1). `enable_auth=False` makes the runtime attach no auth dependency, so generated CRUD routes mount with no permit/scope enforcement — world-writable. That is fine for local dev but a critical misconfiguration in production (a downstream hit it when an auth toggle was on in prod). The runtime now refuses to start when `DAZZLE_ENV=production` and auth is disabled, unless `DAZZLE_ALLOW_INSECURE_NO_AUTH=1` is set to explicitly acknowledge a public, unauthenticated deploy (logged loudly). Dev/test (default `DAZZLE_ENV`) is unchanged.

  ### Agent Guidance
  - **Don't disable auth in production to "make it work."** If a generated route 401/403s, fix the `permit:`/`scope:` rules or the session, not `enable_auth`. A production boot with auth off now hard-fails by design (#1420). The `DAZZLE_ALLOW_INSECURE_NO_AUTH` escape hatch is only for a deliberately fully-public deployment.
```

- [ ] **Step 2: Full pre-ship gates**

Run: `uv run ruff check src/ tests/ && uv run mypy src/dazzle && uv run pytest tests/ -m "not e2e" -q`
Expected: all green. (Watch for any existing test that boots with `DAZZLE_ENV=production` + auth off — it would now raise; none are expected, but the full run is the check.)

- [ ] **Step 3: Bump + ship**

Run `/bump patch`, then `/ship` (commits, tags, pushes — triggers release). Confirm clean worktree.

- [ ] **Step 4: Close-out**

Comment on #1420 noting Slice 1 (the fail-closed guard) shipped, and that Slices 2 (`api: expose:`) and 3 (declared custom routes) remain per the design spec. Append the session-lens trailer (`🔖 Claude-lens: dazzle`). (Issue stays open — Slices 2/3 are tracked there.)

---

## Self-Review

**Spec coverage (Slice 1 only):** The spec's Slice 1 = "deny mutating routes / fail closed when no auth dep, outside an explicit dev profile." This plan implements **boot-refusal** (the stronger, simpler fail-closed disposition within the spec's stated latitude — "or emits a loud boot warning + denies mutations"), keyed on `is_production()` (the dev/prod signal the spec left open), with an explicit env escape hatch. Reads are not separately allowed — an auth-off prod app is treated as a misconfiguration in whole; the escape hatch covers the genuine public-read case. ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete code; the one implementer note points at concrete existing test files to mirror, not a guess. ✓

**Type consistency:** `assert_secure_auth_config(enable_auth, *, production, allow_insecure)`, `insecure_ack_from_env()`, `INSECURE_ACK_VAR`, `InsecureAuthConfigError` are used identically across Tasks 1 and 2. ✓

## Decision recorded for the spec (Slice 1 dev-profile open item)
Resolved: the "dev profile" signal is `dazzle.core.environment.is_production()` (`DAZZLE_ENV`,
default `development`); the disposition is **boot-refusal** with the `DAZZLE_ALLOW_INSECURE_NO_AUTH`
escape hatch — not a per-request mutation-deny middleware (simpler, fails at deploy not first
request, strictly fail-closed).
```
