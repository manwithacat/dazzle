"""
Feedback widget types for DAZZLE IR.

Opt-in in-app feedback collection. When ``feedback_widget: enabled`` is
declared in the DSL, the framework auto-generates a ``FeedbackReport``
entity and injects a client-side widget into every authenticated page.

DSL Syntax:

    feedback_widget: enabled
      position: bottom-right
      shortcut: backtick
      categories: [bug, ux, visual, behaviour, enhancement, other]
      severities: [blocker, annoying, minor]
      capture: [url, persona, viewport, user_agent, console_errors, nav_history, page_snapshot]
"""

from pydantic import BaseModel, ConfigDict, Field


class FeedbackWidgetSpec(BaseModel):
    """
    Configuration for the in-app feedback widget.

    Attributes:
        enabled: Whether the widget is active.
        position: Screen position for the floating button.
        shortcut: Keyboard shortcut to toggle the panel.
        categories: Allowed feedback category values.
        severities: Allowed severity values.
        capture: Auto-captured context fields.
    """

    enabled: bool = False
    position: str = "bottom-right"
    shortcut: str = "backtick"
    categories: list[str] = Field(
        default_factory=lambda: [
            "bug",
            "ux",
            "visual",
            "behaviour",
            "enhancement",
            "other",
        ]
    )
    severities: list[str] = Field(default_factory=lambda: ["blocker", "annoying", "minor"])
    capture: list[str] = Field(
        default_factory=lambda: [
            "url",
            "persona",
            "viewport",
            "user_agent",
            "console_errors",
            "nav_history",
            "page_snapshot",
        ]
    )

    model_config = ConfigDict(frozen=True)


# Field definitions for auto-generated FeedbackReport entity.
# Format: (name, type_str, modifiers_tuple, default_value_or_None)
# Follows the same convention as AI_JOB_FIELDS in ir/llm.py.
FEEDBACK_REPORT_FIELDS: tuple[tuple[str, str, tuple[str, ...], str | None], ...] = (
    # Primary key
    ("id", "uuid", ("pk",), None),
    # Human input
    ("category", "enum[bug,ux,visual,behaviour,enhancement,other]", ("required",), None),
    ("severity", "enum[blocker,annoying,minor]", (), "minor"),
    ("description", "text", ("required",), None),
    # Auto-captured context
    ("page_url", "str(500)", (), None),
    ("page_title", "str(200)", (), None),
    ("persona", "str(50)", (), None),
    ("viewport", "str(20)", (), None),
    ("user_agent", "str(500)", (), None),
    ("console_errors", "text", (), None),
    ("nav_history", "text", (), None),
    ("page_snapshot", "text", (), None),
    ("screenshot_data", "text", (), None),
    ("annotation_data", "text", (), None),
    # Agent triage
    ("agent_classification", "str(100)", (), None),
    ("related_entity", "str(100)", (), None),
    ("related_story", "str(20)", (), None),
    ("agent_notes", "text", (), None),
    # Audit — stored as string IDs, not FK refs, because the auto-entity
    # must not assume any particular User/tenant entity exists.
    # Apps that need FK refs can declare their own FeedbackReport entity.
    ("reported_by", "str(200)", (), None),
    ("assigned_to", "str(200)", (), None),
    ("resolved_by", "str(200)", (), None),
    ("created_at", "datetime", (), "now"),
    ("updated_at", "datetime", (), "now"),
    ("resolved_at", "datetime", (), None),
    # Lifecycle
    ("status", "enum[new,triaged,in_progress,resolved,verified,wont_fix,duplicate]", (), "new"),
    # Idempotency — deduplicates resubmissions from page reload / navigation (#693)
    ("idempotency_key", "str(36)", ("unique",), None),
    # Notification tracking — prevents repeat toasts on page load (#721)
    ("notification_sent", "bool", (), "false"),
)
