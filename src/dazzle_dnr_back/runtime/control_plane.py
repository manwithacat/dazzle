"""
Dazzle Bar Control Plane API.

Provides /dazzle/dev/* endpoints for the Dazzle Bar developer overlay.
These endpoints handle persona switching, scenario control, data management,
feedback capture, and session export.

These endpoints are only available in dev/native mode or when test_mode is enabled.
"""

from __future__ import annotations

import json
import logging
import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

try:
    from fastapi import APIRouter, HTTPException, Response

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    APIRouter = None  # type: ignore[misc, assignment]
    HTTPException = None  # type: ignore[misc, assignment]
    Response = None  # type: ignore[misc, assignment]


if TYPE_CHECKING:
    from dazzle_dnr_back.runtime.auth import AuthStore
    from dazzle_dnr_back.runtime.repository import DatabaseManager, SQLiteRepository
    from dazzle_dnr_back.specs.entity import EntitySpec


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


class FeedbackEntry(BaseModel):
    """A single feedback entry (LLM-friendly structure)."""

    id: str
    timestamp: str
    message: str
    category: str = "General"
    route: str | None = None
    url: str | None = None
    persona_id: str | None = None
    scenario_id: str | None = None
    extra_context: dict[str, Any] | None = None
    status: str = "new"  # new, acknowledged, addressed, wont_fix
    notes: str | None = None  # Developer notes


