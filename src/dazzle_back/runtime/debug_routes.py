"""
Debug routes for runtime inspection.

Provides /_dazzle/* endpoints for inspecting running state, entity counts,
recent actions, and system health.

These endpoints are always available in development mode (localhost).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

try:
    from fastapi import APIRouter

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    APIRouter = None  # type: ignore[misc, assignment]

from pydantic import BaseModel

from dazzle_back.runtime.query_builder import validate_sql_identifier

if TYPE_CHECKING:
    from dazzle_back.runtime.repository import DatabaseManager
    from dazzle_back.specs import BackendSpec
    from dazzle_back.specs.entity import EntitySpec


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
# Debug Routes
# =============================================================================


def create_debug_routes(
    spec: BackendSpec,
    db_manager: DatabaseManager,
    entities: list[EntitySpec],
    start_time: datetime,
) -> APIRouter:
    """
    Create debug routes for runtime inspection.

    Args:
        spec: Backend specification
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

    @router.get("/health", response_model=SystemHealth)
    async def health_check() -> SystemHealth:
        """
        Check system health.

        Returns database connectivity status and current timestamp.
        """
        db_status = "ok"
        try:
            with db_manager.connection() as conn:
                conn.execute("SELECT 1")
        except Exception as e:
            db_status = f"error: {e}"

        return SystemHealth(
            status="ok" if db_status == "ok" else "degraded",
            database=db_status,
            timestamp=datetime.now().isoformat(),
        )

    @router.get("/live", response_model=LivenessResponse)
    async def liveness_probe() -> LivenessResponse:
        """
        Kubernetes liveness probe.

        Returns alive=true if the process is running.
        Use for detecting if the container needs restart.
        """
        return LivenessResponse(alive=True)

    @router.get("/ready", response_model=ReadinessResponse)
    async def readiness_probe() -> ReadinessResponse:
        """
        Kubernetes readiness probe.

        Returns ready=true if the application can handle traffic.
        Checks database connectivity before returning ready.
        """
        try:
            with db_manager.connection() as conn:
                conn.execute("SELECT 1")
            return ReadinessResponse(ready=True, database="ok")
        except Exception as e:
            return ReadinessResponse(
                ready=False,
                database="error",
                reason=str(e),
            )

    @router.get("/stats", response_model=RuntimeStats)
    async def runtime_stats() -> RuntimeStats:
        """
        Get runtime statistics.

        Returns entity counts, uptime, and general statistics.
        """
        entity_stats: list[EntityStats] = []
        total_records = 0

        with db_manager.connection() as conn:
            for entity in entities:
                try:
                    cursor = conn.execute(f"SELECT COUNT(*) FROM {entity.name}")
                    count = cursor.fetchone()[0]

                    # Check for FTS table
                    has_fts = False
                    try:
                        conn.execute(f"SELECT 1 FROM {entity.name}_fts LIMIT 1")
                        has_fts = True
                    except Exception:
                        pass

                    entity_stats.append(EntityStats(name=entity.name, count=count, has_fts=has_fts))
                    total_records += count
                except Exception:
                    entity_stats.append(EntityStats(name=entity.name, count=0))

        uptime = (datetime.now() - start_time).total_seconds()

        return RuntimeStats(
            app_name=spec.name,
            app_description=spec.description,
            uptime_seconds=uptime,
            entities=entity_stats,
            total_records=total_records,
        )

    @router.get("/spec", response_model=SpecInfo)
    async def spec_info() -> SpecInfo:
        """
        Get information about the loaded specification.

        Returns entity names, service names, and endpoint count.
        """
        return SpecInfo(
            name=spec.name,
            description=spec.description,
            entities=[e.name for e in entities],
            services=[s.name for s in spec.services],
            endpoints=len(spec.endpoints),
        )

    @router.get("/entity/{entity_name}")
    async def entity_details(entity_name: str) -> dict[str, Any]:
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
        except ValueError as e:
            return {"error": str(e)}

        entity = next((e for e in entities if e.name == entity_name), None)
        if not entity:
            return {"error": f"Entity not found: {entity_name}"}

        # Get field info
        fields = []
        for field in entity.fields:
            # Convert FieldType to a string representation
            type_str = (
                str(field.type.scalar_type.value) if field.type.scalar_type else field.type.kind
            )
            if field.type.kind == "ref" and field.type.ref_entity:
                type_str = f"ref({field.type.ref_entity})"
            elif field.type.kind == "enum" and field.type.enum_values:
                type_str = f"enum({', '.join(field.type.enum_values)})"

            fields.append(
                {
                    "name": field.name,
                    "type": type_str,
                    "required": field.required,
                    "unique": field.unique,
                    "indexed": field.indexed,
                }
            )

        # Get sample data
        sample: list[dict[str, Any]] = []
        with db_manager.connection() as conn:
            try:
                cursor = conn.execute(f"SELECT * FROM {entity_name} LIMIT 5")
                rows = cursor.fetchall()
                sample = [dict(row) for row in rows]
            except Exception:
                pass

        # Get count
        count = 0
        with db_manager.connection() as conn:
            try:
                cursor = conn.execute(f"SELECT COUNT(*) FROM {entity_name}")
                count = cursor.fetchone()[0]
            except Exception:
                pass

        return {
            "name": entity.name,
            "label": entity.label,
            "description": entity.description,
            "fields": fields,
            "count": count,
            "sample": sample,
        }

    @router.get("/tables")
    async def list_tables() -> dict[str, Any]:
        """
        List all database tables and their row counts.
        """
        tables: list[dict[str, Any]] = []

        with db_manager.connection() as conn:
            # Get all tables
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            table_names = [row[0] for row in cursor.fetchall()]

            for table_name in table_names:
                try:
                    count_cursor = conn.execute(f"SELECT COUNT(*) FROM [{table_name}]")
                    count = count_cursor.fetchone()[0]
                    tables.append({"name": table_name, "count": count})
                except Exception:
                    tables.append({"name": table_name, "count": -1, "error": "unreadable"})

        return {"tables": tables}

    return router
