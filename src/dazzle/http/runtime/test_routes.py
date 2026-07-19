"""
Test routes for E2E testing.

Provides /__test__/* endpoints for seeding fixtures, resetting data,
and capturing database snapshots.

These endpoints are only available when test mode is enabled.
When ``DAZZLE_TEST_SECRET`` is set, all routes require the
``X-Test-Secret`` header to match (#458).
"""

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from dazzle.core import ir
from dazzle.http.runtime.auth_identity_mirror import mirror_auth_user_to_domain
from dazzle.http.runtime.http_errors import require_found
from dazzle.http.runtime.repository import DatabaseManager, Repository
from dazzle.http.specs.entity import EntitySpec

logger = logging.getLogger(__name__)

# Identifier pattern: letters, digits, underscores only (SQL-safe)
_SAFE_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# #1626 re-eval: fixed auth user UUIDs so demo jsonl can assign
# Task/Ticket/Invoice rows to the same principals QA capture logs in as.
# Pattern: a1 + persona index in the last hex group (version/variant valid).
STABLE_PERSONA_USER_IDS: dict[str, str] = {
    "member": "a1000000-0000-4000-8000-000000000001",
    "manager": "a1000000-0000-4000-8000-000000000002",
    "admin": "a1000000-0000-4000-8000-000000000003",
    "agent": "a1000000-0000-4000-8000-000000000004",
    "customer": "a1000000-0000-4000-8000-000000000005",
    "requester": "a1000000-0000-4000-8000-000000000006",
    "approver": "a1000000-0000-4000-8000-000000000007",
    "finance": "a1000000-0000-4000-8000-000000000008",
    "auditor": "a1000000-0000-4000-8000-000000000009",
    "user": "a1000000-0000-4000-8000-00000000000a",
    "designer": "a1000000-0000-4000-8000-00000000000b",
    "reviewer": "a1000000-0000-4000-8000-00000000000c",
    # Showcase product personas beyond the core set (#1626 re-eval).
    "tester": "a1000000-0000-4000-8000-00000000000d",
    "engineer": "a1000000-0000-4000-8000-00000000000e",
    "ops_engineer": "a1000000-0000-4000-8000-00000000000f",
    "employee": "a1000000-0000-4000-8000-000000000010",
    "hr_admin": "a1000000-0000-4000-8000-000000000011",
    "tenant_admin": "a1000000-0000-4000-8000-000000000012",
    "finance_admin": "a1000000-0000-4000-8000-000000000013",
}


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
    # Core-IR `User` entity (carries any `auth_identity:` binding) for the ADR-0039
    # domain-User mirror. None = app has no User entity → no mirror.
    user_ir_spec: ir.EntitySpec | None = None


# =============================================================================
# Module-level handler functions
# =============================================================================


def _build_fixture_id_map(fixtures: list[FixtureData]) -> dict[str, str]:
    """First pass: fixture id → entity uuid (from data or fresh)."""
    import uuid

    id_mapping: dict[str, str] = {}
    for fixture in fixtures:
        entity_id = fixture.data["id"] if "id" in fixture.data else str(uuid.uuid4())
        id_mapping[fixture.id] = entity_id
    return id_mapping


def _prepare_fixture_row(
    fixture: FixtureData,
    repo: Repository[Any],
    id_mapping: dict[str, str],
) -> dict[str, Any]:
    """Filter known fields, apply id + refs for one fixture."""
    known_fields = set(repo._field_types) | {"id"}
    data = {k: v for k, v in fixture.data.items() if k in known_fields}
    if "id" not in data:
        data["id"] = id_mapping[fixture.id]
    if fixture.refs:
        for field_name, ref_fixture_id in fixture.refs.items():
            if ref_fixture_id in id_mapping:
                data[field_name] = id_mapping[ref_fixture_id]
    return data