class FeedbackLogger:
    """
    Logs feedback to structured files for human and LLM consumption.

    Storage formats:
    - feedback.md: Human-readable Markdown (for quick review)
    - feedback.jsonl: Machine-readable JSONL (for LLM ingestion)

    The JSONL format is optimized for LLM processing with structured fields.
    """

    def __init__(self, feedback_dir: Path | None = None):
        self.feedback_dir = feedback_dir or Path("./.dazzle/feedback")
        self.feedback_file = self.feedback_dir / "feedback.md"
        self.jsonl_file = self.feedback_dir / "feedback.jsonl"

    def append_feedback(self, feedback: FeedbackRequest) -> str:
        """
        Append feedback entry to both Markdown and JSONL logs.

        Returns:
            Feedback ID for reference
        """
        import uuid

        self.feedback_dir.mkdir(parents=True, exist_ok=True)

        feedback_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now().isoformat()

        # Create structured entry
        entry = FeedbackEntry(
            id=feedback_id,
            timestamp=timestamp,
            message=feedback.message,
            category=feedback.category or "General",
            route=feedback.route,
            url=feedback.url,
            persona_id=feedback.persona_id,
            scenario_id=feedback.scenario_id,
            extra_context=feedback.extra_context,
            status="new",
        )

        # Write to JSONL (primary format for LLM)
        with open(self.jsonl_file, "a", encoding="utf-8") as f:
            f.write(entry.model_dump_json() + "\n")

        # Write to Markdown (human review)
        md_entry = f"""---
## [{timestamp}] Feedback #{feedback_id}

**Persona**: {feedback.persona_id or "N/A"}
**Scenario**: {feedback.scenario_id or "N/A"}
**Route**: `{feedback.route or "N/A"}`
**Category**: {feedback.category or "General"}

### Message
> {feedback.message}

"""
        if feedback.extra_context:
            md_entry += f"""### Extra Context
```json
{json.dumps(feedback.extra_context, indent=2)}
```

"""

        with open(self.feedback_file, "a", encoding="utf-8") as f:
            f.write(md_entry)

        return feedback_id

    def list_feedback(
        self,
        status: str | None = None,
        category: str | None = None,
        limit: int = 50,
    ) -> list[FeedbackEntry]:
        """
        List feedback entries with optional filtering.

        Args:
            status: Filter by status (new, acknowledged, addressed, wont_fix)
            category: Filter by category
            limit: Maximum entries to return

        Returns:
            List of feedback entries (newest first)
        """
        if not self.jsonl_file.exists():
            return []

        entries: list[FeedbackEntry] = []
        with open(self.jsonl_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = FeedbackEntry.model_validate_json(line)
                    # Apply filters
                    if status and entry.status != status:
                        continue
                    if category and entry.category.lower() != category.lower():
                        continue
                    entries.append(entry)
                except Exception:  # nosec B112
                    continue  # Skip malformed entries

        # Return newest first, limited
        return list(reversed(entries))[:limit]

    def get_feedback(self, feedback_id: str) -> FeedbackEntry | None:
        """
        Get a specific feedback entry by ID.

        Args:
            feedback_id: The feedback ID to retrieve

        Returns:
            FeedbackEntry or None if not found
        """
        if not self.jsonl_file.exists():
            return None

        with open(self.jsonl_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = FeedbackEntry.model_validate_json(line)
                    if entry.id == feedback_id:
                        return entry
                except Exception:  # nosec B112
                    continue

        return None

    def update_feedback_status(
        self,
        feedback_id: str,
        status: str,
        notes: str | None = None,
    ) -> bool:
        """
        Update the status of a feedback entry.

        Args:
            feedback_id: ID of feedback to update
            status: New status (acknowledged, addressed, wont_fix)
            notes: Optional developer notes

        Returns:
            True if updated, False if not found
        """
        if not self.jsonl_file.exists():
            return False

        # Read all entries
        entries: list[FeedbackEntry] = []
        found = False
        with open(self.jsonl_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = FeedbackEntry.model_validate_json(line)
                    if entry.id == feedback_id:
                        # Update this entry
                        entry = FeedbackEntry(
                            **{
                                **entry.model_dump(),
                                "status": status,
                                "notes": notes or entry.notes,
                            }
                        )
                        found = True
                    entries.append(entry)
                except Exception:  # nosec B112
                    continue

        if not found:
            return False

        # Rewrite file with updated entries
        with open(self.jsonl_file, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(entry.model_dump_json() + "\n")

        return True

    def get_summary(self) -> dict[str, Any]:
        """
        Get a summary of feedback for LLM context.

        Returns:
            Summary with counts by status and category
        """
        entries = self.list_feedback(limit=1000)

        by_status: dict[str, int] = {}
        by_category: dict[str, int] = {}

        for entry in entries:
            by_status[entry.status] = by_status.get(entry.status, 0) + 1
            by_category[entry.category] = by_category.get(entry.category, 0) + 1

        return {
            "total": len(entries),
            "by_status": by_status,
            "by_category": by_category,
            "unaddressed": by_status.get("new", 0) + by_status.get("acknowledged", 0),
        }


# =============================================================================
# Feedback Email Sender
# =============================================================================


class FeedbackEmailSender:
    """
    Sends feedback notifications via email.

    Uses SMTP (Mailpit in dev) to send emails to developers.
    Configurable via environment variables:
    - DAZZLE_FEEDBACK_EMAIL: Developer email to receive feedback
    - DAZZLE_SMTP_HOST: SMTP host (default: localhost)
    - DAZZLE_SMTP_PORT: SMTP port (default: 1025 for Mailpit)
    - DAZZLE_APP_NAME: Application name for branding
    """

    def __init__(self) -> None:
        self.developer_email = os.environ.get("DAZZLE_FEEDBACK_EMAIL", "")
        self.smtp_host = os.environ.get("DAZZLE_SMTP_HOST", "localhost")
        self.smtp_port = int(os.environ.get("DAZZLE_SMTP_PORT", "1025"))
        self.app_name = os.environ.get("DAZZLE_APP_NAME", "Dazzle App")
        self.from_email = os.environ.get("DAZZLE_FROM_EMAIL", "feedback@dazzle.local")

    @property
    def is_configured(self) -> bool:
        """Check if email sending is configured."""
        return bool(self.developer_email)

    def send_feedback_email(
        self,
        feedback: FeedbackRequest,
        feedback_id: str,
    ) -> bool:
        """
        Send feedback notification email.

        Args:
            feedback: The feedback request
            feedback_id: Assigned feedback ID

        Returns:
            True if email sent successfully, False otherwise
        """
        if not self.is_configured:
            logger.debug("Feedback email not configured (DAZZLE_FEEDBACK_EMAIL not set)")
            return False

        try:
            # Build email content
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            category = feedback.category or "General"
            route = feedback.route or "N/A"
            persona = feedback.persona_id or "N/A"
            scenario = feedback.scenario_id or "N/A"

            # Extract viewport from extra context
            viewport = "N/A"
            if feedback.extra_context:
                viewport_data = feedback.extra_context.get("viewport", {})
                if viewport_data:
                    viewport = (
                        f"{viewport_data.get('width', '?')}x{viewport_data.get('height', '?')}"
                    )

            # Build HTML email
            subject = f"[Feedback] {category} - {self.app_name}"
            html_body = self._build_html_email(
                feedback=feedback,
                feedback_id=feedback_id,
                timestamp=timestamp,
                category=category,
                route=route,
                persona=persona,
                scenario=scenario,
                viewport=viewport,
            )
            text_body = self._build_text_email(
                feedback=feedback,
                feedback_id=feedback_id,
                timestamp=timestamp,
                category=category,
                route=route,
                persona=persona,
                scenario=scenario,
                viewport=viewport,
            )

            # Build MIME message with structured headers for LLM ingestion
            msg = MIMEMultipart("alternative")
            msg["From"] = self.from_email
            msg["To"] = self.developer_email
            msg["Subject"] = subject

            # Structured headers for machine parsing
            # These X-Dazzle-* headers enable LLM agents to parse feedback
            # from email without needing to extract from body text
            msg["X-Dazzle-Feedback-ID"] = feedback_id
            msg["X-Dazzle-Category"] = category
            msg["X-Dazzle-Route"] = route
            msg["X-Dazzle-Persona"] = persona
            msg["X-Dazzle-Scenario"] = scenario
            msg["X-Dazzle-Viewport"] = viewport
            msg["X-Dazzle-Timestamp"] = timestamp
            msg["X-Dazzle-Status"] = "new"
            msg["X-Dazzle-App"] = self.app_name

            msg.attach(MIMEText(text_body, "plain"))
            msg.attach(MIMEText(html_body, "html"))

            # Send via SMTP
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10) as smtp:
                smtp.sendmail(self.from_email, [self.developer_email], msg.as_string())

            logger.info(f"Feedback email sent to {self.developer_email} (ID: {feedback_id})")
            return True

        except smtplib.SMTPException as e:
            logger.warning(f"Failed to send feedback email (SMTP error): {e}")
            return False
        except ConnectionRefusedError:
            logger.warning(
                f"Failed to send feedback email: Cannot connect to "
                f"{self.smtp_host}:{self.smtp_port} (is Mailpit running?)"
            )
            return False
        except Exception as e:
            logger.warning(f"Failed to send feedback email: {e}")
            return False

    def _build_html_email(
        self,
        feedback: FeedbackRequest,
        feedback_id: str,
        timestamp: str,
        category: str,
        route: str,
        persona: str,
        scenario: str,
        viewport: str,
    ) -> str:
        """Build HTML email body."""
        import html

        extra_context_html = ""
        if feedback.extra_context:
            context_json = json.dumps(feedback.extra_context, indent=2)
            extra_context_html = f"""
                <details style="margin-top: 20px;">
                    <summary style="cursor: pointer; color: #666; font-size: 14px;">Additional Context</summary>
                    <pre style="background: #f0f0f0; padding: 10px; border-radius: 4px; overflow-x: auto; font-size: 12px;">{html.escape(context_json)}</pre>
                </details>
            """

        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5;">
    <table width="100%" cellpadding="0" cellspacing="0" style="max-width: 600px; margin: 0 auto; padding: 20px;">
        <tr>
            <td style="background: #fff; padding: 30px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                <h2 style="color: #0066cc; margin: 0 0 20px 0;">💬 New Feedback Received</h2>

                <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
                    <tr>
                        <td style="padding: 8px 0; border-bottom: 1px solid #eee; color: #666; width: 120px;">Feedback ID:</td>
                        <td style="padding: 8px 0; border-bottom: 1px solid #eee;"><code style="background: #f0f0f0; padding: 2px 6px; border-radius: 3px;">#{feedback_id}</code></td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; border-bottom: 1px solid #eee; color: #666;">Category:</td>
                        <td style="padding: 8px 0; border-bottom: 1px solid #eee;"><strong>{html.escape(category)}</strong></td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; border-bottom: 1px solid #eee; color: #666;">Page:</td>
                        <td style="padding: 8px 0; border-bottom: 1px solid #eee;"><code style="background: #f0f0f0; padding: 2px 6px; border-radius: 3px;">{html.escape(route)}</code></td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; border-bottom: 1px solid #eee; color: #666;">Persona:</td>
                        <td style="padding: 8px 0; border-bottom: 1px solid #eee;">{html.escape(persona)}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; border-bottom: 1px solid #eee; color: #666;">Scenario:</td>
                        <td style="padding: 8px 0; border-bottom: 1px solid #eee;">{html.escape(scenario)}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; border-bottom: 1px solid #eee; color: #666;">Viewport:</td>
                        <td style="padding: 8px 0; border-bottom: 1px solid #eee;">{html.escape(viewport)}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #666;">Timestamp:</td>
                        <td style="padding: 8px 0;">{html.escape(timestamp)}</td>
                    </tr>
                </table>

                <div style="background: #f8f9fa; border-left: 4px solid #0066cc; padding: 15px; margin: 20px 0; border-radius: 0 4px 4px 0;">
                    <p style="margin: 0; white-space: pre-wrap;">{html.escape(feedback.message)}</p>
                </div>

                {extra_context_html}

                <p style="margin: 20px 0 0 0; color: #999; font-size: 12px;">
                    Sent from {html.escape(self.app_name)} Dazzle Bar
                </p>
            </td>
        </tr>
    </table>
</body>
</html>"""

    def _build_text_email(
        self,
        feedback: FeedbackRequest,
        feedback_id: str,
        timestamp: str,
        category: str,
        route: str,
        persona: str,
        scenario: str,
        viewport: str,
    ) -> str:
        """Build plain text email body."""
        extra_context_text = ""
        if feedback.extra_context:
            extra_context_text = f"""
Additional Context:
{json.dumps(feedback.extra_context, indent=2)}
"""

        return f"""NEW FEEDBACK RECEIVED
=====================

Feedback ID: #{feedback_id}
Category: {category}
Page: {route}
Persona: {persona}
Scenario: {scenario}
Viewport: {viewport}
Timestamp: {timestamp}

Message:
--------
{feedback.message}
{extra_context_text}
---
Sent from {self.app_name} Dazzle Bar
"""


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
    auth_store: AuthStore | None = None,
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

    # Initialize feedback logger and email sender
    feedback_logger = FeedbackLogger(feedback_dir)
    feedback_email_sender = FeedbackEmailSender()

    # Log email configuration status
    if feedback_email_sender.is_configured:
        logger.info(
            f"Feedback emails enabled: sending to {feedback_email_sender.developer_email} "
            f"via {feedback_email_sender.smtp_host}:{feedback_email_sender.smtp_port}"
        )
    else:
        logger.debug("Feedback emails disabled (set DAZZLE_FEEDBACK_EMAIL to enable)")

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
    # Health Endpoint
    # -------------------------------------------------------------------------

    @router.get("/health")
    async def get_system_health() -> dict[str, Any]:
        """
        Get system health status for the Dazzle Bar health panel.

        Returns health of API, database, mail provider, and event bus.
        """
        import time

        components = []
        overall = "healthy"

        # Check API health (always healthy if we got here)
        components.append(
            {
                "name": "API",
                "status": "healthy",
                "latency_ms": 1,
            }
        )

        # Check database health
        if db_manager:
            start = time.time()
            try:
                # Quick check - try to access the engine
                if hasattr(db_manager, "_engine") and db_manager._engine:
                    latency = int((time.time() - start) * 1000)
                    components.append(
                        {
                            "name": "Database",
                            "status": "healthy",
                            "latency_ms": latency,
                        }
                    )
                else:
                    components.append(
                        {
                            "name": "Database",
                            "status": "degraded",
                            "message": "Not initialized",
                        }
                    )
                    if overall == "healthy":
                        overall = "degraded"
            except Exception as e:
                components.append(
                    {
                        "name": "Database",
                        "status": "unhealthy",
                        "message": str(e),
                    }
                )
                overall = "unhealthy"
        else:
            components.append(
                {
                    "name": "Database",
                    "status": "degraded",
                    "message": "Not configured",
                }
            )

        # Check Mailpit/email provider
        try:
            import httpx

            mailpit_url = os.getenv("MAILPIT_URL", "http://localhost:8025")
            async with httpx.AsyncClient() as client:
                start = time.time()
                response = await client.get(f"{mailpit_url}/api/v1/info", timeout=2.0)
                latency = int((time.time() - start) * 1000)
                if response.status_code == 200:
                    components.append(
                        {
                            "name": "Mailpit",
                            "status": "healthy",
                            "latency_ms": latency,
                        }
                    )
                else:
                    components.append(
                        {
                            "name": "Mailpit",
                            "status": "degraded",
                            "message": f"Status {response.status_code}",
                        }
                    )
                    if overall == "healthy":
                        overall = "degraded"
        except Exception:
            components.append(
                {
                    "name": "Mailpit",
                    "status": "unhealthy",
                    "message": "Not running",
                }
            )
            # Don't mark overall as unhealthy for Mailpit - it's optional

        # Check event bus (if configured)
        components.append(
            {
                "name": "Events",
                "status": "healthy",
                "message": "In-memory",
            }
        )

        return {
            "overall": overall,
            "components": components,
            "checked_at": datetime.now().isoformat(),
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

        Updates the active persona for the Dazzle Bar session.
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
                        pass

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
                        # Skip on error (e.g., duplicate)
                        pass

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
        import uuid

        from dazzle_dnr_back.demo_data import DemoDataGenerator

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

        Logs feedback to a Markdown file and optionally sends an email
        to the developer (if DAZZLE_FEEDBACK_EMAIL is configured).
        """
        # Add current state to feedback
        if not request.persona_id:
            request.persona_id = state["current_persona"]
        if not request.scenario_id:
            request.scenario_id = state["current_scenario"]

        # Log to file
        feedback_id = feedback_logger.append_feedback(request)

        # Send email notification (non-blocking, logs on failure)
        email_sent = feedback_email_sender.send_feedback_email(request, feedback_id)

        status = "logged_and_emailed" if email_sent else "logged"
        return FeedbackResponse(status=status, feedback_id=feedback_id)

    @router.get("/feedback")
    async def list_feedback_endpoint(
        status: str | None = None,
        category: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """
        List feedback entries for monitoring.

        Useful for Claude Code async feedback monitoring.
        """
        entries = feedback_logger.list_feedback(status=status, category=category, limit=limit)
        return [
            {
                "id": e.id,
                "timestamp": e.timestamp,
                "category": e.category,
                "message": e.message,
                "route": e.route,
                "status": e.status,
                "persona_id": e.persona_id,
                "scenario_id": e.scenario_id,
            }
            for e in entries
        ]

    @router.get("/feedback/{feedback_id}")
    async def get_feedback_endpoint(feedback_id: str) -> dict[str, Any] | None:
        """Get a specific feedback entry by ID."""
        entry = feedback_logger.get_feedback(feedback_id)
        if not entry:
            return None
        return {
            "id": entry.id,
            "timestamp": entry.timestamp,
            "category": entry.category,
            "message": entry.message,
            "route": entry.route,
            "url": entry.url,
            "status": entry.status,
            "persona_id": entry.persona_id,
            "scenario_id": entry.scenario_id,
            "extra_context": entry.extra_context,
        }

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
            title = (
                f"[Dazzle Feedback] Session Export - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            )
            body = f"""## Dazzle Bar Session Export

**Persona**: {state["current_persona"] or "None"}
**Scenario**: {state["current_scenario"] or "None"}
**Timestamp**: {export_data["timestamp"]}

---

"""
            if request.include_feedback and "feedback" in export_data:
                body += f"""### Feedback Log

{export_data["feedback"]}

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
        from dazzle_dnr_back.runtime.logging import log_frontend_entry

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
        from dazzle_dnr_back.runtime.logging import get_log_file, get_recent_logs

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
        from dazzle_dnr_back.runtime.logging import get_error_summary

        return get_error_summary()

    @router.delete("/logs")
    async def clear_logs_endpoint() -> dict[str, Any]:
        """
        Clear all log files.

        Useful for starting fresh when debugging.
        """
        from dazzle_dnr_back.runtime.logging import clear_logs

        count = clear_logs()
        return {"status": "cleared", "files_deleted": count}

    # -------------------------------------------------------------------------
    # Developer Dashboard (Phase 2b)
    # -------------------------------------------------------------------------

    @router.get("/dashboard")
    async def get_dashboard() -> Response:
        """
        Serve the developer dashboard HTML page.

        Provides a comprehensive view of system health, metrics, and events.
        """
        from fastapi.responses import HTMLResponse

        html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Dazzle Developer Dashboard</title>
  <style>
    :root {
      --bg-primary: #0f0f1a;
      --bg-secondary: #1a1a2e;
      --bg-card: #16213e;
      --accent: #e94560;
      --accent-hover: #ff6b6b;
      --text-primary: #e8e8e8;
      --text-secondary: #888;
      --border: #0f3460;
      --success: #4ade80;
      --warning: #fbbf24;
      --error: #ef4444;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: var(--bg-primary);
      color: var(--text-primary);
      min-height: 100vh;
      padding: 24px;
    }
    .dashboard-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 24px;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--border);
    }
    .dashboard-header h1 {
      font-size: 24px;
      font-weight: 600;
      color: var(--accent);
    }
    .refresh-btn {
      background: var(--bg-card);
      border: 1px solid var(--border);
      color: var(--text-primary);
      padding: 8px 16px;
      border-radius: 6px;
      cursor: pointer;
      font-size: 14px;
      transition: all 0.15s;
    }
    .refresh-btn:hover { background: var(--accent); }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }
    .card {
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 16px;
    }
    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 12px;
    }
    .card-title {
      font-size: 14px;
      font-weight: 600;
      color: var(--text-secondary);
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .status-dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
    }
    .status-dot.healthy { background: var(--success); }
    .status-dot.degraded { background: var(--warning); }
    .status-dot.unhealthy { background: var(--error); }
    .component-list { list-style: none; }
    .component-item {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 8px 0;
      border-bottom: 1px solid var(--border);
    }
    .component-item:last-child { border-bottom: none; }
    .component-info {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .component-name { font-weight: 500; }
    .component-latency {
      color: var(--text-secondary);
      font-size: 12px;
    }
    .metric-value {
      font-size: 32px;
      font-weight: 700;
      color: var(--text-primary);
      margin-bottom: 4px;
    }
    .metric-label {
      font-size: 12px;
      color: var(--text-secondary);
    }
    .error-list {
      max-height: 300px;
      overflow-y: auto;
    }
    .error-item {
      padding: 12px;
      background: rgba(239, 68, 68, 0.1);
      border: 1px solid rgba(239, 68, 68, 0.3);
      border-radius: 6px;
      margin-bottom: 8px;
      font-size: 13px;
    }
    .error-item:last-child { margin-bottom: 0; }
    .error-time {
      font-size: 11px;
      color: var(--text-secondary);
      margin-bottom: 4px;
    }
    .error-message { color: var(--error); }
    .empty-state {
      text-align: center;
      padding: 32px;
      color: var(--text-secondary);
    }
    .updated-at {
      text-align: center;
      color: var(--text-secondary);
      font-size: 12px;
      margin-top: 16px;
    }
  </style>
</head>
<body>
  <div class="dashboard-header">
    <h1>Dazzle Developer Dashboard</h1>
    <button class="refresh-btn" onclick="refreshAll()">&#x21bb; Refresh</button>
  </div>

  <div class="grid">
    <!-- Health Status Card -->
    <div class="card">
      <div class="card-header">
        <span class="card-title">System Health</span>
        <span class="status-dot" id="overall-status"></span>
      </div>
      <ul class="component-list" id="health-components">
        <li class="empty-state">Loading...</li>
      </ul>
    </div>

    <!-- Request Metrics Card -->
    <div class="card">
      <div class="card-header">
        <span class="card-title">Request Metrics</span>
      </div>
      <div class="metric-value" id="request-count">--</div>
      <div class="metric-label">Total Requests</div>
      <div style="margin-top: 16px;">
        <div class="metric-value" id="avg-latency">--</div>
        <div class="metric-label">Avg Latency (ms)</div>
      </div>
    </div>

    <!-- Event Bus Card -->
    <div class="card">
      <div class="card-header">
        <span class="card-title">Event Bus</span>
      </div>
      <div class="metric-value" id="event-count">--</div>
      <div class="metric-label">Events Published</div>
      <div style="margin-top: 16px;">
        <div class="metric-value" id="subscriber-count">--</div>
        <div class="metric-label">Active Subscribers</div>
      </div>
    </div>
  </div>

  <!-- Recent Errors Card -->
  <div class="card">
    <div class="card-header">
      <span class="card-title">Recent Errors</span>
    </div>
    <div class="error-list" id="error-list">
      <div class="empty-state">Loading...</div>
    </div>
  </div>

  <div class="updated-at" id="updated-at"></div>

  <script>
    async function fetchHealth() {
      try {
        const resp = await fetch('/dazzle/dev/health');
        const data = await resp.json();

        const statusDot = document.getElementById('overall-status');
        statusDot.className = 'status-dot ' + (data.overall || 'healthy');

        const list = document.getElementById('health-components');
        if (data.components && data.components.length) {
          list.innerHTML = data.components.map(c => `
            <li class="component-item">
              <div class="component-info">
                <span class="status-dot ${c.status}"></span>
                <span class="component-name">${c.name}</span>
              </div>
              <span class="component-latency">${c.latency_ms ? c.latency_ms + 'ms' : c.message || ''}</span>
            </li>
          `).join('');
        } else {
          list.innerHTML = '<li class="empty-state">No components</li>';
        }
      } catch (e) {
        console.error('Failed to fetch health:', e);
      }
    }

    async function fetchMetrics() {
      try {
        const resp = await fetch('/dazzle/dev/dashboard/metrics');
        const data = await resp.json();

        document.getElementById('request-count').textContent = data.total_requests || 0;
        document.getElementById('avg-latency').textContent = data.avg_latency_ms?.toFixed(1) || '--';
        document.getElementById('event-count').textContent = data.events_published || 0;
        document.getElementById('subscriber-count').textContent = data.active_subscribers || 0;
      } catch (e) {
        // Metrics endpoint may not exist yet
        document.getElementById('request-count').textContent = '--';
        document.getElementById('avg-latency').textContent = '--';
      }
    }

    async function fetchErrors() {
      try {
        const resp = await fetch('/dazzle/dev/logs/errors');
        const data = await resp.json();

        const list = document.getElementById('error-list');
        const errors = data.recent_errors || [];

        if (errors.length === 0) {
          list.innerHTML = '<div class="empty-state">No recent errors</div>';
        } else {
          list.innerHTML = errors.slice(0, 10).map(e => `
            <div class="error-item">
              <div class="error-time">${e.timestamp || ''}</div>
              <div class="error-message">${e.message || e.error || 'Unknown error'}</div>
            </div>
          `).join('');
        }
      } catch (e) {
        document.getElementById('error-list').innerHTML =
          '<div class="empty-state">Failed to load errors</div>';
      }
    }

    async function refreshAll() {
      await Promise.all([fetchHealth(), fetchMetrics(), fetchErrors()]);
      document.getElementById('updated-at').textContent =
        'Last updated: ' + new Date().toLocaleTimeString();
    }

    // Initial load
    refreshAll();

    // Auto-refresh every 10 seconds
    setInterval(refreshAll, 10000);
  </script>
</body>
</html>"""
        return HTMLResponse(content=html)

    @router.get("/dashboard/metrics")
    async def get_dashboard_metrics() -> dict[str, Any]:
        """
        Get request metrics for the dashboard.

        Returns request counts, latency stats, and event bus metrics.
        """
        # These would come from actual instrumentation
        # For now, return placeholder data that can be enhanced
        metrics: dict[str, Any] = {
            "total_requests": 0,
            "avg_latency_ms": 0.0,
            "p50_latency_ms": 0.0,
            "p95_latency_ms": 0.0,
            "p99_latency_ms": 0.0,
            "events_published": 0,
            "active_subscribers": 0,
            "errors_last_hour": 0,
        }

        # Try to get actual metrics from logging system
        try:
            from dazzle_dnr_back.runtime.logging import get_recent_logs

            logs = get_recent_logs(count=100)
            request_logs = [log for log in logs if log.get("type") == "request"]
            error_logs = [log for log in logs if log.get("level") == "ERROR"]

            metrics["total_requests"] = len(request_logs)
            metrics["errors_last_hour"] = len(error_logs)

            if request_logs:
                latencies = [
                    entry.get("latency_ms", 0) for entry in request_logs if "latency_ms" in entry
                ]
                if latencies:
                    metrics["avg_latency_ms"] = sum(latencies) / len(latencies)
        except Exception:
            pass

        return metrics

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
