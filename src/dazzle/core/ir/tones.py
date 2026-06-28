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
