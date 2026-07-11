"""Typed ingestion boundary for HM Hyperpart seams.

Runtime copies of the HaTchi-MaXchi contract models (the wheel cannot ship
``packages/``, so no runtime import crosses the dist-only boundary). The
copies are locked to the HM contract modules by
``tests/unit/test_hm_contract_schema_parity.py`` — field-for-field schema
equality — and the emitted DOM is locked by
``tests/unit/test_hm_contract_dom_conformance.py``.

Seam models: ``GridEditCell``, ``ComboboxField``, ``TagsField``,
``MoneyField``, ``SearchResultRow``, ``SearchSelectShell``, ``ActionCard``,
``StatusListEntry``, ``QueueRow``, ``MetricTile``, ``KanbanCard``,
``ActivityRow``, ``TimelineEvent``.

**Two layers (#1577):** form primitives in ``primitives/forms.py`` are the
public product API (``required``, currency selector, symbol, …). These
ingest models are the HM contract shape. Emission is
``form primitive → *_from_form adapter → attr helper`` — HM contract
attributes are assembled **only** in this module (sole-emitter gates).

Source of truth: ``packages/hatchi-maxchi/contracts/<part>.py``.
"""

from __future__ import annotations

import html as _html
import json
import re
from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, field_validator, model_validator

Kind = Literal["text", "date", "bool", "select"]


class GridEditCell(BaseModel):
    """One editable cell's seam data — the single canonical ingestion shape.

    Mirrors ``contracts/grid_edit.py`` (schema-parity gated). The options
    field validator is THE one normalisation boundary for the #1573 class:
    producers may hold dicts ({"value","label"}), pairs, or bare strings;
    all become pairs here — never at a consumer.
    """

    col: str
    kind: Kind
    value: str
    label: str  # a11y label for the editor
    options: list[tuple[str, str]] | None = None  # [(value, label), …] — select only

    @field_validator("options", mode="before")
    @classmethod
    def _normalise_options(cls, v: object) -> object:
        if v is None:
            return v
        out: list[tuple[str, str]] = []
        for o in v:  # type: ignore[attr-defined]
            if isinstance(o, dict):
                out.append((str(o.get("value", "")), str(o.get("label", ""))))
            elif isinstance(o, (tuple, list)) and len(o) >= 2:
                out.append((str(o[0]), str(o[1])))
            else:
                out.append((str(o), str(o)))
        return out

    @model_validator(mode="after")
    def _select_requires_options(self) -> GridEditCell:
        if self.kind == "select" and not self.options:
            raise ValueError("kind='select' requires options")
        if self.kind != "select" and self.options:
            raise ValueError(f"kind={self.kind!r} must not carry options")
        return self


def edit_span_attrs(cell: GridEditCell) -> str:
    """The ONLY place in src/dazzle that assembles data-dz-edit-* attributes
    (gated by test_hm_contract_dom_conformance.py::test_typed_path_is_sole_emitter)."""
    opts = ""
    if cell.kind == "select" and cell.options is not None:
        pairs = json.dumps([[v, label] for v, label in cell.options])
        opts = f' data-dz-edit-options="{_html.escape(pairs, quote=True)}"'
    return (
        f'data-dz-grid-edit="{_html.escape(cell.col, quote=True)}" '
        f'data-dz-edit-kind="{cell.kind}" '
        f'data-dz-edit-value="{_html.escape(cell.value, quote=True)}" '
        f'data-dz-edit-label="{_html.escape(cell.label, quote=True)}"{opts}'
    )


# ── Combobox / tags / money seam copies ──────────────────────────────
# Mirrors packages/hatchi-maxchi/contracts/{combobox,tags,money}.py.
# Name collision note: dazzle.render.fragment.TagsField / MoneyField are
# form *primitives* (dataclasses). These Pydantic seam models are only
# importable as dazzle.render.fragment.ingest.TagsField / MoneyField.


class ComboboxOption(BaseModel):
    value: str
    label: str


