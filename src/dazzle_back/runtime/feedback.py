"""
Feedback logging and email notification for Dazzle Bar.

This module handles user feedback capture, storage, and email notifications.
Extracted from control_plane.py to improve modularity.
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
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)


# =============================================================================
# Feedback Models
# =============================================================================


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


# =============================================================================
# Feedback Logger
# =============================================================================


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
