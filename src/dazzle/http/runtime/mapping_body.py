"""Dotted paths into an integration request body.

A name segment builds an object. An all-digit segment is a list index
(#1770): ``otherGains.0.assetType`` is
``{"otherGains": [{"assetType": value}]}``. A later ``.1`` extends that
list. An index written without the ones below it leaves ``None`` in the gap.
"""

from __future__ import annotations

from typing import Any


def set_nested_value(root: dict[str, Any], key: str, value: Any) -> None:
    """Write ``value`` at the dotted path ``key``."""
    parts = key.split(".")
    cursor: Any = root
    for index, part in enumerate(parts):
        if index == len(parts) - 1:
            _write(cursor, part, value)
            return
        cursor = _descend(cursor, part, parts[index + 1])


def _write(cursor: Any, part: str, value: Any) -> None:
    if _is_index(part):
        slot = int(part)
        _grow(cursor, slot)
        cursor[slot] = value
        return
    cursor[part] = value


def _descend(cursor: Any, part: str, nxt: str) -> Any:
    wants_list = _is_index(nxt)
    if _is_index(part):
        slot = int(part)
        _grow(cursor, slot)
        current = cursor[slot]
        if not isinstance(current, list if wants_list else dict):
            current = [] if wants_list else {}
            cursor[slot] = current
        return current
    current = cursor.get(part)
    if not isinstance(current, list if wants_list else dict):
        current = [] if wants_list else {}
        cursor[part] = current
    return current


def _grow(seq: list[Any], index: int) -> None:
    while len(seq) <= index:
        seq.append(None)


def _is_index(part: str) -> bool:
    return part.isascii() and part.isdigit()