class ComboboxField(BaseModel):
    """Server-rendered seed for a combobox (pre-enhancement markup)."""

    name: str
    field_id: str
    label: str
    options: list[ComboboxOption]
    selected: str = ""
    placeholder: str = ""

    @field_validator("options", mode="before")
    @classmethod
    def _pairs(cls, v: object) -> object:
        if not isinstance(v, list):
            return v
        out = []
        for o in v:
            if isinstance(o, dict):
                out.append({"value": str(o.get("value", "")), "label": str(o.get("label", ""))})
            elif isinstance(o, (tuple, list)) and len(o) >= 2:
                out.append({"value": str(o[0]), "label": str(o[1])})
            else:
                out.append({"value": str(o), "label": str(o)})
        return out


class TagsField(BaseModel):
    name: str
    field_id: str
    label: str
    tags: list[str] = []
    placeholder: str = ""

    @field_validator("tags", mode="before")
    @classmethod
    def _split(cls, v: object) -> object:
        if isinstance(v, str):
            return [t.strip() for t in v.split(",") if t.strip()]
        return v


class MoneyField(BaseModel):
    name: str
    currency: str = "GBP"
    scale: int = 2
    major_display: str = "0.00"
    minor_value: int = 0
    field_id: str = "money-field"


# ── Search-select seam copies (contracts/search_select.py) ───────────
# Schema-parity gated. Result rows map any domain record into slots;
# the shell is the SSR seed for the typeahead widget.


class SearchResultRow(BaseModel):
    """One listbox option the search exchange emits.

    Map *any* domain record into this shape:

    - ``id`` → select-exchange query param (FK to store)
    - ``name`` → primary line (required for AT + scan)
    - ``secondary`` → optional meta (company no., email, SKU, …)
    - ``media_html`` → optional leading 2rem slot (initials span, ``<img>``,
      icon ``<svg>``). Empty string = text-only row.
    - ``select_url`` / ``results_target`` → the row's own ``hx-get`` wiring
    """

    id: str
    name: str
    secondary: str = ""
    media_html: str = ""
    select_url: str
    results_target: str  # e.g. "#search-results-company"


class SearchSelectShell(BaseModel):
    """SSR seed for the typeahead widget (before any search)."""

    field_name: str
    field_id: str = "field"
    input_id: str = "search-input"
    results_id: str = "search-results"
    search_url: str
    placeholder: str = "Search…"
    prompt: str = "Type at least 3 characters to search..."
    initial_value: str = ""
    initial_label: str = ""
    debounce_ms: int = 300
    blur_grace_ms: int = 200
    confirm_hold_ms: int = 1500


# ── Action-grid seam copy (contracts/action_grid.py) ─────────────────
# Schema-parity gated. Product API stays the frozen dataclass in
# primitives/data.py; emission maps through this model then render.


ActionCardTone = Literal["neutral", "positive", "warning", "destructive", "accent"]


class ActionCard(BaseModel):
    """One CTA tile the action-grid region emits.

    Map dashboard action specs into this shape:

    - ``label`` → primary line (required)
    - ``tone`` → surface tint via ``data-dz-tone``
    - ``url`` → non-empty makes the card an ``<a>``; empty → static ``<div>``
    - ``count`` → ``None`` omits badge; ``0`` still renders a badge
    - ``icon_html`` → trusted HTML for the icon slot; empty → spacer
    """

    label: str
    tone: ActionCardTone = "neutral"
    url: str = ""
    count: int | None = None
    icon_html: str = ""

    @field_validator("label")
    @classmethod
    def _label_nonempty(cls, v: str) -> str:
        if not (v or "").strip():
            raise ValueError("ActionCard requires a non-empty label")
        return v


# ── Status-list seam copy (contracts/status_list.py) ─────────────────


StatusListState = Literal["neutral", "positive", "warning", "destructive", "accent"]


class StatusListEntry(BaseModel):
    """One status row — dual-lock unit for the status-list Hyperpart."""

    title: str
    state: StatusListState = "neutral"
    caption: str = ""
    icon_html: str = ""

    @field_validator("title")
    @classmethod
    def _title_nonempty(cls, v: str) -> str:
        if not (v or "").strip():
            raise ValueError("StatusListEntry requires a non-empty title")
        return v


