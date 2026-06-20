"""Cards-family region builders.

Houses the 5 card-shaped builders. All produce a Surface with card-style
content (kanban columns of cards, single profile card, action-CTA grid,
composite multi-section card, horizontal member skim):

  - _build_kanban         KanbanRegion of KanbanColumns × KanbanCards
  - _build_profile_card   single ProfileCard with avatar/stats/facts
  - _build_action_grid    ActionGrid of ActionCard CTAs
  - _build_entity_card    EntityCardRegion (composite 360°) (#1017)
  - _build_cohort_strip   horizontal CohortStripRegion (#1018)

No family-local helpers — `_coerce_columns` and `_format_card` that
were the Phase 4A `_build_kanban` substrate are not used by the
Phase 4B.4 `KanbanRegion` rewrite and were dropped during this
extraction.

See issue #1065 for the full decomposition plan.
"""

from __future__ import annotations

from typing import Any, Literal

from dazzle.render.fragment import (
    URL,
    ActionCard,
    ActionGrid,
    CohortStripCell,
    CohortStripLensTab,
    CohortStripRegion,
    EmptyState,
    EntityCardRegion,
    EntityCardSection,
    Fragment,
    KanbanCard,
    KanbanColumn,
    KanbanRegion,
    ProfileCard,
    RawHTML,
    Surface,
)
from dazzle.render.fragment.region._context import RegionContext
from dazzle.render.fragment.region._shared import (
    _region_title,
    _render_typed_value,
    _wrap_surface,
)


