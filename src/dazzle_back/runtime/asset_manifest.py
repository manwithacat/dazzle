# src/dazzle_back/runtime/asset_manifest.py
"""
Conditional JS asset derivation from surface field specs.

Walks the fields of a surface and collects which vendor widget libraries
are needed, so base.html can conditionally load only the required scripts.
"""

from __future__ import annotations

from typing import Any, Protocol


class _HasWidget(Protocol):
    type: str
    widget: str | None


class _HasFields(Protocol):
    fields: list[Any]


# Maps (widget, optional type constraint) → vendor asset key
_WIDGET_ASSET_MAP: dict[str, str | tuple[str, set[str]]] = {
    "rich_text": "quill",
    "combobox": "tom-select",
    "multi_select": "tom-select",
    "tags": "tom-select",
    "color": "pickr",
    # picker and range only apply to date/datetime fields
    "picker": ("flatpickr", {"date", "datetime"}),
    "range": ("flatpickr", {"date", "datetime"}),
}


def collect_required_assets(surface: _HasFields) -> set[str]:
    """Derive the set of vendor JS asset keys required by a surface's fields.

    Returns a set of strings like ``{"quill", "tom-select", "flatpickr"}``.
    These keys correspond to conditional blocks in ``base.html``.
    """
    assets: set[str] = set()
    for field in surface.fields:
        widget = getattr(field, "widget", None)
        if not widget:
            continue
        mapping = _WIDGET_ASSET_MAP.get(widget)
        if mapping is None:
            continue
        if isinstance(mapping, tuple):
            asset_key, allowed_types = mapping
            field_type = getattr(field, "type", "")
            if field_type in allowed_types:
                assets.add(asset_key)
        else:
            assets.add(mapping)
    return assets
