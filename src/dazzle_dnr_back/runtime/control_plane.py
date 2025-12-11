"""
Dazzle Bar Control Plane API.

Provides /dazzle/dev/* endpoints for the Dazzle Bar developer overlay.
These endpoints handle persona switching, scenario control, data management,
feedback capture, and session export.

These endpoints are only available in dev/native mode or when test_mode is enabled.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

try:
    from fastapi import APIRouter, HTTPException

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    APIRouter = None  # type: ignore[misc, assignment]
    HTTPException = None  # type: ignore[misc, assignment]


if TYPE_CHECKING:
    from dazzle_dnr_back.runtime.repository import DatabaseManager, SQLiteRepository
    from dazzle_dnr_back.specs.entity import EntitySpec


# =============================================================================
# Request/Response Models
# =============================================================================


class PersonaContext(BaseModel):
    """Current persona context."""

    persona_id: str
    label: str | None = None


class ScenarioContext(BaseModel):
    """Current scenario context."""

    scenario_id: str
    name: str | None = None


class SetPersonaRequest(BaseModel):
    """Request to set current persona."""

    persona_id: str


class SetScenarioRequest(BaseModel):
    """Request to set current scenario."""

    scenario_id: str


class FeedbackRequest(BaseModel):
    """Feedback submission from Dazzle Bar."""

    message: str
    category: str | None = None
    persona_id: str | None = None
    scenario_id: str | None = None
    route: str | None = None
    url: str | None = None
    extra_context: dict[str, Any] | None = None


class FeedbackResponse(BaseModel):
    """Response after feedback submission."""

    status: str
    feedback_id: str


class ExportRequest(BaseModel):
    """Session export request."""

    include_spec: bool = True
    include_feedback: bool = True
    include_session_data: bool = False
    export_format: str = "github_issue"  # github_issue, json, markdown


class ExportResponse(BaseModel):
    """Session export response."""

    status: str
    export_url: str | None = None
    export_data: dict[str, Any] | None = None


class RegenerateRequest(BaseModel):
    """Request to regenerate demo data."""

    scenario_id: str | None = None
    entity_counts: dict[str, int] | None = None


class DazzleBarState(BaseModel):
    """Complete Dazzle Bar state."""

    current_persona: str | None = None
    current_scenario: str | None = None
    available_personas: list[dict[str, Any]] = Field(default_factory=list)
    available_scenarios: list[dict[str, Any]] = Field(default_factory=list)
    dev_mode: bool = True


# =============================================================================
# Feedback Logger
# =============================================================================


class FeedbackLogger:
    """
    Logs feedback to a Markdown file.

    Appends feedback entries in a structured format for easy review.
    """

    def __init__(self, feedback_dir: Path | None = None):
        self.feedback_dir = feedback_dir or Path("./dazzle_feedback")
        self.feedback_file = self.feedback_dir / "feedback.md"

    def append_feedback(self, feedback: FeedbackRequest) -> str:
        """
        Append feedback entry to Markdown log.

        Returns:
            Feedback ID for reference
        """
        import uuid

        self.feedback_dir.mkdir(parents=True, exist_ok=True)

        feedback_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now().isoformat()

        entry = f"""---
## [{timestamp}] Feedback #{feedback_id}

**Persona**: {feedback.persona_id or 'N/A'}
**Scenario**: {feedback.scenario_id or 'N/A'}
**Route**: `{feedback.route or 'N/A'}`
**Category**: {feedback.category or 'General'}

### Message
> {feedback.message}

"""
        if feedback.extra_context:
            entry += f"""### Extra Context
```json
{json.dumps(feedback.extra_context, indent=2)}
```

