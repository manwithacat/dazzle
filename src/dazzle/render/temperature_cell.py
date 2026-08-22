"""Clerk-facing temperature cells for list/queue/detail/CSV (oral #174).

Field-test lists dumped ``22.5`` with no unit. Kept out of
``filters.py`` so that module's maintainability index stays A.
Do not map generic decimals (humidity, amount, score).
"""

from __future__ import annotations

from html import escape as _html_escape
from typing import Any

from dazzle.render.filters import _LEFTOVER_STAGE_TOKENS

_TEMP_C_KEYS = frozenset(
    {
        "temperature",
        "temp",
        "temp_c",
        "temperature_c",
        "ambient_temperature",
        "ambient_temp",
    }
)
_TEMP_F_KEYS = frozenset({"temp_f", "temperature_f"})


def temperature_field_name(name: Any) -> bool:
    """True when ``name`` is a temperature reading (not ``template``)."""
    key = str(name or "").strip().lower()
    if key in _TEMP_C_KEYS or key in _TEMP_F_KEYS:
        return True
    return key.endswith("_temperature") or key.endswith("_temp_c") or key.endswith("_temp_f")


def clerk_temperature_unit(field_key: Any = "") -> str:
    """``°C`` default; ``°F`` only for explicit Fahrenheit field names."""
    key = str(field_key or "").strip().lower()
    if key in _TEMP_F_KEYS or key.endswith("_temp_f") or key.endswith("temperature_f"):
        return "°F"
    return "°C"


def clerk_temperature_display(value: Any, field_key: Any = "") -> str:
    """CSV / related text: ``22.5°C`` not bare ``22.5``. Leftover stays put."""
    if value is None or value == "":
        return ""
    if isinstance(value, str) and value.strip().lower() in _LEFTOVER_STAGE_TOKENS:
        return value.strip()
    if isinstance(value, bool):
        return str(value)
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    rounded = round(number, 1)
    shown = str(int(rounded)) if rounded == int(rounded) else str(rounded)
    return f"{shown}{clerk_temperature_unit(field_key)}"


def clerk_temperature_cell_html(value: Any, field_key: Any = "") -> str:
    """Read-only temperature. Empty invents nothing. Leftover ``zzz`` stays put."""
    if value is None or value == "":
        return ""
    if isinstance(value, str) and value.strip().lower() in _LEFTOVER_STAGE_TOKENS:
        return _html_escape(value.strip())
    display = clerk_temperature_display(value, field_key)
    try:
        float(value)
    except (TypeError, ValueError):
        return _html_escape(display)
    return f'<span class="dz-temperature">{_html_escape(display)}</span>'
