# Auth Plan 2a — Membership Lifecycle Event Substrate

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every membership lifecycle change (provision / role-change / suspend / reactivate / remove) emit a typed, durable, tamper-evident event row in the same DB transaction as the mutation — the "complete by construction" compliance-evidence substrate the access-review export (Plan 2b) will query.

**Architecture:** A new append-only `membership_events` table (Alembic `0009` + `_init_db` parity) stores one row per lifecycle change with `roles_before/after` + `status_before/after` + `actor_id`. Each row carries a sha256 hash-chain (`row_hash = sha256(prev_hash || canonical_payload)`), mirroring `audit_log.py`'s integrity scheme, computed inline under a per-transaction Postgres advisory lock so concurrent mutations can't fork the chain. The `AuthStore` membership mutation methods write the mutation and its event in one transaction (durable; never fire-and-forget, never drop-if-full — losing a deprovision event is a control failure).

**Tech Stack:** Python 3.12, psycopg3 (sync, `dict_row`), PostgreSQL (auth store is PG-only, ADR-0008), Alembic (ADR-0017), `hashlib.sha256`, pytest (`e2e`+`postgres` markers for real-PG integration tests).

**Spec:** `docs/superpowers/specs/2026-06-05-auth-identity-model-design.md` §6 (Compliance evidence). This is slice **2a** (lifecycle-event substrate). Slice **2b** (per-org membership snapshots + JML export + taxonomy control mappings + `rbac` report extension) is a follow-on plan that consumes this substrate.

**Scope boundary:** 2a covers the **membership** JML lifecycle only (Provision / Role-change / Deprovision rows of the spec §6 table). Session/authenticate events (login, org-activation) and the control-mapping/export layer are explicitly **out of scope** for 2a.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `src/dazzle/http/runtime/auth/membership_events.py` (**create**) | The `MembershipEvent` dataclass, `MembershipEventType` constants, the `membership_events` DDL constant, canonical-payload + hash-chain helpers, the in-cursor `record_membership_event(cur, ...)` writer, and `verify_membership_event_chain(conn)`. Self-contained; no import cycle with `store.py`. |
| `src/dazzle/http/runtime/auth/store.py` (**modify**) | Add the `membership_events` table to `_init_db`; add a `_transaction()` context manager (atomic multi-statement); wire `create_membership` to emit a `PROVISIONED` event in-transaction; add `update_membership_roles` / `suspend_membership` / `reactivate_membership` / `remove_membership`; add `get_membership_events` query + `verify_membership_event_chain` passthrough. |
| `src/dazzle/http/alembic/versions/0009_membership_events.py` (**create**) | Idempotent migration creating `membership_events` (mirrors `0008_organizations.py`). |
| `tests/unit/test_membership_event_hash.py` (**create**) | Pure-Python tests for canonical payload determinism + chain hashing (no DB). |
| `tests/integration/test_membership_events_pg.py` (**create**) | Real-PG: each mutation writes the right event atomically; the chain verifies and detects tampering; the JML query filters by tenant/identity/time; a removed membership's event survives. |

---

## Task 1: The `membership_events` module (dataclass, constants, DDL, hash helpers)

**Files:**
- Create: `src/dazzle/http/runtime/auth/membership_events.py`
- Test: `tests/unit/test_membership_event_hash.py`

- [ ] **Step 1: Write the failing unit test**

```python
# tests/unit/test_membership_event_hash.py
"""Pure-Python hash-chain helpers for membership_events (auth Plan 2a)."""

from dazzle.http.runtime.auth.membership_events import (
    MembershipEventType,
    _canonical_event_payload,
    compute_event_hash,
)


def _row(**over):
    base = {
        "id": "evt-1",
        "event_type": MembershipEventType.PROVISIONED,
        "membership_id": "m-1",
        "tenant_id": "org-1",
        "identity_id": "u-1",
        "actor_id": None,
        "roles_before": None,
        "roles_after": '["admin"]',
        "status_before": None,
        "status_after": "active",
        "reason": None,
        "created_at": "2026-06-05T00:00:00+00:00",
    }
    base.update(over)
    return base


def test_canonical_payload_is_deterministic_and_excludes_hash_and_seq() -> None:
    row = _row()
    row_with_noise = {**row, "row_hash": "deadbeef", "seq": 42}
    # row_hash and seq must NOT affect the canonical payload.
    assert _canonical_event_payload(row) == _canonical_event_payload(row_with_noise)
    # Deterministic: sorted keys, compact separators.
    assert _canonical_event_payload(row).startswith("{")
    assert '"id":"evt-1"' in _canonical_event_payload(row)


def test_compute_event_hash_chains_on_prev() -> None:
    row = _row()
    h1 = compute_event_hash("", row)
    h2 = compute_event_hash(h1, row)
    assert h1 != h2  # same content, different prev → different hash
    assert len(h1) == 64  # sha256 hexdigest
    # Recomputation is stable.
    assert compute_event_hash("", row) == h1


def test_event_types_are_the_five_jml_kinds() -> None:
    assert MembershipEventType.PROVISIONED == "provisioned"
    assert MembershipEventType.ROLE_CHANGED == "role_changed"
    assert MembershipEventType.SUSPENDED == "suspended"
    assert MembershipEventType.REACTIVATED == "reactivated"
    assert MembershipEventType.REMOVED == "removed"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/unit/test_membership_event_hash.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'dazzle.http.runtime.auth.membership_events'`

- [ ] **Step 3: Create the module**

