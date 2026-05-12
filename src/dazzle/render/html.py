"""Canonical HTML-escape helpers for the inline-Python rendering path.

Post-#1042 (v0.67.92) the framework no longer uses Jinja for any
HTML emission. Every renderer composes HTML in Python via f-strings
(or string concatenation), with `html.escape` applied at every
last-mile interpolation. Pre-v0.67.94 each renderer redefined the
same ``_esc(value, *, quote=False)`` helper locally — 7 byte-identical
copies. This module is the canonical single source.

## Two-pattern model

This module supports **Pattern A — framework code emits HTML**:

    from dazzle.render.html import esc

    def render_link(href: str, label: str) -> str:
        return f'<a href="{esc(href, quote=True)}">{esc(label)}</a>'

The other pattern in the codebase is **Pattern B — framework code
executes a user-authored template** (DSL ``llm_intent`` prompts,
DSL vocab ``expansion.body``, project-supplied
``compliance/document.html``). That path uses ``string.Template`` for
``$var`` substitution because the template-author is a downstream
user, not a framework engineer.

The choice is determined by *who writes the template*:

- Dazzle framework code writes the template → f-strings + ``esc``.
- Downstream user writes the template → ``string.Template``.

Don't mix the two within one renderer. If a Pattern A renderer
ingests user data, pass that data through ``esc`` at the
interpolation point — never re-export the raw input as a placeholder
the user can populate.

## Why a single ``esc(*, quote=False)`` and not separate
   ``escape`` / ``escape_attr`` functions?

The 7 pre-existing local helpers all had the same shape:
``_esc(value, *, quote=False)``. ~150 call sites already pass
``quote=True`` for attribute context. Renaming would have required
touching every call site (which broke during the migration when an
auto-translation mishandled multi-line arguments). Keeping the
existing signature lets the convergence be a near-mechanical
``from dazzle.render.html import esc as _esc`` import + delete-local
edit per file. Future renaming to ``escape`` / ``escape_attr`` is
trivial if desired — it's a search-and-replace away.
"""

from __future__ import annotations

import html as _html
from typing import Any

__all__ = ["esc"]


def esc(value: Any, *, quote: bool = False) -> str:
    """Escape *value* for safe embedding in an HTML document.

    Stringifies via ``str(value)`` first; ``None`` is rendered as the
    empty string so callers can interpolate optional fields without
    a guard.

    Pass ``quote=True`` for values embedded inside an attribute (so
    quote characters can't break out of the attribute value). Element
    bodies use the default ``quote=False`` — slightly faster, and
    quote escaping is unnecessary there.

    Mirrors the 7 byte-identical local ``_esc`` helpers it replaces.
    """
    if value is None:
        return ""
    return _html.escape(str(value), quote=quote)
