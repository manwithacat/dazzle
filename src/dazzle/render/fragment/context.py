"""RenderContext — carries tokens and helpers through the render pass.

Tokens flow via this context rather than as constructor args on every
primitive. Per-instance overrides remain possible (a primitive's own
`tokens` field, when present, takes precedence over the context's).
"""

import html
from dataclasses import dataclass, field

from dazzle.render.fragment.tokens import Tokens


@dataclass
class RenderContext:
    """Mutable context threaded through the renderer.

    Not frozen — the renderer may replace `tokens` when descending into a
    primitive that overrides them. Frozen-ness is a property of Fragments,
    not the rendering machinery.
    """

    tokens: Tokens = field(default_factory=Tokens)

    def escape(self, text: str) -> str:
        """HTML-escape text content (between tags). Does NOT escape quotes —
        use `escape_attr` for content that goes inside an attribute value.

        Wraps stdlib `html.escape` so any future changes (e.g. additional
        text-context rules) live in one place.
        """
        return html.escape(text, quote=False)

    def escape_attr(self, text: str) -> str:
        """HTML-escape text destined for an attribute value (escapes quotes
        in addition to `&<>`). Use this when emitting attribute strings to
        prevent breaking out of the attribute context."""
        return html.escape(text, quote=True)
