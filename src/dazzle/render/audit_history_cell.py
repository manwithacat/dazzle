"""Clerk-facing audit-history labels (oral #179).

Invoice hubs dumped ISO clocks, ``update``, and ``dunning_state`` on the
HTMX history region. Queue/list already timeago + title-case those tokens.
Leftover junk stays put. Do not join remaining actor UUIDs or restyle
remaining money/IBAN before/after values (oral #175/#176/#178).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from dazzle.render.filters import (
    _ISO_DATE_ONLY_RE,
    _ISO_DT_PREFIX_RE,
    _LEFTOVER_STAGE_TOKENS,
    _SCHEMA_TOKEN_RE,
    _timeago_filter,
    clerk_entity_card_field_label,
    clerk_stage_label,
)
from dazzle.render.fragment.format_cell import format_cell


def _leftover(value: Any) -> bool:
    if value is None or value == "":
        return False
    return str(value).strip().lower() in _LEFTOVER_STAGE_TOKENS


def clerk_audit_op_display(value: Any) -> str:
    """``update`` → ``Update``. Leftover stays put."""
    return clerk_stage_label(value)


def clerk_audit_field_label(value: Any) -> str:
    """``dunning_state`` → ``Dunning State``. Leftover stays put."""
    return clerk_entity_card_field_label(value)


def clerk_audit_when_display(value: Any) -> str:
    """Relative clock for history ``at``. Leftover ISO-junk stays put."""
    if value is None or value == "":
        return ""
    if _leftover(value):
        return str(value).strip()
    return _timeago_filter(value)


def clerk_audit_when_attr(value: Any) -> str:
    """Machine ``datetime`` attribute; leftover/empty omit."""
    if value is None or value == "" or _leftover(value):
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if _ISO_DT_PREFIX_RE.match(text) or _ISO_DATE_ONLY_RE.match(text):
        return text.replace(" ", "T", 1)
    return ""


def clerk_audit_value_display(value: Any, field_key: Any = "") -> str:
    """Bool/datetime/schema-token values; leftover stays put.

    Do not map remaining INT cents / IBAN / tags (oral #171–#176).
    """
    del field_key
    if value is None or value == "":
        return ""
    if _leftover(value):
        return str(value).strip()
    if isinstance(value, bool):
        return format_cell(value, "bool")
    if isinstance(value, datetime):
        return _timeago_filter(value)
    if isinstance(value, date):
        return format_cell(value, "date")
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return ""
        if _ISO_DT_PREFIX_RE.match(text):
            return _timeago_filter(text)
        if _ISO_DATE_ONLY_RE.match(text):
            return format_cell(text, "date")
        if _SCHEMA_TOKEN_RE.match(text):
            return clerk_stage_label(text)
        return text
    return str(value)