"""

        # Append to file
        with open(self.feedback_file, "a", encoding="utf-8") as f:
            f.write(entry)

        return feedback_id


# =============================================================================
# Session Export
# =============================================================================


def generate_github_issue_url(
    title: str,
    body: str,
    repo: str | None = None,
    labels: list[str] | None = None,
) -> str:
    """
    Generate a GitHub issue creation URL.

    Args:
        title: Issue title
        body: Issue body (Markdown)
        repo: Repository in format "owner/repo" (optional)
        labels: Issue labels (optional)

    Returns:
        GitHub issue creation URL
    """
    import urllib.parse

    # Default repo from environment or use a placeholder
    repo = repo or os.environ.get("DAZZLE_GITHUB_REPO", "")

    if not repo:
        # Return a template URL that user can customize
        repo = "owner/repo"

    params = {
        "title": title,
        "body": body,
    }

    if labels:
        params["labels"] = ",".join(labels)

    query_string = urllib.parse.urlencode(params)
    return f"https://github.com/{repo}/issues/new?{query_string}"


# =============================================================================
# Control Plane Router
# =============================================================================


def create_control_plane_routes(
    db_manager: DatabaseManager | None,
    repositories: dict[str, SQLiteRepository[Any]] | None,
    entities: list[EntitySpec],
    personas: list[dict[str, Any]] | None = None,
    scenarios: list[dict[str, Any]] | None = None,
    feedback_dir: Path | None = None,
) -> APIRouter:
    """
    Create Dazzle Bar control plane routes.

    Args:
        db_manager: Database manager instance (optional)
        repositories: Dictionary of repositories by entity name (optional)
        entities: List of entity specifications
        personas: List of persona configurations
        scenarios: List of scenario configurations
        feedback_dir: Directory for feedback logs

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

    # Initialize feedback logger
    feedback_logger = FeedbackLogger(feedback_dir)

    # Prepare personas and scenarios lists
    available_personas = personas or []
    available_scenarios = scenarios or []

    # -------------------------------------------------------------------------
    # State Endpoints
    # -------------------------------------------------------------------------

    @router.get("/state", response_model=DazzleBarState)
    async def get_dazzle_state() -> DazzleBarState:
        """
        Get complete Dazzle Bar state.

        Returns current persona, scenario, and available options.
        """
        return DazzleBarState(
            current_persona=state["current_persona"],
            current_scenario=state["current_scenario"],
            available_personas=available_personas,
            available_scenarios=available_scenarios,
            dev_mode=True,
        )

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

        Updates the active persona for the Dazzle Bar session.
        """
        state["current_persona"] = request.persona_id

        # Find persona details
        label = None
        for p in available_personas:
            if p.get("id") == request.persona_id:
                label = p.get("label")
                break

        return PersonaContext(persona_id=request.persona_id, label=label)

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
        Set the current scenario.

        Updates the active scenario and can trigger data seeding.
        """
        state["current_scenario"] = request.scenario_id

        # Find scenario details
        name = None
        for s in available_scenarios:
            if s.get("id") == request.scenario_id:
                name = s.get("name")
                break

        return ScenarioContext(scenario_id=request.scenario_id, name=name)

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
                    # Table might not exist
                    pass

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
        from dazzle_dnr_back.demo_data import DemoDataGenerator

        import uuid

        # First reset
        with db_manager.connection() as conn:
            for entity in entities:
                try:
                    conn.execute(f"DELETE FROM {entity.name}")
                except Exception:
                    pass

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
                    # Skip on error
                    pass

            counts[entity.name] = created

        return {
            "status": "regenerated",
            "counts": counts,
            "scenario_id": request.scenario_id if request else None,
        }

    # -------------------------------------------------------------------------
    # Feedback Endpoints
    # -------------------------------------------------------------------------

    @router.post("/feedback", response_model=FeedbackResponse)
    async def submit_feedback(request: FeedbackRequest) -> FeedbackResponse:
        """
        Submit feedback from the Dazzle Bar.

        Logs feedback to a Markdown file for review.
        """
        # Add current state to feedback
        if not request.persona_id:
            request.persona_id = state["current_persona"]
        if not request.scenario_id:
            request.scenario_id = state["current_scenario"]

        feedback_id = feedback_logger.append_feedback(request)

        return FeedbackResponse(status="logged", feedback_id=feedback_id)

    # -------------------------------------------------------------------------
    # Export Endpoints
    # -------------------------------------------------------------------------

    @router.post("/export", response_model=ExportResponse)
    async def export_session(request: ExportRequest) -> ExportResponse:
        """
        Export session data for reporting.

        Can generate GitHub issue URLs or raw export data.
        """
        # Check if export is enabled
        export_enabled = os.environ.get("DAZZLE_EXPORT_ENABLED", "true").lower() == "true"

        if not export_enabled:
            return ExportResponse(
                status="disabled",
                export_url=None,
                export_data={"message": "Export is disabled via DAZZLE_EXPORT_ENABLED"},
            )

        # Build export content
        export_data: dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "persona": state["current_persona"],
            "scenario": state["current_scenario"],
        }

        if request.include_feedback:
            feedback_file = feedback_logger.feedback_file
            if feedback_file.exists():
                export_data["feedback"] = feedback_file.read_text()

        if request.export_format == "github_issue":
            # Generate GitHub issue
            title = f"[Dazzle Feedback] Session Export - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            body = f"""## Dazzle Bar Session Export

