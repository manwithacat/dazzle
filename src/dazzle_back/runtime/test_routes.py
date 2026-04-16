"""
Test routes for E2E testing.

Provides /__test__/* endpoints for seeding fixtures, resetting data,
and capturing database snapshots.

These endpoints are only available when test mode is enabled.
When ``DAZZLE_TEST_SECRET`` is set, all routes require the
``X-Test-Secret`` header to match (#458).
"""

from __future__ import annotations  # required: forward reference

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from dazzle_back.runtime._fastapi_compat import (
    FASTAPI_AVAILABLE,
    APIRouter,
    Depends,
    HTTPException,
    Request,
)
from dazzle_back.runtime.repository import DatabaseManager, Repository
from dazzle_back.specs.entity import EntitySpec

logger = logging.getLogger(__name__)

# Identifier pattern: letters, digits, underscores only (SQL-safe)
_SAFE_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class _EntitySQL:
    """Pre-computed SQL statements for a known entity table.

    All SQL is built once at router creation time from validated entity
    names -- no string formatting happens at request time.
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
# Dependencies Container
# =============================================================================


@dataclass
class _TestDeps:
    db_manager: DatabaseManager
    repositories: dict[str, Repository[Any]]
    entities: list[EntitySpec]
    entity_sql: dict[str, _EntitySQL]
    auth_store: Any
    personas: list[dict[str, Any]]
    project_root: Path | None = None


# =============================================================================
# Module-level handler functions
# =============================================================================


async def _seed_fixtures(deps: _TestDeps, request: SeedRequest) -> SeedResponse:
    """
    Seed test fixtures into the database.

    Creates entities from fixture specifications, resolving references
    between fixtures. On failure, rolls back by deleting all entities
    created in this batch so callers don't get partial state.
    """
    import uuid

    created: dict[str, Any] = {}
    id_mapping: dict[str, str] = {}  # fixture_id -> actual entity id
    # Track created entity IDs for rollback
    created_ids: list[tuple[str, str]] = []  # (entity_name, entity_id)

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
        repo = deps.repositories.get(entity_name)

        if not repo:
            _rollback_created(deps, created_ids)
            raise HTTPException(
                status_code=400,
                detail="Unknown entity: " + entity_name,
            )

        # Prepare data -- filter to known entity fields to avoid
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
            created_ids.append((entity_name, data["id"]))
        except Exception as e:
            logger.error("Failed to create %s: %s", entity_name, e)
            _rollback_created(deps, created_ids)
            raise HTTPException(
                status_code=400,
                detail=f"Failed to create {entity_name}: {e}",
            )

    return SeedResponse(created=created)


def _rollback_created(deps: _TestDeps, created_ids: list[tuple[str, str]]) -> None:
    """Delete entities created during a failed seed batch (best-effort)."""
    for entity_name, entity_id in reversed(created_ids):
        sql_obj = deps.entity_sql.get(entity_name)
        if not sql_obj:
            continue
        try:
            with deps.db_manager.connection() as conn:
                conn.execute(sql_obj.delete_by_id, (entity_id,))
        except Exception:
            logger.debug("Rollback delete failed for %s/%s", entity_name, entity_id)


async def _reset_test_data(deps: _TestDeps) -> dict[str, str]:
    """
    Clear all data from the database and recreate demo auth users.

    Truncates all entity tables while preserving schema, then
    recreates auth users for each configured persona so that
    ``/__test__/authenticate`` works immediately after reset.

    When ``.dazzle/test_credentials.json`` exists in the project root,
    uses the emails and passwords defined there instead of generic
    defaults so that generated auth tests work without extra config (#688).
    """
    # Delete each entity in its own connection so FK violations on one
    # table don't abort the transaction and poison subsequent deletes.
    for sql in deps.entity_sql.values():
        try:
            with deps.db_manager.connection() as conn:
                conn.execute(sql.delete_all)
        except Exception:
            logger.debug("Table %s might not exist yet", sql.name, exc_info=True)

    # Also clear the auth store's users table (not the entity table) so
    # fixture-created auth users from previous runs don't block re-seeding.
    if deps.auth_store is not None:
        try:
            with deps.db_manager.connection() as conn:
                conn.execute('DELETE FROM "users"')
        except Exception:
            logger.debug("Could not clear auth users table", exc_info=True)

    # Load project-specific credentials if available (#688)
    creds_personas: dict[str, dict[str, str]] = {}
    if deps.project_root:
        creds_path = deps.project_root / ".dazzle" / "test_credentials.json"
        if creds_path.exists():
            try:
                creds = json.loads(creds_path.read_text())
                creds_personas = creds.get("personas", {})
            except Exception:
                logger.debug("Could not load test_credentials.json", exc_info=True)

    # Recreate demo auth users from personas (#465, #688)
    if deps.auth_store is not None and deps.personas:
        for p in deps.personas:
            pid = p.get("id", "")
            if not pid:
                continue
            # Use credentials file when available, fall back to generic defaults
            persona_creds = creds_personas.get(pid, {})
            email = persona_creds.get("email") or (pid + "@demo.dazzle.local")
            password = persona_creds.get("password") or ("demo_" + pid + "_password")  # nosec B106
            try:
                user = deps.auth_store.get_user_by_email(email)
                if not user:
                    user = deps.auth_store.create_user(
                        email=email,
                        password=password,
                        username=p.get("label") or pid,
                        roles=[pid],
                    )
                elif user.roles != [pid]:
                    # Roles may be stale -- reset to the canonical persona role
                    # so authenticate calls after reset always get the right role.
                    deps.auth_store.update_user(user.id, roles=[pid])
                # Mirror into User domain entity (#778)
                if user:
                    _mirror_auth_user_to_domain(
                        deps, str(user.id), email, p.get("label") or pid, pid
                    )
            except Exception:
                logger.debug("Could not recreate demo user for %s", pid, exc_info=True)

    return {"status": "reset_complete"}


def _mirror_auth_user_to_domain(
    deps: _TestDeps, user_id: str, email: str, name: str, role: str
) -> None:
    """Mirror an auth-store user into the DSL-defined User domain entity.

    Closes manwithacat/dazzle#778. The QA/test auth flow provisions users
    into the auth store but not into the domain ``User`` entity table.
    Any app with ``ref User`` foreign keys then fails on create because
    the referenced User row doesn't exist.

    This helper upserts a matching row into the ``User`` entity table
    (if one exists in the app's schema). It's called after every auth
    user creation in the test/QA path so the two stores stay in sync.

    The upsert uses ``INSERT ... ON CONFLICT (id) DO UPDATE`` so it's
    safe to call repeatedly (idempotent). Only the ``User`` entity is
    mirrored — other persona-backed entities (Tester, Agent, etc.) are
    handled by the ``backed_by`` DSL construct (cycle 248).
    """
    user_sql = deps.entity_sql.get("User")
    if user_sql is None:
        return  # App has no User entity — nothing to mirror

    try:
        with deps.db_manager.connection() as conn:
            # Check if the User table has the expected columns
            # Attempt a simple upsert with common User entity fields
            conn.execute(
                """
                INSERT INTO "User" (id, email, name, role, is_active, created_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
                ON CONFLICT (id) DO UPDATE SET
                    email = EXCLUDED.email,
                    name = EXCLUDED.name,
                    role = EXCLUDED.role,
                    is_active = EXCLUDED.is_active
                """,
                (user_id, email, name, role, True),
            )
            conn.commit()
    except Exception:
        # The User entity may have a different schema than expected
        # (different columns, SQLite vs Postgres syntax, etc.).
        # Fall back to a minimal insert with just id + email.
        try:
            with deps.db_manager.connection() as conn:
                conn.execute(
                    """
                    INSERT INTO "User" (id, email, name, is_active, created_at)
                    VALUES (%s, %s, %s, %s, NOW())
                    ON CONFLICT (id) DO NOTHING
                    """,
                    (user_id, email, name, True),
                )
                conn.commit()
        except Exception:
            logger.debug("Could not mirror auth user %s into User entity", user_id, exc_info=True)


async def _get_snapshot(deps: _TestDeps) -> SnapshotResponse:
    """
    Get a snapshot of all data in the database.

    Returns all records from all entity tables.
    """
    result: dict[str, list[dict[str, Any]]] = {}

    with deps.db_manager.connection() as conn:
        for sql in deps.entity_sql.values():
            try:
                cursor = conn.execute(sql.select_all)
                rows = cursor.fetchall()
                result[sql.name] = [dict(row) for row in rows]
            except Exception:
                # Table might not exist
                result[sql.name] = []

    return SnapshotResponse(entities=result)


async def _authenticate_test_user(deps: _TestDeps, request: AuthenticateRequest) -> Any:
    """
    Create a test authentication session.

    When auth_store is available, creates a real user and session so the
    returned token works with the auth middleware.  Otherwise falls back
    to returning a mock token.
    """
    import uuid

    username = request.username or request.role or "test_user"
    role = request.role or "user"

    if deps.auth_store is not None:
        # Create (or reuse) a real user + session in the auth store
        email = username + "@test.local"
        user = deps.auth_store.get_user_by_email(email)
        if not user:
            user = deps.auth_store.create_user(
                email=email,
                password="test_password",  # nosec B106 - test-only credential
                username=username,
                roles=[role],
            )
        elif user.roles != [role]:
            # Roles may be stale from a previous test cycle -- update them so
            # the LIST gate (and other RBAC checks) sees the correct role.
            updated = deps.auth_store.update_user(user.id, roles=[role])
            if updated is not None:
                user = updated
        session = deps.auth_store.create_session(user)
        session_token = session.id
        user_id = str(user.id)

        # Mirror auth user into User domain entity (#778)
        _mirror_auth_user_to_domain(deps, user_id, email, username, role)
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


async def _get_entity_data(deps: _TestDeps, entity_name: str) -> list[dict[str, Any]]:
    """
    Get all records for a specific entity.

    Args:
        entity_name: Name of the entity to query

    Returns:
        List of all records
    """
    sql = deps.entity_sql.get(entity_name)
    if sql is None:
        raise HTTPException(
            status_code=404,
            detail="Unknown entity: " + entity_name,
        )

    with deps.db_manager.connection() as conn:
        try:
            cursor = conn.execute(sql.select_all)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception:
            return []


async def _get_entity_count(deps: _TestDeps, entity_name: str) -> dict[str, int]:
    """
    Get count of records for a specific entity.

    Args:
        entity_name: Name of the entity to count

    Returns:
        Count of records
    """
    sql = deps.entity_sql.get(entity_name)
    if sql is None:
        raise HTTPException(
            status_code=404,
            detail="Unknown entity: " + entity_name,
        )

    with deps.db_manager.connection() as conn:
        try:
            cursor = conn.execute(sql.select_count)
            row = cursor.fetchone()
            count = row[0] if isinstance(row, (tuple, list)) else next(iter(row.values()))
            return {"count": count}
        except Exception:
            return {"count": 0}


async def _delete_entity(deps: _TestDeps, entity_name: str, entity_id: str) -> dict[str, str]:
    """
    Delete a specific entity by ID.

    Args:
        entity_name: Name of the entity
        entity_id: ID of the entity to delete

    Returns:
        Status message
    """
    sql = deps.entity_sql.get(entity_name)
    if sql is None:
        raise HTTPException(
            status_code=404,
            detail="Unknown entity: " + entity_name,
        )

    with deps.db_manager.connection() as conn:
        cursor = conn.execute(sql.delete_by_id, (entity_id,))
        if cursor.rowcount == 0:
            raise HTTPException(
                status_code=404,
                detail="Entity not found: " + entity_name + "/" + entity_id,
            )

    return {"status": "deleted"}


# =============================================================================
# Route Factory
# =============================================================================


def create_test_routes(
    db_manager: DatabaseManager,
    repositories: dict[str, Repository[Any]],
    entities: list[EntitySpec],
    auth_store: Any = None,
    personas: list[dict[str, Any]] | None = None,
    project_root: Path | None = None,
) -> APIRouter:
    """
    Create test routes for E2E testing.

    Args:
        db_manager: Database manager instance
        repositories: Dictionary of repositories by entity name
        entities: List of entity specifications
        auth_store: Optional AuthStore for creating real test sessions
        personas: Optional list of persona configurations for demo user recreation
        project_root: Optional project root for loading test_credentials.json

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

    deps = _TestDeps(
        db_manager=db_manager,
        repositories=repositories,
        entities=entities,
        entity_sql=entity_sql,
        auth_store=auth_store,
        personas=personas or [],
        project_root=project_root,
    )

    # --- Authentication dependency ---
    # When DAZZLE_TEST_SECRET is set, require X-Test-Secret header.
    # When unset, test routes are open (backward compat for local dev).
    test_secret = os.environ.get("DAZZLE_TEST_SECRET", "")

    async def _verify_test_secret(request: Request) -> None:
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

    # Use closures instead of functools.partial — FastAPI can't introspect
    # partial objects to identify Pydantic models as body parameters (#743).

    async def seed(request: SeedRequest) -> SeedResponse:
        return await _seed_fixtures(deps, request)

    async def reset() -> dict[str, str]:
        return await _reset_test_data(deps)

    async def snapshot() -> SnapshotResponse:
        return await _get_snapshot(deps)

    async def authenticate(request: AuthenticateRequest) -> Any:
        return await _authenticate_test_user(deps, request)

    async def entity_data(entity_name: str) -> list[dict[str, Any]]:
        return await _get_entity_data(deps, entity_name)

    async def entity_count(entity_name: str) -> dict[str, int]:
        return await _get_entity_count(deps, entity_name)

    async def entity_delete(entity_name: str, entity_id: str) -> dict[str, str]:
        return await _delete_entity(deps, entity_name, entity_id)

    router.add_api_route("/seed", seed, methods=["POST"], response_model=SeedResponse)
    router.add_api_route("/reset", reset, methods=["POST"])
    router.add_api_route("/snapshot", snapshot, methods=["GET"], response_model=SnapshotResponse)
    router.add_api_route(
        "/authenticate", authenticate, methods=["POST"], response_model=AuthenticateResponse
    )
    router.add_api_route("/entity/{entity_name}", entity_data, methods=["GET"])
    router.add_api_route("/entity/{entity_name}/count", entity_count, methods=["GET"])
    router.add_api_route("/entity/{entity_name}/{entity_id}", entity_delete, methods=["DELETE"])

    return router