```python
# src/dazzle/http/runtime/auth/membership_events.py
"""Durable, tamper-evident membership lifecycle events (auth Plan 2a).

Every membership lifecycle change (provision / role-change / suspend / reactivate
/ remove) is recorded as one append-only row in ``membership_events`` — the
"complete by construction" compliance-evidence substrate (spec §6). Each row is
hash-chained (``row_hash = sha256(prev_hash || canonical_payload)``), mirroring
``audit_log.py``'s integrity scheme.

Unlike the high-volume ``_dazzle_audit_log`` access trail (async, drop-if-full),
these events are written **in the same transaction as the mutation** via
``record_membership_event`` — losing a deprovision event would be a control
failure, so they must never be dropped. The chain head read + insert are
serialised by a per-transaction Postgres advisory lock so concurrent mutations
cannot fork the chain.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


class MembershipEventType:
    """The five membership JML (joiner/mover/leaver) lifecycle event kinds."""

    PROVISIONED = "provisioned"  # joiner — membership created
    ROLE_CHANGED = "role_changed"  # mover — roles granted/revoked
    SUSPENDED = "suspended"  # leaver-ish — access paused
    REACTIVATED = "reactivated"  # mover — access restored
    REMOVED = "removed"  # leaver — membership deleted


# Per-transaction advisory-lock key serialising chain-head read + insert. A fixed
# arbitrary 32-bit constant (only the membership_events writer takes this lock).
MEMBERSHIP_EVENTS_LOCK_KEY = 0x6D656D65  # "meme"

# Columns that feed the canonical hash payload, in stable order. ``seq`` (chain
# order) and ``row_hash`` are deliberately excluded — seq is assigned by the DB
# and order is implied by it; row_hash depends on the payload so cannot be an
# input (mirrors audit_log._AUDIT_ROW_COLUMNS).
_EVENT_HASH_COLUMNS: tuple[str, ...] = (
    "id",
    "event_type",
    "membership_id",
    "tenant_id",
    "identity_id",
    "actor_id",
    "roles_before",
    "roles_after",
    "status_before",
    "status_after",
    "reason",
    "created_at",
)

# The full insert column order (adds row_hash; seq is BIGSERIAL, DB-assigned).
_EVENT_INSERT_COLUMNS: tuple[str, ...] = (*_EVENT_HASH_COLUMNS, "row_hash")

MEMBERSHIP_EVENTS_DDL = """
CREATE TABLE IF NOT EXISTS membership_events (
    seq BIGSERIAL UNIQUE,
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    membership_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    identity_id TEXT NOT NULL,
    actor_id TEXT,
    roles_before TEXT,
    roles_after TEXT,
    status_before TEXT,
    status_after TEXT,
    reason TEXT,
    created_at TEXT NOT NULL,
    row_hash TEXT NOT NULL
)
"""

MEMBERSHIP_EVENTS_INDEXES: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS ix_membership_events_tenant ON membership_events(tenant_id, seq)",
    "CREATE INDEX IF NOT EXISTS ix_membership_events_identity ON membership_events(identity_id, seq)",
    "CREATE INDEX IF NOT EXISTS ix_membership_events_membership ON membership_events(membership_id, seq)",
)


@dataclass(frozen=True)
class MembershipEvent:
    """One recorded membership lifecycle change."""

    id: str
    event_type: str
    membership_id: str
    tenant_id: str
    identity_id: str
    actor_id: str | None
    roles_before: list[str] | None
    roles_after: list[str] | None
    status_before: str | None
    status_after: str | None
    reason: str | None
    created_at: datetime
    seq: int | None = None
    row_hash: str | None = None


def _canonical_event_payload(row: dict[str, Any]) -> str:
    """Deterministic hash-input string for an event row.

    ``sort_keys=True``, compact separators, ``default=str``. Only
    ``_EVENT_HASH_COLUMNS`` participate (``seq``/``row_hash`` excluded).
    """
    payload = {k: row[k] for k in _EVENT_HASH_COLUMNS if k in row}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def compute_event_hash(prev_hash: str, row: dict[str, Any]) -> str:
    """``sha256(prev_hash || canonical_payload(row)).hexdigest()`` — chain integrity."""
    return hashlib.sha256((prev_hash + _canonical_event_payload(row)).encode("utf-8")).hexdigest()


def record_membership_event(
    cur: Any,
    *,
    event_type: str,
    membership_id: str,
    tenant_id: str,
    identity_id: str,
    actor_id: str | None = None,
    roles_before: list[str] | None = None,
    roles_after: list[str] | None = None,
    status_before: str | None = None,
    status_after: str | None = None,
    reason: str | None = None,
) -> MembershipEvent:
    """Append one hash-chained event row using ``cur`` (caller's open transaction).

    The caller MUST already hold the membership-events advisory lock in this
    transaction (``SELECT pg_advisory_xact_lock(MEMBERSHIP_EVENTS_LOCK_KEY)``) so
    the chain-head read below is serialised. Writing through the caller's cursor
    makes the event atomic with the mutation — durable, never dropped.
    """
    now = datetime.now(UTC)
    row: dict[str, Any] = {
        "id": secrets.token_urlsafe(18),
        "event_type": event_type,
        "membership_id": membership_id,
        "tenant_id": tenant_id,
        "identity_id": identity_id,
        "actor_id": actor_id,
        "roles_before": json.dumps(roles_before) if roles_before is not None else None,
        "roles_after": json.dumps(roles_after) if roles_after is not None else None,
        "status_before": status_before,
        "status_after": status_after,
        "reason": reason,
        "created_at": now.isoformat(),
    }
    cur.execute("SELECT row_hash FROM membership_events ORDER BY seq DESC LIMIT 1")
    head = cur.fetchone()
    prev_hash = "" if head is None else (head["row_hash"] if isinstance(head, dict) else head[0])
    row["row_hash"] = compute_event_hash(prev_hash or "", row)

    cols = ", ".join(_EVENT_INSERT_COLUMNS)
    placeholders = ", ".join("%s" for _ in _EVENT_INSERT_COLUMNS)
    cur.execute(
        f"INSERT INTO membership_events ({cols}) VALUES ({placeholders})",  # nosemgrep: fixed column constants
        tuple(row[c] for c in _EVENT_INSERT_COLUMNS),
    )
    return MembershipEvent(
        id=row["id"],
        event_type=event_type,
        membership_id=membership_id,
        tenant_id=tenant_id,
        identity_id=identity_id,
        actor_id=actor_id,
        roles_before=roles_before,
        roles_after=roles_after,
        status_before=status_before,
        status_after=status_after,
        reason=reason,
        created_at=now,
        row_hash=row["row_hash"],
    )


@dataclass(frozen=True)
class EventChainResult:
    """Result of verifying the membership_events hash-chain."""

    ok: bool
    total_rows: int
    first_mismatch_id: str | None
    mismatched_count: int


def verify_membership_event_chain(conn: Any) -> EventChainResult:
    """Recompute the chain in ``seq`` order and compare stored vs recomputed hashes."""
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM membership_events ORDER BY seq ASC"  # full scan; low-volume table
    )
    rows = cur.fetchall()
    prev_hash = ""
    mismatched = 0
    first_mismatch: str | None = None
    for row in rows:
        rowd = dict(row)
        expected = compute_event_hash(prev_hash, rowd)
        stored = rowd.get("row_hash")
        if stored != expected:
            mismatched += 1
            if first_mismatch is None:
                first_mismatch = rowd.get("id")
        prev_hash = stored or expected
    return EventChainResult(
        ok=mismatched == 0,
        total_rows=len(rows),
        first_mismatch_id=first_mismatch,
        mismatched_count=mismatched,
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/unit/test_membership_event_hash.py -q`
Expected: PASS (3 tests)

