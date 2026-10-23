"""A list row's human-readable name for its control labels (#1842, WCAG 1.1.1).

The row's expander, select checkbox, edit and delete controls are named
"Toggle detail for <row>", "Select <row>", and so on. Naming them by the
first column read "Toggle detail for <uuid>" whenever that column was an id.
"""

from __future__ import annotations

import re
from typing import Any

from dazzle.render.filters import _ref_display_name

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
# Column types never used as a row's accessible name: chrome-y cells, and
# `sensitive` (masked in its cell, so it must not leak through a label).
_NON_LABEL_COL_TYPES = frozenset({"ref", "badge", "bool", "currency", "sensitive"})


def row_label_value(columns: list[Any], item: dict[str, Any]) -> Any:
    """The row's display text.

    Order: the `__display__` the list handler injects from the entity's
    `display_field`, then the first non-empty column whose type can name a
    row and whose key and value are not identifiers; the record id only when
    nothing readable exists. Ref dicts resolve via `_ref_display_name`.
    """
    candidates: list[Any] = [item.get("__display__")]
    for col in columns:
        key = str(col.get("key", "") or "")
        if col.get("type") in _NON_LABEL_COL_TYPES or not key:
            continue
        value = item.get(key)
        if key == "id" or key.endswith("_id"):
            continue
        if isinstance(value, str) and _UUID_RE.match(value.strip()):
            continue
        candidates.append(value)
    for value in candidates:
        if isinstance(value, dict):
            value = _ref_display_name(value)
        if value not in (None, ""):
            return value
    return item.get("id", "")
