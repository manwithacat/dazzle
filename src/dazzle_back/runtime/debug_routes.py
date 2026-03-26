"""
Debug routes for runtime inspection.

Provides /_dazzle/* endpoints for inspecting running state, entity counts,
recent actions, and system health.

These endpoints are always available in development mode (localhost).
"""

from __future__ import annotations  # required: forward reference

import logging
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from typing import Any

from pydantic import BaseModel

from dazzle_back.runtime._fastapi_compat import FASTAPI_AVAILABLE, APIRouter
from dazzle_back.runtime.query_builder import quote_identifier, validate_sql_identifier
from dazzle_back.runtime.repository import DatabaseManager
from dazzle_back.specs.entity import EntitySpec

logger = logging.getLogger(__name__)


# =============================================================================
# Response Models
# =============================================================================


class EntityStats(BaseModel):
    """Stats for a single entity."""

    name: str
    count: int
    has_fts: bool = False


class RuntimeStats(BaseModel):
    """Overall runtime statistics."""

    app_name: str
    app_description: str | None
    uptime_seconds: float
    entities: list[EntityStats]
    total_records: int


class SystemHealth(BaseModel):
    """System health information."""

    status: str
    database: str
    timestamp: str


class LivenessResponse(BaseModel):
    """Liveness probe response (Kubernetes-style)."""

    alive: bool


class ReadinessResponse(BaseModel):
    """Readiness probe response (Kubernetes-style)."""

    ready: bool
    database: str
    reason: str | None = None


class SpecInfo(BaseModel):
    """Information about the loaded spec."""

    name: str
    description: str | None
    entities: list[str]
    services: list[str]
    endpoints: int


# =============================================================================
# Dependencies Container
# =============================================================================


@dataclass
class _DebugDeps:
    appspec: Any
    db_manager: DatabaseManager
    entities: list[EntitySpec]
    start_time: datetime


# =============================================================================
# Module-level handler functions
# =============================================================================


async def _health_check(deps: _DebugDeps) -> SystemHealth:
    """
    Check system health.

    Returns database connectivity status and current timestamp.
    """
    db_status = "ok"
    try:
        with deps.db_manager.connection() as conn:
            conn.execute("SELECT 1")
    except Exception as e:
        logger.warning("Health check database error: %s", e)
        db_status = "error: database unreachable"

    return SystemHealth(
        status="ok" if db_status == "ok" else "degraded",
        database=db_status,
        timestamp=datetime.now().isoformat(),
    )


async def _liveness_probe(deps: _DebugDeps) -> LivenessResponse:
    """
    Kubernetes liveness probe.

    Returns alive=true if the process is running.
    Use for detecting if the container needs restart.
    """
    return LivenessResponse(alive=True)


async def _readiness_probe(deps: _DebugDeps) -> ReadinessResponse:
    """
    Kubernetes readiness probe.

    Returns ready=true if the application can handle traffic.
    Checks database connectivity before returning ready.
    """
    try:
        with deps.db_manager.connection() as conn:
            conn.execute("SELECT 1")
        return ReadinessResponse(ready=True, database="ok")
    except Exception as e:
        logger.warning("Readiness probe database error: %s", e)
        return ReadinessResponse(
            ready=False,
            database="error",
            reason="database unreachable",
        )


async def _runtime_stats(deps: _DebugDeps) -> RuntimeStats:
    """
    Get runtime statistics.

    Returns entity counts, uptime, and general statistics.
    """
    entity_stats: list[EntityStats] = []
    total_records = 0

    with deps.db_manager.connection() as conn:
        for entity in deps.entities:
            try:
                cursor = conn.execute(f"SELECT COUNT(*) FROM {entity.name}")  # nosemgrep
                row = cursor.fetchone()
                count = row[0] if isinstance(row, (tuple, list)) else next(iter(row.values()))

                # Check for FTS table
                has_fts = False
                try:
                    conn.execute(f"SELECT 1 FROM {entity.name}_fts LIMIT 1")  # nosemgrep
                    has_fts = True
                except Exception:
                    logger.debug("FTS table not available for %s", entity.name, exc_info=True)

                entity_stats.append(EntityStats(name=entity.name, count=count, has_fts=has_fts))
                total_records += count
            except Exception:
                entity_stats.append(EntityStats(name=entity.name, count=0))

    uptime = (datetime.now() - deps.start_time).total_seconds()

    return RuntimeStats(
        app_name=deps.appspec.name,
        app_description=deps.appspec.title,
        uptime_seconds=uptime,
        entities=entity_stats,
        total_records=total_records,
    )


async def _spec_info(deps: _DebugDeps) -> SpecInfo:
    """
    Get information about the loaded specification.

    Returns entity names, service names, and endpoint count.
    """
    return SpecInfo(
        name=deps.appspec.name,
        description=deps.appspec.title,
        entities=[e.name for e in deps.entities],
        services=[s.name for s in deps.appspec.surfaces],
        endpoints=len(deps.appspec.surfaces),
    )


