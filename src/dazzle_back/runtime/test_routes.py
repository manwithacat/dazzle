"""
Test routes for E2E testing.

Provides /__test__/* endpoints for seeding fixtures, resetting data,
and capturing database snapshots.

These endpoints are only available when test mode is enabled.
When ``DAZZLE_TEST_SECRET`` is set, all routes require the
``X-Test-Secret`` header to match (#458).
"""

import logging
import os
import re
from typing import Any

try:
    from fastapi import APIRouter, Depends, HTTPException, Request

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    APIRouter = None  # type: ignore[misc, assignment]
    Depends = None  # type: ignore[misc, assignment]
    HTTPException = None  # type: ignore[misc, assignment]
    Request = None  # type: ignore[misc, assignment]

from pydantic import BaseModel

from dazzle_back.runtime.repository import DatabaseManager, SQLiteRepository
from dazzle_back.specs.entity import EntitySpec

logger = logging.getLogger(__name__)

# Identifier pattern: letters, digits, underscores only (SQL-safe)
_SAFE_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class _EntitySQL:
    """Pre-computed SQL statements for a known entity table.

    All SQL is built once at router creation time from validated entity
    names — no string formatting happens at request time.
    """

    __slots__ = ("name", "select_all", "select_count", "delete_all", "delete_by_id")

    def __init__(self, name: str) -> None:
        if not _SAFE_IDENT_RE.match(name):
            raise ValueError("Invalid entity name: " + name)
        quoted = '"' + name + '"'
        self.name = name
        self.select_all = "SELECT * FROM " + quoted
        self.select_count = "SELECT COUNT(*) FROM " + quoted
        self.delete_all = "DELETE FROM " + quoted
        self.delete_by_id = "DELETE FROM " + quoted + " WHERE id = %s"


# =============================================================================
# Request/Response Models
# =============================================================================


class FixtureData(BaseModel):
    """Fixture data for seeding."""

    id: str
    entity: str
    data: dict[str, Any]
    refs: dict[str, str] | None = None


class SeedRequest(BaseModel):
    """Request to seed fixtures."""

    fixtures: list[FixtureData]


class SeedResponse(BaseModel):
    """Response from seeding fixtures."""

    created: dict[str, Any]
    """Mapping from fixture ID to created entity data."""


class SnapshotResponse(BaseModel):
    """Database snapshot response."""

    entities: dict[str, list[dict[str, Any]]]
    """Mapping from entity name to list of records."""


class AuthenticateRequest(BaseModel):
    """Test authentication request."""

    username: str | None = None
    password: str | None = None
    role: str | None = None


class AuthenticateResponse(BaseModel):
    """Test authentication response."""

    user_id: str
    username: str
    role: str
    session_token: str
    token: str = ""  # Alias for session_token (used by DazzleClient)


# =============================================================================
# Test Routes
# =============================================================================


