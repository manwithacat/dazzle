"""
Email Template System with Tracking.

Provides a template engine for emails with:
- Variable substitution
- Branded signatures and footers
- Open tracking (pixel injection)
- Click tracking (link rewriting)

Usage:
    template_engine = EmailTemplateEngine(ops_db, tracking_base_url="https://app.example.com")

    email = template_engine.render(
        template_name="welcome",
        context={"user_name": "John", "app_name": "MyApp"},
        recipient="john@example.com",
    )
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode
from uuid import uuid4

if TYPE_CHECKING:
    from dazzle_back.runtime.ops_database import OpsDatabase


def _utcnow() -> datetime:
    """Return current UTC datetime (timezone-aware)."""
    return datetime.now(UTC)


@dataclass
class BrandConfig:
    """Brand configuration for email signatures."""

    name: str = "My App"
    logo_url: str | None = None
    tagline: str | None = None
    website_url: str | None = None
    support_email: str | None = None

    # Social links
    twitter_url: str | None = None
    linkedin_url: str | None = None
    facebook_url: str | None = None

    # Colors
    primary_color: str = "#0066cc"
    text_color: str = "#333333"
    background_color: str = "#ffffff"


@dataclass
class EmailTemplate:
    """An email template definition."""

    name: str
    subject: str
    body_html: str
    body_text: str | None = None

    # Template metadata
    description: str | None = None
    category: str = "transactional"  # transactional, marketing, notification


@dataclass
class RenderedEmail:
    """A fully rendered email ready for sending."""

    email_id: str
    recipient: str
    subject: str
    body_html: str
    body_text: str
    template_name: str
    rendered_at: datetime = field(default_factory=_utcnow)
    tracking_enabled: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EmailTrackingRecord:
    """Record of email tracking events."""

    id: str
    email_id: str
    event_type: str  # "sent", "opened", "clicked"
    timestamp: datetime
    click_url: str | None = None
    user_agent: str | None = None
    ip_address: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


# Default templates
DEFAULT_TEMPLATES: dict[str, EmailTemplate] = {
    "welcome": EmailTemplate(
        name="welcome",
        subject="Welcome to {{ app_name }}, {{ user_name }}!",
        body_html="""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
    <table width="100%" cellpadding="0" cellspacing="0" style="max-width: 600px; margin: 0 auto; padding: 20px;">
        <tr>
            <td>
                <h1 style="color: {{ brand_color }};">Welcome, {{ user_name }}!</h1>
                <p>Thank you for joining {{ app_name }}. We're excited to have you on board.</p>
                <p>{{ custom_message }}</p>
                <p>
                    <a href="{{ action_url }}" style="display: inline-block; padding: 12px 24px; background: {{ brand_color }}; color: white; text-decoration: none; border-radius: 4px;">
                        {{ action_text }}
                    </a>
                </p>
                {{ signature }}
            </td>
        </tr>
    </table>
</body>
</html>
        """,
        body_text="""
Welcome, {{ user_name }}!

Thank you for joining {{ app_name }}. We're excited to have you on board.

{{ custom_message }}

{{ action_text }}: {{ action_url }}

{{ signature_text }}
        """,
        description="Welcome email for new users",
        category="transactional",
    ),
    "notification": EmailTemplate(
        name="notification",
        subject="{{ notification_title }}",
        body_html="""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
    <table width="100%" cellpadding="0" cellspacing="0" style="max-width: 600px; margin: 0 auto; padding: 20px;">
        <tr>
            <td>
                <h2 style="color: {{ brand_color }};">{{ notification_title }}</h2>
                <p>{{ notification_body }}</p>
                {% if action_url %}
                <p>
                    <a href="{{ action_url }}" style="display: inline-block; padding: 10px 20px; background: {{ brand_color }}; color: white; text-decoration: none; border-radius: 4px;">
                        {{ action_text }}
                    </a>
                </p>
                {% endif %}
                {{ signature }}
            </td>
        </tr>
    </table>
