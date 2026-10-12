"""Misc-family region builders.

Houses the builders that don't slot into cards, tables, charts,
metrics, or timeline families:

  - _build_grid                  CSS-driven responsive card grid
  - _build_confirm_action_panel  three-state consent panel (ConfirmGate)
  - _build_search_box            HTMX FTS input + lazy results

See issue #1065 for the full decomposition plan.
"""

from __future__ import annotations

from typing import Any

from dazzle.render.fragment import (
    URL,
    ConfirmCheckItem,
    ConfirmGate,
    Fragment,
    GridCell,
    GridRegion,
    SearchBox,
    Surface,
)
from dazzle.render.fragment.region._context import RegionContext
from dazzle.render.fragment.region._row_links import _resolve_row_links
from dazzle.render.fragment.region._shared import (
    _region_title,
    _render_typed_value,
    _wrap_surface,
)


def _search_box_placeholder(ctx: RegionContext, region: Any, empty_msg: Any) -> str:
    """Resolve visible search input chrome.

    Prefer explicit placeholder → *author* region.title (not auto-derived
    name titles) → short empty: coaching. Bare "Search…" is last resort —
    pilots and panel agents otherwise watch the A–Z list and report
    "search broken" when FTS results land in the results panel (cycle 1332).
    """
    explicit_ph = str(ctx.get("placeholder") or "").strip()
    if explicit_ph:
        return explicit_ph
    author_title = getattr(region, "title", None)
    if author_title and str(author_title).strip():
        return str(author_title).strip()
    if empty_msg:
        clause = str(empty_msg).split(".")[0].strip()
        return clause[:72] if clause else "Type to search"
    return "Search…"


