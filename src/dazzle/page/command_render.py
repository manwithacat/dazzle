"""Render command-palette markup from a CommandEntry list.

``render_command_results`` renders the swap-target body (grouped items or
empty state) returned by the ``/app/command`` hx-get endpoint. The dialog
SHELL is emitted by the render layer (``_render_shell``) so this page-layer
module stays results-only.

Server-rendered, no client templating — the palette is hypermedia.
"""

from __future__ import annotations

from dazzle.page.command_index import CommandEntry
from dazzle.render.fragment.icon_html import lucide_icon_html
from dazzle.render.html import esc

__all__ = ["render_command_results"]


def render_command_results(entries: list[CommandEntry]) -> str:
    """Grouped ``.dz-command__item`` anchors, or the empty state."""
    if not entries:
        return '<div class="dz-command__empty">No matching destinations.</div>'

    parts: list[str] = []
    current_group = ""
    for e in entries:
        if e.group != current_group:
            current_group = e.group
            parts.append(f'<div class="dz-command__group">{esc(e.group)}</div>')
        icon = lucide_icon_html(e.icon, cls="dz-icon dz-icon--size-sm")
        # hx-boost lets the anchor navigate via htmx (boosted) while staying a
        # real link — keyboard Enter and click both work, and it degrades to a
        # plain navigation with JS off.
        parts.append(
            f'<a class="dz-command__item" href="{esc(e.url, quote=True)}" hx-boost="true" role="option">'
            f"{icon}<span>{esc(e.label)}</span></a>"
        )
    return "".join(parts)
