"""Misc-family region builders.

Houses the builders that don't slot into cards, tables, charts,
metrics, or timeline families:

  - _build_grid                  CSS-driven responsive card grid
  - _build_confirm_action_panel  three-state consent panel (ConfirmGate)

See issue #1065 for the full decomposition plan.
"""

from __future__ import annotations

from typing import Any

from dazzle.render.fragment import (
    ConfirmCheckItem,
    ConfirmGate,
    Fragment,
    GridCell,
    GridRegion,
    Surface,
)
from dazzle.render.fragment.region._context import RegionContext
from dazzle.render.fragment.region._row_links import _resolve_row_links
from dazzle.render.fragment.region._shared import (
    _region_title,
    _render_typed_value,
    _wrap_surface,
)


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