def create_test_routes(
    db_manager: DatabaseManager,
    repositories: dict[str, SQLiteRepository[Any]],
    entities: list[EntitySpec],
    auth_store: Any = None,
    personas: list[dict[str, Any]] | None = None,
) -> APIRouter:
    """
    Create test routes for E2E testing.

    Args:
        db_manager: Database manager instance
        repositories: Dictionary of repositories by entity name
        entities: List of entity specifications
        auth_store: Optional AuthStore for creating real test sessions
        personas: Optional list of persona configurations for demo user recreation

    Returns:
        APIRouter with test endpoints

    Raises:
        RuntimeError: If FastAPI is not available
    """
    if not FASTAPI_AVAILABLE:
        raise RuntimeError(
            "FastAPI is required for test routes. Install it with: pip install fastapi"
        )

    # Pre-compute SQL statements from validated entity names (startup-time only)
    entity_sql: dict[str, _EntitySQL] = {e.name: _EntitySQL(e.name) for e in entities}

    # --- Authentication dependency ---
    # When DAZZLE_TEST_SECRET is set, require X-Test-Secret header.
    # When unset, test routes are open (backward compat for local dev).
    test_secret = os.environ.get("DAZZLE_TEST_SECRET", "")

    async def _verify_test_secret(request: Request) -> None:  # type: ignore[valid-type]
        if not test_secret:
            return
        header_val = request.headers.get("X-Test-Secret", "")
        if header_val != test_secret:
            raise HTTPException(
                status_code=403,
                detail="Invalid or missing X-Test-Secret header",
            )

    router = APIRouter(
        prefix="/__test__",
        tags=["Testing"],
        dependencies=[Depends(_verify_test_secret)],
    )

    @router.post("/seed", response_model=SeedResponse)
    async def seed_fixtures(request: SeedRequest) -> SeedResponse:
        """
        Seed test fixtures into the database.

        Creates entities from fixture specifications, resolving references
        between fixtures.
        """
        import uuid

        created: dict[str, Any] = {}
        id_mapping: dict[str, str] = {}  # fixture_id -> actual entity id

        # First pass: generate IDs for all fixtures
        for fixture in request.fixtures:
            if "id" in fixture.data:
                entity_id = fixture.data["id"]
            else:
                entity_id = str(uuid.uuid4())
            id_mapping[fixture.id] = entity_id

        # Second pass: create entities with resolved references
        for fixture in request.fixtures:
            entity_name = fixture.entity
            repo = repositories.get(entity_name)

            if not repo:
                raise HTTPException(
                    status_code=400,
                    detail="Unknown entity: " + entity_name,
                )

            # Prepare data — filter to known entity fields to avoid
            # SQL errors from stale or incorrect fixture schemas
            known_fields = set(repo._field_types) | {"id"}
            data = {k: v for k, v in fixture.data.items() if k in known_fields}

            # Add ID if not present
            if "id" not in data:
                data["id"] = id_mapping[fixture.id]

            # Resolve references
            if fixture.refs:
                for field_name, ref_fixture_id in fixture.refs.items():
                    if ref_fixture_id in id_mapping:
                        data[field_name] = id_mapping[ref_fixture_id]

            # Create entity
            try:
                entity = await repo.create(data)
                created[fixture.id] = entity.model_dump() if hasattr(entity, "model_dump") else data
            except Exception as e:
                logger.error("Failed to create %s: %s", entity_name, e)
                raise HTTPException(
                    status_code=400,
                    detail=f"Failed to create {entity_name}: {e}",
                )

        return SeedResponse(created=created)

    @router.post("/reset")
    async def reset_test_data() -> dict[str, str]:
        """
        Clear all data from the database and recreate demo auth users.

        Truncates all entity tables while preserving schema, then
        recreates auth users for each configured persona so that
        ``/__test__/authenticate`` works immediately after reset.
        """
        with db_manager.connection() as conn:
            for sql in entity_sql.values():
                try:
                    conn.execute(sql.delete_all)
                except Exception:
                    logger.debug("Table %s might not exist yet", sql.name, exc_info=True)

        # Recreate demo auth users from personas (#465)
        if auth_store is not None and personas:
            for p in personas:
                pid = p.get("id", "")
                if not pid:
                    continue
                email = pid + "@demo.dazzle.local"
                try:
                    user = auth_store.get_user_by_email(email)
                    if not user:
                        auth_store.create_user(
                            email=email,
                            password="demo_" + pid + "_password",  # nosec B106
                            username=p.get("label") or pid,
                            roles=[pid],
                        )
                except Exception:
                    logger.debug("Could not recreate demo user for %s", pid, exc_info=True)

        return {"status": "reset_complete"}

    @router.get("/snapshot", response_model=SnapshotResponse)
    async def get_snapshot() -> SnapshotResponse:
        """
        Get a snapshot of all data in the database.

        Returns all records from all entity tables.
        """
        result: dict[str, list[dict[str, Any]]] = {}

        with db_manager.connection() as conn:
            for sql in entity_sql.values():
                try:
                    cursor = conn.execute(sql.select_all)
                    rows = cursor.fetchall()
                    result[sql.name] = [dict(row) for row in rows]
                except Exception:
                    # Table might not exist
                    result[sql.name] = []

        return SnapshotResponse(entities=result)

    @router.post("/authenticate", response_model=AuthenticateResponse)
    async def authenticate_test_user(request: AuthenticateRequest) -> Any:
        """
        Create a test authentication session.

        When auth_store is available, creates a real user and session so the
        returned token works with the auth middleware.  Otherwise falls back
        to returning a mock token.
        """
        import uuid

        username = request.username or request.role or "test_user"
        role = request.role or "user"

        if auth_store is not None:
            # Create (or reuse) a real user + session in the auth store
            email = username + "@test.local"
            user = auth_store.get_user_by_email(email)
            if not user:
                user = auth_store.create_user(
                    email=email,
                    password="test_password",  # nosec B106 - test-only credential
                    username=username,
                    roles=[role],
                )
            session = auth_store.create_session(user)
            session_token = session.id
            user_id = str(user.id)
        else:
            user_id = str(uuid.uuid4())
            session_token = str(uuid.uuid4())

        from starlette.responses import JSONResponse

        # Return as JSON with Set-Cookie so both cookie-based and
        # token-based clients can authenticate.
        resp = JSONResponse(
            content={
                "user_id": user_id,
                "username": username,
                "role": role,
                "session_token": session_token,
                "token": session_token,
            }
        )
        resp.set_cookie(
            key="dazzle_session",
            value=session_token,
            httponly=True,
            samesite="lax",
        )
        return resp

    @router.get("/entity/{entity_name}")
    async def get_entity_data(entity_name: str) -> list[dict[str, Any]]:
        """
        Get all records for a specific entity.

        Args:
            entity_name: Name of the entity to query

        Returns:
            List of all records
        """
        sql = entity_sql.get(entity_name)
        if sql is None:
            raise HTTPException(
                status_code=404,
                detail="Unknown entity: " + entity_name,
            )

        with db_manager.connection() as conn:
            try:
                cursor = conn.execute(sql.select_all)
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
            except Exception:
                return []

    @router.get("/entity/{entity_name}/count")
    async def get_entity_count(entity_name: str) -> dict[str, int]:
        """
        Get count of records for a specific entity.

        Args:
            entity_name: Name of the entity to count

        Returns:
            Count of records
        """
        sql = entity_sql.get(entity_name)
        if sql is None:
            raise HTTPException(
                status_code=404,
                detail="Unknown entity: " + entity_name,
            )

        with db_manager.connection() as conn:
            try:
                cursor = conn.execute(sql.select_count)
                row = cursor.fetchone()
                count = row[0] if isinstance(row, (tuple, list)) else next(iter(row.values()))
                return {"count": count}
            except Exception:
                return {"count": 0}

    @router.delete("/entity/{entity_name}/{entity_id}")
    async def delete_entity(entity_name: str, entity_id: str) -> dict[str, str]:
        """
        Delete a specific entity by ID.

        Args:
            entity_name: Name of the entity
            entity_id: ID of the entity to delete

        Returns:
            Status message
        """
        sql = entity_sql.get(entity_name)
        if sql is None:
            raise HTTPException(
                status_code=404,
                detail="Unknown entity: " + entity_name,
            )

        with db_manager.connection() as conn:
            cursor = conn.execute(sql.delete_by_id, (entity_id,))
            if cursor.rowcount == 0:
                raise HTTPException(
                    status_code=404,
                    detail="Entity not found: " + entity_name + "/" + entity_id,
                )

        return {"status": "deleted"}

    return router