- [ ] **Step 5: Lint + commit**

```bash
ruff check src/dazzle/http/runtime/auth/membership_events.py tests/unit/test_membership_event_hash.py --fix
ruff format src/dazzle/http/runtime/auth/membership_events.py tests/unit/test_membership_event_hash.py
git add src/dazzle/http/runtime/auth/membership_events.py tests/unit/test_membership_event_hash.py
git commit -m "feat(auth): membership_events module — typed lifecycle events + hash chain (Plan 2a)"
```

---

## Task 2: `_init_db` table + `_transaction` helper + emit on `create_membership` + queries

**Files:**
- Modify: `src/dazzle/http/runtime/auth/store.py` (`_init_db` ~line 1015–1033; `create_membership` ~line 714–762; add helpers near `_execute` ~line 1108)
- Test: `tests/integration/test_membership_events_pg.py` (created here; extended in Task 3)

- [ ] **Step 1: Write the failing integration test**

```python
# tests/integration/test_membership_events_pg.py
"""Real-PG proof of the membership lifecycle event substrate (auth Plan 2a)."""

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
def store_url() -> Iterator[str]:
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL/DATABASE_URL")
    admin = _admin_url()
    base, _, _old = admin.rpartition("/")
    scratch = f"dazzle_memevt_{uuid.uuid4().hex[:8]}"
    url = f"{base}/{scratch}"
    with psycopg.connect(admin, autocommit=True) as a:
        a.execute(f'CREATE DATABASE "{scratch}"')  # nosemgrep
    try:
        yield url
    finally:
        with psycopg.connect(admin, autocommit=True) as a:
            a.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname=%s AND pid<>pg_backend_pid()",
                (scratch,),
            )
            a.execute(f'DROP DATABASE IF EXISTS "{scratch}"')  # nosemgrep


def _store(store_url: str):
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=store_url)
    store._init_db()
    return store


def test_create_membership_emits_provisioned_event(store_url: str) -> None:
    store = _store(store_url)
    u = store.create_user(email="a@b.test", password="pw123456", roles=["worker"])
    m = store.create_membership(tenant_id="org-1", identity_id=str(u.id), roles=["admin"])

    events = store.get_membership_events(membership_id=m.id)
    assert len(events) == 1
    e = events[0]
    assert e.event_type == "provisioned"
    assert e.roles_after == ["admin"]
    assert e.status_after == "active"
    assert e.roles_before is None  # joiner has no prior state
    # The chain verifies.
    assert store.verify_membership_event_chain().ok
```

- [ ] **Step 2: Run it to verify it fails**

Run: `TEST_DATABASE_URL="postgresql://localhost:5432/postgres" python -m pytest tests/integration/test_membership_events_pg.py::test_create_membership_emits_provisioned_event -q`
Expected: FAIL — `AttributeError: 'AuthStore' object has no attribute 'get_membership_events'` (and no event written).

- [ ] **Step 3: Add the table to `_init_db`**

In `src/dazzle/http/runtime/auth/store.py`, inside `_init_db`, immediately after the `organizations` table block (the `CREATE TABLE IF NOT EXISTS organizations (...)` ending ~line 1058), add:

```python
            # auth Plan 2a: append-only, hash-chained membership lifecycle events
            # (compliance evidence). Mirrors alembic 0009_membership_events.
            from dazzle.http.runtime.auth.membership_events import (
                MEMBERSHIP_EVENTS_DDL,
                MEMBERSHIP_EVENTS_INDEXES,
            )

            cursor.execute(MEMBERSHIP_EVENTS_DDL)
            for _ix in MEMBERSHIP_EVENTS_INDEXES:
                cursor.execute(_ix)
```

- [ ] **Step 4: Add the `_transaction` helper**

In `store.py`, immediately after `_execute_modify` (~line 1136), add:

```python
    from contextlib import contextmanager as _contextmanager

    @_contextmanager
    def _transaction(self):  # type: ignore[no-untyped-def]
        """Yield a cursor in a single transaction; commit on success, rollback on error.

        Used for mutations that must be atomic with their membership_events row
        (auth Plan 2a) — the mutation and the event INSERT share one commit.
        """
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
```