# ── Queue seam copy (contracts/queue.py) ─────────────────────────────


class QueueRow(BaseModel):
    """One triage row — dual-lock unit for the queue Hyperpart."""

    title: str
    attention_level: str = ""
    attention_message: str = ""
    date_html: str = ""
    badges_html: str = ""
    actions_html: str = ""

    @field_validator("title")
    @classmethod
    def _title_nonempty(cls, v: str) -> str:
        if not (v or "").strip():
            raise ValueError("QueueRow requires a non-empty title")
        return v


# ── Metrics seam copy (contracts/metrics.py) ─────────────────────────


MetricTone = Literal["", "positive", "warning", "destructive", "accent", "neutral"]
MetricDeltaDir = Literal["", "up", "down", "flat"]
MetricDeltaSent = Literal["", "positive_up", "positive_down"]


def _metric_slug_key(label: str) -> str:
    return re.sub(r"_+", "_", label.lower().replace(" ", "_")).strip("_") or "metric"


class MetricTile(BaseModel):
    """One KPI tile — dual-lock unit for the metrics Hyperpart."""

    label: str
    value: str
    metric_key: str = ""
    tone: MetricTone = ""
    delta_direction: MetricDeltaDir = ""
    delta_sentiment: MetricDeltaSent = ""
    delta_value: str = ""
    delta_pct: float = 0.0
    delta_period_label: str = ""

    @field_validator("label")
    @classmethod
    def _label_nonempty(cls, v: str) -> str:
        if not (v or "").strip():
            raise ValueError("MetricTile requires a non-empty label")
        return v

    @model_validator(mode="after")
    def _default_key(self) -> MetricTile:
        if not self.metric_key:
            self.metric_key = _metric_slug_key(self.label)
        return self


# ── Kanban seam copy (contracts/kanban.py) ───────────────────────────


class KanbanCard(BaseModel):
    """One board card — dual-lock unit for the kanban Hyperpart."""

    title: str
    fields_html: str = ""
    attention_level: str = ""
    attention_message: str = ""

    @field_validator("title")
    @classmethod
    def _title_nonempty(cls, v: str) -> str:
        if not (v or "").strip():
            raise ValueError("KanbanCard requires a non-empty title")
        return v


# ── Activity-feed seam copy (contracts/activity_feed.py) ─────────────


class ActivityRow(BaseModel):
    """One activity feed row — dual-lock unit for activity-feed."""

    time_str: str
    description: str
    actor: str = ""

    @field_validator("description")
    @classmethod
    def _description_nonempty(cls, v: str) -> str:
        if not (v or "").strip():
            raise ValueError("ActivityRow requires a non-empty description")
        return v


# ── Timeline seam copy (contracts/timeline.py) ───────────────────────


class TimelineEvent(BaseModel):
    """One timeline item — dual-lock unit for timeline."""

    title: str
    date_label: str = ""
    fields_html: str = ""
    bullet_html: str = ""

    @field_validator("title")
    @classmethod
    def _title_nonempty(cls, v: str) -> str:
        if not (v or "").strip():
            raise ValueError("TimelineEvent requires a non-empty title")
        return v


# ── Form → ingest adapters (#1577) ───────────────────────────────────
# Form primitives stay the public API; emission builds these models then
# uses the attr helpers below for HM contract attributes.


def tags_from_form(
    *,
    name: str,
    label: str = "",
    placeholder: str = "",
    initial_value: str = "",
) -> TagsField:
    """Map a form ``TagsField`` (or equivalent kwargs) to the HM seam model."""
    # Pass comma-string through the validator when non-empty; else empty list.
    tags_seed: str | list[str] = initial_value if initial_value else []
    return TagsField(
        name=name,
        field_id=f"field-{name}",
        label=label or name,
        tags=tags_seed,  # type: ignore[arg-type]  # before-validator accepts str
        placeholder=placeholder,
    )


