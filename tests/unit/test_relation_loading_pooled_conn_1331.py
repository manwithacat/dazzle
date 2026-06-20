"""Regression gate for GitHub issue #1331.

Relation loading (and grant reads) used `get_persistent_connection()` — a single,
shared, app-lifetime, non-autocommit connection. The relation loader only ever
runs `SELECT`s and never commits, so after a read the shared connection parked
`idle in transaction` holding `ACCESS SHARE` on the tables it touched (e.g.
`Contact`), which blocks `ALTER TABLE` (Alembic migrations) and pins the xmin
horizon (VACUUM bloat). Same class of bug as #1325, on the request path.

Fix (Option B): route relation loading through the *pooled* `db.connection()`
context manager (leased per operation, rolled back on return), and remove the
`conn_factory` fallback from `RelationLoader` so a missing connection fails loud
instead of silently re-leaking.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel, ConfigDict

from dazzle.http.runtime.relation_loader import RelationLoader, RelationRegistry
from dazzle.http.runtime.repository import Repository
from dazzle.http.specs.entity import EntitySpec, FieldSpec, FieldType, ScalarType


def _contact_spec() -> EntitySpec:
    return EntitySpec(
        name="Contact",
        fields=[FieldSpec(name="id", type=FieldType(kind="scalar", scalar_type=ScalarType.UUID))],
    )


class _ContactModel(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str | None = None


_ID = "00000000-0000-0000-0000-000000000001"


def _mock_db_with_pool() -> tuple[MagicMock, MagicMock]:
    """Mock backend whose `connection()` is a context manager yielding `conn`.

    Also exposes `get_persistent_connection()` (as a MagicMock auto-attribute)
    so the test can assert it is *never* called.
    """
    cursor = MagicMock()
    cursor.execute = MagicMock()
    cursor.fetchone = MagicMock(return_value={"id": _ID})
    cursor.fetchall = MagicMock(return_value=[{"id": _ID}])

    conn = MagicMock()
    conn.cursor.return_value = cursor

    db = MagicMock()
    db.placeholder = "%s"
    db.connection.return_value.__enter__.return_value = conn
    db.connection.return_value.__exit__.return_value = False
    return db, conn


def test_load_relations_requires_explicit_conn() -> None:
    """#1331: the conn_factory fallback was removed. load_relations must refuse
    to run without a live conn (rather than silently leasing/leaking a shared
    one) — this is the structural guard that prevents re-introducing the leak."""
    loader = RelationLoader(RelationRegistry(), [])
    with pytest.raises(ValueError, match="requires a live"):
        loader.load_relations("Contact", [{"id": "x"}], ["owner"], conn=None)


def test_relation_loader_no_longer_has_conn_factory() -> None:
    """The loader must not carry a connection factory — owning one is what let
    it reach for the shared persistent connection (#1331)."""
    loader = RelationLoader(RelationRegistry(), [])
    assert not hasattr(loader, "_conn_factory")


@pytest.mark.asyncio
async def test_read_with_include_uses_pooled_conn_not_persistent() -> None:
    """#1331: relation loading on `read(include=...)` must lease the pooled
    `db.connection()` (rolled back on return) and never touch the shared
    `get_persistent_connection()`."""
    db, conn = _mock_db_with_pool()
    loader = MagicMock()
    loader.load_relations = MagicMock(return_value=[{"id": _ID, "owner": None}])

    repo = Repository(
        db_manager=db,
        entity_spec=_contact_spec(),
        model_class=_ContactModel,
        relation_loader=loader,
    )

    await repo.read(_ID, include=["owner"])

    # Relation loading happened on the pooled connection handed in by the
    # `with db.connection()` block...
    loader.load_relations.assert_called_once()
    _, kwargs = loader.load_relations.call_args
    assert kwargs["conn"] is conn
    # ...and the shared, never-committed persistent connection was not used.
    db.get_persistent_connection.assert_not_called()