class _BuildersCardsMixin:
    """Mixin adding the 5 cards-family `_build_*` methods to
    `WorkspaceRegionAdapter`. Same pattern as other family mixins.
    """

    def _build_kanban(self, region: Any, ctx: RegionContext) -> Surface:
        """`display: kanban` regions render as a `KanbanRegion` primitive
        matching `workspace/regions/kanban.html` byte-for-byte.

        Phase 4B.4 wave 4: replaced the simpler `KanbanBoard` primitive
        with the workspace-shaped `KanbanRegion` carrying full per-card
        title + secondary fields + attention tag.

        ctx shape (production runtime):
            items: list of dicts (rows from the source entity)
            kanban_columns: ordered status values (legacy key)
                (alt) group_keys for Phase 4A back-compat
            group_by: str — field name to bucket items by
                (alt) group_by_field for Phase 4A back-compat
            columns: list of column dicts {key, label, type, ref_route}
                — secondary fields rendered per-card (excludes
                display_key and group_by)
            display_key: str — field name for the card title
            entity_name: str — fallback title when display_key is None
            total: int — overflow indicator denominator
            empty_message: optional empty-state fallback
        """
        from dazzle.render.filters import _timeago_filter

        title = _region_title(region)
        items: list[dict[str, Any]] = ctx.get("items", []) or []
        # Accept both legacy `kanban_columns`/`group_by` and Phase 4A
        # `group_keys`/`group_by_field` shapes.
        column_keys: list[str] = list(ctx.get("kanban_columns") or ctx.get("group_keys") or [])
        group_by: str = str(ctx.get("group_by") or ctx.get("group_by_field") or "")
        columns_meta = ctx.get("columns") or []
        display_key = str(ctx.get("display_key") or "")
        entity_name = str(ctx.get("entity_name") or "Item")
        try:
            total = int(ctx.get("total") or 0)
        except (TypeError, ValueError):
            total = 0
        endpoint = str(ctx.get("endpoint") or "")

        # Build the per-card secondary-field list once — the same set
        # of meta columns applies to every card.
        meta_columns: list[dict[str, Any]] = []
        for col in columns_meta:
            if not isinstance(col, dict):
                continue
            key = str(col.get("key") or "")
            if not key or key == display_key or key == group_by:
                continue
            meta_columns.append(col)

        def _card_title(item: dict[str, Any]) -> str:
            """Mirror the legacy fallback chain for the card heading."""
            for fallback in ("title", "name", "company_name"):
                v = item.get(fallback)
                if v:
                    return str(v)
            first = str(item.get("first_name", "") or "")
            last = str(item.get("last_name", "") or "")
            joined = f"{first} {last}".strip()
            if joined:
                return joined
            for fallback in ("label", "email"):
                v = item.get(fallback)
                if v:
                    return str(v)
            dk_val = item.get(display_key) if display_key else None
            if dk_val:
                return str(dk_val)
            return entity_name

        kanban_cols: list[KanbanColumn] = []
        if not items and not column_keys:
            body: Fragment = KanbanRegion(
                columns=(),
                empty_message=str(
                    ctx.get("empty_message")
                    or getattr(region, "empty_message", None)
                    or "No items found."
                ),
            )
            return _wrap_surface(title, "kanban", body)

        # Group items by column key.
        buckets: dict[str, list[dict[str, Any]]] = {k: [] for k in column_keys}
        for item in items:
            if not isinstance(item, dict):
                continue
            key = str(item.get(group_by, "") or "")
            buckets.setdefault(key, []).append(item)

        for col_key in column_keys:
            cards: list[KanbanCard] = []
            for item in buckets.get(col_key, []):
                # Per-cell type-aware rendering for secondary fields.
                fields: list[tuple[str, object]] = []
                for col in meta_columns:
                    label = str(col.get("label") or col.get("key") or "")
                    col_type = str(col.get("type") or "")
                    if col_type == "date":
                        # Legacy template does timeago directly on date columns.
                        date_val = item.get(str(col.get("key") or ""))
                        date_str = _timeago_filter(date_val) if date_val else ""
                        fields.append((label, RawHTML(date_str)))
                    else:
                        # KANBAN renders badges with size='sm' per legacy.
                        fields.append((label, _render_typed_value(item, col, badge_size="sm")))
                attn_raw = item.get("_attention") if hasattr(item, "get") else None
                attn_level = ""
                attn_message = ""
                if isinstance(attn_raw, dict):
                    attn_level = str(attn_raw.get("level") or "")
                    attn_message = str(attn_raw.get("message") or "")
                cards.append(
                    KanbanCard(
                        title=_card_title(item),
                        fields=tuple(fields),
                        attention_level=attn_level,
                        attention_message=attn_message,
                    )
                )
            kanban_cols.append(KanbanColumn(label=col_key, cards=tuple(cards)))

        empty_msg = (
            ctx.get("empty_message") or getattr(region, "empty_message", None) or "No items found."
        )
        body = KanbanRegion(
            columns=tuple(kanban_cols),
            total=total,
            endpoint=endpoint,
            empty_message=str(empty_msg),
        )
        return _wrap_surface(title, "kanban", body)

    def _build_profile_card(self, region: Any, ctx: RegionContext) -> Surface:
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

    def _build_action_grid(self, region: Any, ctx: RegionContext) -> Surface:
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

        empty_msg = getattr(region, "empty_message", None) or "No actions available."
        body: Fragment = ActionGrid(cards=tuple(cards), empty_message=str(empty_msg))
        return _wrap_surface(title, "dashboard", body)

    def _build_cohort_strip(self, region: Any, ctx: RegionContext) -> Surface:
        """`display: cohort_strip` regions render as a horizontal
        member-skim strip with lens toggle (#1018, v0.67.7).

        Reads `region.cohort_strip_config` for the lens definitions
        and active-lens default, plus `ctx` for the data resolution
        upstream (member rows + active lens id + endpoint URL). Pure
        config-to-primitive translation — the row resolution + FK
        join + lens-primary extraction live one layer up in
        `workspace_rendering.py`, which populates the ctx dict.

        ctx shape:
            cohort_cells: list of dicts {"member_id": str, "member_name":
                str, "primary_value": str, "subtitle": str (default ""),
                "avatar_initials": str (default ""), "tone": str
                (default "neutral"), "drill_url": str (default "")}
            cohort_active_lens: id of the lens to mark active. Falls
                back to config.default_lens, then config.lenses[0].id.
            cohort_endpoint: str — the URL the lens-toggle hx-get
                targets. Falls back to ctx["region_url"] then "".
        """
        title = _region_title(region)
        cfg = getattr(region, "cohort_strip_config", None)
        region_name = str(getattr(region, "name", "") or "cohort")

        # Pull config-defined lenses; if no config, render an
        # empty-state surface (defensive: parser should reject this).
        config_lenses = list(getattr(cfg, "lenses", None) or []) if cfg is not None else []
        if not config_lenses:
            return _wrap_surface(
                title,
                "dashboard",
                EmptyState(
                    title="Cohort strip not configured",
                    description="No lenses declared on this region.",
                ),
            )

        # Resolve active lens: explicit ctx → config default → first lens.
        default_lens_id = str(getattr(cfg, "default_lens", "") or "") if cfg is not None else ""
        first_lens_id = str(getattr(config_lenses[0], "id", "") or "")
        active_lens_id = str(ctx.get("cohort_active_lens") or default_lens_id or first_lens_id)
        # If the requested lens isn't in the config, fall back to the
        # first declared lens — defensive against stale URL params.
        known_lens_ids = {str(getattr(lens, "id", "") or "") for lens in config_lenses}
        if active_lens_id not in known_lens_ids:
            active_lens_id = first_lens_id

        lens_tabs: list[CohortStripLensTab] = []
        for lens in config_lenses:
            lens_id = str(getattr(lens, "id", "") or "")
            if not lens_id:
                continue
            lens_tabs.append(
                CohortStripLensTab(
                    id=lens_id,
                    label=str(getattr(lens, "label", "") or lens_id),
                    is_active=(lens_id == active_lens_id),
                )
            )

        # Constructor invariant: exactly one active lens. If our
        # active-id selection produced zero (e.g. all ids empty),
        # promote the first tab.
        if lens_tabs and not any(tab.is_active for tab in lens_tabs):
            head = lens_tabs[0]
            lens_tabs[0] = CohortStripLensTab(id=head.id, label=head.label, is_active=True)

        valid_tones = ("neutral", "good", "warn", "bad")
        cells: list[CohortStripCell] = []
        for entry in ctx.get("cohort_cells") or []:
            if not isinstance(entry, dict):
                continue
            member_id = str(entry.get("member_id") or "")
            if not member_id:
                continue  # primitive's __post_init__ would reject empty id
            tone_raw = str(entry.get("tone") or "neutral")
            tone = tone_raw if tone_raw in valid_tones else "neutral"
            cells.append(
                CohortStripCell(
                    member_id=member_id,
                    member_name=str(entry.get("member_name") or ""),
                    primary_value=str(entry.get("primary_value") or ""),
                    subtitle=str(entry.get("subtitle") or ""),
                    avatar_initials=str(entry.get("avatar_initials") or ""),
                    tone=tone,
                    drill_url=str(entry.get("drill_url") or ""),
                    action_html=str(entry.get("action_html") or ""),
                )
            )

        endpoint_str = str(ctx.get("cohort_endpoint") or ctx.get("region_url") or "")
        empty_msg = getattr(region, "empty_message", None) or "No members in this view."

        body: Fragment = CohortStripRegion(
            region_name=region_name,
            endpoint=URL(endpoint_str),
            lenses=tuple(lens_tabs),
            cells=tuple(cells),
            empty_message=str(empty_msg),
        )
        return _wrap_surface(title, "dashboard", body)

    def _build_entity_card(self, region: Any, ctx: RegionContext) -> Surface:
        """`display: entity_card` regions render as a composite 360°
        single-entity drill-down (#1017, v0.67.8). Domain-agnostic:
        pupil-360 in MIS, customer-360 in CRM, etc.

        ctx shape:
            entity_card_sections: list of dicts {"section_id": str,
                "label": str, "mode": str (default "halo"), "body":
                str (pre-rendered HTML — adapter owns escape),
                "column": "main"|"sidebar" (default "main"),
                "is_omitted": bool (default False)}.
            entity_card_record_label: optional str for the region's
                heading. Empty string omits the heading.

        The data resolution layer queries each section's source
        independently, applies the mode-specific compact renderer to
        produce `body`, and decides per-section whether to mark
        `is_omitted=True` (optional sections that resolved zero rows).
        """
        title = _region_title(region)
        region_name = str(getattr(region, "name", "") or "entity_card")
        record_label = str(ctx.get("entity_card_record_label") or "")

        valid_modes = (
            "halo",
            "flags",
            "mini_bars",
            "stamps",
            "thread_summary",
            "quick_actions",
        )
        valid_columns = ("main", "sidebar")
        sections: list[EntityCardSection] = []
        for entry in ctx.get("entity_card_sections") or []:
            if not isinstance(entry, dict):
                continue
            section_id = str(entry.get("section_id") or "")
            if not section_id:
                continue
            mode_raw = str(entry.get("mode") or "halo")
            mode = mode_raw if mode_raw in valid_modes else "halo"
            column_raw = str(entry.get("column") or "main")
            column = column_raw if column_raw in valid_columns else "main"
            sections.append(
                EntityCardSection(
                    section_id=section_id,
                    label=str(entry.get("label") or ""),
                    mode=mode,  # type: ignore[arg-type]
                    body=str(entry.get("body") or ""),
                    column=column,  # type: ignore[arg-type]
                    is_omitted=bool(entry.get("is_omitted") or False),
                )
            )

        body: Fragment = EntityCardRegion(
            region_name=region_name,
            sections=tuple(sections),
            record_label=record_label,
        )
        return _wrap_surface(title, "dashboard", body)