async def _create_one_fixture(
    deps: _TestDeps,
    fixture: FixtureData,
    id_mapping: dict[str, str],
    created_ids: list[tuple[str, str]],
) -> tuple[str, dict[str, Any]]:
    """Create one fixture row; raise HTTPException on failure (after rollback)."""
    entity_name = fixture.entity
    repo = deps.repositories.get(entity_name)
    if not repo:
        _rollback_created(deps, created_ids)
        raise HTTPException(status_code=400, detail="Unknown entity: " + entity_name)

    data = _prepare_fixture_row(fixture, repo, id_mapping)
    try:
        entity = await repo.create(data)
        row = entity.model_dump() if hasattr(entity, "model_dump") else data
        created_ids.append((entity_name, data["id"]))
        if _entity_is_tenant_root(deps, entity_name):
            _mirror_seeded_tenant_to_org(deps, data)
        return fixture.id, row
    except Exception as e:
        # Idempotent re-seed: same id after partial reset / concurrent capture
        # (#1626 fleet recapture). Prefer update over fail when the row exists.
        msg = str(e).lower()
        if "already exists" in msg and data.get("id"):
            try:
                updated = await repo.update(data["id"], data)
                row = (
                    updated.model_dump()
                    if updated is not None and hasattr(updated, "model_dump")
                    else data
                )
                if _entity_is_tenant_root(deps, entity_name):
                    _mirror_seeded_tenant_to_org(deps, data)
                return fixture.id, row
            except Exception as update_exc:
                logger.error(
                    "Failed to upsert %s %s: create=%s update=%s",
                    entity_name,
                    data.get("id"),
                    e,
                    update_exc,
                )
        logger.error("Failed to create %s: %s", entity_name, e)
        _rollback_created(deps, created_ids)
        raise HTTPException(
            status_code=400,
            detail=f"Failed to create {entity_name}: {e}",
        ) from e


async def _seed_fixtures(deps: _TestDeps, request: SeedRequest) -> SeedResponse:
    """
    Seed test fixtures into the database.

    Creates entities from fixture specifications, resolving references
    between fixtures. On failure, rolls back by deleting all entities
    created in this batch so callers don't get partial state.
    """
    created: dict[str, Any] = {}
    id_mapping = _build_fixture_id_map(request.fixtures)
    created_ids: list[tuple[str, str]] = []

    for fixture in request.fixtures:
        fid, row = await _create_one_fixture(deps, fixture, id_mapping, created_ids)
        created[fid] = row

    # After tenants are seeded, attach demo personas to the first tenant org
    # so /__test__/authenticate + qa capture see non-empty job desks.
    if any(_entity_is_tenant_root(deps, name) for name, _ in created_ids):
        _ensure_demo_persona_memberships(deps)

    return SeedResponse(created=created)


def _entity_is_tenant_root(deps: _TestDeps, entity_name: str) -> bool:
    """True when *entity_name* is the app's tenant-root / archetype:tenant."""
    if entity_name == "Tenant":
        return True
    for ent in deps.entities:
        if ent.name != entity_name:
            continue
        if getattr(ent, "is_tenant_root", False):
            return True
        kind = getattr(getattr(ent, "archetype_kind", None), "name", "") or ""
        return kind == "TENANT"
    return False


def _mirror_seeded_tenant_to_org(deps: _TestDeps, data: dict[str, Any]) -> None:
    """Create organizations row with id == domain Tenant id (#1626)."""
    if deps.auth_store is None:
        return
    org_id = str(data.get("id") or "")
    if not org_id:
        return
    slug = str(data.get("slug") or data.get("name") or org_id)[:60]
    name = str(data.get("name") or slug)
    try:
        deps.auth_store.ensure_organization_at_id(org_id=org_id, slug=slug, name=name, is_test=True)
    except Exception:
        # Best-effort mirror for QA seed; warn so swallow ratchet stays clean.
        logger.warning("Could not mirror Tenant %s to organization", org_id, exc_info=True)


def _primary_demo_org_id(deps: _TestDeps) -> str | None:
    """First test org id (mirrored tenants prefer is_test)."""
    try:
        with deps.db_manager.connection() as conn:
            cur = conn.execute(
                "SELECT id FROM organizations ORDER BY is_test DESC, created_at ASC LIMIT 1"
            )
            row = cur.fetchone()
    except Exception:
        logger.warning("Could not list organizations for demo memberships", exc_info=True)
        return None
    if not row:
        return None
    return str(row["id"] if isinstance(row, dict) else row[0])


def _persona_email_candidates(deps: _TestDeps, persona_id: str) -> list[str]:
    """Emails used by reset / authenticate / credentials file for a persona."""
    candidates = [
        f"{persona_id}@demo.dazzle.local",
        f"{persona_id}@test.local",
        f"{persona_id}@example.test",
    ]
    if not deps.project_root:
        return candidates
    creds_path = deps.project_root / ".dazzle" / "test_credentials.json"
    if not creds_path.exists():
        return candidates
    try:
        creds = json.loads(creds_path.read_text(encoding="utf-8"))
        email = (creds.get("personas") or {}).get(persona_id, {}).get("email")
        if email:
            candidates.insert(0, email)
    except Exception:
        logger.warning("creds read for memberships failed", exc_info=True)
    return candidates


