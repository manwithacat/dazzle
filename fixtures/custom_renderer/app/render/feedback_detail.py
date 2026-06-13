"""Worked example — a per-entity *detail viewer* custom renderer (#1297).

This is the modern, supported replacement for the (removed, ADR-0023)
Jinja `components/detail_view.html` override that downstream projects
used to route specific entities to bespoke detail viewers:

    {# dazzle:override components/detail_view.html #}      <-- gone
    {% if detail.entity_name == "Manuscript" %}
      {% include "components/manuscript_viewer.html" %}
    {% else %}
      {% include "dz://components/detail_view.html" %}      <-- fall-through
    {% endif %}

The new shape is **per-surface**, not one god-file branching on
`entity_name`: declare `render: feedback_detail` on the entity's VIEW
surface (see `dsl/app.dsl`) and register a handler. The renderer
receives the same flat detail ctx the built-in fragment adapter gets,
*plus* `ctx["detail_context"]` — the original `DetailContext` — so it
can delegate to the generic detail rendering and then wrap/append its
own chrome. That delegation is the direct analogue of the old
`{% include "dz://components/detail_view.html" %}` fall-through.

Registration happens in this directory's ``register_all`` (see
``app/render/__init__.py``) — call it once at app boot.
"""

from __future__ import annotations

import html as _html
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dazzle.back.runtime.services import RuntimeServices
    from dazzle.core.ir.protocols import SurfaceLike

# Sentiment → (label, accent colour) for the bespoke banner this viewer
# adds above the standard field layout. A real per-entity viewer would
# render a domain widget here (AegisMark: a per-AO marks grid); we keep
# the example focused on the *delegation* mechanics.
_SENTIMENT_ACCENT = {
    "positive": ("Positive", "#16a34a"),
    "neutral": ("Neutral", "#6b7280"),
    "negative": ("Negative", "#dc2626"),
}


class FeedbackDetailRenderer:
    """Per-entity detail viewer for Feedback.

    Demonstrates the canonical #1297 pattern:

    1. Render a bespoke header/banner for this specific entity.
    2. **Delegate** to the framework's generic detail rendering via
       ``render_detail_view(ctx["detail_context"])`` — no need to
       re-implement the field-section layout, related-record tables,
       transition buttons, etc.
    3. Compose: bespoke chrome + generic body.

    Because the delegation is lazy (the generic HTML is only produced
    when this renderer asks for it), a viewer that *fully* replaces the
    standard layout simply never calls ``render_detail_view`` — it costs
    nothing.
    """

    def render(self, surface: SurfaceLike, ctx: dict[str, Any]) -> str:
        # The original DetailContext, threaded through by
        # `_build_dispatch_ctx` for VIEW-mode `render:` surfaces (#1297).
        detail = ctx.get("detail_context")

        # Bespoke banner derived from this entity's own data.
        item = getattr(detail, "item", {}) if detail is not None else {}
        sentiment = str((item or {}).get("sentiment", "neutral"))
        label, accent = _SENTIMENT_ACCENT.get(sentiment, _SENTIMENT_ACCENT["neutral"])
        # Escape every value interpolated into HTML — even `accent`, which
        # is a trusted hex literal from the static dict above. A worked
        # example should model the always-escape habit so a future editor
        # who adds a dict value can't silently introduce an injection.
        accent_attr = _html.escape(accent, quote=True)
        banner = (
            '<div class="dz-feedback-sentiment-banner" '
            f'style="border-left:4px solid {accent_attr};padding:0.5rem 0.75rem;'
            'margin-bottom:1rem;background:var(--dz-surface-2,#f8fafc);">'
            f'<strong style="color:{accent_attr};">Sentiment: {_html.escape(label)}</strong>'
            "</div>"
        )

        # Delegate the standard body to the framework — the modern
        # `{% include "dz://components/detail_view.html" %}` fall-through.
        if detail is None:
            generic_body = '<p class="dz-empty">No detail context available.</p>'  # defensive
        else:
            from dazzle.ui.runtime import render_detail_view

            generic_body = render_detail_view(detail)

        return (
            '<section class="dz-section dz-section-feedback-detail">'
            f"{banner}{generic_body}"
            "</section>"
        )


def register_with_app(services: RuntimeServices) -> None:
    """Register the Feedback detail viewer under the name `feedback_detail`.

    The name must match the surface's `render: feedback_detail` clause
    (DSL) and the `[renderers] extra` allowlist (dazzle.toml). See this
    directory's README for the full two-halves-of-the-contract recipe.
    """
    services.renderer_registry.register(
        name="feedback_detail",
        handler=FeedbackDetailRenderer(),
    )
