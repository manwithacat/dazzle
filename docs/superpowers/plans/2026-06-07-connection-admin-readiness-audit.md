# Org-admin connection surface: readiness panel + rotation audit — Implementation Plan

> **For agentic workers:** execute task-by-task. Steps use checkbox (`- [ ]`) syntax.
> Spec: `docs/superpowers/specs/2026-06-07-connection-admin-readiness-audit-design.md`.

**Goal:** Show per-connection activation readiness (reuse `connection_doctor`) and a read-only
secret-rotation history (consume `connection_secret_events`) on the existing `/auth/connections`
org-admin page — secret-free, no new route/RBAC/capability change.

**Architecture:** Extend the `connections_page` handler to attach three secret-free fields
(`readiness`, `events`, `grace`) to each per-connection dict; `_connection_block` renders them.
Readiness reuses `diagnose_connection`; audit reads `get_connection_secret_events` (org-fenced
because the loop only iterates the caller's org connections); grace reads a new tiny store
method. No new Fragment primitives.

**Tech Stack:** Python 3.12, typed Fragment substrate (`dazzle.render.fragment`), FastAPI,
psycopg3 auth store, pytest.

**Execution mode:** Hybrid (inline) per global CLAUDE.md on Opus 4.8 — implement inline, then an
independent review focused on the secret-free invariant + org-scoping of the audit read.

---

### Task 1: Shared `environment_flags()` in `connection_doctor`

**Files:**
- Modify: `src/dazzle/back/runtime/auth/connection_doctor.py`
- Modify: `src/dazzle/cli/auth_connection.py` (`_env_flags` delegates)
- Test: `tests/unit/test_auth_connection_cli.py`

- [ ] **Step 1: Write the failing test** (append to test_auth_connection_cli.py)

```python
def test_environment_flags_reports_key_presence(monkeypatch) -> None:
    import base64

    from dazzle.back.runtime.auth.connection_doctor import environment_flags

    monkeypatch.setenv("DAZZLE_CONNECTION_SECRET", base64.b64encode(b"k" * 32).decode())
    secret_ok, _sso, _dns = environment_flags()
    assert secret_ok is True
    monkeypatch.delenv("DAZZLE_CONNECTION_SECRET", raising=False)
    secret_ok2, _sso2, _dns2 = environment_flags()
    assert secret_ok2 is False
```

- [ ] **Step 2: Run — expect FAIL** (`environment_flags` doesn't exist).
Run: `pytest tests/unit/test_auth_connection_cli.py -q -k environment_flags`

- [ ] **Step 3: Add `environment_flags()` to connection_doctor.py** (module level):

```python
def environment_flags() -> tuple[bool, bool, bool]:
    """(secret_key_ok, sso_extra_ok, dns_extra_ok) — the doctor's environment inputs.

    Shared by the CLI `doctor`/`_env_flags` and the org-admin readiness panel so the two
    can't drift. secret_key_ok = DAZZLE_CONNECTION_SECRET is a loadable 32-byte key.
    """
    from importlib.util import find_spec

    from dazzle.back.runtime.auth.connection_crypto import ConnectionSecretError, _load_key

    try:
        _load_key()
        secret_key_ok = True
    except ConnectionSecretError:
        secret_key_ok = False
    return secret_key_ok, find_spec("authlib") is not None, find_spec("dns") is not None
```

- [ ] **Step 4: Make the CLI `_env_flags` delegate** (auth_connection.py) — replace its body:

```python
def _env_flags() -> tuple[bool, bool, bool]:
    """(secret_key_ok, sso_extra_ok, dns_extra_ok) for the doctor."""
    from dazzle.back.runtime.auth.connection_doctor import environment_flags

    return environment_flags()
```

- [ ] **Step 5: Run — expect PASS** (new test + existing doctor CLI tests still green).
Run: `pytest tests/unit/test_auth_connection_cli.py -q`

- [ ] **Step 6: Commit** — `refactor(auth): share environment_flags between doctor CLI + runtime (#1342)`

---

### Task 2: `get_connection_grace_status` store method

**Files:**
- Modify: `src/dazzle/back/runtime/auth/store.py`
- Test: `tests/integration/test_connections_pg.py`

- [ ] **Step 1: Write the failing PG test** (append)

```python
def test_get_connection_grace_status(store_url: str) -> None:
    store = _store(store_url)
    conn = _make_scim_connection(store, "b1")
    assert store.get_connection_grace_status(conn.id) == (False, None)
    store.rotate_connection_secret(
        conn.id, {"scim_bearer": "b2"}, grace=timedelta(days=1), actor="cli"
    )
    active, exp = store.get_connection_grace_status(conn.id)
    assert active is True and exp is not None
    store.revoke_previous_connection_secret(conn.id, actor="cli")
    assert store.get_connection_grace_status(conn.id) == (False, None)
```

- [ ] **Step 2: Run — expect FAIL.**
Run: `DATABASE_URL=postgresql://localhost/dazzle_dev pytest tests/integration/test_connections_pg.py -q -k grace_status`

- [ ] **Step 3: Add the method** (near `get_connection_secret_events` in store.py):

```python
    def get_connection_grace_status(self, connection_id: str) -> tuple[bool, str | None]:
        """(grace_active, expires_at_iso) for a connection's SCIM-bearer overlap window
        (#1342). A timestamp, not a secret. (False, None) when there's no grace secret or
        the window has lapsed. Read-only — revoking stays in the CLI."""
        row = self._execute_one(
            "SELECT previous_secret_expires_at FROM connections WHERE id = %s",
            (connection_id,),
        )
        exp = row["previous_secret_expires_at"] if row else None
        if not exp:
            return (False, None)
        try:
            return (datetime.fromisoformat(exp) > datetime.now(UTC), exp)
        except ValueError:
            return (False, None)
```

- [ ] **Step 4: Run — expect PASS.**
Run: `DATABASE_URL=postgresql://localhost/dazzle_dev pytest tests/integration/test_connections_pg.py -q -k grace_status`

- [ ] **Step 5: Commit** — `feat(auth): get_connection_grace_status (secret-free overlap status) (#1342)`

---

### Task 3: Handler gathers readiness / events / grace

**Files:** Modify `src/dazzle/back/runtime/auth/connection_admin_routes.py` (`connections_page`).

- [ ] **Step 1: Add imports** to the `connections_page` handler (it already imports
`build_connections_view`, `ConnectionSecretError`, `txt_record`, `FragmentRenderer`):

```python
        from dazzle.back.runtime.auth.connection_doctor import (
            diagnose_connection,
            environment_flags,
        )
```

- [ ] **Step 2: Compute env flags once + attach the three fields per connection.** Inside
`connections_page`, compute `flags = environment_flags()` before the `for conn in
store.get_connections_for_tenant(org_id):` loop, and in the loop body (where the per-connection
dict is appended) attach the extras. Replace the `connections.append({...})` block with:

```python
        flags = environment_flags()
        ...
        for conn in store.get_connections_for_tenant(org_id):
            # ... existing verified/unverified computation unchanged ...
            try:
                diag = diagnose_connection(
                    conn,
                    secret_key_ok=flags[0],
                    sso_extra_ok=flags[1],
                    dns_extra_ok=flags[2],
                )
                readiness = {
                    "ready": diag.ready,
                    "checks": [
                        {"name": c.name, "ok": c.status == "ok", "detail": c.detail}
                        for c in diag.checks
                        if c.level == "required"
                    ],
                    "next_steps": list(diag.next_steps),
                }
            except ConnectionSecretError:
                readiness = {
                    "ready": False,
                    "checks": [],
                    "next_steps": [
                        "The operator must set DAZZLE_CONNECTION_SECRET to assess readiness."
                    ],
                }
            events = [
                {
                    "at": e.at.isoformat() if hasattr(e.at, "isoformat") else str(e.at),
                    "event": e.event,
                    "actor": e.actor or "-",
                    "grace_until": (e.detail or {}).get("grace_until"),
                }
                for e in store.get_connection_secret_events(conn.id)[:5]
            ]
            grace_active, grace_exp = store.get_connection_grace_status(conn.id)
            connections.append(
                {
                    "id": conn.id,
                    "type": conn.type,
                    "status": conn.status,
                    "verified": sorted(verified),
                    "unverified": unverified,
                    "active_for_sso": bool(verified),
                    "readiness": readiness,
                    "events": events,
                    "grace": {"active": grace_active, "expires_at": grace_exp},
                }
            )
```

(Keep the existing `verified`/`unverified` computation exactly; only the appended dict grows.)

- [ ] **Step 3:** No standalone run — covered by Task 5's integration tests.
- [ ] **Step 4: Commit** with Task 4 (handler + view ship together).

---

### Task 4: View renders readiness + grace + history

**Files:** Modify `src/dazzle/back/runtime/auth/connection_admin_views.py`.

- [ ] **Step 1: Add two render helpers** (module level, after `_CSS`/`_JS`):

```python
def _readiness_block(readiness: dict[str, Any]) -> list[Any]:
    out: list[Any] = [
        Badge(
            label="Activation-ready ✓" if readiness["ready"] else "Not activation-ready",
            variant="default" if readiness["ready"] else "warning",
        )
    ]
    for check in readiness["checks"]:
        mark = "✓" if check["ok"] else "✗"
        out.append(Text(body=f"{mark} {check['name']}: {check['detail']}", tone="muted"))
    if not readiness["ready"] and readiness["next_steps"]:
        out.append(Text(body="What's left:", tone="muted"))
        for step in readiness["next_steps"]:
            out.append(Text(body=f"  • {step}", tone="muted"))
    return out


def _history_block(events: list[dict[str, Any]]) -> list[Any]:
    out: list[Any] = [Text(body="Secret-rotation history")]
    if not events:
        out.append(Text(body="No rotation events yet.", tone="muted"))
        return out
    for e in events:
        line = f"{e['at']}  {e['event']}  ({e['actor']})"
        if e.get("grace_until"):
            line += f"  → grace until {e['grace_until']}"
        out.append(Text(body=line, tone="muted"))
    return out
```

- [ ] **Step 2: Wire them into `_connection_block`.** After the existing readiness badge
(`"Verified domain ✓" / "No verified domain"`), extend the readiness panel; add the grace badge;
and append the history block at the end. Insert after the `active_for_sso` badge in the initial
`children` list:

```python
    children.extend(_readiness_block(conn.get("readiness", {"ready": False, "checks": [], "next_steps": []})))
    grace = conn.get("grace") or {}
    if grace.get("active"):
        children.append(
            Badge(label=f"Grace window active until {grace['expires_at']}", variant="warning")
        )
```

And just before `return Stack(children=tuple(children))`, append the history:

```python
    children.extend(_history_block(conn.get("events", [])))
    return Stack(children=tuple(children))
```

(`.get(...)` defaults keep the view robust if a caller omits the new keys.)

- [ ] **Step 3: Commit** — `feat(auth): org-admin connection page shows readiness + rotation history (#1342)` (handler from Task 3 + view together).

---

### Task 5: Integration tests

**Files:** Modify `tests/integration/test_connection_admin_routes.py`.

- [ ] **Step 1: Extend the fake `_Store`** with the two reads (default to empty/none so existing
tests are unaffected):

```python
    def get_connection_secret_events(self, connection_id):
        return getattr(self, "_events", {}).get(connection_id, [])

    def get_connection_grace_status(self, connection_id):
        return getattr(self, "_grace", {}).get(connection_id, (False, None))
```

- [ ] **Step 2: Add tests** (use `SimpleNamespace` events shaped like `ConnectionSecretEvent`):

```python
def test_page_shows_readiness(monkeypatch) -> None:
    store = _Store(connections=[_conn()])
    r = _client(store).get("/auth/connections", cookies={"dazzle_session": "good-sid"})
    assert r.status_code == 200
    # Readiness badge renders (ready or not — at least the panel exists).
    assert "ready" in r.text.lower()


def test_page_shows_rotation_history(monkeypatch) -> None:
    store = _Store(connections=[_conn()])
    store._events = {
        "conn-1": [
            SimpleNamespace(
                at=datetime(2026, 6, 7), event="rotated", actor="cli",
                detail={"grace_until": "2026-06-08T00:00:00+00:00"},
            )
        ]
    }
    r = _client(store).get("/auth/connections", cookies={"dazzle_session": "good-sid"})
    assert r.status_code == 200 and "rotated" in r.text and "2026-06-07" in r.text


def test_page_shows_grace_window_when_active(monkeypatch) -> None:
    store = _Store(connections=[_conn()])
    store._grace = {"conn-1": (True, "2026-06-08T00:00:00+00:00")}
    r = _client(store).get("/auth/connections", cookies={"dazzle_session": "good-sid"})
    assert r.status_code == 200 and "Grace window active" in r.text


def test_readiness_and_audit_never_leak_secret(monkeypatch) -> None:
    store = _Store(connections=[_conn(secrets={"client_secret": "SUPER-SECRET"})])
    store._events = {
        "conn-1": [SimpleNamespace(at=datetime(2026, 6, 7), event="rotated", actor="cli", detail={})]
    }
    store._grace = {"conn-1": (True, "2026-06-08T00:00:00+00:00")}
    r = _client(store).get("/auth/connections", cookies={"dazzle_session": "good-sid"})
    assert r.status_code == 200
    assert "SUPER-SECRET" not in r.text  # no secret via any new path


def test_audit_is_org_scoped(monkeypatch) -> None:
    # Admin of org-1; a second-org connection's events must never be fetched/rendered.
    other = _conn(cid="conn-2", tenant="org-2")
    store = _Store(connections=[_conn(), other])
    store._events = {
        "conn-2": [SimpleNamespace(at=datetime(2026, 6, 7), event="rotated", actor="cli", detail={})]
    }
    r = _client(store).get("/auth/connections", cookies={"dazzle_session": "good-sid"})
    assert r.status_code == 200 and "conn-2" not in r.text  # other org filtered out
```

(Confirm the cookie name the existing tests use — read the top of the file's `_client`/requests;
mirror whatever the existing `test_page_lists_connections_never_leaks_secret` does for the
authenticated session, e.g. `cookies={...}` or a header. Use the SAME mechanism.)

- [ ] **Step 3: Run — expect PASS.**
Run: `pytest tests/integration/test_connection_admin_routes.py -q`

- [ ] **Step 4: Commit** — `test(auth): readiness + rotation-history render, secret-free, org-scoped (#1342)`

---

### Task 6: Docs + CHANGELOG + bump

**Files:** `docs/reference/enterprise-sso.md`, `CHANGELOG.md`, then `/bump patch`.

- [ ] **Step 1: enterprise-sso.md** — in the org-admin surface description, note the page now
shows per-connection **activation readiness** (mirrors `dazzle auth connection doctor`,
secret-free) and a read-only **secret-rotation history** (event names + timestamps, never a
secret). Reaffirm rotation/revoke/create stay in the CLI.
- [ ] **Step 2: CHANGELOG** under `[Unreleased]`: `Added` (org-admin page readiness panel +
rotation audit view + grace indicator; `connection_doctor.environment_flags`;
`get_connection_grace_status`) + an Agent Guidance bullet (readiness panel reuses
`diagnose_connection` — keep them sharing it; the page is read-only/secret-free; rotation stays
CLI).
- [ ] **Step 3:** `/bump patch` → v0.81.79.
- [ ] **Step 4:** commit handled by the ship step (Task 7).

---

### Task 7: Gates + independent review + ship

- [ ] **Step 1:** `ruff check src/ tests/ --fix && ruff format src/ tests/`; `mypy src/dazzle`.
- [ ] **Step 2:** drift/policy gates (the `/ship` block, incl. `test_typed_runtime_no_jinja`,
`test_api_surface_drift`); `mkdocs build --strict`; `dazzle inspect api runtime-urls --diff`
(should be "No drift" — no new routes).
- [ ] **Step 3:** `pytest tests/ -m "not e2e" -q` AND
`DATABASE_URL=…/dazzle_dev pytest -m postgres -q` (the store method).
- [ ] **Step 4: Independent review** — `feature-dev:code-reviewer` over the diff, focused on:
(a) **secret-free invariant** — no secret/bearer reaches the rendered HTML via readiness
`detail`, event `detail`, or grace; (b) **org-scoping** — audit events read only for the
caller's org connections (no cross-org leak); (c) readiness parity with the CLI `doctor`
(same `diagnose_connection`). Fix CRITICAL/HIGH before ship.
- [ ] **Step 5: Ship** — acquire `.dazzle/improve.lock`; commit (docs/bump); tag `v0.81.79`;
push + tags; watch CI + tag release; release the lock; clean worktree.
- [ ] **Step 6: Close-out** — comment the increment on #1342; update memory.

## Self-review (plan vs spec)

- **Coverage:** `environment_flags` (T1), `get_connection_grace_status` (T2), handler gathering
  (T3), view rendering (T4), tests incl. secret-free + org-scoped (T5), docs/changelog (T6),
  review+ship (T7) — every spec section maps to a task.
- **Type consistency:** `environment_flags() -> tuple[bool,bool,bool]`,
  `get_connection_grace_status(connection_id) -> tuple[bool, str | None]`, the per-conn dict
  keys `readiness`/`events`/`grace` consumed by `_readiness_block`/`_history_block` and the
  grace badge — consistent across handler and view.
- **Placeholder scan:** none — code is concrete. The one verify-at-impl note: confirm the
  authenticated-session mechanism the existing tests use (cookie vs header) and mirror it (T5
  Step 2).