def combobox_from_form(
    *,
    name: str,
    label: str = "",
    options: Sequence[tuple[str, str]] = (),
    placeholder: str = "",
    initial_value: str = "",
) -> ComboboxField:
    """Map a form ``WidgetCombobox`` to the HM combobox seam model."""
    # Pairs go through ComboboxField._pairs before → list[ComboboxOption].
    return ComboboxField(
        name=name,
        field_id=f"field-{name}",
        label=label or name,
        options=list(options),  # type: ignore[arg-type]  # before-validator
        selected=initial_value,
        placeholder=placeholder,
    )


def money_from_form(
    *,
    name: str,
    currency_code: str = "",
    scale: str = "",
    minor_initial: str = "",
) -> MoneyField:
    """Map core money root fields from a form ``MoneyField`` to the HM seam.

    Product chrome (``symbol``, ``currency_fixed``, ``currency_options``,
    ``required``, ``label``) stays on the form primitive — not on this model.
    """
    try:
        scale_i = 2 if scale in ("", None) else int(scale)
    except (TypeError, ValueError):
        scale_i = 2
    minor_i = 0
    major = ""
    if minor_initial:
        try:
            minor_i = int(minor_initial)
            major = f"{minor_i / (10**scale_i):.{scale_i}f}"
        except (TypeError, ValueError):
            minor_i = 0
            major = ""
    return MoneyField(
        name=name,
        currency=currency_code or "GBP",
        scale=scale_i,
        # Empty when no minor seed — preserves blank edit form (not "0.00").
        major_display=major,
        minor_value=minor_i,
        field_id=f"field-{name}",
    )


# ── Sole-emitter attr helpers (HM contract attributes only) ──────────


def tags_marker_attrs(field: TagsField) -> str:
    """Assemble ``name`` + ``data-dz-tags`` — the ONLY site for that marker."""
    return f'name="{_html.escape(field.name, quote=True)}" data-dz-tags'


def combobox_marker_attrs(field: ComboboxField) -> str:
    """Assemble ``name`` + ``data-dz-combobox`` — the ONLY site for that marker."""
    return f'name="{_html.escape(field.name, quote=True)}" data-dz-combobox'


def money_root_attrs(field: MoneyField) -> str:
    """Assemble money root ``data-dz-money`` / currency / scale attrs only."""
    return (
        f"data-dz-money "
        f'data-dz-currency="{_html.escape(field.currency, quote=True)}" '
        f'data-dz-scale="{field.scale}"'
    )


def combobox_options_html(field: ComboboxField, *, placeholder_html: str) -> str:
    """Render ``<option>`` list from a typed combobox seam (incl. leading empty)."""
    opts = [f'<option value="">{placeholder_html}</option>']
    for o in field.options:
        # Match form emission: selected when value equals selected (incl. "").
        sel = " selected" if o.value == field.selected else ""
        opts.append(
            f'<option value="{_html.escape(o.value, quote=True)}"{sel}>'
            f"{_html.escape(o.label)}</option>"
        )
    return "".join(opts)


def search_select_shell_from_form(
    *,
    name: str,
    search_url: str,
    label: str = "",
    placeholder: str = "",
    debounce_ms: int = 300,
    min_chars: int = 0,
    initial_value: str = "",
    initial_label: str = "",
    blur_grace_ms: int = 200,
    confirm_hold_ms: int = 1500,
) -> SearchSelectShell:
    """Map a form ``SearchSelect`` (or equivalent kwargs) to the HM shell seam."""
    prompt = (
        f"Type at least {min_chars} characters to search..."
        if min_chars
        else "Type at least 3 characters to search..."
    )
    return SearchSelectShell(
        field_name=name,
        field_id=f"field-{name}",
        input_id=f"search-input-{name}",
        results_id=f"search-results-{name}",
        search_url=search_url,
        placeholder=placeholder or (f"Search {label}..." if label else "Search…"),
        prompt=prompt,
        initial_value=initial_value,
        initial_label=initial_label,
        debounce_ms=debounce_ms,
        blur_grace_ms=blur_grace_ms,
        confirm_hold_ms=confirm_hold_ms,
    )


