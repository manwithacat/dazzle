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
    type: str = "text"  # text, textarea, select, checkbox, date, datetime, number, email, url
    required: bool = False
    placeholder: str = ""
    options: list[dict[str, str]] = Field(default_factory=list)  # For select fields
    default: Any = None
    source: FieldSourceContext | None = None  # Dynamic data source (e.g. search_select)


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


class TransitionContext(BaseModel):
    """Context for a state machine transition button."""

    to_state: str
    label: str
    api_url: str = ""


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


class PageContext(BaseModel):
    """Top-level page context passed to templates."""

    page_title: str
    app_name: str = "Dazzle"
    layout: str = "app_shell"  # app_shell or single_column
    template: str = "components/filterable_table.html"
    nav_items: list[NavItemContext] = Field(default_factory=list)
    current_route: str = "/"
    design_tokens: dict[str, str] = Field(default_factory=dict)
    theme_css: str = ""

    # Content context (one of these will be set)
    table: TableContext | None = None
    form: FormContext | None = None
    detail: DetailContext | None = None

    # Semantic identifier for the current view (surface name)
    view_name: str = ""

    # Extra data for custom templates
    extra: dict[str, Any] = Field(default_factory=dict)


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
