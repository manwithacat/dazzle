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


class FieldContext(BaseModel):
    """Field definition for form rendering."""

    name: str
    label: str
    type: str = "text"  # text, textarea, select, checkbox, date, datetime, number, email, url
    required: bool = False
    placeholder: str = ""
    options: list[dict[str, str]] = Field(default_factory=list)  # For select fields
    default: Any = None


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
