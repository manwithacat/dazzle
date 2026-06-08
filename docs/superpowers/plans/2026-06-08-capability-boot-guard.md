# Capability Boot Guard (#1344) Implementation Plan

> **For agentic workers:** Execute Hybrid (inline). Steps use checkbox (`- [ ]`).

**Goal:** A boot-time `ERROR` log when `connections` rows exist for a protocol whose
`auth.enterprise.{type}` capability isn't active (routes silently won't mount otherwise).

**Architecture:** Pure `capability_boot_warnings(type_counts, is_active)` + a DB read
`AuthStore.connection_type_counts()` + a lifespan **startup** hook registered from the auth
subsystem (pool open by then). Loud-log only; never aborts boot.

**Spec:** `docs/superpowers/specs/2026-06-08-capability-boot-guard-design.md`

---

## File Structure

- Create `src/dazzle/back/runtime/auth/capability_guard.py` — pure mapping + warnings.
- Modify `src/dazzle/back/runtime/auth/store.py` — `connection_type_counts()`.
- Modify `src/dazzle/back/runtime/subsystems/auth.py` — register the startup hook.
- Create `tests/unit/test_capability_guard.py`; modify `tests/integration/test_connections_pg.py`.

---

### Task 1: Pure mapping + warnings

**Files:** Create `src/dazzle/back/runtime/auth/capability_guard.py`

- [ ] **Step 1: Write the failing test** `tests/unit/test_capability_guard.py`:

```python
"""Pure capability-boot-guard logic (#1344) — no DB, no logging."""

from __future__ import annotations

from dazzle.back.runtime.auth.capability_guard import capability_boot_warnings


def _active(*ids):
    s = set(ids)
    return lambda cid: cid in s


def test_no_warning_when_capability_active() -> None:
    w = capability_boot_warnings({"oidc": 3}, _active("auth.enterprise.oidc"))
    assert w == []


def test_warns_for_inactive_type_with_connections() -> None:
    w = capability_boot_warnings({"saml": 2}, _active())  # nothing active
    assert len(w) == 1
    assert "2 saml connection(s)" in w[0]
    assert "auth.enterprise.saml" in w[0]
    assert "dazzle capability enable auth.enterprise.saml" in w[0]


def test_zero_count_type_does_not_warn() -> None:
    assert capability_boot_warnings({"scim": 0}, _active()) == []


def test_unknown_type_is_ignored() -> None:
    assert capability_boot_warnings({"ldap": 5}, _active()) == []


def test_capabilities_none_path_warns_for_every_present_type() -> None:
    # When no manifest is resolved the hook passes is_active=lambda: False.
    w = capability_boot_warnings({"oidc": 1, "saml": 1, "scim": 1}, lambda _cid: False)
    assert len(w) == 3


def test_mixed_active_and_inactive() -> None:
    w = capability_boot_warnings(
        {"oidc": 1, "saml": 1}, _active("auth.enterprise.oidc")
    )
    assert len(w) == 1 and "saml" in w[0]
```

- [ ] **Step 2: Run** `pytest tests/unit/test_capability_guard.py -q` → FAIL (no module).

- [ ] **Step 3: Implement** `src/dazzle/back/runtime/auth/capability_guard.py`:

```python
"""Capability boot guard (#1344): warn when connection rows exist for a protocol whose
enterprise capability isn't active (its routes silently don't mount). Pure logic — the DB
read and logging live in the store / the lifespan hook respectively, so the mapping +
mismatch detection is unit-tested directly."""

from __future__ import annotations

from collections.abc import Callable, Mapping

# connection.type -> the capability that must be active for its routes to mount.
_TYPE_TO_CAPABILITY: dict[str, str] = {
    "oidc": "auth.enterprise.oidc",
    "saml": "auth.enterprise.saml",
    "scim": "auth.enterprise.scim",
}


def capability_boot_warnings(
    type_counts: Mapping[str, int],
    is_active: Callable[[str], bool],
) -> list[str]:
    """One actionable warning per connection type whose enterprise capability isn't active.

    A mismatch is SAFE (feature-off, no security hole) but quiet; the warning is the loud,
    actionable signal. Types not in the enterprise map (none today) are ignored.
    """
    warnings: list[str] = []
    for ctype, capability in _TYPE_TO_CAPABILITY.items():
        n = type_counts.get(ctype, 0)
        if n > 0 and not is_active(capability):
            warnings.append(
                f"{n} {ctype} connection(s) exist but {capability} is not enabled — "
                f"their routes will not mount (SSO/SCIM will 404). Add {capability} to "
                f"[capabilities] in dazzle.toml or run: dazzle capability enable {capability}"
            )
    return warnings
```

- [ ] **Step 4: Run** `pytest tests/unit/test_capability_guard.py -q` → all PASS.

---

### Task 2: `AuthStore.connection_type_counts()`

**Files:** Modify `src/dazzle/back/runtime/auth/store.py`

- [ ] **Step 1: Write the failing PG test** (append to `tests/integration/test_connections_pg.py`):

