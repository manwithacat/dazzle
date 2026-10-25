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
      review:
        personas: [super_admin, trust_admin]
        shortcut: alt-shift-r
        screenshot: off
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator

DEFAULT_FEEDBACK_CATEGORIES: tuple[str, ...] = (
    "bug",
    "ux",
    "visual",
    "behaviour",
    "enhancement",
    "other",
)
DEFAULT_FEEDBACK_SEVERITIES: tuple[str, ...] = ("blocker", "annoying", "minor")
DEFAULT_REVIEW_SHORTCUT = "alt+shift+r"
REVIEW_SCREENSHOT_POLICIES: tuple[str, ...] = ("off", "optional")


class FeedbackReviewSpec(BaseModel):
    """The review posture of the feedback widget (#1854).

    Reviewers point at an element on the page and leave a note anchored to
    it; the server stores the anchor and the page context with the report.

    Attributes:
        personas: Declared persona names that get the review posture. Every
            name must be a declared persona (validated by the linker).
        shortcut: Keyboard chord that arms anchor mode, same grammar as
            ``FeedbackWidgetSpec.shortcut`` (``none`` turns it off). Sent to
            the client as ``<meta name="dz-feedback-review-shortcut">``.
        screenshot: ``off`` (default) or ``optional`` — ``optional`` offers
            "Attach screenshot" where ``getDisplayMedia`` exists.
    """

    personas: list[str] = Field(default_factory=list)
    shortcut: str = DEFAULT_REVIEW_SHORTCUT
    screenshot: str = "off"

    model_config = ConfigDict(frozen=True)

    @field_validator("screenshot")
    @classmethod
    def _screenshot_policy(cls, value: str) -> str:
        if value not in REVIEW_SCREENSHOT_POLICIES:
            raise ValueError(
                f"feedback_widget review screenshot must be one of "
                f"{', '.join(REVIEW_SCREENSHOT_POLICIES)}; got {value!r}"
            )
        return value


class FeedbackWidgetSpec(BaseModel):
    """
    Configuration for the in-app feedback widget.

    Attributes:
        enabled: Whether the widget is active.
        position: Screen position for the floating button.
        shortcut: Keyboard shortcut to toggle the panel (#1842): ``backtick``
            (default), ``none`` to turn it off, a key name (``f1``, ``slash``)
            or a combination joined by ``+`` / ``-`` (``ctrl+shift+f``). Sent
            to the client as ``<meta name="dz-feedback-shortcut">``.
        categories: Allowed feedback category values. The linker builds the
            ``FeedbackReport.category`` enum from this list (#1854).
        severities: Allowed severity values; the first is the default.
        capture: Auto-captured context fields.
        review: The review posture (``review:`` block), ``None`` when absent.
    """

    enabled: bool = False
    position: str = "bottom-right"
    shortcut: str = "backtick"
    categories: list[str] = Field(default_factory=lambda: list(DEFAULT_FEEDBACK_CATEGORIES))
    severities: list[str] = Field(default_factory=lambda: list(DEFAULT_FEEDBACK_SEVERITIES))
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
    review: FeedbackReviewSpec | None = None

    model_config = ConfigDict(frozen=True)


# Field definitions for auto-generated FeedbackReport entity.
# Format: (name, type_str, modifiers_tuple, default_value_or_None)
# Follows the same convention as AI_JOB_FIELDS in ir/llm.py.
#
# ``category`` / ``severity`` carry the framework-default enums here; the
# linker rebuilds them from the DSL's ``categories:`` / ``severities:`` via
# :func:`feedback_report_fields` (#1854).
FEEDBACK_REPORT_FIELDS: tuple[tuple[str, str, tuple[str, ...], str | None], ...] = (
    # Primary key
    ("id", "uuid", ("pk",), None),
    # Human input
    ("category", f"enum[{','.join(DEFAULT_FEEDBACK_CATEGORIES)}]", ("required",), None),
    ("severity", f"enum[{','.join(DEFAULT_FEEDBACK_SEVERITIES)}]", (), "minor"),
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
    # Review posture (#1854): the element the note points at, the page
    # context at the time, the surface it was left on and the per-tab
    # review session that groups a walk-through.
    ("anchor", "json", (), None),
    ("context", "json", (), None),
    ("surface", "str(100)", (), None),
    ("review_session", "str(40)", (), None),
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


def feedback_report_fields(
    spec: FeedbackWidgetSpec | None,
) -> tuple[tuple[str, str, tuple[str, ...], str | None], ...]:
    """``FEEDBACK_REPORT_FIELDS`` with the enums the DSL declared (#1854).

    ``categories:`` becomes the ``category`` enum and ``severities:`` the
    ``severity`` enum, whose default is the first declared severity. With no
    spec, or with the framework defaults, the result equals the constant
    (``minor`` stays the default severity).
    """
    categories = list(spec.categories) if spec is not None and spec.categories else None
    severities = list(spec.severities) if spec is not None and spec.severities else None
    out: list[tuple[str, str, tuple[str, ...], str | None]] = []
    for name, type_str, modifiers, default in FEEDBACK_REPORT_FIELDS:
        if name == "category" and categories is not None:
            type_str = f"enum[{','.join(categories)}]"
        elif name == "severity" and severities is not None:
            type_str = f"enum[{','.join(severities)}]"
            if severities != list(DEFAULT_FEEDBACK_SEVERITIES):
                default = severities[0]
        out.append((name, type_str, modifiers, default))
    return tuple(out)