async def _entity_details(deps: _DebugDeps, entity_name: str) -> dict[str, Any]:
    """
    Get details about a specific entity.

    Args:
        entity_name: Name of the entity to inspect

    Returns:
        Entity schema and sample data
    """
    # Validate entity name before any database operations
    try:
        validate_sql_identifier(entity_name, "entity name")
    except ValueError:
        return {"error": "Invalid entity name"}

    entity = next((e for e in deps.entities if e.name == entity_name), None)
    if not entity:
        return {"error": f"Entity not found: {entity_name}"}

    # Get field info
    fields = []
    for fld in entity.fields:
        # Convert FieldType to a string representation
        type_str = str(fld.type.scalar_type.value) if fld.type.scalar_type else fld.type.kind
        if fld.type.max_length is not None and fld.type.scalar_type:
            type_str = f"{fld.type.scalar_type.value}({fld.type.max_length})"
        if fld.type.kind == "ref" and fld.type.ref_entity:
            type_str = f"ref({fld.type.ref_entity})"
        elif fld.type.kind == "enum" and fld.type.enum_values:
            type_str = f"enum({', '.join(fld.type.enum_values)})"

        field_info: dict[str, Any] = {
            "name": fld.name,
            "type": type_str,
            "required": fld.required,
            "unique": fld.unique,
            "indexed": fld.indexed,
        }
        if fld.type.max_length is not None:
            field_info["max_length"] = fld.type.max_length
        if fld.sensitive:
            field_info["sensitive"] = True
        fields.append(field_info)

    # Get sample data
    sample: list[dict[str, Any]] = []
    with deps.db_manager.connection() as conn:
        try:
            cursor = conn.execute(f"SELECT * FROM {entity_name} LIMIT 5")  # nosemgrep
            rows = cursor.fetchall()
            sample = [dict(row) for row in rows]
        except Exception:
            logger.debug("Failed to fetch sample data for %s", entity_name, exc_info=True)

    # Get count
    count = 0
    with deps.db_manager.connection() as conn:
        try:
            cursor = conn.execute(f"SELECT COUNT(*) FROM {entity_name}")  # nosemgrep
            row = cursor.fetchone()
            count = row[0] if isinstance(row, (tuple, list)) else next(iter(row.values()))
        except Exception:
            logger.debug("Failed to count records for %s", entity_name, exc_info=True)

    return {
        "name": entity.name,
        "label": entity.label,
        "description": entity.description,
        "fields": fields,
        "count": count,
        "sample": sample,
    }


async def _list_tables(deps: _DebugDeps) -> dict[str, Any]:
    """
    List all database tables and their row counts.
    """
    tables: list[dict[str, Any]] = []

    with deps.db_manager.connection() as conn:
        # Get all tables from PostgreSQL catalog
        cursor = conn.execute(
            "SELECT tablename AS name FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
        )
        table_names = [row["name"] for row in cursor.fetchall()]

        for table_name in table_names:
            try:
                tbl = quote_identifier(table_name)
                count_cursor = conn.execute(f"SELECT COUNT(*) FROM {tbl}")  # nosemgrep
                row = count_cursor.fetchone()
                count = next(iter(row.values())) if row else 0
                tables.append({"name": table_name, "count": count})
            except Exception:
                tables.append({"name": table_name, "count": -1, "error": "unreadable"})

    return {"tables": tables}


# =============================================================================
# Route Factory
# =============================================================================


def create_debug_routes(
    appspec: Any,
    db_manager: DatabaseManager,
    entities: list[EntitySpec],
    start_time: datetime,
) -> APIRouter:
    """
    Create debug routes for runtime inspection.

    Args:
        appspec: Dazzle AppSpec (parsed IR)
        db_manager: Database manager instance
        entities: List of entity specifications
        start_time: Server start time

    Returns:
        APIRouter with debug endpoints

    Raises:
        RuntimeError: If FastAPI is not available
    """
    if not FASTAPI_AVAILABLE:
        raise RuntimeError(
            "FastAPI is required for debug routes. Install it with: pip install fastapi"
        )

    router = APIRouter(prefix="/_dazzle", tags=["Debug"])

    deps = _DebugDeps(
        appspec=appspec,
        db_manager=db_manager,
        entities=entities,
        start_time=start_time,
    )

    router.add_api_route(
        "/health", partial(_health_check, deps), methods=["GET"], response_model=SystemHealth
    )
    router.add_api_route(
        "/live", partial(_liveness_probe, deps), methods=["GET"], response_model=LivenessResponse
    )
    router.add_api_route(
        "/ready", partial(_readiness_probe, deps), methods=["GET"], response_model=ReadinessResponse
    )
    router.add_api_route(
        "/stats", partial(_runtime_stats, deps), methods=["GET"], response_model=RuntimeStats
    )
    router.add_api_route(
        "/spec", partial(_spec_info, deps), methods=["GET"], response_model=SpecInfo
    )
    router.add_api_route("/entity/{entity_name}", partial(_entity_details, deps), methods=["GET"])
    router.add_api_route("/tables", partial(_list_tables, deps), methods=["GET"])

    return router