</body>
</html>
        """,
        body_text="""
{{ notification_title }}

{{ notification_body }}

{% if action_url %}{{ action_text }}: {{ action_url }}{% endif %}

{{ signature_text }}
        """,
        description="Generic notification email",
        category="notification",
    ),
    "password_reset": EmailTemplate(
        name="password_reset",
        subject="Reset your {{ app_name }} password",
        body_html="""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
    <table width="100%" cellpadding="0" cellspacing="0" style="max-width: 600px; margin: 0 auto; padding: 20px;">
        <tr>
            <td>
                <h2 style="color: {{ brand_color }};">Password Reset Request</h2>
                <p>Hi {{ user_name }},</p>
                <p>We received a request to reset your password. Click the button below to create a new password:</p>
                <p>
                    <a href="{{ reset_url }}" style="display: inline-block; padding: 12px 24px; background: {{ brand_color }}; color: white; text-decoration: none; border-radius: 4px;">
                        Reset Password
                    </a>
                </p>
                <p style="color: #666; font-size: 14px;">This link will expire in {{ expiry_hours }} hours.</p>
                <p style="color: #666; font-size: 14px;">If you didn't request this, you can safely ignore this email.</p>
                {{ signature }}
            </td>
        </tr>
    </table>
</body>
</html>
        """,
        body_text="""
Password Reset Request

Hi {{ user_name }},

We received a request to reset your password. Visit this link to create a new password:

{{ reset_url }}

This link will expire in {{ expiry_hours }} hours.

If you didn't request this, you can safely ignore this email.

{{ signature_text }}
        """,
        description="Password reset email",
        category="transactional",
    ),
    "feedback": EmailTemplate(
        name="feedback",
        subject="[Feedback] {{ category }} - {{ app_name }}",
        body_html="""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5;">
    <table width="100%" cellpadding="0" cellspacing="0" style="max-width: 600px; margin: 0 auto; padding: 20px;">
        <tr>
            <td style="background: #fff; padding: 30px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                <h2 style="color: {{ brand_color }}; margin: 0 0 20px 0;">💬 New Feedback Received</h2>

                <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
                    <tr>
                        <td style="padding: 8px 0; border-bottom: 1px solid #eee; color: #666; width: 120px;">Category:</td>
                        <td style="padding: 8px 0; border-bottom: 1px solid #eee;"><strong>{{ category }}</strong></td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; border-bottom: 1px solid #eee; color: #666;">Page:</td>
                        <td style="padding: 8px 0; border-bottom: 1px solid #eee;"><code style="background: #f0f0f0; padding: 2px 6px; border-radius: 3px;">{{ route }}</code></td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; border-bottom: 1px solid #eee; color: #666;">Persona:</td>
                        <td style="padding: 8px 0; border-bottom: 1px solid #eee;">{{ persona }}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; border-bottom: 1px solid #eee; color: #666;">Scenario:</td>
                        <td style="padding: 8px 0; border-bottom: 1px solid #eee;">{{ scenario }}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; border-bottom: 1px solid #eee; color: #666;">Viewport:</td>
                        <td style="padding: 8px 0; border-bottom: 1px solid #eee;">{{ viewport }}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; color: #666;">Timestamp:</td>
                        <td style="padding: 8px 0;">{{ timestamp }}</td>
                    </tr>
                </table>

                <div style="background: #f8f9fa; border-left: 4px solid {{ brand_color }}; padding: 15px; margin: 20px 0; border-radius: 0 4px 4px 0;">
                    <p style="margin: 0; white-space: pre-wrap;">{{ message }}</p>
                </div>

                {% if extra_context %}
                <details style="margin-top: 20px;">
                    <summary style="cursor: pointer; color: #666; font-size: 14px;">Additional Context</summary>
                    <pre style="background: #f0f0f0; padding: 10px; border-radius: 4px; overflow-x: auto; font-size: 12px;">{{ extra_context }}</pre>
                </details>
                {% endif %}

                <p style="margin: 20px 0 0 0; color: #999; font-size: 12px;">
                    Sent from {{ app_name }} Dazzle Bar
                </p>
            </td>
        </tr>
    </table>