**Persona**: {state['current_persona'] or 'None'}
**Scenario**: {state['current_scenario'] or 'None'}
**Timestamp**: {export_data['timestamp']}

---

"""
            if request.include_feedback and "feedback" in export_data:
                body += f"""### Feedback Log

{export_data['feedback']}

"""

            body += """---

*Generated by Dazzle Bar*
"""

            export_url = generate_github_issue_url(
                title=title,
                body=body,
                labels=["dazzle-feedback"],
            )

            return ExportResponse(
                status="generated",
                export_url=export_url,
                export_data=None,
            )

        else:
            # Return raw export data
            return ExportResponse(
                status="exported",
                export_url=None,
                export_data=export_data,
            )

    # -------------------------------------------------------------------------
    # Inspector Endpoints (Basic)
    # -------------------------------------------------------------------------

    @router.get("/inspect/entities")
    async def inspect_entities() -> dict[str, Any]:
        """
        Get entity information for the inspector panel.

        Returns entity schemas and current record counts.
        """
        entity_info: list[dict[str, Any]] = []

        for entity in entities:
            info: dict[str, Any] = {
                "name": entity.name,
                "label": entity.label or entity.name,
                "fields": [
                    {
                        "name": f.name,
                        "type": str(f.type.scalar_type.value) if f.type.scalar_type else "unknown",
                        "required": f.required,
                    }
                    for f in entity.fields
                ],
            }

            # Add count if database is available
            if db_manager:
                try:
                    with db_manager.connection() as conn:
                        cursor = conn.execute(f"SELECT COUNT(*) FROM {entity.name}")
                        info["count"] = cursor.fetchone()[0]
                except Exception:
                    info["count"] = 0

            entity_info.append(info)

        return {"entities": entity_info}

    @router.get("/inspect/routes")
    async def inspect_routes() -> dict[str, Any]:
        """
        Get registered route information for the inspector panel.
        """
        # Return basic route info - this would be enhanced with actual route data
        return {
            "routes": [
                {"path": "/dazzle/dev/*", "tags": ["Dazzle Control Plane"]},
                {"path": "/__test__/*", "tags": ["Testing"]},
            ],
            "note": "Full route inspection requires app context",
        }

    return router


# =============================================================================
# Helper Functions
# =============================================================================


def _generate_field_value(field: Any, index: int) -> Any:
    """
    Generate a simple demo value for a field.

    This is a basic implementation - can be enhanced with Faker integration.
    """
    from datetime import date, datetime

    field_type = str(field.type).lower() if hasattr(field, "type") else ""
    field_name = field.name.lower() if hasattr(field, "name") else ""

    # Type-based generation
    if "uuid" in field_type:
        import uuid

        return str(uuid.uuid4())
    elif "email" in field_type or "email" in field_name:
        return f"user{index}@example.com"
    elif "bool" in field_type:
        return index % 2 == 0
    elif "int" in field_type:
        return index + 1
    elif "float" in field_type or "decimal" in field_type:
        return float(index) + 0.5
    elif "date" in field_type and "time" not in field_type:
        return date.today().isoformat()
    elif "datetime" in field_type or "timestamp" in field_type:
        return datetime.now().isoformat()
    elif "str" in field_type or "text" in field_type:
        # Name-based heuristics
        if "name" in field_name:
            return f"Demo Item {index + 1}"
        elif "title" in field_name:
            return f"Title {index + 1}"
        elif "description" in field_name:
            return f"Description for item {index + 1}"
        elif "status" in field_name:
            statuses = ["pending", "active", "completed"]
            return statuses[index % len(statuses)]
        else:
            return f"Value {index + 1}"

    # Return None for unknown types (will be skipped)
    return None
