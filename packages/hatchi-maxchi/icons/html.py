"""Inline-SVG rendering helpers over the registry (stdlib only).

The HM-side twins of Dazzle's ``render/fragment/icon_html.py`` — kept
tiny and dependency-free so the gallery builds in the standalone repo.
Unknown names: ``lucide_icon_html`` falls back to a ``data-lucide`` span
(client hydration); ``lucide_svg_html`` silently uses *fallback* (both
arguments are author-chosen constants here, never user input).
"""

import html as _html

from .registry import ICONS

_SVG_SHELL = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
    'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
    'stroke-linejoin="round">{inner}</svg>'
)


def lucide_icon_html(name: str, *, cls: str) -> str:
    """Icon *name* inside a ``<span class=cls>`` wrapper."""
    inner = ICONS.get(name)
    if inner is not None:
        return f'<span class="{cls}" aria-hidden="true">{_SVG_SHELL.format(inner=inner)}</span>'
    return (
        f'<span class="{cls}" data-lucide="{_html.escape(name, quote=True)}" '
        f'aria-hidden="true"></span>'
    )


def lucide_svg_html(name: str, *, cls: str, fallback: str = "inbox") -> str:
    """Bare ``<svg>`` for a registry name — for slots whose CSS styles the
    ``svg`` element directly (badge, alert, empty-state icon boxes)."""
    inner = ICONS.get(name) or ICONS[fallback]
    cls_attr = f' class="{cls}"' if cls else ""
    return (
        f'<svg{cls_attr} xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        f'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        f'stroke-linejoin="round" aria-hidden="true">{inner}</svg>'
    )