def _ensure_membership_for_persona(deps: _TestDeps, persona_id: str, tenant_id: str) -> None:
    """Attach one matching auth user for *persona_id* to *tenant_id*."""
    assert deps.auth_store is not None
    for email in _persona_email_candidates(deps, persona_id):
        user = deps.auth_store.get_user_by_email(email)
        if user is None:
            continue
        try:
            deps.auth_store.ensure_membership(
                tenant_id=tenant_id,
                identity_id=str(user.id),
                roles=list(user.roles or [persona_id]),
            )
        except Exception:
            logger.warning(
                "Could not ensure membership for %s on %s",
                email,
                tenant_id,
                exc_info=True,
            )
        return


def _ensure_demo_persona_memberships(deps: _TestDeps) -> None:
    """Give every configured demo persona a membership on the first tenant org.

    Without memberships, shared_schema RLS leaves workspace queues empty even
    when Invoice seeds exist (fail-closed dazzle.tenant_id).
    """
    if deps.auth_store is None:
        return
    primary = _primary_demo_org_id(deps)
    if not primary:
        return
    for p in deps.personas or []:
        pid = p.get("id") or ""
        if pid:
            _ensure_membership_for_persona(deps, pid, primary)


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
            logger.warning("Could not clear auth users table", exc_info=True)

    # Load project-specific credentials if available (#688)
    creds_personas: dict[str, dict[str, str]] = {}
    if deps.project_root:
        creds_path = deps.project_root / ".dazzle" / "test_credentials.json"
        if creds_path.exists():
            try:
                creds = json.loads(creds_path.read_text(encoding="utf-8"))
                creds_personas = creds.get("personas", {})
            except Exception:
                logger.debug("Could not load test_credentials.json", exc_info=True)

    # Recreate demo auth users from personas (#465, #688).
    # #1626: when a stable demo UUID is known, force that id so domain seeds
    # (assigned_to / created_by / …) match the principal QA/auth logs in as.
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
                user = _ensure_stable_demo_user(
                    deps,
                    persona_id=pid,
                    email=email,
                    password=password,
                    username=p.get("label") or pid,
                )
                if user:
                    _mirror_auth_user_to_domain(
                        deps, str(user.id), email, p.get("label") or pid, pid
                    )
            except Exception:
                logger.warning("Could not recreate demo user for %s", pid, exc_info=True)

    return {"status": "reset_complete"}


def _ensure_stable_demo_user(
    deps: _TestDeps,
    *,
    persona_id: str,
    email: str,
    password: str,
    username: str,
) -> Any:
    """Return an auth user for *persona_id* bound to STABLE_PERSONA_USER_IDS.

    Pre-#1626 reset reused random UUIDs for pre-existing demo emails, so
    assignment-aware seed jsonl (fixed UUIDs) never matched the login
    principal — empty hero desks in qa capture despite seeded rows.
    """
    from uuid import UUID

    assert deps.auth_store is not None
    stable = STABLE_PERSONA_USER_IDS.get(persona_id)
    if stable:
        try:
            by_id = deps.auth_store.get_user_by_id(UUID(stable))
        except Exception:  # noqa: BLE001
            by_id = None
        if by_id is not None:
            if by_id.roles != [persona_id]:
                deps.auth_store.update_user(by_id.id, roles=[persona_id])
            return by_id

    existing = deps.auth_store.get_user_by_email(email)
    if existing is not None:
        if stable and str(existing.id) != stable:
            # Drop the non-stable principal so we can re-create at the fixed id.
            try:
                deps.auth_store.delete_user_sessions(existing.id)
            except Exception:  # noqa: BLE001
                logger.debug("delete_user_sessions during rekey failed", exc_info=True)
            try:
                deps.auth_store._execute(  # noqa: SLF001 — test reset only
                    'DELETE FROM "users" WHERE id = %s', (str(existing.id),)
                )
            except Exception:  # noqa: BLE001
                logger.warning(
                    "Could not rekey demo user %s → %s", existing.id, stable, exc_info=True
                )
                # Fall through: keep existing rather than fail reset
                if existing.roles != [persona_id]:
                    deps.auth_store.update_user(existing.id, roles=[persona_id])
                return existing
        else:
            if existing.roles != [persona_id]:
                deps.auth_store.update_user(existing.id, roles=[persona_id])
            return existing

    return deps.auth_store.create_user(
        email=email,
        password=password,
        username=username,
        roles=[persona_id],
        user_id=stable,
    )


