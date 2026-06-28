"""Canonical semantic-tone vocabulary for status badges (#1493).

The single source of truth for the tone palette an enum value's ``semantic:``
clause may bind to. Lives in ``core`` (not ``render``) because the validator
(``core.validation``) must check declared tones against it, and ``core`` is the
bottom layer — ``render``/``page`` may import *up* from here, never the reverse.

The five tones are exactly those with CSS rules (``badge.css``) and entries in
the render-layer name-guess map (``_STATUS_TONE_MAP``). ``positive`` is accepted
as a DSL-author-friendly alias for ``success`` (the issue body proposed
``positive``; the live stylesheet only has ``success``), so a declared
``done=positive`` normalises to ``success`` at parse/validate/render time.
"""

from __future__ import annotations

from typing import Any

# Ordered by lifecycle valence (positive → neutral). The render layer maps each
# to a CSS class + (slice 2) a WCAG icon.
CANONICAL_TONES: tuple[str, ...] = ("success", "info", "warning", "destructive", "neutral")

# Author-friendly aliases → canonical tone. ``positive`` has no CSS rule of its
# own; it means ``success``.
TONE_ALIASES: dict[str, str] = {"positive": "success"}


def normalize_tone(tone: str) -> str | None:
    """Canonicalise a declared tone, applying aliases.

    Returns the canonical tone name, or ``None`` if *tone* is neither canonical
    nor a known alias (the validator turns ``None`` into ``E_SEMANTIC_TONE_UNKNOWN``).
    """
    key = tone.strip().lower()
    key = TONE_ALIASES.get(key, key)
    return key if key in CANONICAL_TONES else None


def field_enum_semantic_map(field_type: Any, enums: Any = None) -> dict[str, str]:
    """Declared value→tone `semantic:` map for an enum field type (#1493 slice 2).

    Resolution: an inline `enum[...]` field's own ``enum_semantics`` wins;
    otherwise a shared ``enum`` block whose value-set matches the field's
    ``enum_values`` (the same match the column builders use to recover titles)
    contributes its per-value ``EnumValueSpec.semantic``. Tones are returned as
    declared (raw/lowercased); ``resolve_status_tone`` normalises them at render
    time. Empty dict when nothing is declared or the field isn't an enum.

    Duck-typed (no IR import) so the page-render (`template_compiler`) and the
    http-workspace (`workspace_columns`) column builders share one implementation
    without either layer importing the other.
    """
    ft = field_type
    if ft is None:
        return {}
    kind = getattr(ft, "kind", None)
    kind_val = getattr(kind, "value", None) or (str(kind) if kind else "")
    if kind_val != "enum":
        return {}
    inline = getattr(ft, "enum_semantics", None)
    if inline:
        return dict(inline)
    enum_values = getattr(ft, "enum_values", None)
    if enums and enum_values:
        vals_set = set(enum_values)
        for enum_spec in enums:
            if {ev.name for ev in enum_spec.values} == vals_set:
                return {ev.name: ev.semantic for ev in enum_spec.values if ev.semantic}
    return {}
