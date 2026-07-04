"""Sprite-sheet delivery for the icon registry (stdlib only).

The same registry that renders inline SVG also emits one ``<symbol>`` sheet.
A ``<use href="#name">`` reference then resolves *same-document* — which
renders on ``file://`` and on Pages alike (only *external-file*
``<use href="sheet.svg#name">`` breaks under ``file://``). Sprite delivery
is the SVG-native way to get short, legible markup for a repeated icon
without an icon font: inspectable DOM, ``currentColor``, no FOUT, no build.

Both forms come from the one registry, so the inline and sprite renderings
can never disagree.
"""


def build_symbol_sheet(icons: dict[str, str]) -> str:
    """One hidden ``<svg>`` carrying a ``<symbol>`` per registry icon.

    Inline this once per page; every ``sprite_use_html`` reference below
    resolves against it. Stroke defaults live on the sheet so a ``<use>``
    inherits them; ``currentColor`` still flows from the referencing element.
    """
    # Symbol ids are namespaced `i-<name>` so they can never collide with a
    # page element id (e.g. a gallery section id="menu" vs the `menu` icon) —
    # duplicate ids are invalid HTML. The `i-` prefix carries no `dz-`, so the
    # namespace transform leaves both the sheet and the <use> refs untouched.
    symbols = "".join(
        f'<symbol id="i-{name}" viewBox="0 0 24 24">{inner}</symbol>'
        for name, inner in sorted(icons.items())
    )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" style="display:none" '
        'fill="none" stroke="currentColor" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{symbols}</svg>\n'
    )


def sprite_use_html(name: str, *, cls: str = "icon") -> str:
    """Short decorative ``<use>`` reference to a symbol in the sheet.

    Pairs with :func:`build_symbol_sheet`. Decorative (``aria-hidden``) — HM
    icons are always accompanied by text, and the sheet must be present on
    the page for this to render.
    """
    return f'<svg class="{cls}" aria-hidden="true"><use href="#i-{name}"/></svg>'
