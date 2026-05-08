"""WorkspaceRegion → Fragment primitive adapter (Phase 4A).

Parallel to `FragmentSurfaceAdapter` but for `WorkspaceRegion` — the
multi-region dashboard layout uses a different render shape than
single-surface pages. Each region declares a `display:` mode that
determines which primitive renders the data.

The integration with `workspace_renderer.py` is a separate plan; this
module is the substrate piece that maps `(region_spec, ctx) →
Fragment`. Coverage is driven by `_BUILDERS` (direct dispatches) and
`_ALIASES` (display modes that share a builder). The audit's
`_SUPPORTED_DISPLAYS` derives from these, so adding a new display is
a single dict edit instead of two synced lists across two files.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, Literal

from dazzle.render.fragment import (
    URL,
    ActionCard,
    Badge,
    BarChart,
    BarTrack,
    BoxPlot,
    Card,
    Diagram,
    EmptyState,
    Fragment,
    Grid,
    Heading,
    KanbanBoard,
    Link,
    MetricTile,
    PivotTable,
    ProfileCard,
    Radar,
    ReferenceBand,
    ReferenceLine,
    Region,
    Row,
    Stack,
    StageBar,
    Surface,
    Tabs,
    Text,
    Timeline,
    TimeSeries,
)

_log = logging.getLogger(__name__)

_LABEL_CANDIDATES: tuple[str, ...] = ("title", "name", "id")
_DATE_CANDIDATES: tuple[str, ...] = ("date", "created_at", "occurred_at", "timestamp")


def _region_title(region: Any) -> str:
    """Extract a region's display title.

    Prefers the explicit `title` attribute, falls back to the snake-cased
    `name` attribute. Used by every `_build_*` method — consolidating it
    here removes ~19 verbatim copies of the same expression.
    """
    title = getattr(region, "title", None)
    if title:
        return str(title)
    return getattr(region, "name", "").replace("_", " ").title()


def _wrap_surface(title: str, kind: str, body: Fragment) -> Surface:
    """Wrap a body fragment in the standard region Surface chrome.

    Every `_build_*` method ends with `Surface(header=Heading(title,
    level=2), body=Region(kind=..., body=body))` — the only variation
    is `kind`. This helper consolidates the wrapping.
    """
    return Surface(
        header=Heading(title, level=2),
        body=Region(kind=kind, body=body),  # type: ignore[arg-type]
    )


_BADGE_TONE_TO_VARIANT: dict[str, str] = {
    "success": "success",
    "warning": "warning",
    "info": "info",
    "destructive": "danger",
    "neutral": "default",
}


def _render_typed_value(item: dict[str, Any], col: dict[str, Any]) -> Fragment:
    """Render a single field value as a typed Fragment based on `col["type"]`.

    Mirrors the legacy `workspace/regions/detail.html` per-type dispatch:
        - "badge"    → Badge primitive with variant from status-tone map
        - "bool"     → Text(✓) or Text(✗)
        - "date"     → Text formatted via the dazzle_ui date filter
        - "currency" → Text formatted via the dazzle_ui currency filter
        - "ref"      → Link if ref_route is set, else Text(display)
        - default    → Text(str(value)) with em-dash for None

    Filter implementations are reused from `dazzle_ui.runtime.template_renderer`
    so the typed-Fragment path renders the same string the Jinja path
    would have produced. Phase 4B.1.a.
    """
    key = str(col.get("key") or "")
    col_type = str(col.get("type") or "")
    value = item.get(key) if key else None

    if col_type == "badge":
        from dazzle_ui.runtime.template_renderer import _badge_tone_filter

        tone_name = _badge_tone_filter(value)
        variant = _BADGE_TONE_TO_VARIANT.get(tone_name, "default")
        label = "" if value is None else str(value)
        return Badge(label=label or "—", variant=variant)  # type: ignore[arg-type]

    if col_type == "bool":
        return Text("✓" if value else "✗")

    if value is None or value == "":
        return Text("—")

    if col_type == "date":
        from dazzle_ui.runtime.template_renderer import _date_filter

        return Text(_date_filter(value))

    if col_type == "currency":
        from dazzle_ui.runtime.template_renderer import _currency_filter

        return Text(_currency_filter(value))

    if col_type == "ref":
        ref_route = str(col.get("ref_route") or "")
        display = item.get(f"{key}_display") or value
        display_str = str(display)
        if ref_route:
            url = f"{ref_route}/{value}" if not ref_route.endswith("/") else f"{ref_route}{value}"
            return Link(label=display_str, href=URL(url))
        return Text(display_str)

    return Text(str(value))


def _pick_label(
    item: dict[str, Any],
    field_hint: str = "",
    candidates: tuple[str, ...] = _LABEL_CANDIDATES,
) -> str:
    """Pick a display label from a dict item.

    `field_hint` wins if provided and present; otherwise the first
    matching candidate field is returned. Used by every list-style
    builder; consolidating it here removes 5 copies of the same loop.
    """
    if field_hint and field_hint in item:
        return str(item.get(field_hint) or "")
    for cand in candidates:
        if cand in item:
            return str(item.get(cand) or "")
    return ""


def _coerce_columns(
    group_keys: list[str], items_by_group: dict[str, list[Any]]
) -> tuple[tuple[str, tuple[object, ...]], ...]:
    """Build the KanbanBoard.columns tuple from a group→items mapping.

    `group_keys` carries declared order (e.g. enum value order); any
    items grouped under a key not in the list go into a synthetic
    "Other" column at the end. Columns with zero items still render
    (empty column = "no items in this status yet" UX).
    """
    columns: list[tuple[str, tuple[object, ...]]] = []
    seen: set[str] = set()
    for key in group_keys:
        seen.add(key)
        items = tuple(_format_card(item) for item in items_by_group.get(key, []))
        columns.append((key, items))
    leftover_items: list[object] = []
    for key, raw_items in items_by_group.items():
        if key in seen:
            continue
        leftover_items.extend(_format_card(item) for item in raw_items)
    if leftover_items:
        columns.append(("Other", tuple(leftover_items)))
    return tuple(columns)


def _format_card(item: Any) -> object:
    """Item → card body. Items are usually dicts (from the runtime's
    aggregate result); render as plain Text of the display title for
    now. Future plans introduce a typed Card primitive that carries
    title + supplementary fields (assignee avatar, due date, etc.)."""
    if isinstance(item, dict):
        title = (
            item.get("display_title")
            or item.get("title")
            or item.get("name")
            or item.get("id")
            or ""
        )
        return Text(str(title))
    return Text(str(item))


class WorkspaceRegionAdapter:
    """Translate a WorkspaceRegion + ctx into a Fragment tree.

    Dispatch is table-driven: `_BUILDERS` maps display values to
    methods, `_ALIASES` redirects shared shapes (e.g. `histogram`
    renders the same as `bar_chart`). `_TIMESERIES_VIEWS` is the
    one special case — line/area/sparkline share `_build_time_series`
    but pass a `view` argument that the others don't.
    """

    # Direct dispatches — display value → bound method name.
    _BUILDERS: dict[str, str] = {
        "": "_build_list",  # default for missing display
        "list": "_build_list",
        "kanban": "_build_kanban",
        "timeline": "_build_timeline",
        "grid": "_build_grid",
        "metrics": "_build_metrics",
        "bar_chart": "_build_bar_chart",
        "pivot_table": "_build_pivot_table",
        "tabbed_list": "_build_tabbed_list",
        "detail": "_build_detail",
        "funnel_chart": "_build_funnel_chart",
        "status_list": "_build_status_list",
        "tree": "_build_tree",
        "pipeline_steps": "_build_pipeline_steps",
        "progress": "_build_progress",
        "confirm_action_panel": "_build_confirm_action_panel",
        "search_box": "_build_search_box",
        "bar_track": "_build_bar_track",
        "bullet": "_build_bullet",
        "diagram": "_build_diagram",
        "radar": "_build_radar",
        "box_plot": "_build_box_plot",
        "action_grid": "_build_action_grid",
        "profile_card": "_build_profile_card",
    }

    # Display values that share a builder with another display value.
    # Resolved before _BUILDERS lookup; lets us add an alias without
    # duplicating dispatch code.
    _ALIASES: dict[str, str] = {
        "summary": "metrics",
        "activity_feed": "timeline",
        "queue": "list",
        "histogram": "bar_chart",
        "heatmap": "pivot_table",
    }

    # TimeSeries variants — share `_build_time_series` but each passes
    # a different `view` argument. Kept separate from `_BUILDERS` so
    # the table-lookup signature stays uniform.
    _TIMESERIES_VIEWS: dict[str, Literal["line", "area", "sparkline"]] = {
        "line_chart": "line",
        "area_chart": "area",
        "sparkline": "sparkline",
    }

    def build(self, region: Any, ctx: dict[str, Any]) -> Fragment:
        """Dispatch on `region.display` to the right primitive.

        Resolves aliases first, then looks up the canonical builder.
        Adding a new display value is one entry in `_BUILDERS` (or
        `_ALIASES` for a redirect) — no if-chain edits required.
        """
        display_obj = getattr(region, "display", None)
        raw_display = getattr(display_obj, "value", None)
        if raw_display is None:
            raw_display = "" if display_obj is None else str(display_obj)
        display_value = raw_display.strip()

        # TimeSeries family — same builder, different view argument.
        view = self._TIMESERIES_VIEWS.get(display_value)
        if view is not None:
            return self._build_time_series(region, ctx, view)

        # Resolve any alias to its canonical display value.
        canonical = self._ALIASES.get(display_value, display_value)
        method_name = self._BUILDERS.get(canonical)
        if method_name is not None:
            builder: Callable[[Any, dict[str, Any]], Fragment] = getattr(self, method_name)
            return builder(region, ctx)

        raise NotImplementedError(
            f"WorkspaceRegionAdapter does not yet support display={display_value!r}; "
            f"audit `unsupported_display={display_value}` blockers tell you which to "
            f"close next. KanbanBoard, Timeline, KPI, BarChart, PivotTable primitives "
            f"already exist (Plan 1); the work is wiring them here."
        )

    def _build_list(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: list` regions render as a Region(kind=list) with
        the same Table primitive used for surface lists. Identical
        ctx shape (items + columns) so the surface-list adapter could
        be lifted out of FragmentSurfaceAdapter for shared use later."""
        from dazzle.render.fragment import Table

        title = _region_title(region)
        items = ctx.get("items", []) or []
        columns = ctx.get("columns", []) or []

        body: Fragment
        if not items:
            body = EmptyState(
                title="No items",
                description=getattr(region, "empty_message", None) or "No data in this region.",
            )
        else:
            column_labels = tuple(col.get("label", col.get("key", "")) for col in columns)
            rows = tuple(tuple(str(item.get(col["key"], "")) for col in columns) for item in items)
            body = Table(columns=column_labels, rows=rows)

        return _wrap_surface(title, "list", body)

    def _build_kanban(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: kanban` regions render as a KanbanBoard.

        ctx shape:
            items: list of dicts (rows from the source entity)
            group_keys: list[str] — declared status/state values in
                order (typically from an enum field's enum_values)
            group_by_field: str — the field name to bucket items by
                (the region's `group_by` clause)
        """
        title = _region_title(region)
        items: list[dict[str, Any]] = ctx.get("items", []) or []
        group_keys: list[str] = list(ctx.get("group_keys") or [])
        group_by_field: str = str(ctx.get("group_by_field") or "")

        body: Fragment
        if not items and not group_keys:
            body = EmptyState(
                title="No items",
                description=getattr(region, "empty_message", None) or "No data in this region.",
            )
        else:
            # Bucket items by group_by_field
            buckets: dict[str, list[Any]] = {k: [] for k in group_keys}
            for item in items:
                if not isinstance(item, dict):
                    continue
                key = str(item.get(group_by_field, "") or "")
                buckets.setdefault(key, []).append(item)
            columns = _coerce_columns(group_keys, buckets)
            if not columns:
                # KanbanBoard requires at least one column — synthesize
                # an empty placeholder if we have neither items nor keys.
                columns = (("All", ()),)
            body = KanbanBoard(columns=columns)

        return _wrap_surface(title, "kanban", body)

    def _build_timeline(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: timeline` regions render as a Timeline primitive
        — chronological list of (label, iso-date) events.

        ctx shape:
            items: list of dicts (rows from the source entity)
            label_field: str — which field carries the event label
                (defaults to 'title' / 'name' / 'id')
            date_field: str — which field carries the event date
                (typically the region's `date_field` clause; falls
                back to `created_at` then any iso-date-shaped field)
        """
        title = _region_title(region)
        items: list[dict[str, Any]] = ctx.get("items", []) or []
        label_field = str(ctx.get("label_field") or "")
        date_field = str(ctx.get("date_field") or getattr(region, "date_field", "") or "")

        body: Fragment
        if not items:
            body = EmptyState(
                title="No events",
                description=getattr(region, "empty_message", None) or "No data in this region.",
            )
        else:
            events: list[tuple[str, str]] = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                label = _pick_label(item, label_field)
                date = _pick_label(item, date_field, candidates=_DATE_CANDIDATES)
                if label and date:
                    events.append((label, date))
            if events:
                body = Timeline(events=tuple(events))
            else:
                body = EmptyState(
                    title="No events",
                    description=getattr(region, "empty_message", None)
                    or "No items had a label and date.",
                )

        return _wrap_surface(title, "report", body)

    def _build_pivot_table(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: pivot_table` regions render as a PivotTable primitive
        — a 2-D matrix indexed by row + column dimensions.

        ctx shape:
            rows: list[str] — row dimension labels (e.g. enum values)
            columns: list[str] — column dimension labels
            cells: dict[(row, col) → int] — pre-aggregated counts
            chart_label: optional override
        """
        title = _region_title(region)
        chart_label = str(ctx.get("chart_label") or title or "Pivot")
        rows = tuple(str(r) for r in (ctx.get("rows") or []))
        columns = tuple(str(c) for c in (ctx.get("columns") or []))
        raw_cells = ctx.get("cells") or {}
        cells: dict[tuple[str, str], int] = {}
        if isinstance(raw_cells, dict):
            for key, val in raw_cells.items():
                if isinstance(key, (list, tuple)) and len(key) == 2:
                    r, c = str(key[0]), str(key[1])
                    if r in rows and c in columns:
                        try:
                            cells[(r, c)] = int(val)
                        except (TypeError, ValueError):
                            continue

        body: Fragment
        if not rows or not columns:
            body = EmptyState(
                title="No data",
                description=getattr(region, "empty_message", None)
                or "No row or column dimensions to pivot.",
            )
        else:
            body = PivotTable(label=chart_label, rows=rows, columns=columns, cells=cells)

        return _wrap_surface(title, "report", body)

    def _build_profile_card(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: profile_card` regions render single-record identity
        panels.

        Phase 4B.1.b — replaces the prior alias to `_build_detail`, which
        rendered a generic key/value Card. The legacy template uses a
        pre-assembled `profile_card_data` dict with avatar/initials/
        primary/secondary/stats/facts; this builder consumes the same
        shape and produces the typed `ProfileCard` primitive.

        ctx shape:
            profile_card_data: dict {
                primary: str (name)
                secondary: str (meta line)
                avatar_url: str
                initials: str
                stats: list[{label, value}]
                facts: list[str]
            }

        Degrades to EmptyState when none of primary/avatar_url/initials
        are populated — matches the legacy template's else branch and
        avoids tripping the strict ProfileCard primitive's invariant.
        """
        title = _region_title(region)
        data = ctx.get("profile_card_data") or {}
        if not isinstance(data, dict):
            data = {}

        primary = str(data.get("primary") or "")
        secondary = str(data.get("secondary") or "")
        avatar_url = str(data.get("avatar_url") or "")
        initials = str(data.get("initials") or "")

        body: Fragment
        if not (primary or avatar_url or initials):
            body = EmptyState(
                title="No profile data",
                description=getattr(region, "empty_message", None) or "No profile data available.",
            )
            return _wrap_surface(title, "dashboard", body)

        # Stats: each entry should be a dict with label + value;
        # silently drop malformed entries so a single bad row doesn't
        # take down the whole panel.
        stats: list[tuple[str, str]] = []
        for entry in data.get("stats") or []:
            if not isinstance(entry, dict):
                continue
            label = str(entry.get("label") or "")
            value = entry.get("value")
            value_str = "" if value is None else str(value)
            if label:
                stats.append((label, value_str))

        # Facts: each entry should be a string.
        facts: list[str] = []
        for entry in data.get("facts") or []:
            text = str(entry or "")
            if text:
                facts.append(text)

        body = ProfileCard(
            primary=primary,
            secondary=secondary,
            avatar_url=avatar_url,
            initials=initials,
            stats=tuple(stats),
            facts=tuple(facts),
        )
        return _wrap_surface(title, "dashboard", body)

    def _build_action_grid(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: action_grid` regions render dashboard CTA cards.

        Phase 4B.1.b — replaces the prior alias to `_build_grid`, which
        rendered plain Card(Text(label)) tiles with no icons, counts,
        tones, or URLs. This builder uses the typed `ActionCard`
        primitive so each card carries the full design contract from the
        legacy template.

        ctx shape:
            action_cards: list of dicts {"label": str, "icon": str (optional),
                "count": int | None, "tone": str (default "neutral"),
                "url": str (optional)}
            (legacy alias: `action_card_data` accepted as alias)
            columns: int (default 3, max 12) for the surrounding Grid

        Cards with empty labels or unknown tones silently drop rather
        than crashing the strict ActionCard primitive.
        """
        title = _region_title(region)
        raw_cards = ctx.get("action_cards") or ctx.get("action_card_data") or []
        columns = int(ctx.get("columns") or 3)
        columns = max(1, min(12, columns))

        cards: list[object] = []
        for entry in raw_cards:
            if not isinstance(entry, dict):
                continue
            label = str(entry.get("label") or "")
            if not label:
                continue
            tone_raw = str(entry.get("tone") or "neutral")
            tone: Literal["neutral", "positive", "warning", "destructive", "accent"] = (
                tone_raw  # type: ignore[assignment]
                if tone_raw in ("neutral", "positive", "warning", "destructive", "accent")
                else "neutral"
            )
            count_raw = entry.get("count")
            count: int | None
            if count_raw is None:
                count = None
            else:
                try:
                    count = int(count_raw)
                except (TypeError, ValueError):
                    count = None
            cards.append(
                ActionCard(
                    label=label,
                    icon=str(entry.get("icon") or ""),
                    count=count,
                    tone=tone,
                    url=str(entry.get("url") or ""),
                )
            )

        body: Fragment
        if not cards:
            body = EmptyState(
                title="No actions",
                description=getattr(region, "empty_message", None) or "No actions available.",
            )
        else:
            body = Grid(children=tuple(cards), columns=columns)

        return _wrap_surface(title, "dashboard", body)

    def _build_radar(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: radar` regions render as a Radar polar profile.

        ctx shape:
            axes: list of (label, value) tuples or {axis, value} dicts
            chart_label: optional override
        """
        title = _region_title(region)
        chart_label = str(ctx.get("chart_label") or title or "Radar")
        raw_axes = ctx.get("axes") or []
        axes: list[tuple[str, float]] = []
        for entry in raw_axes:
            if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                try:
                    axes.append((str(entry[0]), float(entry[1])))
                except (TypeError, ValueError):
                    continue
            elif isinstance(entry, dict):
                label = str(entry.get("axis") or entry.get("label") or "")
                try:
                    val = float(entry.get("value") or 0)
                except (TypeError, ValueError):
                    val = 0.0
                if label:
                    axes.append((label, val))

        body: Fragment
        # Radar primitive requires ≥3 axes; fewer collapses to a line.
        # Adapter degrades to EmptyState rather than crashing.
        if len(axes) < 3:
            body = EmptyState(
                title="No data",
                description=getattr(region, "empty_message", None)
                or "Radar requires at least 3 axes.",
            )
        else:
            body = Radar(label=chart_label, axes=tuple(axes))

        return _wrap_surface(title, "report", body)

    def _build_box_plot(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: box_plot` regions render as a BoxPlot quartile table.

        ctx shape:
            groups: list of dicts {"label": str, "min": float, "q1": float,
                                   "median": float, "q3": float, "max": float}
                or 6-tuples (label, min, q1, median, q3, max)
            chart_label: optional override
        """
        title = _region_title(region)
        chart_label = str(ctx.get("chart_label") or title or "Distribution")
        raw_groups = ctx.get("groups") or []
        groups: list[tuple[str, float, float, float, float, float]] = []
        for entry in raw_groups:
            label = ""
            mn = q1 = med = q3 = mx = 0.0
            if isinstance(entry, (list, tuple)) and len(entry) == 6:
                try:
                    label = str(entry[0])
                    mn, q1, med, q3, mx = (float(v) for v in entry[1:6])
                except (TypeError, ValueError):
                    continue
            elif isinstance(entry, dict):
                label = str(entry.get("label") or "")
                try:
                    mn = float(entry.get("min") or 0)
                    q1 = float(entry.get("q1") or 0)
                    med = float(entry.get("median") or 0)
                    q3 = float(entry.get("q3") or 0)
                    mx = float(entry.get("max") or 0)
                except (TypeError, ValueError):
                    continue
            else:
                continue
            # Drop groups with non-monotonic quartiles — BoxPlot's
            # __post_init__ would raise; the adapter is permissive.
            if label and mn <= q1 <= med <= q3 <= mx:
                groups.append((label, mn, q1, med, q3, mx))

        body: Fragment
        if not groups:
            body = EmptyState(
                title="No data",
                description=getattr(region, "empty_message", None)
                or "No box-plot groups to render.",
            )
        else:
            body = BoxPlot(label=chart_label, groups=tuple(groups))

        return _wrap_surface(title, "report", body)

    def _build_time_series(
        self,
        region: Any,
        ctx: dict[str, Any],
        view: Literal["line", "area", "sparkline"],
    ) -> Surface:
        """Render a TimeSeries primitive (line / area / sparkline).

        ctx shape:
            points: list of (label, value) tuples or {label, value} /
                {x, y} dicts — pre-aggregated by the runtime
            chart_label: optional override
            reference_lines: list of dicts {value, label, style} — Phase
                4B.1.b. Style is one of solid/dashed/dotted; unknown
                styles fall back to solid.
            reference_bands: list of dicts {from, to, label, color}.
                `color` is one of target/positive/warning/destructive/
                muted; unknown colors fall back to target. Bands with
                from > to silently drop.
        """
        title = _region_title(region)
        chart_label = str(ctx.get("chart_label") or title or view.title())
        raw_points = ctx.get("points") or []
        points: list[tuple[str, float]] = []
        for entry in raw_points:
            if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                try:
                    points.append((str(entry[0]), float(entry[1])))
                except (TypeError, ValueError):
                    continue
            elif isinstance(entry, dict):
                label = str(entry.get("label") or entry.get("x") or "")
                try:
                    val = float(entry.get("value") or entry.get("y") or 0)
                except (TypeError, ValueError):
                    val = 0.0
                if label:
                    points.append((label, val))

        body: Fragment
        if not points:
            body = EmptyState(
                title="No data",
                description=getattr(region, "empty_message", None) or "No points to plot.",
            )
            return _wrap_surface(title, "report", body)

        # Reference lines — defensive parsing; unknown styles fall back.
        ref_lines: list[ReferenceLine] = []
        for entry in ctx.get("reference_lines") or []:
            if not isinstance(entry, dict):
                continue
            try:
                value = float(entry.get("value") or 0)
            except (TypeError, ValueError):
                continue
            style_raw = str(entry.get("style") or "solid")
            style: Literal["solid", "dashed", "dotted"] = (
                style_raw  # type: ignore[assignment]
                if style_raw in ("solid", "dashed", "dotted")
                else "solid"
            )
            ref_lines.append(
                ReferenceLine(value=value, label=str(entry.get("label") or ""), style=style)
            )

        # Reference bands — handle Python keyword `from` via subscript.
        ref_bands: list[ReferenceBand] = []
        for entry in ctx.get("reference_bands") or []:
            if not isinstance(entry, dict):
                continue
            try:
                from_val = float(entry.get("from") or entry.get("from_value") or 0)
                to_val = float(entry.get("to") or entry.get("to_value") or 0)
            except (TypeError, ValueError):
                continue
            if from_val > to_val:
                continue
            color_raw = str(entry.get("color") or "target")
            color: Literal["target", "positive", "warning", "destructive", "muted"] = (
                color_raw  # type: ignore[assignment]
                if color_raw in ("target", "positive", "warning", "destructive", "muted")
                else "target"
            )
            ref_bands.append(
                ReferenceBand(
                    from_value=from_val,
                    to_value=to_val,
                    label=str(entry.get("label") or ""),
                    color=color,
                )
            )

        body = TimeSeries(
            label=chart_label,
            points=tuple(points),
            view=view,
            reference_lines=tuple(ref_lines),
            reference_bands=tuple(ref_bands),
        )
        return _wrap_surface(title, "report", body)

    def _build_diagram(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: diagram` renders an entity-relationship-style
        node/edge graph via the new Diagram primitive.

        ctx shape:
            nodes: list[str] — node labels (typically entity names)
            edges: list[(str, str)] — directed edges as (from, to) pairs
                or list[dict{"from": str, "to": str}]
            (legacy) `relations` is accepted as alias for `edges`
        """
        title = _region_title(region)
        nodes = tuple(str(n) for n in (ctx.get("nodes") or []) if n)
        raw_edges = ctx.get("edges") or ctx.get("relations") or []
        edges: list[tuple[str, str]] = []
        node_set = set(nodes)
        for entry in raw_edges:
            src: str = ""
            dst: str = ""
            if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                src, dst = str(entry[0]), str(entry[1])
            elif isinstance(entry, dict):
                src = str(entry.get("from") or entry.get("source") or "")
                dst = str(entry.get("to") or entry.get("target") or "")
            # Drop edges that reference unknown nodes — Diagram's
            # __post_init__ raises on these and the runtime should
            # cope rather than crash.
            if src and dst and src in node_set and dst in node_set:
                edges.append((src, dst))

        body: Fragment
        if not nodes:
            body = EmptyState(
                title="No diagram",
                description=getattr(region, "empty_message", None) or "No nodes to diagram.",
            )
        else:
            body = Diagram(nodes=nodes, edges=tuple(edges))

        return _wrap_surface(title, "report", body)

    def _build_confirm_action_panel(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: confirm_action_panel` renders a Card with the
        action's title and a description prompt. Without a Button
        primitive wired here, the actual confirm UI is deferred to
        a later plan; this just closes the audit gap.

        ctx shape:
            title: optional override
            prompt / description / message: prompt text
            action_label: optional button text shown as plain Text below
        """
        heading = _region_title(region)
        prompt = str(ctx.get("prompt") or ctx.get("description") or ctx.get("message") or "")
        action_label = str(ctx.get("action_label") or "")

        rows: list[object] = [Heading(heading or "(no title)", level=3)]
        if prompt:
            rows.append(Text(prompt))
        if action_label:
            rows.append(Text(f"[ {action_label} ]"))

        body: Fragment = Card(body=Stack(children=tuple(rows), gap="sm"))
        return _wrap_surface(heading or "Confirm", "dashboard", body)

    def _build_search_box(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: search_box` renders a Card with a search Field.

        ctx shape:
            field_name: optional, defaults to 'q'
            placeholder: optional
            label: optional, defaults to "Search"
        """
        from dazzle.render.fragment import Field

        title = _region_title(region)
        field_name = str(ctx.get("field_name") or "q")
        label = str(ctx.get("label") or "Search")
        placeholder = str(ctx.get("placeholder") or "")

        body = Card(
            body=Field(
                name=field_name,
                label=label,
                kind="text",
                placeholder=placeholder,
            )
        )
        return _wrap_surface(title, "form", body)

    def _build_bar_track(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: bar_track` renders one labelled, filled track per
        row with ARIA progressbar semantics + a summary line. Phase
        4B.1.b — uses the typed `BarTrack` primitive (replaced the
        prior alias to `_build_progress` which produced the simpler
        Stack-of-Row(Text, Badge) shape).

        ctx shape:
            bar_track_rows: list of dicts {"label": str, "value": float,
                "formatted_value": str, "fill_pct": float (0..100)}
                — pre-computed by the runtime per `track_format` Python
                format spec
            bar_track_max: float — scale endpoint for aria-valuemax
                + summary line
            (legacy fallback) `items` with `{label, percent}` shape from
                Phase 4A is still accepted; `formatted_value` is filled
                in as `"<percent>%"`, `value` mirrors `percent`,
                `bar_track_max` defaults to 100.

        Empty rows degrade to EmptyState; rows with malformed shapes or
        out-of-range fill_pct silently drop rather than tripping the
        BarTrack primitive's invariants.
        """
        title = _region_title(region)
        raw_rows = ctx.get("bar_track_rows") or []
        max_value: float
        try:
            max_value = float(ctx.get("bar_track_max") or 100.0)
        except (TypeError, ValueError):
            max_value = 100.0
        if max_value <= 0:
            max_value = 100.0

        rows: list[tuple[str, float, str, float]] = []
        # Primary path — pre-computed bar_track_rows from the runtime
        for entry in raw_rows:
            if not isinstance(entry, dict):
                continue
            label = str(entry.get("label") or "")
            if not label:
                continue
            try:
                value = float(entry.get("value") or 0)
                fill_pct = float(entry.get("fill_pct") or 0)
            except (TypeError, ValueError):
                continue
            fill_pct = max(0.0, min(100.0, fill_pct))
            formatted = str(entry.get("formatted_value") or value)
            rows.append((label, value, formatted, fill_pct))

        # Legacy fallback — Phase 4A `items` with `{label, percent}` shape
        if not rows:
            for entry in ctx.get("items") or []:
                if not isinstance(entry, dict):
                    continue
                label = str(entry.get("label") or entry.get("name") or "")
                if not label:
                    continue
                try:
                    percent = float(entry.get("percent") or entry.get("value") or 0)
                except (TypeError, ValueError):
                    percent = 0.0
                percent = max(0.0, min(100.0, percent))
                rows.append((label, percent, f"{percent:g}%", percent))

        body: Fragment
        if not rows:
            body = EmptyState(
                title="No data",
                description=getattr(region, "empty_message", None) or "No data available.",
            )
        else:
            body = BarTrack(rows=tuple(rows), max_value=max_value)

        return _wrap_surface(title, "report", body)

    def _build_bullet(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: bullet` renders rows showing actual-vs-target.
        Each row: label + actual Badge + "/ target" Text + target Badge.

        ctx shape:
            items: list of dicts {"label": str, "actual": int|str,
                                  "target": int|str}
        """
        title = _region_title(region)
        items = ctx.get("items") or []

        rows: list[object] = []
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                label = str(item.get("label") or item.get("name") or "")
                actual = item.get("actual", "—")
                target = item.get("target", "—")
                # Map "actual >= target" → success, "<half" → danger, else warning.
                variant: str = "info"
                try:
                    a, t = float(actual), float(target)
                    if t > 0:
                        ratio = a / t
                        if ratio >= 1.0:
                            variant = "success"
                        elif ratio < 0.5:
                            variant = "danger"
                        else:
                            variant = "warning"
                except (TypeError, ValueError):
                    variant = "info"
                rows.append(
                    Row(
                        children=(
                            Text(label or "(no label)"),
                            Badge(label=str(actual), variant=variant),  # type: ignore[arg-type]
                            Text("/"),
                            Badge(label=str(target), variant="default"),
                        ),
                        gap="sm",
                        align="center",
                    )
                )

        body: Fragment
        if not rows:
            body = EmptyState(
                title="No data",
                description=getattr(region, "empty_message", None) or "No bullet rows.",
            )
        else:
            body = Stack(children=tuple(rows), gap="sm")

        return _wrap_surface(title, "report", body)

    def _build_tree(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: tree` regions render a hierarchical list as a Stack
        of indented Heading rows. Indent is encoded as leading whitespace
        in the label, so depth stays visible in plain HTML without a
        dedicated Tree primitive.

        ctx shape:
            items: list of dicts; each may carry a `children` list with
                the same shape (recursive tree)
            label_field: optional, defaults to title/name/id auto-pick
        """
        title = _region_title(region)
        items = ctx.get("items") or []
        label_field = str(ctx.get("label_field") or "")

        rows: list[object] = []

        def _walk(node_list: list[Any], depth: int) -> None:
            for node in node_list:
                if not isinstance(node, dict):
                    continue
                indent = "  " * depth
                label = _pick_label(node, label_field) or "(no label)"
                rows.append(Text(f"{indent}{label}"))
                children = node.get("children") or []
                if isinstance(children, list) and children:
                    _walk(children, depth + 1)

        if isinstance(items, list):
            _walk(items, 0)

        body: Fragment
        if not rows:
            body = EmptyState(
                title="No items",
                description=getattr(region, "empty_message", None) or "No data in this region.",
            )
        else:
            body = Stack(children=tuple(rows), gap="sm")

        return _wrap_surface(title, "list", body)

    def _build_pipeline_steps(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: pipeline_steps` renders a sequence of steps as a
        horizontal Row of Cards — one Card per step with a Heading and
        descriptive Text.

        ctx shape:
            steps: list of dicts {"label": str, "description": str (optional),
                                  "status": str (optional)}
        """
        title = _region_title(region)
        steps = ctx.get("steps") or ctx.get("items") or []

        cards: list[object] = []
        if isinstance(steps, list):
            for step in steps:
                if not isinstance(step, dict):
                    continue
                label = str(step.get("label") or step.get("name") or step.get("title") or "")
                description = str(step.get("description") or step.get("status") or "")
                inner: list[object] = [Heading(label or "(no step)", level=4)]
                if description:
                    inner.append(Text(description))
                cards.append(Card(body=Stack(children=tuple(inner), gap="sm")))

        body: Fragment
        if not cards:
            body = EmptyState(
                title="No steps",
                description=getattr(region, "empty_message", None) or "No steps declared.",
            )
        else:
            body = Row(children=tuple(cards), gap="md", align="stretch")

        return _wrap_surface(title, "dashboard", body)

    def _build_progress(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: progress` renders a `<progress>` header + chip list
        of stages. Phase 4B.1.b uses the typed StageBar primitive
        matching the legacy `workspace/regions/progress.html` shape.

        ctx shape (primary):
            stage_counts: list of dicts {"name": str, "count": int,
                "complete": bool} — pre-computed per-stage rollups
            complete_pct: float (0..100) — percentage for the header bar
            complete_count: int — for the "N of M complete" summary
            progress_total: int — denominator for the summary; 0 omits it

        ctx shape (legacy fallback, Phase 4A):
            items: list of dicts {"label": str, "percent": int 0..100}
                — fallback-rendered as one synthetic stage per row with
                `complete = (percent == 100)`. The Phase 4B.2 translator
                will replace this with the primary path.
        """
        title = _region_title(region)
        stage_counts = ctx.get("stage_counts") or []

        stages: list[tuple[str, int, bool]] = []
        for entry in stage_counts:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name") or entry.get("label") or "")
            if not name:
                continue
            try:
                count = int(entry.get("count") or 0)
            except (TypeError, ValueError):
                count = 0
            complete = bool(entry.get("complete"))
            stages.append((name, count, complete))

        # Legacy fallback — items: [{label, percent}]
        if not stages:
            for entry in ctx.get("items") or []:
                if not isinstance(entry, dict):
                    continue
                name = str(entry.get("label") or entry.get("name") or "")
                if not name:
                    continue
                try:
                    percent = int(entry.get("percent") or entry.get("value") or 0)
                except (TypeError, ValueError):
                    percent = 0
                percent = max(0, min(100, percent))
                stages.append((f"{name} ({percent}%)", percent, percent == 100))

        body: Fragment
        if not stages:
            body = EmptyState(
                title="No progress",
                description=getattr(region, "empty_message", None) or "No data in this region.",
            )
            return _wrap_surface(title, "list", body)

        try:
            complete_pct = float(ctx.get("complete_pct") or 0)
        except (TypeError, ValueError):
            complete_pct = 0.0
        complete_pct = max(0.0, min(100.0, complete_pct))
        try:
            complete_count = int(ctx.get("complete_count") or 0)
        except (TypeError, ValueError):
            complete_count = 0
        try:
            total = int(ctx.get("progress_total") or 0)
        except (TypeError, ValueError):
            total = 0

        body = StageBar(
            stages=tuple(stages),
            complete_pct=complete_pct,
            complete_count=complete_count,
            total=total,
        )
        return _wrap_surface(title, "list", body)

    def _build_status_list(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: status_list` regions render as a Stack of rows
        where each row shows a label and a status Badge.

        ctx shape:
            items: list of dicts (rows from the source entity)
            label_field: optional, defaults to title/name/id auto-pick
            status_field: which field carries the status value
                (defaults to 'status' / 'state' / 'stage')
            status_variants: optional dict[status_value → Badge.variant]
                for severity colouring (e.g. {"failed": "danger"})
        """
        title = _region_title(region)
        items: list[dict[str, Any]] = ctx.get("items", []) or []
        label_field = str(ctx.get("label_field") or "")
        status_field = str(ctx.get("status_field") or "")
        variants = ctx.get("status_variants") or {}
        if not isinstance(variants, dict):
            variants = {}

        body: Fragment
        if not items:
            body = EmptyState(
                title="No items",
                description=getattr(region, "empty_message", None) or "No data in this region.",
            )
        else:
            rows: list[object] = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                label = _pick_label(item, label_field)
                status_val = _pick_label(
                    item, status_field, candidates=("status", "state", "stage")
                )
                variant_raw = str(variants.get(status_val) or "default")
                variant = (
                    variant_raw
                    if variant_raw in ("default", "info", "success", "warning", "danger")
                    else "default"
                )
                rows.append(
                    Row(
                        children=(
                            Text(label or "(no label)"),
                            Badge(label=status_val or "—", variant=variant),  # type: ignore[arg-type]
                        ),
                        gap="md",
                        align="center",
                    )
                )
            if rows:
                body = Stack(children=tuple(rows), gap="sm")
            else:
                body = EmptyState(title="No items", description="No items had a label.")

        return _wrap_surface(title, "list", body)

    def _build_funnel_chart(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: funnel_chart` is a BarChart with buckets sorted in
        descending order — funnels narrow from a wide top stage to a
        narrow conversion at the bottom.

        ctx shape:
            buckets: list[(str, int)] — pre-aggregated stages
            chart_label: optional override
        """
        # Reuse bar_chart's parsing, then sort descending. Caller can
        # pre-sort if a non-monotonic visualisation is intended; the
        # default funnel rendering is "biggest stage first".
        raw_buckets = ctx.get("buckets") or []
        parsed: list[tuple[str, int]] = []
        for entry in raw_buckets:
            if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                try:
                    parsed.append((str(entry[0]), int(entry[1])))
                except (TypeError, ValueError):
                    continue
            elif isinstance(entry, dict):
                key = str(entry.get("label") or entry.get("key") or "")
                try:
                    val = int(entry.get("value") or entry.get("count") or 0)
                except (TypeError, ValueError):
                    val = 0
                if key:
                    parsed.append((key, val))
        parsed.sort(key=lambda kv: kv[1], reverse=True)
        # Hand off to bar_chart's render path with the sorted buckets.
        return self._build_bar_chart(region, {**ctx, "buckets": parsed})

    def _build_detail(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: detail` regions render a single item's fields as a
        labelled Card. One Stack child per (label, value) pair, with
        type-aware value rendering matching the legacy template:
        Badge for `type=badge`, ✓/✗ for `type=bool`, formatted strings
        for `type=date`/`type=currency`, Link for `type=ref` (when
        `ref_route` is supplied), Text otherwise.

        ctx shape:
            item: dict (single record)
            fields: list of {"key": str, "label": str (optional),
                "type": str (optional — one of "badge"/"bool"/"date"/
                "currency"/"ref"), "ref_route": str (optional, for ref)}
                — declared field order from the region's `fields:` clause
            (legacy) `columns` is accepted as alias for `fields`
        """
        title = _region_title(region)
        item = ctx.get("item")

        # Single linear path — no conditional reassignment of `fields`.
        if not isinstance(item, dict) or not item:
            body: Fragment = EmptyState(
                title="No item",
                description=getattr(region, "empty_message", None) or "No item to display.",
            )
            return _wrap_surface(title, "dashboard", body)

        # `fields` is materialised once: explicit list, legacy `columns`,
        # or fallback to all keys of the item in declared order (no type info).
        fields = ctx.get("fields") or ctx.get("columns") or [{"key": k} for k in item.keys()]
        rows: list[object] = []
        for f in fields:
            if not isinstance(f, dict):
                continue
            key = str(f.get("key") or "")
            if not key:
                continue
            label = str(f.get("label") or key.replace("_", " ").title())
            rows.append(Heading(label, level=4))
            rows.append(_render_typed_value(item, f))

        body = (
            Card(body=Stack(children=tuple(rows), gap="sm"))
            if rows
            else EmptyState(title="No fields", description="")
        )
        return _wrap_surface(title, "dashboard", body)

    def _build_tabbed_list(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: tabbed_list` regions render as a Tabs container, one
        tab per source-or-filter slice. Each tab body is a Table.

        ctx shape:
            tabs: list of dicts with shape:
                {"key": str, "label": str (optional), "items": list[dict],
                 "columns": list[{"key": str, "label": str}]}
            (legacy) `slices` is accepted as alias for `tabs`
        """
        from dazzle.render.fragment import Table

        title = _region_title(region)
        raw_tabs = ctx.get("tabs") or ctx.get("slices") or []

        body: Fragment
        if not raw_tabs:
            body = EmptyState(
                title="No tabs",
                description=getattr(region, "empty_message", None) or "No data slices declared.",
            )
            return _wrap_surface(title, "list", body)

        built: list[tuple[str, object]] = []
        seen_keys: set[str] = set()
        for tab in raw_tabs:
            if not isinstance(tab, dict):
                continue
            key = str(tab.get("key") or tab.get("label") or f"tab_{len(built)}")
            if key in seen_keys:
                continue
            seen_keys.add(key)
            items = tab.get("items") or []
            cols = tab.get("columns") or []
            tab_body: Fragment
            if not items:
                tab_body = EmptyState(title="No items", description="")
            elif not cols:
                tab_body = EmptyState(title="No columns", description="")
            else:
                column_labels = tuple(c.get("label", c.get("key", "")) for c in cols)
                rows_data = tuple(
                    tuple(str(item.get(c["key"], "")) for c in cols) for item in items
                )
                tab_body = Table(columns=column_labels, rows=rows_data)
            built.append((key, tab_body))

        if not built:
            body = EmptyState(title="No tabs", description="")
        else:
            body = Tabs(tabs=tuple(built))

        return _wrap_surface(title, "list", body)

    def _build_grid(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: grid` regions render items as cards in an N-column
        Grid. Columns default to 3; ctx can override via `columns`.

        ctx shape:
            items: list of dicts (rows from the source entity)
            label_field: optional, defaults to title/name/id auto-pick
            columns: int (default 3, max 12)
        """
        title = _region_title(region)
        items: list[dict[str, Any]] = ctx.get("items", []) or []
        columns = int(ctx.get("columns") or 3)
        columns = max(1, min(12, columns))
        label_field = str(ctx.get("label_field") or "")

        body: Fragment
        if not items:
            body = EmptyState(
                title="No items",
                description=getattr(region, "empty_message", None) or "No data in this region.",
            )
        else:
            cards: list[object] = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                label = _pick_label(item, label_field)
                cards.append(Card(body=Text(label or "(no label)")))
            if cards:
                body = Grid(children=tuple(cards), columns=columns)
            else:
                body = EmptyState(title="No items", description="No data in this region.")

        return _wrap_surface(title, "dashboard", body)

    def _build_metrics(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: metrics` (and `summary`) regions render a row of
        MetricTile primitives — one per declared aggregate. Phase 4B.1.a
        replaced KPI with MetricTile so the legacy template's extended
        delta block (delta_pct, delta_period_label, delta_sentiment,
        per-tile tone) is preserved on the typed-Fragment path.

        Values are passed through `_metric_number_filter` (K/M-suffix
        formatting) before reaching the primitive — same string the
        Jinja path produces.

        ctx shape:
            metrics: list of dicts with keys:
              - label, value (required)
              - tone: one of "", "positive", "warning", "destructive",
                "accent", "neutral"
              - delta_direction: "" | "up" | "down" | "flat"
              - delta_sentiment: "" | "positive_up" | "positive_down"
              - delta: stringified delta value
              - delta_pct: float (rendered as `(N%)` when non-zero)
              - delta_period_label: rendered as `vs <label>`
            (legacy) aggregates: dict[name → resolved value], used as
                fallback when metrics list isn't supplied
        """
        from dazzle_ui.runtime.template_renderer import _metric_number_filter

        title = _region_title(region)
        metrics_list: list[dict[str, Any]] = ctx.get("metrics", []) or []
        if not metrics_list:
            agg = ctx.get("aggregates") or getattr(region, "aggregates", {}) or {}
            if isinstance(agg, dict):
                metrics_list = [
                    {"label": str(name).replace("_", " ").title(), "value": val}
                    for name, val in agg.items()
                ]

        body: Fragment
        if not metrics_list:
            body = EmptyState(
                title="No metrics",
                description=getattr(region, "empty_message", None) or "No metrics declared.",
            )
            return _wrap_surface(title, "dashboard", body)

        tiles: list[object] = []
        for m in metrics_list:
            if not isinstance(m, dict):
                continue
            label = str(m.get("label") or m.get("name") or "")
            if not label:
                continue
            value_str = _metric_number_filter(m.get("value"))

            tone_raw = str(m.get("tone") or "")
            tone: Literal["", "positive", "warning", "destructive", "accent", "neutral"] = (
                tone_raw  # type: ignore[assignment]
                if tone_raw in ("", "positive", "warning", "destructive", "accent", "neutral")
                else ""
            )
            direction_raw = str(m.get("delta_direction") or "")
            direction: Literal["", "up", "down", "flat"] = (
                direction_raw  # type: ignore[assignment]
                if direction_raw in ("", "up", "down", "flat")
                else ""
            )
            sentiment_raw = str(m.get("delta_sentiment") or "")
            sentiment: Literal["", "positive_up", "positive_down"] = (
                sentiment_raw  # type: ignore[assignment]
                if sentiment_raw in ("", "positive_up", "positive_down")
                else ""
            )
            try:
                delta_pct = float(m.get("delta_pct") or 0)
            except (TypeError, ValueError):
                delta_pct = 0.0

            tiles.append(
                MetricTile(
                    label=label,
                    value=value_str,
                    tone=tone,
                    delta_direction=direction,
                    delta_sentiment=sentiment,
                    delta_value=str(m.get("delta") or ""),
                    delta_pct=delta_pct,
                    delta_period_label=str(m.get("delta_period_label") or ""),
                )
            )

        if not tiles:
            body = EmptyState(title="No metrics", description="No metric tiles produced.")
        else:
            cols = max(1, min(12, len(tiles)))
            body = Grid(children=tuple(tiles), columns=cols)

        return _wrap_surface(title, "dashboard", body)

    def _build_bar_chart(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: bar_chart` regions render as a BarChart primitive
        — list of (label, count) tuples derived from the region's
        group_by aggregation.

        ctx shape:
            buckets: list[(str, int)] — pre-aggregated by the runtime
            (legacy) items + group_by_field as fallback
            chart_label: optional override for the BarChart label
        """
        title = _region_title(region)
        chart_label = str(ctx.get("chart_label") or title or "Chart")
        raw_buckets = ctx.get("buckets") or []
        buckets: list[tuple[str, int]] = []
        for entry in raw_buckets:
            if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                try:
                    buckets.append((str(entry[0]), int(entry[1])))
                except (TypeError, ValueError):
                    continue
            elif isinstance(entry, dict):
                key = str(entry.get("label") or entry.get("key") or "")
                try:
                    val = int(entry.get("value") or entry.get("count") or 0)
                except (TypeError, ValueError):
                    val = 0
                if key:
                    buckets.append((key, val))

        body: Fragment
        if not buckets:
            body = EmptyState(
                title="No data",
                description=getattr(region, "empty_message", None) or "No buckets to chart.",
            )
        else:
            body = BarChart(label=chart_label, buckets=tuple(buckets))

        return _wrap_surface(title, "report", body)