class _BuildersMiscMixin:
    """Mixin adding the misc-family `_build_*` methods to
    `WorkspaceRegionAdapter`. Same pattern as other family mixins.
    """

    def _build_confirm_action_panel(self, region: Any, ctx: RegionContext) -> Surface:
        """`display: confirm_action_panel` renders a `ConfirmGate`
        primitive — three-state consent panel matching the legacy
        `workspace/regions/confirm_action_panel.html` byte-for-byte.

        Phase 4B.1.d — replaces the prior placeholder rendering (Card
        + Heading + bracketed action label). The ConfirmGate primitive
        carries the full state machine (off/pending/draft, live,
        revoked) plus the checklist gated by HM `dz-confirm-gate.js`
        gating + dual button + audit footer.

        ctx shape (Phase 4B preferred):
            state_value: str — entity field value (resolved at request
                time); branches to live / revoked / off rendering
            confirmations: list of dicts {title, caption?, required?}
            primary_action_url: str (commit / re-enable URL)
            secondary_action_url: str ("Save as draft" URL)
            revoke_url: str (live-state revoke URL)
            audit_enabled: bool (entity has `audit:` block)

        ctx shape (Phase 4A fallback):
            prompt / description / message + action_label — produces
            a minimal ConfirmGate with `state="off"` and the prompt
            text wired into a synthetic single-item checklist. Mainly
            for tests; runtime should use the preferred shape.
        """
        title = _region_title(region)

        # Phase 4B preferred: full state machine
        state = str(ctx.get("state_value") or "off")
        primary_url = str(ctx.get("primary_action_url") or "")
        secondary_url = str(ctx.get("secondary_action_url") or "")
        revoke_url = str(ctx.get("revoke_url") or "")
        audit_enabled = bool(ctx.get("audit_enabled"))

        confirmations: list[ConfirmCheckItem] = []
        for entry in ctx.get("confirmations") or []:
            if not isinstance(entry, dict):
                continue
            entry_title = str(entry.get("title") or "")
            if not entry_title:
                continue
            confirmations.append(
                ConfirmCheckItem(
                    title=entry_title,
                    caption=str(entry.get("caption") or ""),
                    required=bool(entry.get("required")),
                )
            )

        # Phase 4A fallback: synthesise from prompt + action_label
        if (
            not confirmations
            and not primary_url
            and not revoke_url
            and (ctx.get("prompt") or ctx.get("description") or ctx.get("message"))
        ):
            prompt = str(ctx.get("prompt") or ctx.get("description") or ctx.get("message") or "")
            action_label = str(ctx.get("action_label") or "")
            if prompt:
                confirmations.append(ConfirmCheckItem(title=prompt, required=False))
            if action_label:
                # Encode the action label as a synthetic primary URL hint —
                # keeps the rendered panel non-empty without a real action.
                primary_url = primary_url or "#"

        body: Fragment = ConfirmGate(
            state=state,
            confirmations=tuple(confirmations),
            primary_action_url=primary_url,
            secondary_action_url=secondary_url,
            revoke_url=revoke_url,
            audit_enabled=audit_enabled,
            primary_label=str(ctx.get("primary_label") or "Confirm and enable"),
            secondary_label=str(ctx.get("secondary_label") or "Save as draft"),
        )
        return _wrap_surface(title or "Confirm", "dashboard", body)

    def _build_search_box(self, region: Any, ctx: RegionContext) -> Surface:
        """`display: search_box` renders a `SearchBox` primitive — HTMX
        FTS input + lazy-loaded results panel + Alpine coaching toggle.

        Phase 4B.1.d — replaces the prior plain-`Field` rendering, which
        had no HTMX wiring, no result panel, and no coaching message.
        Now byte-equivalent to the legacy `workspace/regions/search_box.html`.

        ctx shape (Phase 4B preferred):
            source_entity: str — entity name for the FTS endpoint URL
                (e.g. "Manuscript" → /_dazzle/fts/Manuscript?html=1)
            name: optional results-id slug; defaults to region.name
            placeholder: optional input placeholder
            display_field: optional (for documentation; the endpoint owns
                result-row rendering)
            coaching_message: optional pre-translated string shown until
                the user types (default "Type to search")

        ctx shape (Phase 4A fallback):
            placeholder + label only — produces a SearchBox with a
            self-referential endpoint (`/_dazzle/fts/{region.name}?html=1`)
            so existing tests don't crash. The runtime should always
            supply `source_entity` ahead of the Phase 4B.2 translator.
        """
        title = _region_title(region)
        source_entity = str(ctx.get("source_entity") or "")
        name = str(ctx.get("name") or getattr(region, "name", "") or "searchbox")
        # Prefer explicit coaching_message; else region empty: copy (DSL empty
        # on search_box is pilot coaching — cycle 1280 contact_manager).
        empty_msg = getattr(region, "empty_message", None) or ctx.get("empty_message")
        coaching = str(ctx.get("coaching_message") or empty_msg or "Type to search")
        # Placeholder is the only visible input chrome (label is
        # visually-hidden). See `_search_box_placeholder` for priority.
        placeholder = _search_box_placeholder(ctx, region, empty_msg)
        label = str(ctx.get("label") or title or placeholder)

        # Prefer source_entity; fall back to region name (tests / missing ctx).
        entity_hint = source_entity or name
        endpoint = URL(f"/_dazzle/fts/{entity_hint}?html=1")

        body: Fragment = SearchBox(
            name=name,
            fts_endpoint=endpoint,
            placeholder=placeholder,
            coaching_message=coaching,
            label=label,
        )
        return _wrap_surface(title, "form", body)

    def _build_grid(self, region: Any, ctx: RegionContext) -> Surface:
        """`display: grid` regions render items as cards in a CSS-driven
        responsive grid layout. Phase 4B.4 wave 2: dedicated `GridRegion`
        primitive replacing prior generic `Grid` composition for byte-
        equivalence with `workspace/regions/grid.html`.

        ctx shape (production runtime):
            items: list of dicts (rows from the source entity)
            columns: list of `{key, label, type}` dicts — same shape
                as LIST/DETAIL columns
            display_key: str — column key for the primary cell title
            entity_name: str — fallback title when display_key value is None
            empty_message: optional empty-state fallback
        """
        title = _region_title(region)
        items: list[dict[str, Any]] = ctx.get("items", []) or []
        # `columns` is the production runtime list-of-dicts shape;
        # earlier Phase 4A tests passed an int (column count) as
        # `columns`. Defend against both.
        columns_raw = ctx.get("columns") or []
        columns: list[dict[str, Any]] = columns_raw if isinstance(columns_raw, list) else []
        display_key = str(ctx.get("display_key") or ctx.get("label_field") or "")
        entity_name = str(ctx.get("entity_name") or "Item")
        detail_url_template = str(ctx.get("detail_url_template") or "")

        # #1303: resolve per-cell hub drills (same contract as LIST/QUEUE).
        row_items = [i for i in items if isinstance(i, dict)]
        row_links: tuple[str | None, ...] = (
            _resolve_row_links(row_items, detail_url_template) if detail_url_template else ()
        )

        cells: list[GridCell] = []
        link_idx = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            primary = item.get(display_key) if display_key else None
            if primary is None:
                primary = item.get("name") or item.get("title") or entity_name
            # #1626 S3 + Goal B media: type-ish enum leading the card title
            # (Photo · Storefront) while image columns supply real thumbs.
            type_token = item.get("asset_type") or item.get("type") or item.get("kind")
            if type_token is not None and str(type_token).strip():
                type_label = str(type_token).replace("_", " ").strip().title()
                primary_s = str(primary)
                if not primary_s.lower().startswith(type_label.lower()):
                    primary = f"{type_label} · {primary_s}"
            fields: list[tuple[str, object]] = []
            # Image thumbs first so media grids read as pixels, not meta.
            ordered_cols = sorted(
                [c for c in columns if isinstance(c, dict)],
                key=lambda c: (
                    0
                    if str(c.get("type") or "") == "image"
                    else (1 if str(c.get("type") or "") == "color" else 2)
                ),
            )
            for col in ordered_cols:
                key = str(col.get("key") or "")
                if not key or key == display_key:
                    continue
                col_type = str(col.get("type") or "")
                # Media/palette chrome is the value — "Photo Url:" / "Primary Color:"
                # labels dump raw schema on person/brand cards (cycle 1925 agency_lead).
                if col_type in ("image", "color"):
                    label = ""
                else:
                    label = str(col.get("label") or key)
                # GRID renders badges with default size (md, no border)
                # per legacy macro call (no kwargs). Person refs use
                # present(person, card_meta) — not list_cell mislabel.
                fields.append(
                    (
                        label,
                        _render_typed_value(
                            item,
                            col,
                            host="card_meta",
                            image_card=col_type == "image"
                            and key in {"preview_url", "image_url", "cover_url"},
                        ),
                    )
                )
            drill = ""
            if link_idx < len(row_links) and row_links[link_idx]:
                drill = str(row_links[link_idx])
            link_idx += 1
            cells.append(GridCell(title=str(primary), fields=tuple(fields), drill_url=drill))

        empty_msg = (
            ctx.get("empty_message") or getattr(region, "empty_message", None) or "No items found."
        )
        body: Fragment = GridRegion(cells=tuple(cells), empty_message=str(empty_msg))
        return _wrap_surface(title, "dashboard", body)
