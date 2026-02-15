"""
Dazzle Control Plane API.

Provides /dazzle/dev/* endpoints for developer-mode operations.
These endpoints handle persona switching, scenario control, data management,
and frontend logging.

These endpoints are only available in dev/native mode or when test_mode is enabled.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)

try:
    from fastapi import APIRouter

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    APIRouter = None  # type: ignore[misc, assignment]


if TYPE_CHECKING:
    from dazzle_back.runtime.auth import AuthStore
    from dazzle_back.runtime.repository import DatabaseManager, SQLiteRepository
    from dazzle_back.specs.entity import EntitySpec


# =============================================================================
# Request/Response Models
# =============================================================================


class PersonaContext(BaseModel):
    """Current persona context."""

    persona_id: str
    label: str | None = None
    session_token: str | None = None  # v0.23.0: Auth token for demo login
    default_route: str | None = None  # v0.23.0: Where to navigate


class ScenarioContext(BaseModel):
    """Current scenario context."""

    scenario_id: str
    name: str | None = None
    seeded_counts: dict[str, int] | None = None  # Records seeded per entity


class SetPersonaRequest(BaseModel):
    """Request to set current persona."""

    persona_id: str


class SetScenarioRequest(BaseModel):
    """Request to set current scenario."""

    scenario_id: str


class RegenerateRequest(BaseModel):
    """Request to regenerate demo data."""

    scenario_id: str | None = None
    entity_counts: dict[str, int] | None = None


class FrontendLogRequest(BaseModel):
    """Frontend log entry from the browser."""

    level: str = "info"  # error, warn, info, debug
    message: str
    source: str | None = None
    line: int | None = None
    column: int | None = None
    stack: str | None = None
    url: str | None = None
    user_agent: str | None = None
    extra: dict[str, Any] | None = None


# =============================================================================
# Control Plane Router
# =============================================================================


def create_control_plane_routes(
    db_manager: DatabaseManager | None,
    repositories: dict[str, SQLiteRepository[Any]] | None,
    entities: list[EntitySpec],
    personas: list[dict[str, Any]] | None = None,
    scenarios: list[dict[str, Any]] | None = None,
    auth_store: AuthStore | None = None,
) -> APIRouter:
    """
    Create control plane routes.

    Args:
        db_manager: Database manager instance (optional)
        repositories: Dictionary of repositories by entity name (optional)
        entities: List of entity specifications
        personas: List of persona configurations
        scenarios: List of scenario configurations
        auth_store: Auth store for persona login (v0.23.0)

    Returns:
        APIRouter with control plane endpoints

    Raises:
        RuntimeError: If FastAPI is not available
    """
    if not FASTAPI_AVAILABLE:
        raise RuntimeError(
            "FastAPI is required for control plane routes. Install it with: pip install fastapi"
        )

    router = APIRouter(prefix="/dazzle/dev", tags=["Dazzle Control Plane"])

    # State storage (in-memory for development)
    state: dict[str, str | None] = {
        "current_persona": None,
        "current_scenario": None,
    }

    # Prepare personas and scenarios lists
    available_personas = personas or []
    available_scenarios = scenarios or []

    # -------------------------------------------------------------------------
    # State Endpoints
    # -------------------------------------------------------------------------

    @router.get("/state")
    async def get_dazzle_state() -> dict[str, Any]:
        """
        Get complete control plane state.

        Returns current persona, scenario, and available options.
        """
        return {
            "current_persona": state["current_persona"],
            "current_scenario": state["current_scenario"],
            "available_personas": available_personas,
            "available_scenarios": available_scenarios,
            "dev_mode": True,
        }

    # -------------------------------------------------------------------------
    # Persona Endpoints
    # -------------------------------------------------------------------------

    @router.get("/current_persona", response_model=PersonaContext | None)
    async def get_current_persona() -> PersonaContext | None:
        """Get the currently active persona."""
        persona_id = state["current_persona"]
        if not persona_id:
            return None

        # Find persona details
        for p in available_personas:
            if p.get("id") == persona_id:
                return PersonaContext(persona_id=persona_id, label=p.get("label"))

        return PersonaContext(persona_id=persona_id)

    @router.post("/current_persona", response_model=PersonaContext)
    async def set_current_persona(request: SetPersonaRequest) -> PersonaContext:
        """
        Set the current persona.

        Updates the active persona for the current session.
        If auth is enabled, creates/logs in as a demo user for this persona.
        """
        from datetime import timedelta

        state["current_persona"] = request.persona_id

        # Find persona details
        label = None
        default_route = None
        for p in available_personas:
            if p.get("id") == request.persona_id:
                label = p.get("label")
                default_route = p.get("default_route")
                break

        # If auth is available, create/login demo user for this persona
        session_token = None
        if auth_store is not None:
            demo_email = f"{request.persona_id}@demo.dazzle.local"
            demo_password = f"demo_{request.persona_id}_password"

            # Get or create demo user
            user = auth_store.get_user_by_email(demo_email)
            if not user:
                user = auth_store.create_user(
                    email=demo_email,
                    password=demo_password,
                    username=label or request.persona_id,
                    roles=[request.persona_id],
                )

            # Create session
            session = auth_store.create_session(
                user,
                expires_in=timedelta(days=7),
            )
            session_token = session.id

        return PersonaContext(
            persona_id=request.persona_id,
            label=label,
            session_token=session_token,
            default_route=default_route,
        )

    # -------------------------------------------------------------------------
    # Scenario Endpoints
    # -------------------------------------------------------------------------

    @router.get("/current_scenario", response_model=ScenarioContext | None)
    async def get_current_scenario() -> ScenarioContext | None:
        """Get the currently active scenario."""
        scenario_id = state["current_scenario"]
        if not scenario_id:
            return None

        # Find scenario details
        for s in available_scenarios:
            if s.get("id") == scenario_id:
                return ScenarioContext(scenario_id=scenario_id, name=s.get("name"))

        return ScenarioContext(scenario_id=scenario_id)

    @router.post("/current_scenario", response_model=ScenarioContext)
    async def set_current_scenario(request: SetScenarioRequest) -> ScenarioContext:
        """
        Set the current scenario and seed demo data.

        Updates the active scenario and seeds demo_fixtures if present.
        This enables predictable state setup for Tier 2 (Playwright) testing.
        """
        import uuid

        state["current_scenario"] = request.scenario_id

        # Find scenario details
        scenario = None
        for s in available_scenarios:
            if s.get("id") == request.scenario_id:
                scenario = s
                break

        if not scenario:
            return ScenarioContext(scenario_id=request.scenario_id)

        # Reset and seed demo fixtures for clean state
        demo_fixtures = scenario.get("demo_fixtures", [])
        seeded_counts: dict[str, int] = {}

        if db_manager and repositories:
            # Always reset all data when switching scenarios
            with db_manager.connection() as conn:
                for entity in entities:
                    try:
                        conn.execute(f"DELETE FROM {entity.name}")
                    except Exception:
                        logger.debug("Failed to delete from %s", entity.name, exc_info=True)

            # Seed each fixture if present
            for fixture in demo_fixtures:
                entity_name = fixture.get("entity")
                records = fixture.get("records", [])

                if not entity_name or not records:
                    continue

                repo = repositories.get(entity_name)
                if not repo:
                    continue

                created = 0
                for record in records:
                    # Ensure ID is set
                    if "id" not in record:
                        record["id"] = str(uuid.uuid4())

                    try:
                        await repo.create(record)
                        created += 1
                    except Exception:
                        logger.debug("Failed to seed record for %s", entity_name, exc_info=True)

                seeded_counts[entity_name] = created

        return ScenarioContext(
            scenario_id=request.scenario_id,
            name=scenario.get("name"),
            seeded_counts=seeded_counts if seeded_counts else None,
        )

    # -------------------------------------------------------------------------
    # Data Management Endpoints
    # -------------------------------------------------------------------------

    @router.post("/reset")
    async def reset_data() -> dict[str, str]:
        """
        Reset all data in the database.

        Clears all entity data while preserving schema.
        """
        if not db_manager:
            return {"status": "skipped", "reason": "No database configured"}

        with db_manager.connection() as conn:
            for entity in entities:
                try:
                    conn.execute(f"DELETE FROM {entity.name}")
                except Exception:
                    logger.debug("Failed to reset table %s", entity.name, exc_info=True)

        return {"status": "reset_complete"}

    @router.post("/regenerate")
    async def regenerate_data(request: RegenerateRequest | None = None) -> dict[str, Any]:
        """
        Regenerate demo data for the current scenario.

        Uses Faker-based strategies to generate realistic demo data.
        """
        if not db_manager or not repositories:
            return {"status": "skipped", "reason": "No database configured"}

        # Import demo data generator
        import uuid

        from dazzle_back.demo_data import DemoDataGenerator

        # First reset
        with db_manager.connection() as conn:
            for entity in entities:
                try:
                    conn.execute(f"DELETE FROM {entity.name}")
                except Exception:
                    logger.debug(
                        "Failed to clear table %s before regeneration", entity.name, exc_info=True
                    )

        # Create generator with fixed seed for reproducibility
        generator = DemoDataGenerator(seed=42)
        counts: dict[str, int] = {}
        default_count = 10

        # Use request counts if provided
        entity_counts = (request.entity_counts if request else None) or {}

        for entity in entities:
            repo = repositories.get(entity.name)
            if not repo:
                continue

            count = entity_counts.get(entity.name, default_count)
            created = 0

            # Generate entities using the DemoDataGenerator
            generated_entities = generator.generate_entities(entity, count)

            for entity_data in generated_entities:
                # Ensure ID is set
                if "id" not in entity_data:
                    entity_data["id"] = str(uuid.uuid4())

                try:
                    await repo.create(entity_data)
                    created += 1
                except Exception:
                    logger.debug("Failed to create demo record for %s", entity.name, exc_info=True)

            counts[entity.name] = created

        return {
            "status": "regenerated",
            "counts": counts,
            "scenario_id": request.scenario_id if request else None,
        }

    # -------------------------------------------------------------------------
    # Logging Endpoints (v0.8.11)
    # -------------------------------------------------------------------------

    @router.post("/log")
    async def log_frontend_message(request: FrontendLogRequest) -> dict[str, str]:
        """
        Log a message from the frontend.

        This endpoint captures frontend errors, warnings, and info messages
        and writes them to the JSONL log file for LLM agent monitoring.

        The log file at .dazzle/logs/dnr.log is JSONL format - each line
        is a complete JSON object that LLM agents can parse.
        """
        from dazzle_back.runtime.logging import log_frontend_entry

        log_frontend_entry(
            level=request.level,
            message=request.message,
            source=request.source,
            line=request.line,
            column=request.column,
            stack=request.stack,
            url=request.url,
            user_agent=request.user_agent,
            extra=request.extra,
        )

        return {"status": "logged"}

    @router.get("/logs")
    async def get_logs(count: int = 50, level: str | None = None) -> dict[str, Any]:
        """
        Get recent log entries for LLM agent inspection.

        Returns JSONL entries as a list for easy processing.
        LLM agents can use this to understand recent activity and errors.

        Args:
            count: Number of recent entries (default 50)
            level: Filter by level (ERROR, WARNING, INFO, DEBUG)
        """
        from dazzle_back.runtime.logging import get_log_file, get_recent_logs

        entries = get_recent_logs(count=count, level=level)

        return {
            "count": len(entries),
            "log_file": str(get_log_file()),
            "entries": entries,
        }

    @router.get("/logs/errors")
    async def get_error_summary_endpoint() -> dict[str, Any]:
        """
        Get error summary for LLM agent diagnosis.

        Returns a structured summary of errors grouped by component,
        with recent errors for context. Designed for LLM agents to
        quickly understand what's going wrong.
        """
        from dazzle_back.runtime.logging import get_error_summary

        return get_error_summary()

    @router.delete("/logs")
    async def clear_logs_endpoint() -> dict[str, Any]:
        """
        Clear all log files.

        Useful for starting fresh when debugging.
        """
        from dazzle_back.runtime.logging import clear_logs

        count = clear_logs()
        return {"status": "cleared", "files_deleted": count}

    return router