def search_select_root_attrs(shell: SearchSelectShell) -> str:
    """Assemble search-select root widget + timing knobs — sole emitter site."""
    return (
        f'data-dz-widget="search_select" '
        f'data-dz-blur-grace-ms="{shell.blur_grace_ms}" '
        f'data-dz-confirm-hold-ms="{shell.confirm_hold_ms}"'
    )


def action_card_root_attrs(card: ActionCard) -> str:
    """Assemble action-card dual-lock root + tone — sole emitter site."""
    return f'data-dz-action-card data-dz-tone="{_html.escape(card.tone, quote=True)}"'


def render_action_card(card: ActionCard) -> str:
    """Model → one action card (search-select pattern; matches HM render).

    Byte-faithful to ``packages/hatchi-maxchi/contracts/action_grid.py``
    ``render`` so dual-lock DOM + gallery exemplars stay one shape.
    """
    tone = _html.escape(card.tone, quote=True)
    label = _html.escape(card.label)
    if card.icon_html.strip():
        icon_html = card.icon_html
    else:
        icon_html = '<span class="dz-action-card-icon-spacer"></span>'
    count_html = ""
    if card.count is not None:
        count_html = (
            f'<span class="dz-action-card-count" data-dz-tone-badge="{tone}">{card.count}</span>'
        )
    body = (
        f'<div class="dz-action-card-row">{icon_html}{count_html}</div>'
        f'<span class="dz-action-card-label">{label}</span>'
    )
    root_attrs = action_card_root_attrs(card)
    if card.url:
        href = _html.escape(card.url, quote=True)
        return f'<a href="{href}" class="dz-action-card" {root_attrs}>{body}</a>'
    return f'<div class="dz-action-card" {root_attrs}>{body}</div>'


def status_list_entry_root_attrs(entry: StatusListEntry) -> str:
    """Assemble status-entry dual-lock root + state — sole emitter site."""
    return f'data-dz-status-entry data-dz-state="{_html.escape(entry.state, quote=True)}"'


def queue_row_root_attrs(row: QueueRow) -> str:
    """Assemble queue-row dual-lock root (+ optional attn) — sole emitter site."""
    base = "data-dz-queue-row"
    if row.attention_level:
        return f'{base} data-dz-attn="{_html.escape(row.attention_level, quote=True)}"'
    return base


def render_status_list_entry(entry: StatusListEntry) -> str:
    """Model → one status-list ``<li>`` (matches HM contracts/status_list.py)."""
    title = _html.escape(entry.title)
    if entry.icon_html.strip():
        icon_html = entry.icon_html
    else:
        icon_html = '<span class="dz-status-list-icon-spacer" aria-hidden="true"></span>'
    caption_html = ""
    if entry.caption:
        caption_html = f'<div class="dz-status-list-caption">{_html.escape(entry.caption)}</div>'
    pill_html = ""
    if entry.state != "neutral":
        pill_html = f'<span class="dz-status-list-pill">{_html.escape(entry.state)}</span>'
    root_attrs = status_list_entry_root_attrs(entry)
    return (
        f'<li class="dz-status-list-entry" {root_attrs}>'
        f"{icon_html}"
        f'<div class="dz-status-list-text">'
        f'<div class="dz-status-list-title">{title}</div>'
        f"{caption_html}"
        f"</div>"
        f"{pill_html}"
        f"</li>"
    )


def render_queue_row(row: QueueRow) -> str:
    """Model → one queue row (matches HM contracts/queue.py)."""
    title = _html.escape(row.title)
    attn_class = ""
    attn_message_html = ""
    if row.attention_level:
        attn_class = f"dz-attn-both dz-attn-tone-{_html.escape(row.attention_level)}"
        if row.attention_message:
            attn_message_html = (
                f'<p class="dz-queue-row-attn">{_html.escape(row.attention_message)}</p>'
            )
    headline_html = (
        f'<div class="dz-queue-row-headline">'
        f'<span class="dz-queue-row-title">{title}</span>'
        f"{row.badges_html}"
        f"</div>"
    )
    row_open_class = f"dz-queue-row {attn_class}" if attn_class else "dz-queue-row "
    root_attrs = queue_row_root_attrs(row)
    return (
        f'<div class="{row_open_class}" {root_attrs}>'
        f'<div class="dz-queue-row-main ">'
        f"{headline_html}"
        f"{attn_message_html}"
        f"{row.date_html}"
        f"</div>"
        f"{row.actions_html}"
        f"</div>"
    )