(Note: `from contextlib import contextmanager` is already valid at module top; if the module does not yet import it, add `from contextlib import contextmanager` to the imports and decorate with `@contextmanager` instead of the inline alias. Prefer the top-level import — check the top of `store.py` and add `from contextlib import contextmanager` there, then use `@contextmanager` on `_transaction`.)

- [ ] **Step 5: Rewrite `create_membership` to emit in-transaction**

Replace the body of `create_membership` (the `self._execute("INSERT INTO memberships ...")` block, ~line 743–761) so the membership INSERT and its `PROVISIONED` event share one transaction under the advisory lock. The method keeps its signature and the existing `get_user_by_id` guard:

```python
    def create_membership(
        self,
        *,
        tenant_id: str,
        identity_id: str,
        roles: list[str] | None = None,
        status: str = "active",
        invited_by: str | None = None,
        actor_id: str | None = None,
        reason: str | None = None,
    ) -> MembershipRecord:
        """Create a membership (identity x org x roles) + emit a PROVISIONED event.

        Raises ``ValueError`` if ``identity_id`` does not name an existing user —
        there is no DB foreign key (the auth tables are not in the Alembic chain;
        see migration 0007), so this is the integrity guard against orphan
        memberships / a mistyped identity. The membership row and its lifecycle
        event are written in ONE transaction (auth Plan 2a — durable evidence).
        """
        import json

        from dazzle.http.runtime.auth.membership_events import (
            MEMBERSHIP_EVENTS_LOCK_KEY,
            MembershipEventType,
            record_membership_event,
        )

        if self.get_user_by_id(UUID(identity_id)) is None:
            raise ValueError(f"cannot create membership: no user with id {identity_id!r}")

        membership = MembershipRecord(
            id=secrets.token_urlsafe(24),
            tenant_id=tenant_id,
            identity_id=identity_id,
            roles=roles or [],
            status=status,
            invited_by=invited_by,
        )
        with self._transaction() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (MEMBERSHIP_EVENTS_LOCK_KEY,))
            cur.execute(
                """
                INSERT INTO memberships
                    (id, tenant_id, identity_id, roles, status, invited_by,
                     joined_at, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    membership.id,
                    membership.tenant_id,
                    membership.identity_id,
                    json.dumps(membership.roles),
                    membership.status,
                    membership.invited_by,
                    membership.joined_at.isoformat(),
                    membership.created_at.isoformat(),
                    membership.updated_at.isoformat(),
                ),
            )
            record_membership_event(
                cur,
                event_type=MembershipEventType.PROVISIONED,
                membership_id=membership.id,
                tenant_id=membership.tenant_id,
                identity_id=membership.identity_id,
                actor_id=actor_id,
                roles_after=membership.roles,
                status_after=membership.status,
                reason=reason,
            )
        return membership
```

- [ ] **Step 6: Add `get_membership_events` + `verify_membership_event_chain` + `_row_to_event`**

In `store.py`, after `get_memberships_for_identity` (~line 773), add:

```python
    def _row_to_event(self, row: dict[str, Any]) -> "MembershipEvent":  # noqa: F821
        import json

        from dazzle.http.runtime.auth.membership_events import MembershipEvent

        return MembershipEvent(
            id=row["id"],
            event_type=row["event_type"],
            membership_id=row["membership_id"],
            tenant_id=row["tenant_id"],
            identity_id=row["identity_id"],
            actor_id=row.get("actor_id"),
            roles_before=json.loads(row["roles_before"]) if row.get("roles_before") else None,
            roles_after=json.loads(row["roles_after"]) if row.get("roles_after") else None,
            status_before=row.get("status_before"),
            status_after=row.get("status_after"),
            reason=row.get("reason"),
            created_at=datetime.fromisoformat(row["created_at"]),
            seq=row.get("seq"),
            row_hash=row.get("row_hash"),
        )

    def get_membership_events(
        self,
        *,
        tenant_id: str | None = None,
        identity_id: str | None = None,
        membership_id: str | None = None,
        since: str | None = None,
        until: str | None = None,
    ) -> list["MembershipEvent"]:  # noqa: F821
        """Return the JML event stream, ordered by seq, optionally filtered.

        ``since``/``until`` are ISO-8601 strings compared against ``created_at``
        (TEXT, ISO-8601 sorts lexically). All filters AND together.
        """
        clauses: list[str] = []
        params: list[object] = []
        if tenant_id is not None:
            clauses.append("tenant_id = %s")
            params.append(tenant_id)
        if identity_id is not None:
            clauses.append("identity_id = %s")
            params.append(identity_id)
        if membership_id is not None:
            clauses.append("membership_id = %s")
            params.append(membership_id)
        if since is not None:
            clauses.append("created_at >= %s")
            params.append(since)
        if until is not None:
            clauses.append("created_at <= %s")
            params.append(until)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = self._execute(
            f"SELECT * FROM membership_events{where} ORDER BY seq ASC",  # nosemgrep: parameterised filters, fixed columns
            tuple(params),
        )
        return [self._row_to_event(r) for r in rows]

    def verify_membership_event_chain(self) -> "EventChainResult":  # noqa: F821
        """Verify the append-only membership_events hash-chain (tamper-evidence)."""
        from dazzle.http.runtime.auth.membership_events import (
            verify_membership_event_chain as _verify,
        )

        conn = self._get_connection()
        try:
            return _verify(conn)
        finally:
            conn.close()
```

- [ ] **Step 7: Run the test to verify it passes**

Run: `TEST_DATABASE_URL="postgresql://localhost:5432/postgres" python -m pytest tests/integration/test_membership_events_pg.py::test_create_membership_emits_provisioned_event -q`
Expected: PASS