```python
def test_connection_type_counts(store_url: str) -> None:
    store = _store(store_url)
    store.create_connection(tenant_id="o", type="oidc", config={}, secrets={}, domains=[])
    store.create_connection(tenant_id="o", type="oidc", config={}, secrets={}, domains=[])
    store.create_connection(tenant_id="o", type="saml", config={}, secrets={}, domains=[])
    assert store.connection_type_counts() == {"oidc": 2, "saml": 1}


def test_connection_type_counts_missing_table_returns_empty(store_url: str) -> None:
    # A store whose schema was never initialised must not break boot — return {}.
    from dazzle.back.runtime.auth.store import AuthStore

    bare = AuthStore(database_url=store_url)  # no _init_db()
    assert bare.connection_type_counts() == {}
```

- [ ] **Step 2: Run** `DATABASE_URL=…/dazzle_dev pytest tests/integration/test_connections_pg.py::test_connection_type_counts -q` → FAIL.

- [ ] **Step 3: Implement** `connection_type_counts` on `AuthStore` (near the other connection
reads, e.g. after `get_connections_for_tenant`):

```python
    def connection_type_counts(self) -> dict[str, int]:
        """``{connection.type: count}`` for the capability boot guard (#1344). Defensive:
        returns ``{}`` on ANY failure (missing ``connections`` table on a fresh/unmigrated
        DB, query error) — a boot guard must never break boot."""
        try:
            rows = self._execute("SELECT type, COUNT(*) AS n FROM connections GROUP BY type")
        except Exception:  # noqa: BLE001 — advisory guard; a read failure must not abort boot
            return {}
        return {str(r["type"]): int(r["n"]) for r in rows}
```

- [ ] **Step 4: Run** both new PG tests → PASS. (Run the whole `test_connections_pg.py` to
confirm no regression.)

---

### Task 3: Register the lifespan startup hook

**Files:** Modify `src/dazzle/back/runtime/subsystems/auth.py`

- [ ] **Step 1: Register the hook** — in the auth subsystem's `startup`, immediately after
`self._mount_enterprise_capabilities(ctx)` (~line 271), add a call
`self._register_capability_boot_guard(ctx)` and define the method (mirrors
`subsystems/seed.py`'s `register_lifespan_hook(ctx.app, startup=...)` closure pattern):

```python
    def _register_capability_boot_guard(self, ctx: SubsystemContext) -> None:
        """Loud-log at startup if connection rows exist for a protocol whose enterprise
        capability isn't active (#1344). A startup hook (not build-time) because the DB pool
        only opens at lifespan startup; loud-log only (the lifespan registry swallows
        exceptions and the mismatch is safe — aborting would crash-loop a safe deploy)."""
        from dazzle.back.runtime.auth.capability_guard import capability_boot_warnings
        from dazzle.back.runtime.lifespan_hooks import register_lifespan_hook

        store = ctx.auth_store
        caps = ctx.capabilities

        def _startup() -> None:
            is_active = caps.is_active if caps is not None else (lambda _cid: False)
            for msg in capability_boot_warnings(store.connection_type_counts(), is_active):
                logger.error("Capability boot guard: %s", msg)

        register_lifespan_hook(ctx.app, startup=_startup)
```
Confirm the module-level `logger` exists in `auth.py` (it does — used at line 293); reuse it.

- [ ] **Step 2: Verify wiring** — confirm `ctx.auth_store` is non-None on this path (the
subsystem early-returns when `not ctx.auth_store`, ~line 25, so by the mount point it's set).
The hook closes over `store`/`caps` captured at build time; both are stable for the app's life.

- [ ] **Step 3: Run** the auth subsystem / boot smoke tests if any exist
(`pytest tests/ -k "subsystem and auth" -q`); otherwise rely on Task 1/2 + the full suite.

---

### Task 4: Docs + ship

- [ ] **Step 1: CHANGELOG** `### Added`: "Capability boot guard (#1344) — a loud startup
ERROR when `connections` rows exist for a protocol whose `auth.enterprise.{oidc,saml,scim}`
capability isn't active (routes would silently 404). Loud-log only; never aborts boot."
- [ ] **Step 2:** `/bump patch`.
- [ ] **Step 3: Gates** — `ruff`, `mypy src/dazzle`, drift/policy, `pytest tests/ -m "not
e2e"`, and the postgres slice (`DATABASE_URL=… pytest tests/integration/test_connections_pg.py
-m postgres -q`) since the store changed. Mutation gate unaffected.
- [ ] **Step 4:** commit (verify `COMMIT_EXIT=0` before tag), tag, push, watch CI + release.
- [ ] **Step 5:** comment on #1344 with what shipped + the commit, then `gh issue close 1344`.
  Update memory `project_1342_enterprise_auth_capability` — #1344 done; remaining = SP-initiated SLO.

## Self-review

- **Spec coverage:** pure warnings (Task 1), `connection_type_counts` + the `{}`-on-missing
  contract (Task 2), the startup hook wiring + loud-log decision (Task 3). ✓
- **Type consistency:** `capability_boot_warnings(Mapping[str,int], Callable[[str],bool]) ->
  list[str]`; `connection_type_counts() -> dict[str,int]`; `is_active` falls back to
  `lambda _cid: False` when `capabilities is None`. ✓
- **No placeholders:** every step has concrete code; the only "confirm X exists" notes are
  verifications (logger, auth_store non-None), not shipped placeholders. ✓
- **Security/failure lens:** the guard cannot break boot (`connection_type_counts` swallows to
  `{}`; the lifespan registry swallows hook exceptions); it changes no behaviour, only logs;
  no new attack surface. It's an observability fix.
```
