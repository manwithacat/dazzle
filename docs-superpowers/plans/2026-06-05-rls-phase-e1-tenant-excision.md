# RLS Phase E.1 — Tenant Excision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (Hybrid: inline execution with an independent adversarial-review checkpoint on the destructive excision engine before the CLI). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete every trace of one tenant — all its fenced domain rows, its tenant-root row, its memberships, its `organizations` registry row, and the identities orphaned by that removal — atomically and in FK-safe (children-first) order, with cross-tenant isolation guaranteed and a dry-run preview. Closes #1338.

**Architecture:** The canonical RLS model (shared-schema + uniform `tenant_id` discriminator, Phases A–D) replaced the old FK-closure excision engine with **`DELETE … WHERE tenant_id = X` per tenant-scoped table**, run as the `dazzle_bypass` role (BYPASSRLS — "outside the tenant ring" is never ambient). A pure `FKGraph.deletion_order` (the reverse of the existing `creation_order`) gives the children-before-parents sequence so composite intra-tenant FKs don't block the deletes. A single sync `excise_tenant(appspec, tenant_id, *, conn, dry_run)` runs all deletes — domain tables + the auth-store cascade (`memberships`/`organizations`/orphaned `users`) — in **one transaction** on one bypass connection, so excision is all-or-nothing. The membership model (auth Plan 1a–1c) makes the cascade explicit: `membership.tenant_id = organizations.id = dazzle.tenant_id`, so one discriminator value keys everything.

**Tech Stack:** Python 3.12, psycopg3 (sync, raw SQL, `%s` params, one transaction), `FKGraph` (pure topo), Typer (CLI), pytest (+ `pytest.mark.postgres` real-PG isolation test with a `dazzle_bypass` role harness mirroring `tests/integration/test_rls_enforcement_pg.py`).

---

## Scope

**In scope (Phase E.1):**
- `FKGraph.deletion_order(entities)` — reverse-topo (children-first), `None` on cycle.
- `excise_tenant(appspec, tenant_id, *, conn, dry_run=False) -> ExcisionResult` in `src/dazzle/db/excision.py` — atomic, single-transaction, single bypass connection. Deletes: tenant-scoped domain rows `WHERE tenant_id = X` (children-first), the tenant-root row `WHERE id = X` (last), `memberships WHERE tenant_id = X`, the `organizations` row `WHERE id = X`, and the identities orphaned by *this* excision. `dry_run` reports counts and rolls back.
- `dazzle tenant excise <tenant_id>` CLI: `--dry-run`, `--force`; refuses a non-`is_test` org without `--force` (the destructive-op safety guard); connects as the resolved DB role (documents the `dazzle_bypass`/BYPASSRLS requirement). Surface `is_test` in `dazzle tenant status` (the deferred Slice-0 nicety).
- Real-PG isolation test: seed two tenants (A, B) with multi-level FK descendants + memberships + orgs + a shared-and-an-exclusive identity; excise A; assert (a) all of A's rows gone at every level + A's memberships/org gone, (b) **B untouched** (the critical isolation assertion), (c) A's exclusive identity reaped but the shared identity kept, (d) dry-run deletes nothing.

