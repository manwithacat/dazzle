"""
Test routes for E2E testing.

Provides /__test__/* endpoints for seeding fixtures, resetting data,
and capturing database snapshots.

These endpoints are only available when test mode is enabled.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

try:
    from fastapi import APIRouter, HTTPException

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    APIRouter = None  # type: ignore[misc, assignment]
    HTTPException = None  # type: ignore[misc, assignment]

from pydantic import BaseModel

if TYPE_CHECKING:
    from dazzle_back.runtime.repository import DatabaseManager, SQLiteRepository
    from dazzle_back.specs.entity import EntitySpec


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
) -> APIRouter:
    """
    Create test routes for E2E testing.

    Args:
        db_manager: Database manager instance
        repositories: Dictionary of repositories by entity name
        entities: List of entity specifications
        auth_store: Optional AuthStore for creating real test sessions

    Returns:
        APIRouter with test endpoints

    Raises:
        RuntimeError: If FastAPI is not available
    """
    if not FASTAPI_AVAILABLE:
        raise RuntimeError(
            "FastAPI is required for test routes. Install it with: pip install fastapi"
        )

    router = APIRouter(prefix="/__test__", tags=["Testing"])

    # Build entity lookup
    entity_lookup = {e.name: e for e in entities}

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
                    detail=f"Unknown entity: {entity_name}",
                )

            # Prepare data
            data = dict(fixture.data)

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
                raise HTTPException(
                    status_code=400,
                    detail=f"Failed to create {entity_name}: {str(e)}",
                )

        return SeedResponse(created=created)

    @router.post("/reset")
    async def reset_test_data() -> dict[str, str]:
        """
        Clear all data from the database.

        Truncates all entity tables while preserving schema.
        """
        with db_manager.connection() as conn:
            for entity in entities:
                try:
                    conn.execute(f"DELETE FROM {entity.name}")
                except Exception:
                    # Table might not exist yet
                    pass

        return {"status": "reset_complete"}

    @router.get("/snapshot", response_model=SnapshotResponse)
    async def get_snapshot() -> SnapshotResponse:
        """
        Get a snapshot of all data in the database.

        Returns all records from all entity tables.
        """
        result: dict[str, list[dict[str, Any]]] = {}

        with db_manager.connection() as conn:
            for entity in entities:
                try:
                    cursor = conn.execute(f"SELECT * FROM {entity.name}")
                    rows = cursor.fetchall()
                    result[entity.name] = [dict(row) for row in rows]
                except Exception:
                    # Table might not exist
                    result[entity.name] = []

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
            email = f"{username}@test.local"
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
        if entity_name not in entity_lookup:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown entity: {entity_name}",
            )

        with db_manager.connection() as conn:
            try:
                cursor = conn.execute(f"SELECT * FROM {entity_name}")
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
        if entity_name not in entity_lookup:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown entity: {entity_name}",
            )

        with db_manager.connection() as conn:
            try:
                cursor = conn.execute(f"SELECT COUNT(*) FROM {entity_name}")
                count = cursor.fetchone()[0]
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
        if entity_name not in entity_lookup:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown entity: {entity_name}",
            )

        with db_manager.connection() as conn:
            cursor = conn.execute(
                f"DELETE FROM {entity_name} WHERE id = ?",
                (entity_id,),
            )
            if cursor.rowcount == 0:
                raise HTTPException(
                    status_code=404,
                    detail=f"Entity not found: {entity_name}/{entity_id}",
                )

        return {"status": "deleted"}

    return router