- [ ] **Step 8: Lint + commit**

```bash
ruff check src/dazzle/http/runtime/auth/store.py tests/integration/test_membership_events_pg.py --fix
ruff format src/dazzle/http/runtime/auth/store.py tests/integration/test_membership_events_pg.py
git add src/dazzle/http/runtime/auth/store.py tests/integration/test_membership_events_pg.py
git commit -m "feat(auth): membership_events table + emit on create + JML query (Plan 2a)"
```

---

## Task 3: Mutation methods — role change, suspend, reactivate, remove

**Files:**
- Modify: `src/dazzle/http/runtime/auth/store.py` (add methods after `create_membership`)
- Test: `tests/integration/test_membership_events_pg.py` (extend)

- [ ] **Step 1: Write the failing tests**

Append to `tests/integration/test_membership_events_pg.py`:

```python
def test_role_change_records_before_and_after(store_url: str) -> None:
    store = _store(store_url)
    u = store.create_user(email="a@b.test", password="pw123456", roles=["worker"])
    m = store.create_membership(tenant_id="org-1", identity_id=str(u.id), roles=["member"])

    updated = store.update_membership_roles(m.id, ["member", "approver"], actor_id="admin-1")
    assert updated is not None
    assert updated.roles == ["member", "approver"]

    events = store.get_membership_events(membership_id=m.id)
    assert [e.event_type for e in events] == ["provisioned", "role_changed"]
    rc = events[1]
    assert rc.roles_before == ["member"]
    assert rc.roles_after == ["member", "approver"]
    assert rc.actor_id == "admin-1"
    assert store.verify_membership_event_chain().ok


def test_suspend_reactivate_record_status_transitions(store_url: str) -> None:
    store = _store(store_url)
    u = store.create_user(email="a@b.test", password="pw123456", roles=["worker"])
    m = store.create_membership(tenant_id="org-1", identity_id=str(u.id), roles=["member"])

    store.suspend_membership(m.id, actor_id="admin-1", reason="offboarding")
    store.reactivate_membership(m.id, actor_id="admin-1")

    events = store.get_membership_events(membership_id=m.id)
    assert [e.event_type for e in events] == ["provisioned", "suspended", "reactivated"]
    assert events[1].status_before == "active" and events[1].status_after == "suspended"
    assert events[1].reason == "offboarding"
    assert events[2].status_before == "suspended" and events[2].status_after == "active"
    # The current membership row reflects the final state.
    assert store.get_membership(m.id).status == "active"


def test_suspend_when_already_suspended_is_noop_no_duplicate_event(store_url: str) -> None:
    store = _store(store_url)
    u = store.create_user(email="a@b.test", password="pw123456", roles=["worker"])
    m = store.create_membership(tenant_id="org-1", identity_id=str(u.id), roles=["member"])
    store.suspend_membership(m.id, actor_id="admin-1")
    store.suspend_membership(m.id, actor_id="admin-1")  # no transition
    types = [e.event_type for e in store.get_membership_events(membership_id=m.id)]
    assert types == ["provisioned", "suspended"]  # only one suspend event


def test_remove_membership_deletes_row_but_event_survives(store_url: str) -> None:
    store = _store(store_url)
    u = store.create_user(email="a@b.test", password="pw123456", roles=["worker"])
    m = store.create_membership(tenant_id="org-1", identity_id=str(u.id), roles=["member"])

    assert store.remove_membership(m.id, actor_id="admin-1", reason="left company") is True
    assert store.get_membership(m.id) is None  # current state gone

    events = store.get_membership_events(identity_id=str(u.id))
    assert [e.event_type for e in events] == ["provisioned", "removed"]
    assert events[1].status_before == "active" and events[1].status_after == "removed"
    assert store.verify_membership_event_chain().ok  # leaver evidence survives + chains


def test_jml_query_filters_by_tenant_and_time(store_url: str) -> None:
    store = _store(store_url)
    ua = store.create_user(email="a@b.test", password="pw123456", roles=["worker"])
    ub = store.create_user(email="b@b.test", password="pw123456", roles=["worker"])
    store.create_membership(tenant_id="org-A", identity_id=str(ua.id), roles=["member"])
    store.create_membership(tenant_id="org-B", identity_id=str(ub.id), roles=["member"])

    a_events = store.get_membership_events(tenant_id="org-A")
    assert len(a_events) == 1 and a_events[0].tenant_id == "org-A"


def test_tampering_a_row_breaks_the_chain(store_url: str) -> None:
    store = _store(store_url)
    u = store.create_user(email="a@b.test", password="pw123456", roles=["worker"])
    m = store.create_membership(tenant_id="org-1", identity_id=str(u.id), roles=["member"])
    store.update_membership_roles(m.id, ["member", "approver"], actor_id="admin-1")

    assert store.verify_membership_event_chain().ok
    # Tamper: rewrite a stored event's roles_after without recomputing the hash.
    with psycopg.connect(store_url, autocommit=True) as c:
        c.execute(
            "UPDATE membership_events SET roles_after = %s WHERE event_type = 'role_changed'",
            ('["member","superadmin"]',),
        )
    result = store.verify_membership_event_chain()
    assert result.ok is False
    assert result.mismatched_count >= 1
```

- [ ] **Step 2: Run them to verify they fail**

Run: `TEST_DATABASE_URL="postgresql://localhost:5432/postgres" python -m pytest tests/integration/test_membership_events_pg.py -q`
Expected: FAIL — `AttributeError: 'AuthStore' object has no attribute 'update_membership_roles'`

- [ ] **Step 3: Add the four mutation methods**

In `store.py`, after `create_membership` (~line 762), add. Each reads current state in-transaction (consistent), mutates, and records the event under the advisory lock:

```python
    def update_membership_roles(
        self,
        membership_id: str,
        roles: list[str],
        *,
        actor_id: str | None = None,
        reason: str | None = None,
    ) -> MembershipRecord | None:
        """Grant/revoke roles on a membership (mover) + emit a ROLE_CHANGED event.

        Returns the updated record, or ``None`` if no such membership.
        """
        import json

        from dazzle.http.runtime.auth.membership_events import (
            MEMBERSHIP_EVENTS_LOCK_KEY,
            MembershipEventType,
            record_membership_event,
        )

        now = datetime.now(UTC).isoformat()
        with self._transaction() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (MEMBERSHIP_EVENTS_LOCK_KEY,))
            cur.execute("SELECT * FROM memberships WHERE id = %s", (membership_id,))
            row = cur.fetchone()
            if row is None:
                return None
            roles_before = json.loads(row["roles"]) if row.get("roles") else []
            cur.execute(
                "UPDATE memberships SET roles = %s, updated_at = %s WHERE id = %s",
                (json.dumps(roles), now, membership_id),
            )
            record_membership_event(
                cur,
                event_type=MembershipEventType.ROLE_CHANGED,
                membership_id=membership_id,
                tenant_id=row["tenant_id"],
                identity_id=row["identity_id"],
                actor_id=actor_id,
                roles_before=roles_before,
                roles_after=roles,
                reason=reason,
            )
        return self.get_membership(membership_id)

    def _transition_membership_status(
        self,
        membership_id: str,
        *,
        from_status: str,
        to_status: str,
        event_type: str,
        actor_id: str | None,
        reason: str | None,
    ) -> MembershipRecord | None:
        """Shared suspend/reactivate body: status transition + lifecycle event.

        No-op (no event) when the membership is not in ``from_status`` — keeps the
        evidence stream free of duplicate/contradictory transitions.
        """
        from dazzle.http.runtime.auth.membership_events import (
            MEMBERSHIP_EVENTS_LOCK_KEY,
            record_membership_event,
        )

        now = datetime.now(UTC).isoformat()
        with self._transaction() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (MEMBERSHIP_EVENTS_LOCK_KEY,))
            cur.execute("SELECT * FROM memberships WHERE id = %s", (membership_id,))
            row = cur.fetchone()
            if row is None or row["status"] != from_status:
                return None  # not found, or no transition → no event
            cur.execute(
                "UPDATE memberships SET status = %s, updated_at = %s WHERE id = %s",
                (to_status, now, membership_id),
            )
            record_membership_event(
                cur,
                event_type=event_type,
                membership_id=membership_id,
                tenant_id=row["tenant_id"],
                identity_id=row["identity_id"],
                actor_id=actor_id,
                status_before=from_status,
                status_after=to_status,
                reason=reason,
            )
        return self.get_membership(membership_id)

    def suspend_membership(
        self, membership_id: str, *, actor_id: str | None = None, reason: str | None = None
    ) -> MembershipRecord | None:
        """Suspend an active membership (leaver-ish) + emit a SUSPENDED event."""
        from dazzle.http.runtime.auth.membership_events import MembershipEventType

        return self._transition_membership_status(
            membership_id,
            from_status="active",
            to_status="suspended",
            event_type=MembershipEventType.SUSPENDED,
            actor_id=actor_id,
            reason=reason,
        )

    def reactivate_membership(
        self, membership_id: str, *, actor_id: str | None = None, reason: str | None = None
    ) -> MembershipRecord | None:
        """Reactivate a suspended membership (mover) + emit a REACTIVATED event."""
        from dazzle.http.runtime.auth.membership_events import MembershipEventType

        return self._transition_membership_status(
            membership_id,
            from_status="suspended",
            to_status="active",
            event_type=MembershipEventType.REACTIVATED,
            actor_id=actor_id,
            reason=reason,
        )

    def remove_membership(
        self, membership_id: str, *, actor_id: str | None = None, reason: str | None = None
    ) -> bool:
        """Delete a membership (leaver) + emit a REMOVED event.

        The ``memberships`` row is deleted (current-state), but the REMOVED event
        persists in ``membership_events`` — the leaver evidence survives. Returns
        ``True`` if a membership was deleted, ``False`` if it did not exist.
        """
        from dazzle.http.runtime.auth.membership_events import (
            MEMBERSHIP_EVENTS_LOCK_KEY,
            MembershipEventType,
            record_membership_event,
        )

        with self._transaction() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (MEMBERSHIP_EVENTS_LOCK_KEY,))
            cur.execute("SELECT * FROM memberships WHERE id = %s", (membership_id,))
            row = cur.fetchone()
            if row is None:
                return False
            cur.execute("DELETE FROM memberships WHERE id = %s", (membership_id,))
            record_membership_event(
                cur,
                event_type=MembershipEventType.REMOVED,
                membership_id=membership_id,
                tenant_id=row["tenant_id"],
                identity_id=row["identity_id"],
                actor_id=actor_id,
                status_before=row["status"],
                status_after="removed",
                reason=reason,
            )
        return True
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `TEST_DATABASE_URL="postgresql://localhost:5432/postgres" python -m pytest tests/integration/test_membership_events_pg.py -q`
Expected: PASS (all 7 tests)

- [ ] **Step 5: Lint + commit**

```bash
ruff check src/dazzle/http/runtime/auth/store.py tests/integration/test_membership_events_pg.py --fix
ruff format src/dazzle/http/runtime/auth/store.py tests/integration/test_membership_events_pg.py
git add src/dazzle/http/runtime/auth/store.py tests/integration/test_membership_events_pg.py
git commit -m "feat(auth): membership role-change/suspend/reactivate/remove + lifecycle events (Plan 2a)"
```

---

## Task 4: Alembic migration `0009_membership_events`

**Files:**
- Create: `src/dazzle/http/alembic/versions/0009_membership_events.py`
- Test: `tests/integration/test_membership_events_pg.py` (add a migration-applies test)

- [ ] **Step 1: Write the failing test**

Append to `tests/integration/test_membership_events_pg.py`:

```python
def test_migration_0009_creates_membership_events(store_url: str) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", "src/dazzle/http/alembic")
    cfg.set_main_option("sqlalchemy.url", store_url.replace("postgresql://", "postgresql+psycopg://"))
    command.upgrade(cfg, "0009_membership_events")

    with psycopg.connect(store_url) as c:
        ok = c.execute(
            "SELECT to_regclass('public.membership_events') IS NOT NULL"
        ).fetchone()[0]
    assert ok is True