**Out of scope (Phase E.2 — its own plan, #1339):** QA-auth mint route (`qa_secure_routes.py` + hmac signer, self-disabling without `QA_AUTH_SECRET`), `provision_test_tenant(run_id)`, the **DB-enforced containment invariant** (session→membership→org `is_test` gate), the SSO/containment ADR, adversarial QA-auth tests. E.1 is the destructive primitive E.2 drives.

**Also out of scope:** the 1:1 domain-tenant-root↔org-id seed (Plan 1d) — E.1 excises by a single `tenant_id` discriminator and assumes `organizations.id == the domain discriminator` (the canonical invariant; always true for framework-provisioned/QA tenants, and for real apps once 1d seeds it). Cross-schema (premium isolation) excision; soft-delete/retention.

## Design decisions

- **One discriminator, one transaction, as `dazzle_bypass`.** Excision deletes everything keyed by the single `tenant_id` value across domain + auth-store tables on one connection in one transaction → atomic (a mid-excision failure rolls back; no half-excised tenant). `dazzle_bypass` (BYPASSRLS) is required so the deletes aren't themselves fenced; the engine takes a `conn` so the caller owns the role, and the CLI documents/builds the bypass connection.
- **Deletion order = reverse(creation_order).** Children (FK sources) before parents (FK targets) so composite intra-tenant FKs `(tenant_id, fk) → parent(tenant_id, id)` don't block. The tenant-root entity (no `tenant_id` column — it *is* the tenant) is included in the topo set and deleted by `id`, naturally last. On a cycle (`creation_order` → `None`, e.g. a self-referential FK), raise `ExcisionError` with a clear message — rare, and QA/test tenants are acyclic (documented limit; E.2's provisioning produces acyclic tenants).
- **Precise orphan reaping.** Capture `memberships.identity_id` for the tenant *before* deleting its memberships; after, delete only those captured identities that now have **zero** memberships. A user who also belongs to another tenant is **kept** (no cross-tenant collateral) — this is the load-bearing isolation property for the auth cascade.
- **`is_test` safety guard.** `excise` refuses unless the target org is `is_test=true` or `--force` is given — excision is irreversible; the guard makes the QA/ephemeral case (the #1339 driver) friction-free while protecting prod orgs.

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `src/dazzle/core/ir/fk_graph.py` | `deletion_order` (reverse of `creation_order`) | **Modify** |
| `src/dazzle/db/excision.py` | `ExcisionResult` + `excise_tenant` engine (sync, atomic) | **Create** |
| `src/dazzle/cli/tenant.py` | `excise` command + `is_test` in `status` | **Modify** |
| `tests/unit/test_fk_graph_deletion_order.py` | pure deletion-order tests | **Create** |
| `tests/integration/test_tenant_excision_pg.py` | real-PG isolation + cascade + dry-run | **Create** |

---

## Task 1: `FKGraph.deletion_order`

**Files:**
- Modify: `src/dazzle/core/ir/fk_graph.py`
- Test: `tests/unit/test_fk_graph_deletion_order.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_fk_graph_deletion_order.py
"""FKGraph.deletion_order — children-before-parents (RLS Phase E.1)."""

from dazzle.core.ir.fk_graph import FKGraph


def _graph(edges: dict[str, dict[str, str]]) -> FKGraph:
    g = FKGraph()
    g._edges = {k: dict(v) for k, v in edges.items()}
    return g


def test_deletion_order_is_children_before_parents() -> None:
    # Task -> Project -> Workspace (FK source first in deletion).
    g = _graph(
        {
            "Workspace": {},
            "Project": {"workspace": "Workspace"},
            "Task": {"project": "Project"},
        }
    )
    order = g.deletion_order(["Workspace", "Project", "Task"])
    assert order is not None
    assert order.index("Task") < order.index("Project") < order.index("Workspace")


def test_deletion_order_is_exact_reverse_of_creation_order() -> None:
    g = _graph(
        {"A": {}, "B": {"a": "A"}, "C": {"b": "B"}}
    )
    creation = g.creation_order(["A", "B", "C"])
    deletion = g.deletion_order(["A", "B", "C"])
    assert creation is not None and deletion is not None
    assert deletion == list(reversed(creation))


def test_deletion_order_none_on_cycle() -> None:
    # Self-referential FK → cycle → no safe order.
    g = _graph({"Employee": {"manager": "Employee"}})
    assert g.deletion_order(["Employee"]) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_fk_graph_deletion_order.py -q`
Expected: FAIL — `AttributeError: 'FKGraph' object has no attribute 'deletion_order'`.

- [ ] **Step 3: Add the method**

In `src/dazzle/core/ir/fk_graph.py`, immediately after `creation_order`, add:

```python
    def deletion_order(self, entities: list[str]) -> list[str] | None:
        """Order *entities* child-before-parent for safe FK-respecting deletion.

        The exact reverse of :meth:`creation_order` — every entity appears
        *before* the entities it has an FK to (within the set), so deleting in
        this order never violates a still-present FK reference. Returns ``None``
        on a cycle (incl. a self-referential FK), exactly when ``creation_order``
        does — the caller (excision) treats that as "no safe order" and refuses
        rather than risk a constraint violation or an infinite loop.
        """
        created = self.creation_order(entities)
        return None if created is None else list(reversed(created))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_fk_graph_deletion_order.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/core/ir/fk_graph.py tests/unit/test_fk_graph_deletion_order.py
git commit -m "feat(ir): FKGraph.deletion_order — children-first reverse-topo (Phase E.1)"
```

---

## Task 2: `excise_tenant` engine

**Files:**
- Create: `src/dazzle/db/excision.py`
- Test: `tests/integration/test_tenant_excision_pg.py`

- [ ] **Step 1: Write the failing integration test (real PG, two tenants)**

```python
# tests/integration/test_tenant_excision_pg.py
"""Real-PostgreSQL proof of tenant excision isolation (RLS Phase E.1, #1338).

Marked e2e + postgres: skipped without TEST_DATABASE_URL/DATABASE_URL. Seeds two
tenants with multi-level FK descendants + auth-store memberships/orgs/identities,
excises one, and asserts the other is untouched (the critical isolation property).
Connects as a superuser scratch role (bypasses RLS — the excision-as-dazzle_bypass
posture); the isolation here is the WHERE-clause discipline, not RLS.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import psycopg
import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


def _admin_url() -> str:
    assert _PG_URL is not None
    return _PG_URL.replace("postgresql+psycopg://", "postgresql://")


@pytest.fixture
def scratch_url() -> Iterator[str]:
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL/DATABASE_URL")
    admin_url = _admin_url()
    base, _, _old = admin_url.rpartition("/")
    scratch = f"dazzle_excise_{uuid.uuid4().hex[:8]}"
    url = f"{base}/{scratch}"
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{scratch}"')  # nosemgrep
    try:
        yield url
    finally:
        with psycopg.connect(admin_url, autocommit=True) as admin:
            admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (scratch,),
            )
            admin.execute(f'DROP DATABASE IF EXISTS "{scratch}"')  # nosemgrep


def _build_appspec():
    """A minimal shared_schema AppSpec: tenant root Workspace + scoped Project,
    Task (Task → Project → Workspace). Built via the DSL parser so tenancy_inject
    runs and the scoped entities carry the injected tenant_id."""
    from dazzle.core.dsl_parser import parse_dsl  # canonical parser entry

    dsl = """
module excise_test
app excise_test "Excise Test"

tenancy:
  isolation: shared_schema
  partition_key: tenant_id

entity Workspace "Workspace":
  archetype: tenant
  id: uuid pk
  name: str(100) required

entity Project "Project":
  id: uuid pk
  name: str(100) required

entity Task "Task":
  id: uuid pk
  title: str(100) required
  project: ref Project required
"""
    return parse_dsl(dsl)  # if the entry point differs, mirror tests/unit parser usage


def _seed(conn, appspec) -> None:
    """Create the domain + auth tables and seed tenants A and B with descendants,
    memberships, orgs, and identities (one identity shared across A and B)."""
    from dazzle.http.runtime.auth.store import AuthStore

    # Domain tables (mirror the injected shape: scoped entities carry tenant_id).
    conn.execute('CREATE TABLE "Workspace" (id TEXT PRIMARY KEY, name TEXT)')
    conn.execute(
        'CREATE TABLE "Project" (tenant_id TEXT NOT NULL, id TEXT PRIMARY KEY, name TEXT, '
        'UNIQUE (tenant_id, id))'
    )
    conn.execute(
        'CREATE TABLE "Task" (tenant_id TEXT NOT NULL, id TEXT PRIMARY KEY, title TEXT, '
        'project TEXT, FOREIGN KEY (tenant_id, project) REFERENCES "Project"(tenant_id, id))'
    )
    conn.execute('INSERT INTO "Workspace" VALUES (%s, %s)', ("A", "WS-A"))
    conn.execute('INSERT INTO "Workspace" VALUES (%s, %s)', ("B", "WS-B"))
    for t in ("A", "B"):
        conn.execute('INSERT INTO "Project" VALUES (%s, %s, %s)', (t, f"P-{t}", f"proj-{t}"))
        conn.execute(
            'INSERT INTO "Task" VALUES (%s, %s, %s, %s)', (t, f"T-{t}", f"task-{t}", f"P-{t}")
        )
    conn.commit()

    # Auth store (its own connections) — users, orgs, memberships.
    store = AuthStore(database_url=_url_of(conn))
    store._init_db()
    # Orgs A and B share their id with the domain tenant root (the canonical
    # invariant excision relies on).
    store.create_organization(slug="org-a", name="A")  # slug only; we set id below
    # Force the org ids to match the domain discriminators "A"/"B" for the test.
    conn.execute("UPDATE organizations SET id = 'A' WHERE slug = 'org-a'")
    store.create_organization(slug="org-b", name="B")
    conn.execute("UPDATE organizations SET id = 'B' WHERE slug = 'org-b'")
    only_a = store.create_user(email="only-a@b.test", password="pw123456")
    shared = store.create_user(email="shared@b.test", password="pw123456")
    store.create_membership(tenant_id="A", identity_id=str(only_a.id), roles=["member"])
    store.create_membership(tenant_id="A", identity_id=str(shared.id), roles=["member"])
    store.create_membership(tenant_id="B", identity_id=str(shared.id), roles=["member"])
    conn.commit()
    return str(only_a.id), str(shared.id)


def _url_of(conn) -> str:
    # The scratch_url is what AuthStore needs; recover it from the test scope.
    raise NotImplementedError  # replaced inline in the test below


def test_excise_removes_tenant_a_and_leaves_b(scratch_url: str) -> None:
    from dazzle.db.excision import excise_tenant

    appspec = _build_appspec()
    from dazzle.http.runtime.auth.store import AuthStore

    # --- seed (inline so AuthStore gets the scratch_url directly) ---
    with psycopg.connect(scratch_url) as conn:
        conn.execute('CREATE TABLE "Workspace" (id TEXT PRIMARY KEY, name TEXT)')
        conn.execute(
            'CREATE TABLE "Project" (tenant_id TEXT NOT NULL, id TEXT PRIMARY KEY, name TEXT, '
            'UNIQUE (tenant_id, id))'
        )
        conn.execute(
            'CREATE TABLE "Task" (tenant_id TEXT NOT NULL, id TEXT PRIMARY KEY, title TEXT, '
            'project TEXT, FOREIGN KEY (tenant_id, project) REFERENCES "Project"(tenant_id, id))'
        )
        conn.execute('INSERT INTO "Workspace" VALUES (%s,%s)', ("A", "WS-A"))
        conn.execute('INSERT INTO "Workspace" VALUES (%s,%s)', ("B", "WS-B"))
        for t in ("A", "B"):
            conn.execute('INSERT INTO "Project" VALUES (%s,%s,%s)', (t, f"P-{t}", t))
            conn.execute('INSERT INTO "Task" VALUES (%s,%s,%s,%s)', (t, f"T-{t}", t, f"P-{t}"))
        conn.commit()

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    store.create_organization(slug="org-a", name="A")
    store.create_organization(slug="org-b", name="B")
    with psycopg.connect(scratch_url) as conn:
        conn.execute("UPDATE organizations SET id='A' WHERE slug='org-a'")
        conn.execute("UPDATE organizations SET id='B' WHERE slug='org-b'")
        conn.commit()
    only_a = store.create_user(email="only-a@b.test", password="pw123456")
    shared = store.create_user(email="shared@b.test", password="pw123456")
    store.create_membership(tenant_id="A", identity_id=str(only_a.id), roles=["member"])
    store.create_membership(tenant_id="A", identity_id=str(shared.id), roles=["member"])
    store.create_membership(tenant_id="B", identity_id=str(shared.id), roles=["member"])

    # --- excise tenant A ---
    with psycopg.connect(scratch_url) as conn:
        result = excise_tenant(appspec, "A", conn=conn)

    def _count(sql: str, *params) -> int:
        with psycopg.connect(scratch_url) as c:
            return c.execute(sql, params).fetchone()[0]

    # A gone at every level.
    assert _count('SELECT count(*) FROM "Workspace" WHERE id=%s', "A") == 0
    assert _count('SELECT count(*) FROM "Project" WHERE tenant_id=%s', "A") == 0
    assert _count('SELECT count(*) FROM "Task" WHERE tenant_id=%s', "A") == 0
    assert _count("SELECT count(*) FROM memberships WHERE tenant_id=%s", "A") == 0
    assert _count("SELECT count(*) FROM organizations WHERE id=%s", "A") == 0
    # B fully intact — the isolation assertion.
    assert _count('SELECT count(*) FROM "Workspace" WHERE id=%s', "B") == 1
    assert _count('SELECT count(*) FROM "Project" WHERE tenant_id=%s', "B") == 1
    assert _count('SELECT count(*) FROM "Task" WHERE tenant_id=%s', "B") == 1
    assert _count("SELECT count(*) FROM memberships WHERE tenant_id=%s", "B") == 1
    assert _count("SELECT count(*) FROM organizations WHERE id=%s", "B") == 1
    # Identity reaping: only-a (orphaned) gone; shared (still in B) kept.
    assert _count("SELECT count(*) FROM users WHERE id=%s", str(only_a.id)) == 0
    assert _count("SELECT count(*) FROM users WHERE id=%s", str(shared.id)) == 1
    assert result.deleted["Task"] == 1
    assert result.deleted["memberships"] == 2


def test_excise_dry_run_deletes_nothing(scratch_url: str) -> None:
    from dazzle.http.runtime.auth.store import AuthStore
    from dazzle.db.excision import excise_tenant

    appspec = _build_appspec()
    with psycopg.connect(scratch_url) as conn:
        conn.execute('CREATE TABLE "Workspace" (id TEXT PRIMARY KEY, name TEXT)')
        conn.execute('CREATE TABLE "Project" (tenant_id TEXT NOT NULL, id TEXT PRIMARY KEY, name TEXT, UNIQUE(tenant_id,id))')
        conn.execute('CREATE TABLE "Task" (tenant_id TEXT NOT NULL, id TEXT PRIMARY KEY, title TEXT, project TEXT, FOREIGN KEY (tenant_id,project) REFERENCES "Project"(tenant_id,id))')
        conn.execute('INSERT INTO "Workspace" VALUES (%s,%s)', ("A", "WS-A"))
        conn.execute('INSERT INTO "Project" VALUES (%s,%s,%s)', ("A", "P-A", "a"))
        conn.commit()
    store = AuthStore(database_url=scratch_url)
    store._init_db()
    store.create_organization(slug="org-a", name="A")
    with psycopg.connect(scratch_url) as conn:
        conn.execute("UPDATE organizations SET id='A' WHERE slug='org-a'")
        conn.commit()

    with psycopg.connect(scratch_url) as conn:
        result = excise_tenant(appspec, "A", conn=conn, dry_run=True)

    with psycopg.connect(scratch_url) as c:
        assert c.execute('SELECT count(*) FROM "Workspace"').fetchone()[0] == 1
        assert c.execute("SELECT count(*) FROM organizations").fetchone()[0] == 1
    assert result.dry_run is True
    assert result.deleted["Workspace"] == 1  # would-delete count
```

> Replace `parse_dsl` / `_build_appspec` with the project's canonical parse entry if it differs — grep how `tests/unit/test_parser.py` parses a DSL string to an `AppSpec`, and mirror it. The `_seed`/`_url_of` placeholder block at the top of the file is illustrative; the actual test bodies inline the seed with `scratch_url` directly (use those). Delete the unused `_seed`/`_url_of` helpers when writing the file.

- [ ] **Step 2: Run test to verify it fails**

Run: `TEST_DATABASE_URL="postgresql://localhost:5432/postgres" pytest tests/integration/test_tenant_excision_pg.py -q`
Expected: FAIL — `ModuleNotFoundError: dazzle.db.excision`.

- [ ] **Step 3: Write the engine**

```python
# src/dazzle/db/excision.py
"""Tenant excision — delete one tenant's entire footprint (RLS Phase E.1, #1338).

Deletes, in ONE transaction on a single (BYPASSRLS) connection: every
tenant-scoped domain row ``WHERE tenant_id = X`` (children-first), the
tenant-root row ``WHERE id = X`` (last), the auth-store ``memberships WHERE
tenant_id = X``, the ``organizations`` row ``WHERE id = X``, and the identities
orphaned by this removal. Atomic: any failure rolls the whole thing back — there
is no half-excised tenant. Run as ``dazzle_bypass`` so the deletes are not
themselves fenced by RLS.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from dazzle.http.runtime.query_builder import quote_identifier
from dazzle.http.runtime.sa_schema import scoped_entity_names
from dazzle.core.ir.fk_graph import FKGraph


class ExcisionError(RuntimeError):
    """Excision cannot proceed safely (e.g. an FK cycle in the tenant graph)."""


@dataclass
class ExcisionResult:
    tenant_id: str
    dry_run: bool
    deleted: dict[str, int] = field(default_factory=dict)


def _tenant_root_name(appspec: Any) -> str | None:
    for e in appspec.entities:
        if getattr(e, "is_tenant_root", False) or getattr(
            getattr(e, "archetype_kind", None), "name", ""
        ) == "TENANT":
            return e.name
    return None


def _count(conn: Any, sql: str, params: tuple[Any, ...]) -> int:
    row = conn.execute(sql, params).fetchone()
    # dict_row or tuple — handle both.
    if row is None:
        return 0
    return int(next(iter(row.values())) if isinstance(row, dict) else row[0])


def excise_tenant(
    appspec: Any, tenant_id: str, *, conn: Any, dry_run: bool = False
) -> ExcisionResult:
    """Excise ``tenant_id`` on ``conn`` (must be a BYPASSRLS role for real RLS).

    ``conn`` is a sync psycopg connection; this function manages a single
    transaction and commits on success (or rolls back when ``dry_run`` / on
    error). Returns counts per table (would-delete counts under ``dry_run``).
    """
    partition_key = "tenant_id"
    tenancy = getattr(appspec, "tenancy", None)
    if tenancy is not None and getattr(tenancy, "isolation", None) is not None:
        partition_key = getattr(tenancy.isolation, "partition_key", "tenant_id")

    entities = list(appspec.entities)
    scoped = scoped_entity_names(entities, partition_key)
    root = _tenant_root_name(appspec)

    # Topo set = scoped entities + the root (if any). Children-first.
    topo_set = sorted(scoped) + ([root] if root and root not in scoped else [])
    graph = FKGraph.from_entities(entities)
    order = graph.deletion_order(topo_set) if topo_set else []
    if order is None:
        raise ExcisionError(
            f"cannot excise tenant {tenant_id!r}: the tenant entity graph has a "
            "cycle (self-referential or circular FK) — no safe deletion order"
        )

    result = ExcisionResult(tenant_id=tenant_id, dry_run=dry_run)
    try:
        # Capture identities in this tenant BEFORE deleting its memberships, so
        # we can reap exactly those orphaned by this excision.
        rows = conn.execute(
            "SELECT identity_id FROM memberships WHERE tenant_id = %s", (tenant_id,)
        ).fetchall()
        identity_ids = [
            (r["identity_id"] if isinstance(r, dict) else r[0]) for r in rows
        ]

        for name in order:
            table = quote_identifier(name)
            if name == root:
                where, params = "id = %s", (tenant_id,)
            else:
                where, params = "tenant_id = %s", (tenant_id,)
            if dry_run:
                result.deleted[name] = _count(
                    conn, f"SELECT count(*) FROM {table} WHERE {where}", params  # nosemgrep
                )
            else:
                cur = conn.execute(f"DELETE FROM {table} WHERE {where}", params)  # nosemgrep
                result.deleted[name] = cur.rowcount

        # Auth-store cascade: memberships, then orphaned identities, then org.
        result.deleted["memberships"] = (
            _count(conn, "SELECT count(*) FROM memberships WHERE tenant_id = %s", (tenant_id,))
            if dry_run
            else conn.execute(
                "DELETE FROM memberships WHERE tenant_id = %s", (tenant_id,)
            ).rowcount
        )

        reaped = 0
        if identity_ids:
            # Identities from this tenant that now have NO memberships anywhere.
            orphan_rows = conn.execute(
                "SELECT u.id FROM users u WHERE u.id = ANY(%s) "
                "AND NOT EXISTS (SELECT 1 FROM memberships m WHERE m.identity_id = u.id)",
                (identity_ids,),
            ).fetchall()
            orphans = [(r["id"] if isinstance(r, dict) else r[0]) for r in orphan_rows]
            if orphans and not dry_run:
                conn.execute("DELETE FROM users WHERE id = ANY(%s)", (orphans,))
            reaped = len(orphans)
        result.deleted["users"] = reaped

        result.deleted["organizations"] = (
            _count(conn, "SELECT count(*) FROM organizations WHERE id = %s", (tenant_id,))
            if dry_run
            else conn.execute(
                "DELETE FROM organizations WHERE id = %s", (tenant_id,)
            ).rowcount
        )

        if dry_run:
            conn.rollback()
        else:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    return result
```

> `scoped_entity_names` (sa_schema.py:333) returns the names carrying `partition_key`. Under `dry_run` the memberships count is taken *before* any delete (no deletes happen at all), so the orphan probe (which runs against still-present memberships) reports the would-orphan set correctly. The `# nosemgrep` table interpolations are quoted IR identifiers (`quote_identifier`), never user input; the `tenant_id` value is always a bound `%s` param.

- [ ] **Step 4: Run test to verify it passes**

Run: `TEST_DATABASE_URL="postgresql://localhost:5432/postgres" pytest tests/integration/test_tenant_excision_pg.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/db/excision.py tests/integration/test_tenant_excision_pg.py
git commit -m "feat(db): excise_tenant — atomic single-transaction tenant excision (Phase E.1)"
```

---

> ### ⛳ ADVERSARIAL REVIEW CHECKPOINT (after Task 2)
> Before the CLI, dispatch an **independent reviewer subagent** (or `/code-review`) over the excision engine + test. Brief it to attack: (1) **cross-tenant collateral** — can any delete touch a row whose `tenant_id` ≠ X (e.g. a missing `WHERE`, a wrong key on the root, the orphan `ANY(%s)` reaping a user who still belongs elsewhere)? The "B untouched" + "shared identity kept" assertions must genuinely hold. (2) **atomicity** — confirm a failure mid-sequence rolls back the whole transaction (no partial excision), and that `dry_run` truly writes nothing (rollback) yet reports accurate counts. (3) **FK-order correctness** — does children-first + root-last avoid FK violations under the composite `(tenant_id, fk)` FKs? What happens on a cycle (must raise, not loop/partial-delete)? (4) **SQL injection** — table names via `quote_identifier`, tenant_id via bound param — confirm no interpolation of untrusted data. (5) **orphan-reap precision** — the capture-before/probe-after logic: any TOCTOU or off-by-one that could reap a still-membered identity or miss a true orphan? Apply receiving-code-review rigor; proceed only when isolation + atomicity are airtight.

---

## Task 3: `dazzle tenant excise` CLI + `is_test` in `status`

**Files:**
- Modify: `src/dazzle/cli/tenant.py`
- Test: covered by Task 2's engine test; CLI gets a focused safety-guard unit test (no DB) below.

- [ ] **Step 1: Add the `excise` command**

Read `src/dazzle/cli/tenant.py` to confirm the helper shapes (`_get_registry`, how the AppSpec + DB URL are resolved — mirror `create_command`/`status_command`). Add:

```python
@tenant_app.command(name="excise")
def excise_command(
    tenant_id: str = typer.Argument(..., help="The tenant/org id (dazzle.tenant_id) to excise."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Report what would be deleted; delete nothing."),
    force: bool = typer.Option(False, "--force", help="Allow exciseing a non-test org (DANGER)."),
    database_url: str = typer.Option(
        "", "--database-url",
        help="Override DB URL. MUST be a BYPASSRLS role (dazzle_bypass) in production.",
    ),
) -> None:
    """Permanently delete a tenant: its domain rows, memberships, org, and orphaned identities.

    Irreversible. Refuses a non-`is_test` org unless --force. Run as `dazzle_bypass`
    (BYPASSRLS) so the deletes aren't fenced; the dev superuser bypasses RLS already.
    """
    import psycopg

    from dazzle.db.excision import ExcisionError, excise_tenant

    appspec = _load_appspec()  # mirror how status/create load it; grep _get_* helpers
    url = database_url or _resolve_database_url()  # mirror the registry/manifest URL resolution
    try:
        with psycopg.connect(url) as conn:
            # Safety guard: refuse a non-test org unless --force.
            row = conn.execute(
                "SELECT is_test, slug FROM organizations WHERE id = %s", (tenant_id,)
            ).fetchone()
            is_test = bool(row["is_test"]) if row else False
            if row is not None and not is_test and not force:
                typer.echo(
                    f"Refusing to excise non-test org {tenant_id!r} (slug={row['slug']!r}). "
                    "Re-run with --force if you really mean it.",
                    err=True,
                )
                raise typer.Exit(code=2)
            result = excise_tenant(appspec, tenant_id, conn=conn, dry_run=dry_run)
    except ExcisionError as exc:
        typer.echo(f"Excision aborted: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    verb = "Would delete" if dry_run else "Deleted"
    typer.echo(f"{verb} for tenant {tenant_id}:")
    for table, n in sorted(result.deleted.items()):
        typer.echo(f"  {table}: {n}")
```

> Replace `_load_appspec()` / `_resolve_database_url()` with the actual helpers in `cli/tenant.py` (grep `_get_registry`, `_get_provisioner`, and how `create_command` obtains the manifest DB URL + AppSpec). Do **not** gate `excise` on `_check_tenant_enabled()` — that asserts schema-isolation; excision is for the shared-schema RLS model. If loading the AppSpec needs the project root, mirror the pattern other CLI commands use (e.g. `dazzle validate`).

- [ ] **Step 2: Surface `is_test` in `status`**

In `status_command`, add the org/tenant `is_test` to the printed output (the deferred Slice-0 nicety). If `status` reads from the `public.tenants` registry, print its `is_test`; the canonical shared-schema status is the `organizations` row — print whichever the command already loads, labelled clearly. Keep the change additive (one extra line).

- [ ] **Step 3: Write a safety-guard unit test (no DB)**

```python
# tests/unit/test_tenant_excise_cli.py
"""The excise CLI refuses a non-test org without --force (RLS Phase E.1)."""

from unittest.mock import MagicMock, patch

import pytest
import typer

from dazzle.cli.tenant import excise_command


def test_excise_refuses_non_test_org_without_force() -> None:
    fake_conn = MagicMock()
    fake_conn.execute.return_value.fetchone.return_value = {"is_test": False, "slug": "prod"}
    with patch("dazzle.cli.tenant._load_appspec", return_value=MagicMock()), patch(
        "dazzle.cli.tenant._resolve_database_url", return_value="postgresql://x"
    ), patch("psycopg.connect") as pc:
        pc.return_value.__enter__.return_value = fake_conn
        with pytest.raises(typer.Exit) as exc:
            excise_command(tenant_id="prod-org", dry_run=False, force=False, database_url="")
    assert exc.value.exit_code == 2
```

> Match `_load_appspec`/`_resolve_database_url` to the real helper names you used in Step 1. If the command body calls them differently, adjust the patch targets; the assertion (exit 2 on non-test + no force) is the invariant.

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_tenant_excise_cli.py -q && python -c "from dazzle.cli.tenant import excise_command; print('import ok')"`
Expected: PASS + import ok.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/cli/tenant.py tests/unit/test_tenant_excise_cli.py
git commit -m "feat(cli): dazzle tenant excise (is_test/--force guard, dry-run) + is_test in status (Phase E.1)"
```

---

## Final verification (before handing off / shipping)

- [ ] `ruff check src/ tests/ --fix && ruff format src/ tests/` — clean
- [ ] `mypy src/dazzle` — clean (CI scope)
- [ ] `pytest tests/ -m "not e2e"` — green (the new unit tests; confirm `test_docs_drift` / CLI-sweep tests still pass with the new `excise` command — they assert the CLI surface)
- [ ] With `TEST_DATABASE_URL="postgresql://localhost:5432/postgres"`: `pytest tests/integration/test_tenant_excision_pg.py -q` — green
- [ ] `/bump patch` + CHANGELOG entry under **Added** (tenant excision) with an **Agent Guidance** note:
  - "`dazzle tenant excise <tenant_id>` (RLS Phase E.1, #1338) atomically deletes a tenant's domain rows (`WHERE tenant_id = X`, children-first via `FKGraph.deletion_order`), memberships, `organizations` row, and orphaned identities, in one transaction as `dazzle_bypass`. Refuses a non-`is_test` org without `--force`; `--dry-run` previews counts. Engine: `dazzle.db.excision.excise_tenant(appspec, tenant_id, *, conn, dry_run)`. Assumes `organizations.id == the domain tenant discriminator` (the canonical invariant). FK cycles raise `ExcisionError`. QA-auth + the DB-enforced containment invariant + `provision_test_tenant` are **Phase E.2** (#1339)."

---

## Forward outline (Phase E.2 — its own plan, #1339)

- **QA-auth + ephemeral provisioning + containment invariant.** `provision_test_tenant(run_id)` (creates a `qa-`-namespaced, `is_test=true` org + seeds a first admin membership) → drives `excise_tenant` for teardown; a self-disabling (`QA_AUTH_SECRET`-gated) hmac-signed mint route (`qa_secure_routes.py`, ~60s replay window); the **DB-enforced containment invariant** — a mint may bind `dazzle.tenant_id` only to an org whose row is `is_test=true` + reserved-namespaced (session→active_membership→organization), making cross-tenant access structurally impossible; adversarial tests + its own ADR. E.1's `excise_tenant` is the teardown primitive.

## Self-review notes

- **Spec coverage (RLS §Phase E excision half + lifecycle §Slice 1):** "DELETE … WHERE tenant_id = X + registry delete, reverse-topo, as dazzle_bypass" → Task 2 engine (domain children-first + root + `organizations` delete). "cascade orphaned identities" → the capture-before/probe-after reap (Task 2). "FKGraph reverse method (generalize creation_order)" → Task 1 `deletion_order`. "`dazzle tenant excise` CLI + the --force/is_test safety guard + is_test in status" → Task 3. "real-PG isolation test (A gone, B untouched, dry-run no-op)" → Task 2 test. QA-auth/containment/provisioning (#1339) explicitly deferred to E.2.
- **Placeholder scan:** engine + CLI carry concrete code. The flagged reconciliations (`parse_dsl` entry, `_load_appspec`/`_resolve_database_url`/`status` URL source in `cli/tenant.py`) are real-codebase confirmations with an explicit "grep the existing command and mirror" instruction + an invariant assertion that doesn't change — not deferred work.
- **Type consistency:** `excise_tenant(appspec, tenant_id, *, conn, dry_run) -> ExcisionResult` and `ExcisionResult(tenant_id, dry_run, deleted: dict[str,int])` are used identically in the engine, the CLI, and both tests. `FKGraph.deletion_order(list[str]) -> list[str] | None` matches `creation_order`'s shape and is consumed once (Task 2). `scoped_entity_names(entities, partition_key)` and `quote_identifier(name)` are used at the anchors the Explore confirmed.
