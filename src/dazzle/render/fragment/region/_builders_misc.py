"""Misc-family region builders.

Houses the 5 builders that don't slot into cards, tables, charts,
metrics, or timeline families:

  - _build_grid                  CSS-driven responsive card grid
  - _build_detail                single-item DetailGrid (badge / bool / date / etc.)
  - _build_tree                  recursive nested <details> hierarchy
  - _build_confirm_action_panel  three-state consent panel (ConfirmGate)
  - _build_search_box            HTMX FTS input + lazy results

`_pick_label` migrates with this family because its only caller is
`_build_tree`. The accompanying `_LABEL_CANDIDATES` constant follows.

See issue #1065 for the full decomposition plan.
"""

from __future__ import annotations

from typing import Any

from dazzle.render.fragment import (
    URL,
    ConfirmCheckItem,
    ConfirmGate,
    DetailGrid,
    EmptyState,
    Fragment,
    GridCell,
    GridRegion,
    SearchBox,
    Surface,
    Tree,
    TreeNode,
)
from dazzle.render.fragment.region._shared import (
    _region_title,
    _render_typed_value,
    _wrap_surface,
)

_LABEL_CANDIDATES: tuple[str, ...] = ("title", "name", "id")


def _pick_label(
    item: dict[str, Any],
    field_hint: str = "",
    candidates: tuple[str, ...] = _LABEL_CANDIDATES,
) -> str:
    """Pick a display label from a dict item.

    `field_hint` wins if provided and present; otherwise the first
    matching candidate field is returned. Only caller is `_build_tree`
    in this family; if a future builder needs the same logic, hoist
    this to `_shared`.
    """
    if field_hint and field_hint in item:
        return str(item.get(field_hint) or "")
    for cand in candidates:
        if cand in item:
            return str(item.get(cand) or "")
    return ""


class _BuildersMiscMixin:
    """Mixin adding the 5 misc-family `_build_*` methods to
    `WorkspaceRegionAdapter`. Same pattern as other family mixins.
    """

    def _build_confirm_action_panel(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: confirm_action_panel` renders a `ConfirmGate`
        primitive — three-state consent panel matching the legacy
        `workspace/regions/confirm_action_panel.html` byte-for-byte.

        Phase 4B.1.d — replaces the prior placeholder rendering (Card
        + Heading + bracketed action label). The ConfirmGate primitive
        carries the full state machine (off/pending/draft, live,
        revoked) plus the checklist with Alpine `dzConfirmGate`
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

    def _build_search_box(self, region: Any, ctx: dict[str, Any]) -> Surface:
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
        placeholder = str(ctx.get("placeholder") or "Search…")
        coaching = str(ctx.get("coaching_message") or "Type to search")
        label = str(ctx.get("label") or title or placeholder)

        if source_entity:
            endpoint = URL(f"/_dazzle/fts/{source_entity}?html=1")
        else:
            # Fallback: use the region's own name as the entity hint.
            # Mainly for tests; runtime will supply source_entity.
            endpoint = URL(f"/_dazzle/fts/{name}?html=1")

        body: Fragment = SearchBox(
            name=name,
            fts_endpoint=endpoint,
            placeholder=placeholder,
            coaching_message=coaching,
            label=label,
        )
        return _wrap_surface(title, "form", body)

    def _build_tree(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: tree` regions render a recursive hierarchy as
        nested `<details>` nodes. Phase 4B.4 wave 2: dedicated
        `Tree` primitive replacing prior Stack-of-Text composition for
        byte-equivalence with `workspace/regions/tree.html`.

        ctx shape (primary):
            tree_items: list of nested dicts with `_children` (legacy
                key) or `children` (typed-path) lists holding child
                nodes with the same shape; each node carries a label
                under `display_key`, `name`, or `title`.
            display_key: optional field name to pull label from
                (defaults to "name"/"title" auto-pick)
            (legacy) `items` flat list as fallback
        """
        title = _region_title(region)
        raw = ctx.get("tree_items") or ctx.get("items") or []
        label_field = str(ctx.get("display_key") or ctx.get("label_field") or "")

        def _walk(node_list: list[Any]) -> tuple[TreeNode, ...]:
            out: list[TreeNode] = []
            for node in node_list:
                if not isinstance(node, dict):
                    continue
                label = _pick_label(node, label_field) or "(no label)"
                # Accept both legacy `_children` and typed `children`.
                children_raw = node.get("_children") or node.get("children") or []
                children = _walk(children_raw) if isinstance(children_raw, list) else ()
                out.append(TreeNode(label=label, children=children))
            return tuple(out)

        nodes = _walk(raw) if isinstance(raw, list) else ()

        body: Fragment
        if not nodes:
            body = EmptyState(
                title="No items",
                description=getattr(region, "empty_message", None) or "No data in this region.",
            )
        else:
            body = Tree(nodes=nodes)

        return _wrap_surface(title, "list", body)

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
        rows: list[tuple[str, object]] = []
        for f in fields:
            if not isinstance(f, dict):
                continue
            key = str(f.get("key") or "")
            if not key:
                continue
            label = str(f.get("label") or key.replace("_", " ").title())
            # DETAIL renders badges with `bordered=true` per legacy macro call.
            rows.append((label, _render_typed_value(item, f, badge_bordered=True)))

        body = (
            DetailGrid(rows=tuple(rows)) if rows else EmptyState(title="No fields", description="")
        )
        return _wrap_surface(title, "dashboard", body)

    def _build_grid(self, region: Any, ctx: dict[str, Any]) -> Surface:
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

        cells: list[GridCell] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            primary = item.get(display_key) if display_key else None
            if primary is None:
                primary = item.get("name") or item.get("title") or entity_name
            fields: list[tuple[str, object]] = []
            for col in columns:
                if not isinstance(col, dict):
                    continue
                key = str(col.get("key") or "")
                if not key or key == display_key:
                    continue
                label = str(col.get("label") or key)
                # GRID renders badges with default size (md, no border)
                # per legacy macro call (no kwargs).
                fields.append((label, _render_typed_value(item, col)))
            cells.append(GridCell(title=str(primary), fields=tuple(fields)))

        empty_msg = (
            ctx.get("empty_message") or getattr(region, "empty_message", None) or "No items found."
        )
        body: Fragment = GridRegion(cells=tuple(cells), empty_message=str(empty_msg))
        return _wrap_surface(title, "dashboard", body)
