"""HM dual-lock seam models (Pydantic).

Runtime copies of ``packages/hatchi-maxchi/contracts/*``. Schema parity is
gated by ``tests/unit/test_hm_contract_schema_parity.py``.

Import from ``dazzle.render.fragment.ingest`` (package facade).
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

Kind = Literal["text", "date", "bool", "select"]
TimeSeriesView = Literal["line", "area"]


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


# ── Profile-card seam copy (contracts/profile_card.py) ───────────────


class ProfileCard(BaseModel):
    """Identity panel — dual-lock unit for profile-card."""

    primary: str = ""
    secondary: str = ""
    avatar_url: str = ""
    initials: str = ""
    stats: list[tuple[str, str]] = Field(default_factory=list)
    facts: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _identity_required(self) -> ProfileCard:
        if not (self.primary or self.avatar_url or self.initials):
            raise ValueError(
                "ProfileCard requires at least one of primary, avatar_url, or initials"
            )
        return self


# ── Sparkline seam copy (contracts/sparkline.py) ─────────────────────


class Sparkline(BaseModel):
    """Compact time-series — dual-lock unit for sparkline."""

    points: list[tuple[str, float]] = Field(default_factory=list)
    empty_message: str = "—"


# ── Funnel seam copy (contracts/funnel.py) ───────────────────────────


class FunnelStage(BaseModel):
    """One funnel stage — dual-lock nested unit."""

    label: str
    count: int = 0

    @field_validator("label")
    @classmethod
    def _label_nonempty(cls, v: str) -> str:
        if not (v or "").strip():
            raise ValueError("FunnelStage requires a non-empty label")
        return v


class Funnel(BaseModel):
    """Conversion funnel — dual-lock unit for funnel Hyperpart."""

    stages: list[FunnelStage] = Field(default_factory=list)
    total: int = 0
    empty_message: str = "No data available."


# ── Bar-chart seam copy (contracts/bar_chart.py) ─────────────────────


class BarChartRow(BaseModel):
    """One bar row — dual-lock nested unit."""

    label: str
    count: int = 0
    width_pct: int = 0
    label_html: str = ""

    @field_validator("label")
    @classmethod
    def _label_nonempty(cls, v: str) -> str:
        if not (v or "").strip():
            raise ValueError("BarChartRow requires a non-empty label")
        return v


class BarChart(BaseModel):
    """Bar chart — dual-lock unit for bar-chart Hyperpart."""

    rows: list[BarChartRow] = Field(default_factory=list)


# ── Heatmap seam copy (contracts/heatmap.py) ─────────────────────────


class HeatmapRow(BaseModel):
    """One heatmap matrix row."""

    label: str
    cells: list[float] = Field(default_factory=list)


class Heatmap(BaseModel):
    """Threshold-toned matrix — dual-lock unit for heatmap."""

    columns: list[str] = Field(default_factory=list)
    rows: list[HeatmapRow] = Field(default_factory=list)
    thresholds: list[float] = Field(default_factory=list)
    total: int = 0
    empty_message: str = "No data available."


# ── Bullet seam copy (contracts/bullet.py) ───────────────────────────


BulletBandColor = Literal["target", "positive", "warning", "destructive", "muted"]


class BulletBand(BaseModel):
    """Qualitative range band behind the actual bar."""

    from_value: float
    to_value: float
    label: str = ""
    color: BulletBandColor = "target"


class BulletRow(BaseModel):
    """One bullet chart row."""

    label: str
    actual: float
    target: float | None = None


class Bullet(BaseModel):
    """Stephen Few bullet chart — dual-lock unit for bullet."""

    rows: list[BulletRow] = Field(default_factory=list)
    max_value: float = 100.0
    bands: list[BulletBand] = Field(default_factory=list)
    empty_message: str = "No data available."


# ── Bar-track seam copy (contracts/bar_track.py) ─────────────────────


class BarTrackRow(BaseModel):
    """One capacity track row."""

    label: str
    value: float = 0.0
    formatted: str = ""
    fill_pct: float = 0.0

    @field_validator("fill_pct")
    @classmethod
    def _clamp_fill(cls, v: float) -> float:
        if not (0.0 <= v <= 100.0):
            raise ValueError(f"fill_pct={v} outside [0, 100]")
        return v


class BarTrack(BaseModel):
    """Resource-usage track list — dual-lock unit for bar-track."""

    rows: list[BarTrackRow] = Field(default_factory=list)
    max_value: float = 100.0


# ── Histogram seam copy (contracts/histogram.py) ─────────────────────


class HistogramBin(BaseModel):
    """One continuous histogram bin."""

    label: str
    count: int = 0
    low: float = 0.0
    high: float = 0.0


class Histogram(BaseModel):
    """Distribution histogram — dual-lock unit for histogram."""

    label: str = ""
    bins: list[HistogramBin] = Field(default_factory=list)
    svg_html: str = ""
    empty_message: str = "No data available."


# ── Pivot seam copy (contracts/pivot.py) ─────────────────────────────


class PivotTable(BaseModel):
    """Cross-tab matrix — dual-lock unit for pivot."""

    dim_headers: list[str] = Field(default_factory=list)
    measure_headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    empty_message: str = "No data to pivot."


# ── Box-plot seam copy (contracts/box_plot.py) ───────────────────────


class BoxPlotGroup(BaseModel):
    """One box-plot group five-number summary."""

    label: str
    min: float = 0.0
    q1: float = 0.0
    median: float = 0.0
    q3: float = 0.0
    max: float = 0.0
    samples: int = 0


class BoxPlot(BaseModel):
    """Distribution box-plot — dual-lock unit for box-plot."""

    label: str = ""
    groups: list[BoxPlotGroup] = Field(default_factory=list)
    svg_html: str = ""
    empty_message: str = "No data available."


# ── Progress seam copy (contracts/progress.py) ───────────────────────


class ProgressStage(BaseModel):
    """One workflow stage chip."""

    name: str
    count: int = 0
    complete: bool = False


class Progress(BaseModel):
    """Progress region — dual-lock unit for progress-region."""

    stages: list[ProgressStage] = Field(default_factory=list)
    complete_pct: float = 0.0
    complete_count: int = 0
    total: int = 0


# ── Pagination seam copy (contracts/pagination.py) ───────────────────


class Pagination(BaseModel):
    """List/table pagination footer — dual-lock unit for pagination."""

    total: int = 0
    pages_html: str = ""
    rows_label: str = "rows"


# ── Search-box seam copy (contracts/search_box.py) ───────────────────


class SearchBox(BaseModel):
    """FTS search region shell — dual-lock unit for search-box."""

    name: str = "q"
    label: str = ""
    placeholder: str = "Search…"
    coaching_message: str = "Type a title or keyword"
    endpoint: str = ""
    results_html: str = ""


# ── Radar seam copy (contracts/radar.py) ─────────────────────────────


class RadarAxis(BaseModel):
    """One radar spoke."""

    label: str
    value: float = 0.0


class Radar(BaseModel):
    """Polar radar — dual-lock unit for radar."""

    label: str = ""
    axes: list[RadarAxis] = Field(default_factory=list)
    svg_html: str = ""
    peak_display: str = ""
    empty_message: str = "No data available."


# ── Time-series seam copy (contracts/time_series.py) ─────────────────


class TimeSeriesPoint(BaseModel):
    """One (label, value) sample."""

    label: str
    value: float = 0.0


class TimeSeriesLayer(BaseModel):
    """One named multi-series layer."""

    name: str
    points: list[TimeSeriesPoint] = Field(default_factory=list)


class TimeSeries(BaseModel):
    """Line/area chart — dual-lock unit for time-series."""

    label: str = ""
    view: TimeSeriesView = "line"
    points: list[TimeSeriesPoint] = Field(default_factory=list)
    series: list[TimeSeriesLayer] = Field(default_factory=list)
    svg_html: str = ""
    legend_html: str = ""
    peak_display: str = ""
    empty_message: str = ""