def metric_tile_root_attrs(tile: MetricTile) -> str:
    """Assemble metric-tile dual-lock root (+ optional tone) — sole emitter site."""
    key = _html.escape(tile.metric_key, quote=True)
    base = f'data-dz-metric-key="{key}"'
    if tile.tone:
        return f'{base} data-dz-tone="{_html.escape(tile.tone, quote=True)}"'
    return base


def kanban_card_root_attrs(_card: KanbanCard) -> str:
    """Assemble kanban-card dual-lock root — sole emitter site."""
    return "data-dz-kanban-card"


def activity_row_root_attrs(_row: ActivityRow) -> str:
    """Assemble activity-row dual-lock root — sole emitter site."""
    return "data-dz-activity-row"


def timeline_item_root_attrs(_evt: TimelineEvent) -> str:
    """Assemble timeline-item dual-lock root — sole emitter site."""
    return "data-dz-timeline-item"


def render_metric_tile(tile: MetricTile) -> str:
    """Model → one metric tile (matches HM contracts/metrics.py)."""
    label = _html.escape(tile.label)
    value = _html.escape(tile.value)
    root_attrs = metric_tile_root_attrs(tile)

    delta_html = ""
    if tile.delta_direction:
        is_good = (tile.delta_direction == "up" and tile.delta_sentiment == "positive_up") or (
            tile.delta_direction == "down" and tile.delta_sentiment == "positive_down"
        )
        is_bad = (tile.delta_direction == "down" and tile.delta_sentiment == "positive_up") or (
            tile.delta_direction == "up" and tile.delta_sentiment == "positive_down"
        )
        delta_tone = "positive" if is_good else ("destructive" if is_bad else "neutral")
        arrow = (
            "↑"
            if tile.delta_direction == "up"
            else ("↓" if tile.delta_direction == "down" else "→")
        )
        sign = "+" if tile.delta_direction == "up" else ""
        pct_html = (
            f'<span class="dz-metric-delta-pct">({tile.delta_pct}%)</span>'
            if tile.delta_pct
            else ""
        )
        period_html = f'<span class="dz-metric-delta-period">vs {_html.escape(tile.delta_period_label)}</span>'
        delta_html = (
            f'<div class="dz-metric-delta" '
            f'data-dz-delta-tone="{delta_tone}" '
            f'data-dz-delta-direction="{_html.escape(tile.delta_direction, quote=True)}" '
            f'data-dz-delta-sentiment="{_html.escape(tile.delta_sentiment, quote=True)}">'
            f'<span aria-hidden="true">{arrow}</span>'
            f'<span class="dz-metric-delta-value">{sign}{_html.escape(tile.delta_value)}</span>'
            f"{pct_html}"
            f"{period_html}"
            f"</div>"
        )

    return (
        f'<div class="dz-metric-tile" {root_attrs}>'
        f'<div class="dz-metric-label">{label}</div>'
        f'<div class="dz-metric-value">{value}</div>'
        f"{delta_html}"
        f"</div>"
    )


def render_kanban_card(card: KanbanCard) -> str:
    """Model → one kanban card (matches HM contracts/kanban.py)."""
    title = _html.escape(card.title)
    attn_html = ""
    if card.attention_level:
        level = _html.escape(card.attention_level, quote=True)
        msg = _html.escape(card.attention_message)
        attn_html = f'<p class="dz-kanban-card-attn" data-dz-attn="{level}">{msg}</p>'
    root_attrs = kanban_card_root_attrs(card)
    return (
        f'<div class="dz-kanban-card" {root_attrs}>'
        f'<div class="dz-kanban-card-body">'
        f'<h4 class="dz-kanban-card-title">{title}</h4>'
        f"{card.fields_html}"
        f"{attn_html}"
        f"</div>"
        f"</div>"
    )


