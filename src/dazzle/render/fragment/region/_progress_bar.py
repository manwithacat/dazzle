"""Helpers for ``display: progress_bar`` → ProgressBar (.dz-progress).

Keeps family-local coercion out of ``_builders_metrics`` (MI / "no
family-local helpers" rule for that module). Distinct from StageBar /
``display: progress`` (progress-region).
"""

from __future__ import annotations

from typing import Any, Literal

from dazzle.render.fragment import ProgressBar

_PROGRESS_BAR_TONES = frozenset({"success", "warning", "destructive"})
_PROGRESS_VALUE_KEYS = ("percent", "progress", "value", "complete_pct", "pct")


def _coerce_progress_value(raw: Any) -> float | None:
    if raw is None or raw is False:
        return None
    if isinstance(raw, bool):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        text = str(raw).strip().rstrip("%")
        if not text:
            return None
        try:
            return float(text)
        except (TypeError, ValueError):
            return None


def _progress_tone(raw: Any) -> Literal["", "success", "warning", "destructive"]:
    tone = str(raw or "").strip().lower().replace("-", "_")
    if tone in ("danger", "error", "destructive"):
        return "destructive"
    if tone in _PROGRESS_BAR_TONES:
        return tone  # type: ignore[return-value]
    return ""


def progress_bars_from_entries(raw_entries: list[Any]) -> list[ProgressBar]:
    """Static entries → ProgressBar (title=label, body/caption=value, icon=tone)."""
    bars: list[ProgressBar] = []
    for entry in raw_entries:
        if not isinstance(entry, dict):
            continue
        label = str(entry.get("title") or entry.get("name") or entry.get("label") or "").strip()
        value_raw = entry.get("body") or entry.get("caption") or entry.get("value")
        value = _coerce_progress_value(value_raw)
        if value is None:
            continue
        tone = _progress_tone(entry.get("icon") or entry.get("tone") or entry.get("status"))
        bars.append(ProgressBar(value=value, label=label or "Progress", tone=tone))
    return bars


def progress_bars_from_items(items: list[Any]) -> list[ProgressBar]:
    """Entity/runtime rows → ProgressBar from percent-like fields."""
    bars: list[ProgressBar] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        label = str(
            item.get("name") or item.get("title") or item.get("label") or item.get("metric") or ""
        ).strip()
        value: float | None = None
        for key in _PROGRESS_VALUE_KEYS:
            value = _coerce_progress_value(item.get(key))
            if value is not None:
                break
        if value is None:
            continue
        tone = _progress_tone(item.get("tone") or item.get("status") or item.get("icon"))
        bars.append(ProgressBar(value=value, label=label or "Progress", tone=tone))
    return bars