```

- [ ] **Step 2: Run it to verify it fails**

Run: `TEST_DATABASE_URL="postgresql://localhost:5432/postgres" python -m pytest tests/integration/test_membership_events_pg.py::test_migration_0009_creates_membership_events -q`
Expected: FAIL — `KeyError`/`CommandError`: revision `0009_membership_events` not found.

- [ ] **Step 3: Create the migration (mirrors `0008_organizations.py`)**

```python
# src/dazzle/http/alembic/versions/0009_membership_events.py
"""Add membership_events table (auth Plan 2a — lifecycle compliance evidence).

Append-only, hash-chained record of membership JML changes (provision /
role-change / suspend / reactivate / remove). Written in the same transaction as
the mutation by the auth store (durable; must-not-drop). Idempotent: guards on
table presence so the dev `_init_db` create path and this migration are
interchangeable (mirrors 0007/0008). No DB FK from membership_id/identity_id (the
auth tables are not in the Alembic-managed DSL metadata; joins enforced in store).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "0009_membership_events"
down_revision = "0008_organizations"
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    return sa_inspect(op.get_bind()).has_table(table)


def upgrade() -> None:
    if not _has_table("membership_events"):
        op.create_table(
            "membership_events",
            sa.Column("seq", sa.BigInteger(), sa.Identity(always=True), unique=True),
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("event_type", sa.Text(), nullable=False),
            sa.Column("membership_id", sa.Text(), nullable=False),
            sa.Column("tenant_id", sa.Text(), nullable=False),
            sa.Column("identity_id", sa.Text(), nullable=False),
            sa.Column("actor_id", sa.Text(), nullable=True),
            sa.Column("roles_before", sa.Text(), nullable=True),
            sa.Column("roles_after", sa.Text(), nullable=True),
            sa.Column("status_before", sa.Text(), nullable=True),
            sa.Column("status_after", sa.Text(), nullable=True),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("row_hash", sa.Text(), nullable=False),
        )
        op.create_index(
            "ix_membership_events_tenant", "membership_events", ["tenant_id", "seq"]
        )
        op.create_index(
            "ix_membership_events_identity", "membership_events", ["identity_id", "seq"]
        )
        op.create_index(
            "ix_membership_events_membership", "membership_events", ["membership_id", "seq"]
        )


def downgrade() -> None:
    if _has_table("membership_events"):
        op.drop_table("membership_events")
```

**Note on the `seq`/`Identity` vs `BIGSERIAL` parity:** the `_init_db` DDL uses `seq BIGSERIAL UNIQUE` and `id TEXT PRIMARY KEY`; the migration uses `sa.BigInteger() + sa.Identity()` (PG renders both as an identity/serial). Both yield a DB-assigned monotonic `seq` and a TEXT pk — functionally identical. If the drift test `tests/unit/test_*_drift.py` or a schema-parity check flags a difference, align the migration column types to the `_init_db` DDL (TEXT/serial), not the reverse.

- [ ] **Step 4: Run the test to verify it passes**

Run: `TEST_DATABASE_URL="postgresql://localhost:5432/postgres" python -m pytest tests/integration/test_membership_events_pg.py::test_migration_0009_creates_membership_events -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/http/alembic/versions/0009_membership_events.py tests/integration/test_membership_events_pg.py
git commit -m "feat(auth): alembic 0009 membership_events table (Plan 2a)"
```

---

## Task 5: Full verification + regression sweep

**Files:** none (verification only)

- [ ] **Step 1: Run the full membership_events integration suite**

Run: `TEST_DATABASE_URL="postgresql://localhost:5432/postgres" python -m pytest tests/integration/test_membership_events_pg.py -q`
Expected: PASS (all tests)

- [ ] **Step 2: Run the auth/membership regression that touches `create_membership`**

`create_membership` now uses `_transaction` + writes an event. Confirm the existing membership/migrate/excision/activation suites still pass (they call `create_membership`):

Run:
```bash
TEST_DATABASE_URL="postgresql://localhost:5432/postgres" python -m pytest \
  tests/integration/test_auth_membership_pg.py \
  tests/integration/test_auth_migrate_pg.py \
  tests/integration/test_membership_rls_activation_pg.py \
  tests/integration/test_tenant_excision_pg.py \
  tests/integration/test_qa_auth_containment_pg.py -q
```
Expected: PASS (no regression from the create_membership transaction change).

- [ ] **Step 3: Run the full unit slice + mypy**

Run:
```bash
mypy src/dazzle
python -m pytest tests/ -m "not e2e" -q
```
Expected: mypy clean; full unit slice green. (Watch for any test that mocks `AuthStore._execute` and calls `create_membership` — it now uses `_transaction`; if such a unit test exists, update it to provide a `_transaction` cursor mock or move it to the PG path.)

- [ ] **Step 4: Commit any regression fixes**

```bash
git add -A
git commit -m "test(auth): adapt callers to create_membership transaction + lifecycle events (Plan 2a)"
```

---

## Task 6: Adversarial review checkpoint (MANDATORY — security-sensitive)

**Files:** none (review only)

- [ ] **Step 1: Dispatch an independent adversarial review** (`pr-review-toolkit:silent-failure-hunter` or a fresh reviewer) over the 2a diff with this attack brief:
  - **Durability / must-not-drop:** can any mutation path commit the membership change but NOT the event (or vice versa)? Is the event truly in the same transaction? Does a failure roll back both?
  - **Chain integrity under concurrency:** can two concurrent mutations read the same chain head and fork the chain? Is the advisory lock held for the whole head-read+insert in every writer? Is the lock key consistent everywhere?
  - **Tamper-evidence:** is `row_hash` excluded from its own payload? Does `seq` exclusion weaken anything? Can a row be deleted mid-chain without detection (note: append-only — document the deletion gap if real)?
  - **Canonical payload determinism:** roles serialised consistently (order)? `None` vs `[]` vs `"[]"` handled so the hash is stable across write/verify?
  - **Silent failure:** do the mutations swallow errors? Does a missing membership return `None`/`False` cleanly vs raising? Is the `record_membership_event` cursor always the transaction's cursor (never a fresh autocommit one)?
  - **Injection:** `get_membership_events` filter composition — parameterised, no string interpolation of values?
  - **Regression:** does the `create_membership` signature change (new `actor_id`/`reason` kwargs) break any caller? Are they keyword-only with defaults?

- [ ] **Step 2: Triage findings.** Fix any CRITICAL/HIGH inline; re-run the integration suite after each fix. Record what was found + fixed.

- [ ] **Step 3: Commit hardening**

```bash
git add -A
git commit -m "fix(auth): Plan 2a adversarial review hardening"
```

---

## Task 7: CHANGELOG + ship

**Files:**
- Modify: `CHANGELOG.md`
- Modify: version-line files (via `/bump patch`)

- [ ] **Step 1: Add a CHANGELOG `[Unreleased]` entry** under `### Added`:

```markdown
- **Auth Plan 2a — membership lifecycle event substrate (compliance evidence)** (plan `docs/superpowers/plans/2026-06-05-auth-plan-2a-membership-lifecycle-events.md`). Every membership lifecycle change (provision / role-change / suspend / reactivate / remove) now writes a typed, durable, hash-chained row to a new append-only `membership_events` table **in the same transaction as the mutation** — the "complete by construction" access-evidence substrate (spec §6). New store methods `update_membership_roles`, `suspend_membership`, `reactivate_membership`, `remove_membership` (each emits its JML event; `create_membership` emits `provisioned`), a `get_membership_events` JML query, and `verify_membership_event_chain` tamper-evidence check. The chain (`row_hash = sha256(prev_hash ‖ canonical_payload)`, mirroring the audit-log integrity scheme) is computed inline under a per-transaction Postgres advisory lock so concurrent mutations cannot fork it. Distinct from the high-volume drop-if-full `_dazzle_audit_log` access trail — a deprovision event must never be lost. Alembic `0009_membership_events`. Real-PG proofs in `tests/integration/test_membership_events_pg.py` (atomic emission, status/role transitions, removed-membership evidence survival, JML filtering, tamper detection). **Slice 2b** (per-org membership snapshots + JML export + SOC 2/ISO control mappings + `rbac` report extension) follows.
```

Add a `### Agent Guidance` bullet: membership mutations must go through the store methods (not raw SQL) so the lifecycle event is emitted; `membership_events` is append-only + hash-chained — never UPDATE/DELETE it; `dazzle auth migrate` / provisioning emit `provisioned` events for free.

- [ ] **Step 2: Bump + ship** — `/bump patch`, then `/ship` (runs ruff + mypy + drift/policy gates + docs build; commit + tag + push).

---

## Self-Review

**1. Spec coverage (§6):** Provision → `PROVISIONED` (create_membership) ✓. Role change → `ROLE_CHANGED` (update_membership_roles) ✓. Deprovision → `SUSPENDED`/`REMOVED` (suspend/remove) ✓. "Membership table *is* the access matrix" + "event stream = every access change" → `memberships` (current state) + `membership_events` (JML stream via `get_membership_events`) ✓. "append-only / tamper-evident audit trail" → hash-chain + `verify_membership_event_chain` ✓. "framework concern at the model boundary (incomplete if author-wired)" → emission inside the store mutation methods, not author-wired ✓. **Out of 2a scope (deferred to 2b):** Authenticate (session/login) events, Privileged-use events, Connection-lifecycle events, control mappings, access-review export — all explicitly marked out of scope.

**2. Placeholder scan:** No TBD/TODO; every code step has full code; tests have concrete assertions. ✓

**3. Type consistency:** `MembershipEvent` fields match between the dataclass (Task 1), `_row_to_event` (Task 2), and the tests (Tasks 2–3). `record_membership_event` kwargs match the call sites in `create_membership`/`update_membership_roles`/`_transition_membership_status`/`remove_membership`. `MembershipEventType` constants match the test assertions (`provisioned`/`role_changed`/`suspended`/`reactivated`/`removed`). `_EVENT_INSERT_COLUMNS = _EVENT_HASH_COLUMNS + ("row_hash",)` and the INSERT uses exactly those. `verify_membership_event_chain` returns `EventChainResult` (Task 1) used by the store passthrough (Task 2) and the tamper test (Task 3). ✓

**Open risk flagged for execution:** the migration's `sa.Identity()` vs `_init_db`'s `BIGSERIAL` — if a schema-parity/drift gate compares them, align the migration to the DDL (noted in Task 4 Step 3). Confirm `to_regclass` is available (PG ≥ 9.4 — yes) for the migration test.