_ACTIVITY_DOT_SVG = (
    '<svg fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">'
    '<circle cx="10" cy="10" r="6"/>'
    "</svg>"
)

_TIMELINE_DEFAULT_BULLET = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" '
    'fill="currentColor" '
    'class="dz-timeline-bullet dz-attn-bullet dz-attn-tone-default" '
    'aria-hidden="true">'
    '<circle cx="10" cy="10" r="6"/>'
    "</svg>"
)


def render_activity_row(row: ActivityRow) -> str:
    """Model → one activity feed row (matches HM contracts/activity_feed.py)."""
    time_s = _html.escape(row.time_str)
    actor_html = ""
    if row.actor:
        actor_html = f'<span class="dz-activity-actor">{_html.escape(row.actor)}</span> '
    root_attrs = activity_row_root_attrs(row)
    return (
        f'<li class="dz-activity-row" {root_attrs}>'
        f'<span class="dz-activity-dot">{_ACTIVITY_DOT_SVG}</span>'
        f'<div class="dz-activity-row-inner">'
        f'<div class="dz-activity-time">{time_s}</div>'
        f'<div class="dz-activity-bubble" >'
        f"{actor_html}{_html.escape(row.description)}"
        f"</div>"
        f"</div>"
        f"</li>"
    )


def render_timeline_event(evt: TimelineEvent) -> str:
    """Model → one timeline item (matches HM contracts/timeline.py)."""
    title = _html.escape(evt.title)
    date = _html.escape(evt.date_label)
    bullet = evt.bullet_html.strip() or _TIMELINE_DEFAULT_BULLET
    root_attrs = timeline_item_root_attrs(evt)
    return (
        f'<li class="dz-timeline-item" {root_attrs}>'
        f'<span class="dz-timeline-bullet-wrap">{bullet}</span>'
        f'<div class="dz-timeline-row">'
        f'<div class="dz-timeline-date">{date}</div>'
        f'<div class="dz-timeline-content">'
        f'<p class="dz-timeline-title">{title}</p>'
        f"{evt.fields_html}"
        f"</div>"
        f"</div>"
        f"</li>"
    )


def render_search_result_row(row: SearchResultRow) -> str:
    """Model → one listbox option (search-exchange fragment unit).

    Byte-faithful to ``packages/hatchi-maxchi/contracts/search_select.py``
    ``render_result_row`` so dual-lock DOM + gallery exemplars stay one shape.
    """
    media = ""
    if row.media_html.strip():
        media = f'<div class="dz-search-result-media">{row.media_html}</div>'
    secondary = ""
    if row.secondary:
        secondary = f'<div class="dz-search-result-secondary">{_html.escape(row.secondary)}</div>'
    return (
        f'<div class="dz-search-result-row" role="option" '
        f'tabindex="-1" '
        f'data-dz-result-id="{_html.escape(row.id, quote=True)}" '
        f'hx-get="{_html.escape(row.select_url, quote=True)}" '
        f'hx-target="{_html.escape(row.results_target, quote=True)}" '
        f'hx-swap="innerHTML">'
        f"{media}"
        f'<div class="dz-search-result-body">'
        f'<div class="dz-search-result-name">{_html.escape(row.name)}</div>'
        f"{secondary}"
        f"</div></div>"
    )


def render_search_result_list(rows: list[SearchResultRow], *, empty_q: str = "") -> str:
    """Search exchange body: N rows, or the empty prompt."""
    if not rows:
        msg = (
            f'No results found for "{_html.escape(empty_q)}"'
            if empty_q
            else "Type at least 3 characters to search..."
        )
        return f'<div class="dz-search-result-empty">{msg}</div>'
    return "".join(render_search_result_row(r) for r in rows)
