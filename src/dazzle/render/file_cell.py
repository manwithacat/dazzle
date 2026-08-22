"""Clerk-facing file cells for workspace timeline/queue/CSV (oral #170).

Kept out of ``filters.py`` so that module's maintainability index stays A.
"""

from __future__ import annotations

import re
from typing import Any

from dazzle.render.filters import _LEFTOVER_STAGE_TOKENS, _basename_or_url_filter

_STORAGE_ID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _file_cell_scalar(value: Any) -> Any:
    """Unwrap ``{filename,name,id,path}`` file dicts to a scalar token."""
    if not isinstance(value, dict):
        return value
    for key in ("filename", "name", "id", "key", "path"):
        nested = value.get(key)
        if nested not in (None, ""):
            return nested
    return ""


def clerk_file_cell_display(
    item: dict[str, Any] | None,
    col_key: Any = "",
    value: Any = None,
) -> str:
    """Filename / basename / Download — never a raw storage UUID.

    Leftover junk stays put. Empty stays empty.
    """
    _ = col_key
    if value is None or value == "":
        return ""
    scalar = _file_cell_scalar(value)
    text = str(scalar).strip()
    if text.lower() in _LEFTOVER_STAGE_TOKENS:
        return text
    for key in ("filename", "name"):
        hint = (item or {}).get(key)
        if hint in (None, ""):
            continue
        label = str(hint).strip()
        if not label or label.lower() in _LEFTOVER_STAGE_TOKENS:
            continue
        if _STORAGE_ID_RE.match(label):
            continue
        return label
    base = _basename_or_url_filter(scalar)
    if base and not _STORAGE_ID_RE.match(base) and base.lower() not in _LEFTOVER_STAGE_TOKENS:
        return base
    return "Download"