def _mirror_auth_user_to_domain(
    deps: _TestDeps, user_id: str, email: str, name: str, role: str
) -> None:
    """Mirror an auth-store user into the DSL-defined ``User`` domain entity (#778/#1398).

    Thin adapter onto the shared ADR-0039 helper (``auth_identity_mirror``) — the same rule
    the production ``AuthStore.create_user`` hook runs, so the test/QA path and production
    can't diverge (D4). Uses the core-IR ``User`` spec (carrying any ``auth_identity:``
    binding) threaded in via ``deps.user_ir_spec``; a no-op when the app has no ``User``
    entity. Best-effort + idempotent; never raises into the auth flow (D1).
    """
    if deps.user_ir_spec is None:
        return  # App has no User entity — nothing to mirror

    def _execute(sql: str, params: tuple[Any, ...]) -> None:
        with deps.db_manager.connection() as conn:
            conn.execute(sql, params)
            conn.commit()

    mirror_auth_user_to_domain(
        _execute,
        deps.user_ir_spec,
        user_id=user_id,
        email=email,
        username=name,
        role=role,
    )


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


def _lookup_test_auth_user(deps: _TestDeps, *, username: str, role: str) -> Any:
    """Find or create the auth principal for a test authenticate call (#1626)."""
    from uuid import UUID

    assert deps.auth_store is not None
    stable_id = STABLE_PERSONA_USER_IDS.get(role) or STABLE_PERSONA_USER_IDS.get(username)
    user = None
    if stable_id:
        try:
            user = deps.auth_store.get_user_by_id(UUID(stable_id))
        except Exception:  # noqa: BLE001
            user = None
    if user is None:
        for email in (
            f"{username}@demo.dazzle.local",
            f"{role}@demo.dazzle.local",
            f"{username}@test.local",
            f"{role}@test.local",
            f"{username}@example.test",
        ):
            user = deps.auth_store.get_user_by_email(email)
            if user is not None:
                break
    if user is None:
        return deps.auth_store.create_user(
            email=f"{username}@test.local",
            password="test_password",  # nosec B106 - test-only credential
            username=username,
            roles=[role],
            user_id=stable_id,
        )
    if user.roles != [role]:
        updated = deps.auth_store.update_user(user.id, roles=[role])
        if updated is not None:
            return updated
    return user


def _session_for_test_user(deps: _TestDeps, user: Any) -> Any:
    """Create a session, binding active membership when present (P0-9)."""
    assert deps.auth_store is not None
    active_membership_id = None
    try:
        memberships = deps.auth_store.get_memberships_for_identity(str(user.id))
        active = next(
            (m for m in memberships if getattr(m, "status", "active") == "active"),
            None,
        )
        if active is not None:
            active_membership_id = active.id
    except Exception:
        logger.warning(
            "Could not resolve membership for test auth user %s",
            getattr(user, "email", user.id),
            exc_info=True,
        )
    return deps.auth_store.create_session(user, active_membership_id=active_membership_id)


async def _authenticate_test_user(deps: _TestDeps, request: AuthenticateRequest) -> Any:
    """
    Create a test authentication session.

    When auth_store is available, creates a real user and session so the
    returned token works with the auth middleware.  Otherwise falls back
    to returning a mock token.

    Prefers :data:`STABLE_PERSONA_USER_IDS` so QA capture and assignment-aware
    seeds share the same principal UUID (#1626 empty-desk theater).
    """
    import uuid

    from starlette.responses import JSONResponse

    username = request.username or request.role or "test_user"
    role = request.role or "user"

    if deps.auth_store is not None:
        user = _lookup_test_auth_user(deps, username=username, role=role)
        email = getattr(user, "email", None) or f"{username}@test.local"
        session = _session_for_test_user(deps, user)
        session_token = session.id
        user_id = str(user.id)
        _mirror_auth_user_to_domain(deps, user_id, email, username, role)
    else:
        user_id = str(uuid.uuid4())
        session_token = str(uuid.uuid4())

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
    sql = require_found(deps.entity_sql.get(entity_name), "Unknown entity: " + entity_name)

    with deps.db_manager.connection() as conn:
        try:
            cursor = conn.execute(sql.select_all)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception:
            logger.debug("ignored exception in test_routes.py:451", exc_info=True)
            return []


async def _get_entity_count(deps: _TestDeps, entity_name: str) -> dict[str, int]:
    """
    Get count of records for a specific entity.

    Args:
        entity_name: Name of the entity to count

    Returns:
        Count of records
    """
    sql = require_found(deps.entity_sql.get(entity_name), "Unknown entity: " + entity_name)

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
    sql = require_found(deps.entity_sql.get(entity_name), "Unknown entity: " + entity_name)

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
    user_ir_spec: ir.EntitySpec | None = None,
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
    """
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
        user_ir_spec=user_ir_spec,
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
