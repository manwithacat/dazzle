"""Related-tab cell assembly for hub queues (oral #145).

Kept out of ``fragment_adapter`` so injecting omitted identity does not
drop that module's maintainability rank.
"""

from __future__ import annotations

from typing import Any

from dazzle.render.breadcrumbs import clerk_related_create_noun
from dazzle.render.cell_chrome import (
    related_queue_columns_omit_identity,
    related_queue_identity_from_record,
)
from dazzle.render.fragment.format_cell import format_cell
from dazzle.render.fragment.primitives.data import RelatedTab


def _format_related_cell(
    value: Any,
    kind: str,
    currency_code: str = "",
) -> str:
    return format_cell(value, kind, currency_code=currency_code, override=None)


def related_queue_injects_identity(display: str, cols: list[Any]) -> bool:
    return display == "queue" and related_queue_columns_omit_identity(
        str(c.get("key") or "") for c in cols
    )


def related_tab_headers(cols: list[Any], *, inject: bool) -> tuple[str, ...]:
    headers = tuple(str(c.get("label", c.get("key", ""))) for c in cols)
    return ("Title",) + headers if inject else headers


def related_row_cells(cols: list[Any], rec: dict[str, Any], *, inject: bool) -> tuple[str, ...]:
    cells = tuple(
        _format_related_cell(
            rec.get(c.get("key", "")),
            str(c.get("type", "text") or "text"),
            str(c.get("currency_code", "") or ""),
        )
        for c in cols
    )
    if inject:
        return (related_queue_identity_from_record(rec),) + cells
    return cells


def related_create_affordance(tab: dict[str, Any], item_id: str) -> tuple[str, str, str]:
    create_url = str(tab.get("create_url", "") or "")
    if not create_url:
        return "", "", ""
    sep = "&" if "?" in create_url else "?"
    filter_field = str(tab.get("filter_field", "") or "")
    href = f"{create_url}{sep}{filter_field}={item_id}"
    ftf = str(tab.get("filter_type_field", "") or "")
    if ftf:
        href += f"&{ftf}={tab.get('filter_type_value', '') or ''}"
    action = f"{tab.get('entity_name', '') or ''}.create"
    name = str(tab.get("entity_name", "") or "")
    title = str(tab.get("entity_title", "") or "")
    catalog = {name: title} if name and title else None
    return href, action, clerk_related_create_noun(name, catalog)


def related_tab_from_ctx(tab: dict[str, Any], item_id: str, *, display: str) -> RelatedTab:
    """One related tab: formatted cells + optional queue identity title."""
    cols = tab.get("columns", []) or []
    inject = related_queue_injects_identity(display, cols)
    tmpl = str(tab.get("detail_url_template", "") or "")
    rows: list[tuple[str, ...]] = []
    drills: list[str] = []
    for record in tab.get("rows", []) or []:
        rec = record if isinstance(record, dict) else {}
        rows.append(related_row_cells(cols, rec, inject=inject))
        rid = str(rec.get("id", "") or "")
        drills.append(tmpl.replace("{id}", rid) if (tmpl and rid) else "")
    create_href, create_action, create_label = related_create_affordance(tab, item_id)
    total = max(int(tab.get("total", 0) or 0), len(rows))
    return RelatedTab(
        tab_id=str(tab.get("tab_id", "") or ""),
        label=str(tab.get("label", "") or ""),
        headers=related_tab_headers(cols, inject=inject),
        rows=tuple(rows),
        row_drill=tuple(drills),
        create_href=create_href,
        create_action=create_action,
        create_label=create_label,
        total=total,
    )
