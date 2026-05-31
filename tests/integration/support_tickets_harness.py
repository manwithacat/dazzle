"""Shared harness for the #1304 context-selector scoping tests.

Boots examples/support_tickets in-process against a disposable PostgreSQL DB,
seeds two agent users plus a deterministic ticket/comment fixture via direct
SQL, and exposes a ``_SupportTicketsApp`` dataclass with a per-role client
factory and the seeded identifiers the tests assert on.

What #1304 is about
-------------------
The ``agent_console`` workspace declares a ``context_selector`` (pick a
``User``; their id becomes ``current_context``) and two regions whose filters
reference that sentinel:

* ``agent_tickets``         — ``source: Ticket``,  ``filter: assigned_to = current_context`` (1-hop)
* ``agent_ticket_comments`` — ``source: Comment``, ``filter: ticket.assigned_to = current_context``
                              (2-hop dotted: Comment -> ticket -> assigned_to)

The region data endpoint is::

    GET /api/workspaces/agent_console/regions/{region}?context_id=<user-uuid>

The page handler reads ``?context_id`` into ``filter_context["current_context"]``
(see ``workspace_region_prelude.py``), and the route generator substitutes it
for the ``current_context`` sentinel in the region filter.  The 2-hop dotted
form is the actual #1304 regression: it must resolve the FK path
``Comment.ticket -> Ticket.assigned_to`` and scope correctly.

Why direct SQL inserts for seeding?
-----------------------------------
The regions are read-only endpoints; the scoping logic lives entirely on the
read path.  Seeding the fixture rows via SQL with deterministic UUIDs gives an
unambiguous expected set (distinct A-vs-B counts) without depending on any
create surface.  The tests exercise the HTTP read path — that is where the
scope substitution is exercised.

Auth model
----------
support_tickets enables session auth.  The Ticket/Comment ``scope:`` rules
grant ``read/list: all`` to the ``agent`` and ``manager`` personas, so an
authenticated agent sees *every* in-scope row — the only filter that narrows
the region is the ``current_context`` predicate.  That is precisely what makes
this a clean #1304 probe: with no per-user row scoping in the way, any
narrowing observed in the response is attributable to ``context_id`` alone.

Each seeded role-user needs two rows that share an email:

* an *auth* ``users`` row (``auth_store.create_user``) carrying the session +
  role list, and
* a *domain* ``User`` entity row (inserted into the ``User`` table) — this row's
  id is what we pass as ``context_id`` and what the tickets are ``assigned_to``.

Table names follow the entity spec ``name`` exactly (``User``, ``Ticket``,
``Comment``) and FK columns are bare-named (``assigned_to``, ``created_by``,
``ticket``, ``author``) — verified against the live schema.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    import httpx

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")

_PASSWORD = "ctx-scope-test-password"  # nosec B105 — scratch DB only
_BASE_URL = "http://support-tickets.local"
_PROJECT_ROOT = Path("examples/support_tickets")

# Distinct, unambiguous fixture cardinalities (A != B so scoping is provable).
N_A_TICKETS = 3  # tickets assigned to AGENT_A
N_B_TICKETS = 5  # tickets assigned to AGENT_B
M_A_COMMENTS = 2  # comments on AGENT_A's tickets
M_B_COMMENTS = 0  # comments on AGENT_B's tickets (2-hop region must return 0)


@dataclass
class _SupportTicketsApp:
    """Per-role client factory plus the deterministic seeded ids the tests use."""

    _transport: Any
    _db_url: str

    # role -> (email, password)
    _creds: dict[str, tuple[str, str]] = field(default_factory=dict)

    # Domain User entity ids — these are the values passed as ?context_id.
    agent_a_id: str = ""
    agent_b_id: str = ""
    manager_id: str = ""

    # Seeded ticket numbers + titles, partitioned by assignee, for HTML asserts.
    agent_a_ticket_numbers: list[str] = field(default_factory=list)
    agent_b_ticket_numbers: list[str] = field(default_factory=list)
    agent_a_ticket_titles: list[str] = field(default_factory=list)
    agent_b_ticket_titles: list[str] = field(default_factory=list)

    # Seeded comment contents, partitioned by the assignee of their ticket.
    agent_a_comment_contents: list[str] = field(default_factory=list)
    agent_b_comment_contents: list[str] = field(default_factory=list)

    def credentials(self, role: str) -> tuple[str, str]:
        return self._creds[role]

    async def client_as(self, role: str) -> httpx.AsyncClient:
        """Return an httpx client authenticated as ``role``.

        Every client rides the same in-process ASGI transport; each call logs
        in fresh so tests never share a cookie jar.
        """
        import httpx

        from dazzle.cli.rbac import _login

        email, password = self.credentials(role)
        client = httpx.AsyncClient(
            transport=self._transport,
            base_url=_BASE_URL,
            follow_redirects=True,
        )
        await _login(client, _BASE_URL, email, password)
        return client


def _mk_id() -> str:
    """Return a new random UUID string."""
    return str(uuid.uuid4())


def _sql_insert(conn: Any, table: str, row: dict[str, Any]) -> None:
    """Insert a single row into ``table``.

    Table + column names are hardcoded entity/field literals from the DSL, never
    user input.  Values go through psycopg %s parameterisation — no value
    interpolation.  Mirrors the invoice_ops harness ``_sql_insert``.
    """
    cols = ", ".join(f'"{k}"' for k in row)
    placeholders = ", ".join("%s" for _ in row)
    sql = f'INSERT INTO "{table}" ({cols}) VALUES ({placeholders})'
    # table + column names are hardcoded constants in this module, not user input;
    # values go through %s parameterisation — no SQL injection vector.
    # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query,python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
    conn.execute(sql, list(row.values()))


async def _seed(app: _SupportTicketsApp, auth_store: Any, db_url: str) -> None:
    """Seed auth users, domain User rows, tickets and comments into the scratch DB.

    Layout (all ids deterministic per run):

    * AGENT_A: ``N_A_TICKETS`` tickets, each with one comment up to ``M_A_COMMENTS``.
    * AGENT_B: ``N_B_TICKETS`` tickets, ``M_B_COMMENTS`` (== 0) comments.
    * MANAGER: the authenticated reader (role=manager → ``read/list: all`` scope),
      so the region response is narrowed only by ``context_id``.

    Tickets require ``created_by`` (NOT NULL FK) — set to the manager.  The
    2-hop region (``ticket.assigned_to = current_context``) discriminates A (2
    comments) from B (0 comments).
    """
    from datetime import UTC, datetime

    import psycopg

    now = datetime.now(UTC)

    # --- auth users (one per role) ---------------------------------------
    for role in ("agent_a", "agent_b", "manager"):
        # AGENT_A / AGENT_B are both the `agent` persona; MANAGER is `manager`.
        persona = "manager" if role == "manager" else "agent"
        email = f"{role}@support-tickets.test"
        if auth_store.get_user_by_email(email) is None:
            auth_store.create_user(email, _PASSWORD, roles=[persona])
        app._creds[role] = (email, _PASSWORD)

    # --- deterministic ids -----------------------------------------------
    agent_a_id = _mk_id()
    agent_b_id = _mk_id()
    manager_id = _mk_id()
    app.agent_a_id = agent_a_id
    app.agent_b_id = agent_b_id
    app.manager_id = manager_id

    with psycopg.connect(db_url, autocommit=True) as conn:
        # --- domain User rows (email must match the auth users) -----------
        _sql_insert(
            conn,
            "User",
            {
                "id": agent_a_id,
                "email": app._creds["agent_a"][0],
                "name": "Agent Alpha",
                "role": "agent",
                "is_active": True,
                "created_at": now,
            },
        )
        _sql_insert(
            conn,
            "User",
            {
                "id": agent_b_id,
                "email": app._creds["agent_b"][0],
                "name": "Agent Bravo",
                "role": "agent",
                "is_active": True,
                "created_at": now,
            },
        )
        _sql_insert(
            conn,
            "User",
            {
                "id": manager_id,
                "email": app._creds["manager"][0],
                "name": "Manager Mike",
                "role": "manager",
                "is_active": True,
                "created_at": now,
            },
        )

        # --- Tickets assigned to AGENT_A ---------------------------------
        a_ticket_ids: list[str] = []
        for i in range(N_A_TICKETS):
            tid = _mk_id()
            a_ticket_ids.append(tid)
            number = f"AAA-{i + 1:03d}"
            title = f"Alpha ticket {i + 1} (assigned A)"
            app.agent_a_ticket_numbers.append(number)
            app.agent_a_ticket_titles.append(title)
            _sql_insert(
                conn,
                "Ticket",
                {
                    "id": tid,
                    "ticket_number": number,
                    "title": title,
                    "description": f"Alpha ticket {i + 1} body",
                    "status": "open",
                    "priority": "medium",
                    "category": "bug",
                    "created_by": manager_id,
                    "assigned_to": agent_a_id,
                    "created_at": now,
                    "updated_at": now,
                },
            )

        # --- Tickets assigned to AGENT_B ---------------------------------
        b_ticket_ids: list[str] = []
        for i in range(N_B_TICKETS):
            tid = _mk_id()
            b_ticket_ids.append(tid)
            number = f"BBB-{i + 1:03d}"
            title = f"Bravo ticket {i + 1} (assigned B)"
            app.agent_b_ticket_numbers.append(number)
            app.agent_b_ticket_titles.append(title)
            _sql_insert(
                conn,
                "Ticket",
                {
                    "id": tid,
                    "ticket_number": number,
                    "title": title,
                    "description": f"Bravo ticket {i + 1} body",
                    "status": "open",
                    "priority": "high",
                    "category": "inquiry",
                    "created_by": manager_id,
                    "assigned_to": agent_b_id,
                    "created_at": now,
                    "updated_at": now,
                },
            )

        # --- Comments on AGENT_A's tickets (M_A_COMMENTS) ----------------
        # Spread across A's tickets so the 2-hop FK path is genuinely walked.
        for i in range(M_A_COMMENTS):
            ticket_id = a_ticket_ids[i % len(a_ticket_ids)]
            content = f"Alpha comment {i + 1} on A ticket"
            app.agent_a_comment_contents.append(content)
            _sql_insert(
                conn,
                "Comment",
                {
                    "id": _mk_id(),
                    "ticket": ticket_id,
                    "author": manager_id,
                    "content": content,
                    "is_internal": False,
                    "created_at": now,
                },
            )

        # --- Comments on AGENT_B's tickets (M_B_COMMENTS == 0) -----------
        for i in range(M_B_COMMENTS):  # pragma: no cover - 0 by design
            ticket_id = b_ticket_ids[i % len(b_ticket_ids)]
            content = f"Bravo comment {i + 1} on B ticket"
            app.agent_b_comment_contents.append(content)
            _sql_insert(
                conn,
                "Comment",
                {
                    "id": _mk_id(),
                    "ticket": ticket_id,
                    "author": manager_id,
                    "content": content,
                    "is_internal": False,
                    "created_at": now,
                },
            )


async def booted_support_tickets() -> AsyncIterator[_SupportTicketsApp]:
    """Boot examples/support_tickets in-process against a disposable DB, seed
    it, and yield a ``_SupportTicketsApp`` exposing ``client_as(role)`` + the
    seeded ids.

    Usage in a pytest fixture::

        @pytest.fixture
        async def app():
            async for a in booted_support_tickets():
                yield a
    """
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL / DATABASE_URL")

    import httpx

    from dazzle.rbac.verifier import (
        _build_asgi_app,
        _DisposableDatabase,
        _probe_transport,
    )

    async with _DisposableDatabase(_PG_URL) as db_url:
        built = _build_asgi_app(_PROJECT_ROOT, db_url)
        auth_store = built.builder.auth_store
        assert auth_store is not None, "support_tickets has auth enabled"

        # raise_app_exceptions=False so a server-side 500 surfaces as a status
        # code instead of aborting the test.
        transport = _probe_transport(httpx.ASGITransport(app=built.app))

        app = _SupportTicketsApp(_transport=transport, _db_url=db_url)
        await _seed(app, auth_store, db_url)
        try:
            yield app
        finally:
            db_manager = getattr(built.builder, "_db_manager", None)
            if db_manager is not None:
                db_manager.close_pool()