</body>
</html>
        """,
        body_text="""
NEW FEEDBACK RECEIVED
=====================

Category: {{ category }}
Page: {{ route }}
Persona: {{ persona }}
Scenario: {{ scenario }}
Viewport: {{ viewport }}
Timestamp: {{ timestamp }}

Message:
--------
{{ message }}

{% if extra_context %}
Additional Context:
{{ extra_context }}
{% endif %}

---
Sent from {{ app_name }} Dazzle Bar
        """,
        description="Feedback notification email for developers",
        category="notification",
    ),
}


class EmailTemplateEngine:
    """
    Email template engine with variable substitution and tracking.

    Provides:
    - Template rendering with Jinja2-like syntax
    - Branded signature injection
    - Open tracking via pixel injection
    - Click tracking via link rewriting
    """

    def __init__(
        self,
        ops_db: OpsDatabase | None = None,
        tracking_base_url: str | None = None,
        brand_config: BrandConfig | None = None,
        custom_templates: dict[str, EmailTemplate] | None = None,
    ):
        """
        Initialize the template engine.

        Args:
            ops_db: Operations database for tracking storage
            tracking_base_url: Base URL for tracking endpoints
            brand_config: Brand configuration for signatures
            custom_templates: Additional custom templates
        """
        self.ops_db = ops_db
        self.tracking_base_url = tracking_base_url
        self.brand = brand_config or BrandConfig()

        # Merge templates
        self.templates: dict[str, EmailTemplate] = {
            **DEFAULT_TEMPLATES,
            **(custom_templates or {}),
        }

    def register_template(self, template: EmailTemplate) -> None:
        """Register a new template."""
        self.templates[template.name] = template

    def render(
        self,
        template_name: str,
        context: dict[str, Any],
        recipient: str,
        *,
        track_opens: bool = True,
        track_clicks: bool = True,
        tenant_id: str | None = None,
    ) -> RenderedEmail:
        """
        Render an email template with context.

        Args:
            template_name: Name of the template to use
            context: Variables to substitute
            recipient: Recipient email address
            track_opens: Whether to inject tracking pixel
            track_clicks: Whether to rewrite links for tracking
            tenant_id: Optional tenant ID for scoping

        Returns:
            RenderedEmail ready for sending
        """
        template = self.templates.get(template_name)
        if not template:
            raise ValueError(f"Template not found: {template_name}")

        email_id = str(uuid4())

        # Build full context with brand defaults
        full_context = self._build_context(context)

        # Render subject
        subject = self._substitute_variables(template.subject, full_context)

        # Render HTML body
        body_html = self._substitute_variables(template.body_html, full_context)

        # Add tracking if enabled
        tracking_enabled = False
        if self.tracking_base_url:
            if track_opens:
                body_html = self._inject_tracking_pixel(body_html, email_id)
                tracking_enabled = True

            if track_clicks:
                body_html = self._rewrite_links(body_html, email_id)
                tracking_enabled = True

        # Render text body
        body_text = ""
        if template.body_text:
            body_text = self._substitute_variables(template.body_text, full_context)
            body_text = self._strip_conditionals(body_text)

        return RenderedEmail(
            email_id=email_id,
            recipient=recipient,
            subject=subject,
            body_html=body_html,
            body_text=body_text,
            template_name=template_name,
            tracking_enabled=tracking_enabled,
            metadata={
                "tenant_id": tenant_id,
                "context_keys": list(context.keys()),
            },
        )

    def _build_context(self, context: dict[str, Any]) -> dict[str, Any]:
        """Build full context with brand defaults."""
        return {
            # Brand defaults
            "app_name": self.brand.name,
            "brand_color": self.brand.primary_color,
            "text_color": self.brand.text_color,
            "bg_color": self.brand.background_color,
            "signature": self._generate_signature_html(),
            "signature_text": self._generate_signature_text(),
            # User context (overrides defaults)
            **context,
        }

    def _substitute_variables(self, template: str, context: dict[str, Any]) -> str:
        """Substitute {{ variable }} patterns in template."""

        # Simple variable substitution
        def replace_var(match: re.Match[str]) -> str:
            var_name = match.group(1).strip()
            value = context.get(var_name, "")
            if value is None:
                return ""
            return html.escape(str(value)) if isinstance(value, str) else str(value)

        result = re.sub(r"\{\{\s*(\w+)\s*\}\}", replace_var, template)

        # Handle conditionals {% if var %}...{% endif %}
        result = self._process_conditionals(result, context)

        return result

    def _process_conditionals(self, template: str, context: dict[str, Any]) -> str:
        """Process {% if var %}...{% endif %} conditionals."""
        # Simple if/endif processing
        pattern = r"\{%\s*if\s+(\w+)\s*%\}(.*?)\{%\s*endif\s*%\}"

        def replace_conditional(match: re.Match[str]) -> str:
            var_name = match.group(1)
            content = match.group(2)
            value = context.get(var_name)

            if value:
                return content
            return ""

        return re.sub(pattern, replace_conditional, template, flags=re.DOTALL)

    def _strip_conditionals(self, text: str) -> str:
        """Remove conditional syntax from text (for text version)."""
        # Remove {% if ... %} and {% endif %}
        text = re.sub(r"\{%\s*if\s+\w+\s*%\}", "", text)
        text = re.sub(r"\{%\s*endif\s*%\}", "", text)
        # Clean up extra whitespace
        text = re.sub(r"\n\s*\n\s*\n", "\n\n", text)
        return text.strip()

    def _generate_signature_html(self) -> str:
        """Generate HTML signature block."""
        parts = ['<div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee;">']

        if self.brand.logo_url:
            parts.append(
                f'<img src="{html.escape(self.brand.logo_url)}" '
                f'alt="{html.escape(self.brand.name)}" height="40" style="margin-bottom: 10px;">'
            )

        parts.append(f'<p style="margin: 0; color: {self.brand.text_color};">')
        parts.append(f"<strong>{html.escape(self.brand.name)}</strong>")

        if self.brand.tagline:
            parts.append(f"<br><em>{html.escape(self.brand.tagline)}</em>")

        parts.append("</p>")

        # Social links
        social_links = []
        if self.brand.twitter_url:
            social_links.append(f'<a href="{html.escape(self.brand.twitter_url)}">Twitter</a>')
        if self.brand.linkedin_url:
            social_links.append(f'<a href="{html.escape(self.brand.linkedin_url)}">LinkedIn</a>')
        if self.brand.facebook_url:
            social_links.append(f'<a href="{html.escape(self.brand.facebook_url)}">Facebook</a>')

        if social_links:
            parts.append(
                f'<p style="margin: 10px 0 0 0; font-size: 14px;">{" | ".join(social_links)}</p>'
            )

        if self.brand.website_url:
            parts.append(
                f'<p style="margin: 5px 0 0 0; font-size: 14px;">'
                f'<a href="{html.escape(self.brand.website_url)}">{html.escape(self.brand.website_url)}</a>'
                f"</p>"
            )

        parts.append("</div>")
        return "\n".join(parts)

    def _generate_signature_text(self) -> str:
        """Generate plain text signature."""
        lines = ["---", self.brand.name]

        if self.brand.tagline:
            lines.append(self.brand.tagline)

        if self.brand.website_url:
            lines.append(self.brand.website_url)

        return "\n".join(lines)

    def _inject_tracking_pixel(self, html_body: str, email_id: str) -> str:
        """Inject tracking pixel before </body>."""
        if not self.tracking_base_url:
            return html_body

        pixel_url = f"{self.tracking_base_url}/_ops/email/pixel/{email_id}.gif"
        pixel_tag = f'<img src="{pixel_url}" width="1" height="1" alt="" style="display:none;" />'

        # Insert before </body>
        if "</body>" in html_body:
            return html_body.replace("</body>", f"{pixel_tag}</body>")
        # Or at the end
        return html_body + pixel_tag

    def _rewrite_links(self, html_body: str, email_id: str) -> str:
        """Rewrite links for click tracking."""
        if not self.tracking_base_url:
            return html_body

        def rewrite_link(match: re.Match[str]) -> str:
            original_url = match.group(1)

            # Skip mailto: and anchor links
            if original_url.startswith(("mailto:", "#", "tel:")):
                return match.group(0)

            # Skip tracking URLs (avoid double-encoding)
            if "/_ops/email/" in original_url:
                return match.group(0)

            # Build tracking URL
            params = urlencode({"url": original_url})
            tracking_url = f"{self.tracking_base_url}/_ops/email/click/{email_id}?{params}"
            return f'href="{tracking_url}"'

        # Match href="..." attributes
        return re.sub(r'href="([^"]+)"', rewrite_link, html_body)

    def record_event(
        self,
        email_id: str,
        event_type: str,
        click_url: str | None = None,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> str:
        """
        Record an email tracking event.

        Args:
            email_id: The tracked email ID
            event_type: Event type (sent, opened, clicked)
            click_url: URL clicked (for click events)
            user_agent: User agent string
            ip_address: IP address

        Returns:
            Event ID
        """
        event_id = str(uuid4())

        if self.ops_db:
            self.ops_db.record_event(
                event_type=f"email.{event_type}",
                entity_name="email",
                entity_id=email_id,
                payload={
                    "click_url": click_url,
                    "user_agent": user_agent,
                },
            )

        return event_id

    def list_templates(self) -> list[dict[str, Any]]:
        """List available templates."""
        return [
            {
                "name": t.name,
                "subject": t.subject,
                "description": t.description,
                "category": t.category,
            }
            for t in self.templates.values()
        ]


# =============================================================================
# FastAPI Integration
# =============================================================================


def create_email_tracking_routes(template_engine: EmailTemplateEngine) -> Any:
    """
    Create FastAPI routes for email tracking.

    Provides endpoints for:
    - Tracking pixel (open tracking)
    - Click redirect (click tracking)
    """
    try:
        from fastapi import APIRouter, Query, Request
        from fastapi.responses import RedirectResponse, Response
    except ImportError:
        raise RuntimeError("FastAPI required for email tracking routes")

    router = APIRouter(prefix="/_ops/email", tags=["Email Tracking"])

    # Transparent 1x1 GIF
    TRANSPARENT_GIF = (
        b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00"
        b"\xff\xff\xff\x00\x00\x00\x21\xf9\x04\x01\x00\x00\x00"
        b"\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02"
        b"\x44\x01\x00\x3b"
    )

    @router.get("/pixel/{email_id}.gif")
    async def track_open(
        email_id: str,
        request: Request,
    ) -> Response:
        """
        Tracking pixel endpoint for email open tracking.

        Returns a 1x1 transparent GIF and records the open event.
        """
        template_engine.record_event(
            email_id=email_id,
            event_type="opened",
            user_agent=request.headers.get("User-Agent"),
            ip_address=request.client.host if request.client else None,
        )

        return Response(
            content=TRANSPARENT_GIF,
            media_type="image/gif",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )

    @router.get("/click/{email_id}")
    async def track_click(
        email_id: str,
        request: Request,
        url: str = Query(..., description="Original URL to redirect to"),
    ) -> RedirectResponse:
        """
        Click tracking endpoint.

        Records the click event and redirects to the original URL.
        """
        template_engine.record_event(
            email_id=email_id,
            event_type="clicked",
            click_url=url,
            user_agent=request.headers.get("User-Agent"),
            ip_address=request.client.host if request.client else None,
        )

        return RedirectResponse(url=url, status_code=302)

    return router
