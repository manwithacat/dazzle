"""Server-side Lucide icon rendering (HaTchi-MaXchi TASTE-6).

Known names render as inline SVG from the vendored registry — no JS, no
flash of missing icons, works with scripting disabled. Unknown names fall
back to the pre-Phase-2 ``data-lucide`` span so the vendored client UMD
bundle hydrates them; the registry grows deliberately via
``packages/hatchi-maxchi/icons/gen_registry.py``.
"""

import html as _html

from dazzle.render.fragment.icon_registry import ICONS

__all__ = ["lucide_icon_html", "lucide_svg_html"]

_SVG_SHELL = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
    'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
    'stroke-linejoin="round">{inner}</svg>'
)


def _a11y_attrs(label: str | None) -> str:
    """Decorative by default (``aria-hidden``); *label* exposes an accessible
    name (``role=img``) for the genuinely icon-only case."""
    if label is None:
        return ' aria-hidden="true"'
    return f' role="img" aria-label="{_html.escape(label, quote=True)}"'


def lucide_svg_html(
    name: str, *, cls: str, fallback: str = "inbox", label: str | None = None
) -> str:
    """Bare ``<svg class=cls>`` for a REGISTRY name (no span wrapper).

    For seams whose CSS styles the ``<svg>`` element directly (e.g. the
    empty-state icon). Unknown names silently use *fallback* — both are
    framework-chosen constants here, never author input. Decorative by
    default; pass *label* to expose an accessible name (``role=img``).
    """
    inner = ICONS.get(name) or ICONS[fallback]
    cls_attr = f' class="{cls}"' if cls else ""
    return (
        f'<svg{cls_attr} xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        f'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        f'stroke-linejoin="round"{_a11y_attrs(label)}>{inner}</svg>'
    )


def lucide_icon_html(name: str, *, cls: str, label: str | None = None) -> str:
    """Render icon *name* inside a ``<span class=cls>`` wrapper.

    Registry hit → inline SVG (stroke follows ``currentColor``).
    Miss → ``data-lucide`` span, byte-identical to the legacy client path.
    Decorative by default; pass *label* to expose an accessible name.
    """
    inner = ICONS.get(name)
    a11y = _a11y_attrs(label)
    if inner is not None:
        return f'<span class="{cls}"{a11y}>{_SVG_SHELL.format(inner=inner)}</span>'
    return f'<span class="{cls}" data-lucide="{_html.escape(name, quote=True)}"{a11y}></span>'
