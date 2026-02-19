"""
Template context models for server-rendered pages.

Pydantic models that represent the data needed to render Jinja2 templates.
These replace UISpec as the bridge between IR and rendered HTML.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class NavItemContext(BaseModel):
    """Navigation item for sidebar/header."""

    label: str
    route: str
    active: bool = False


class ColumnContext(BaseModel):
    """Column definition for table rendering."""

    key: str
    label: str
    sortable: bool = False
    type: str = "text"  # text, badge, date, currency, bool
    filterable: bool = False
    filter_type: str = "text"  # text, select
    filter_options: list[dict[str, str]] = Field(default_factory=list)
    hidden: bool = False
    currency_code: str = ""


class FieldSourceContext(BaseModel):
    """Dynamic data source for a form field (e.g. external API search)."""

    endpoint: str  # "/api/_fragments/search?source=companieshouse"
    display_key: str  # "company_name"
    value_key: str  # "company_number"
    secondary_key: str = ""  # "company_status"
    min_chars: int = 3
    debounce_ms: int = 400
    autofill: dict[str, str] = Field(default_factory=dict)  # result_field → form_field_name


class FragmentContext(BaseModel):
    """Context for rendering a composable HTMX fragment."""

    fragment_id: str  # Unique DOM id, also the HTMX target
    template: str  # e.g. "fragments/search_select.html"
    endpoint: str  # URL that returns this fragment's HTML
    trigger: str = "load"  # HTMX trigger
    swap: str = "innerHTML"  # HTMX swap strategy
    children: list[FragmentContext] = []
    params: dict[str, Any] = Field(default_factory=dict)


class FieldContext(BaseModel):
    """Field definition for form rendering."""

    name: str
    label: str
    type: str = (
        "text"  # text, textarea, select, checkbox, date, datetime, number, email, url, money, file
    )
    required: bool = False
    placeholder: str = ""
    options: list[dict[str, str]] = Field(default_factory=list)  # For select fields
    default: Any = None
    source: FieldSourceContext | None = None  # Dynamic data source (e.g. search_select)
    extra: dict[str, Any] = Field(default_factory=dict)  # Extra metadata (e.g. money field config)


class TableContext(BaseModel):
    """Context for rendering a filterable table."""

    entity_name: str
    title: str
    columns: list[ColumnContext]
    api_endpoint: str
    search_enabled: bool = True
    create_url: str | None = None
    detail_url_template: str | None = None  # e.g. "/tasks/{id}"
    rows: list[dict[str, Any]] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20
    bulk_actions: bool = False
    inline_editable: list[str] = Field(default_factory=list)
    slide_over: bool = False
    sort_field: str = ""
    sort_dir: str = "asc"
    default_sort_field: str = ""
    default_sort_dir: str = "asc"
    search_fields: list[str] = Field(default_factory=list)
    empty_message: str = "No items found."
    filter_values: dict[str, str] = Field(default_factory=dict)
    table_id: str = ""
    pagination_mode: str = "pages"  # "pages" (default) or "infinite"


class FormSectionContext(BaseModel):
    """Context for a form section (wizard stage)."""

    name: str
    title: str
    fields: list[FieldContext]


class FormContext(BaseModel):
    """Context for rendering a form."""

    entity_name: str
    title: str
    fields: list[FieldContext]
    action_url: str
    method: str = "post"  # post or put
    mode: str = "create"  # create or edit
    cancel_url: str = "/"
    initial_values: dict[str, Any] = Field(default_factory=dict)
    sections: list[FormSectionContext] = Field(default_factory=list)


class TransitionContext(BaseModel):
    """Context for a state machine transition button."""

    to_state: str
    label: str
    api_url: str = ""


class RelatedTabContext(BaseModel):
    """Context for a related entity tab on a detail page."""

    tab_id: str  # Unique DOM id for tab switching
    label: str  # Display label (e.g. "Contacts")
    entity_name: str  # Related entity name
    api_endpoint: str  # Backend API endpoint for fetching
    filter_field: str  # FK field name to filter by (e.g. "company")
    columns: list[ColumnContext]
    rows: list[dict[str, Any]] = Field(default_factory=list)
    total: int = 0
    detail_url_template: str | None = None  # e.g. "/contacts/{id}"
    create_url: str | None = None  # e.g. "/contacts/create?company={id}"
    # Polymorphic FK support (#321): when set, filter by both type + id
    filter_type_field: str | None = None  # e.g. "entity_type"
    filter_type_value: str | None = None  # e.g. "company"


class DetailContext(BaseModel):
    """Context for rendering a detail/view page."""

    entity_name: str
    title: str
    fields: list[FieldContext]
    item: dict[str, Any] = Field(default_factory=dict)
    edit_url: str | None = None
    delete_url: str | None = None
    back_url: str = "/"
    transitions: list[TransitionContext] = Field(default_factory=list)
    status_field: str = "status"
    related_tabs: list[RelatedTabContext] = Field(default_factory=list)


class ReviewActionContext(BaseModel):
    """Action button for a review surface (approve, return, etc.)."""

    label: str
    event: str  # e.g. "approve", "return"
    style: str = "primary"  # primary, error, ghost
    transition_url: str = ""  # API URL for state transition
    to_state: str = ""  # Target state
    require_notes: bool = False


class ReviewContext(BaseModel):
    """Context for rendering a review queue page (mode: review)."""

    entity_name: str
    title: str
    fields: list[FieldContext]
    item: dict[str, Any] = Field(default_factory=dict)
    api_endpoint: str = ""
    back_url: str = "/"
    status_field: str = "status"

    # Queue navigation
    queue_position: int = 0  # 0-indexed position of current item in queue
    queue_total: int = 0  # total items in queue
    next_url: str | None = None  # URL to next item in queue
    prev_url: str | None = None  # URL to previous item in queue
    queue_url: str = ""  # URL back to the review queue list

    # Review actions (approve, return, etc.)
    actions: list[ReviewActionContext] = Field(default_factory=list)

    # Notes field for return/rejection
    notes_field: str = "review_notes"


class IslandContext(BaseModel):
    """Context for rendering a UI island mount point."""

    name: str
    src: str
    props_json: str  # pre-serialized JSON
    api_base: str
    fallback: str | None = None


class PageContext(BaseModel):
    """Top-level page context passed to templates."""

    page_title: str
    app_name: str = "Dazzle"
    layout: str = "app_shell"  # app_shell or single_column
    template: str = "components/filterable_table.html"
    nav_items: list[NavItemContext] = Field(default_factory=list)
    nav_by_persona: dict[str, list[NavItemContext]] = Field(default_factory=dict)
    current_route: str = "/"
    design_tokens: dict[str, str] = Field(default_factory=dict)
    theme_css: str = ""

    # Content context (one of these will be set)
    table: TableContext | None = None
    form: FormContext | None = None
    detail: DetailContext | None = None
    review: ReviewContext | None = None

    # UI islands available on this page
    islands: list[IslandContext] = Field(default_factory=list)

    # Semantic identifier for the current view (surface name)
    view_name: str = ""

    # Auth context (populated at render time when auth is enabled)
    is_authenticated: bool = False
    user_email: str = ""
    user_name: str = ""
    user_roles: list[str] = Field(default_factory=list)

    # Extra data for custom templates
    extra: dict[str, Any] = Field(default_factory=dict)


# =============================================================================
# Experience Flow Context Models (v0.32.0)
# =============================================================================


class ExperienceStepContext(BaseModel):
    """Step indicator for the experience progress bar."""

    name: str
    title: str
    is_current: bool = False
    is_completed: bool = False
    url: str = ""


class ExperienceTransitionContext(BaseModel):
    """Transition button for an experience step."""

    event: str
    label: str
    style: str = "primary"  # primary, ghost, error
    url: str = ""


class ExperienceContext(BaseModel):
    """Top-level context for rendering an experience flow."""

    name: str
    title: str = ""
    steps: list[ExperienceStepContext] = Field(default_factory=list)
    current_step: str = ""
    transitions: list[ExperienceTransitionContext] = Field(default_factory=list)
    page_context: PageContext | None = None


# =============================================================================
# Fragment / Source Resolution Helpers (v0.20.0)
# =============================================================================


def build_field_source_context(
    source_ref: str,
    fragment_sources: dict[str, dict[str, Any]],
) -> FieldSourceContext | None:
    """Resolve a ``source=`` annotation string to a FieldSourceContext.

    Args:
        source_ref: DSL source reference, e.g. ``"companieshouse.search_companies"``.
        fragment_sources: Registry of configured fragment sources keyed by name.

    Returns:
        FieldSourceContext ready for template rendering, or None if the source
        is not found in the registry.
    """
    # source_ref may be "pack.operation" or just "pack"
    parts = source_ref.split(".", 1)
    source_name = parts[0]

    config = fragment_sources.get(source_name)
    if not config and len(parts) > 1:
        # Try full dotted name
        config = fragment_sources.get(source_ref)
    if not config:
        return None

    return FieldSourceContext(
        endpoint=f"/api/_fragments/search?source={source_name}",
        display_key=config.get("display_key", "name"),
        value_key=config.get("value_key", "id"),
        secondary_key=config.get("secondary_key", ""),
        min_chars=config.get("min_chars", 3),
        debounce_ms=config.get("debounce_ms", 400),
        autofill=config.get("autofill", {}),
    )


# =============================================================================
# Site Page Context Models (Jinja2 site templates)
# =============================================================================


class SiteNavItem(BaseModel):
    """Navigation item for site pages."""

    label: str
    href: str = "#"


class SiteCTAContext(BaseModel):
    """Call-to-action button context."""

    label: str
    href: str = "#"


class SiteFooterLink(BaseModel):
    """Footer column link."""

    label: str
    href: str = "#"


class SiteFooterColumn(BaseModel):
    """Footer column with title and links."""

    title: str
    links: list[SiteFooterLink] = Field(default_factory=list)


class SiteOGMeta(BaseModel):
    """Open Graph / SEO meta tag data."""

    title: str = ""
    description: str = ""
    og_type: str = "website"


class SitePageContext(BaseModel):
    """Top-level context for site page templates."""

    product_name: str = "My App"
    page_title: str = ""
    current_route: str = "/"
    nav_items: list[SiteNavItem] = Field(default_factory=list)
    nav_cta: SiteCTAContext | None = None
    footer_columns: list[SiteFooterColumn] = Field(default_factory=list)
    copyright_text: str = ""
    og_meta: SiteOGMeta | None = None
    sections: list[dict[str, Any]] = Field(default_factory=list)
    custom_css: bool = False


class SiteAuthContext(BaseModel):
    """Context for auth page templates (login, signup, forgot/reset password)."""

    product_name: str = "My App"
    page_type: str = "login"  # login, signup, forgot_password, reset_password
    title: str = "Sign In"
    action_url: str = "/auth/login"
    button_text: str = "Sign In"
    is_login: bool = True
    other_page: str = "/signup"
    other_link_text: str = "Create an account"
    show_forgot_password: bool = False
    show_name_field: bool = False
    show_confirm_password: bool = False
    show_success_alert: bool = False
    subtitle: str = ""
    custom_css: bool = False


class Site404Context(BaseModel):
    """Context for 404 error page template."""

    product_name: str = "My App"
    nav_items: list[SiteNavItem] = Field(default_factory=list)
    nav_cta: SiteCTAContext | None = None
    footer_columns: list[SiteFooterColumn] = Field(default_factory=list)
    copyright_text: str = ""
    custom_css: bool = False


class SiteErrorContext(Site404Context):
    """Context for generic error page templates (403, 500, etc.)."""

    message: str = ""


def resolve_fragment_for_field(field: FieldContext) -> FragmentContext | None:
    """If *field* has a ``source``, wrap it into a FragmentContext for search_select.

    Returns:
        FragmentContext pointing to the ``search_select`` fragment template,
        or None when the field has no dynamic source.
    """
    if not field.source:
        return None

    return FragmentContext(
        fragment_id=f"fragment-{field.name}",
        template="fragments/search_select.html",
        endpoint=field.source.endpoint,
        trigger="load",
        swap="innerHTML",
        params={
            "field_name": field.name,
            "field_label": field.label,
            "field_placeholder": field.placeholder or f"Search {field.label}...",
            "source_endpoint": field.source.endpoint,
            "debounce_ms": field.source.debounce_ms,
            "min_chars": field.source.min_chars,
        },
    )
