"""Typed Fragment renderer for guide steps (v0.71.2).

Pure HTML emission — each builder is a ``GuideStep -> str`` function.
The renderer doesn't fetch state, doesn't compose with surfaces, and
doesn't know about routing; that's the caller's job (the v0.71.3
page-routes wiring computes the active step + state then hands the
result here for HTML).

Only the ``popover`` step kind has a builder in v0.71.2. Other kinds
(spotlight, inline_card, empty_state, banner, checklist_item) get
their builders in v0.71.3+ — same dispatcher shape so adding one is
purely additive.

The popover HTML carries htmx hooks for completion + dismissal:

- ``POST /api/onboarding/<guide>/<step>/complete`` — fires on the
  primary CTA click. The step is marked completed; the popover is
  swapped out via ``hx-swap=outerHTML`` returning empty content.
- ``POST /api/onboarding/<guide>/<step>/dismiss`` — same shape but
  marks the step dismissed instead. Used by the ✕ button.

Both endpoints live in ``onboarding/routes.py``; the renderer just
points hx-post at them.

Card-safety invariants (per docs/reference/card-safety-invariants.md):
the popover emits zero chrome and zero title at the region level —
the overlay primitive carries its own visual treatment. Renders to
a self-contained ``<dz-onboarding-step>`` custom element so CSS
specificity stays local.
"""

from __future__ import annotations

import html as _html
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dazzle.core import ir


class UnknownStepKindError(ValueError):
    """``render_step`` was handed a kind no builder is registered for.

    Raised rather than silently returning empty HTML — callers should
    check ``has_builder`` first when they're rendering a kind that may
    not be supported yet in the current Dazzle version.
    """


# Step kinds with a builder shipped in this version. v0.71.2 ships
# popover only; v0.71.3+ adds the others. ``has_builder`` is the
# stable predicate callers should use.
_SUPPORTED_KINDS: frozenset[str] = frozenset({"popover"})


def has_builder(kind: str) -> bool:
    """Return True iff ``render_step`` can handle ``kind``."""
    return kind in _SUPPORTED_KINDS


def render_step(step: ir.GuideStep, *, guide_name: str) -> str:
    """Dispatch to the right builder for a guide step.

    ``guide_name`` is threaded explicitly rather than read off a parent
    object because steps don't carry back-references to their guide;
    the htmx complete/dismiss URLs need it.

    Raises :class:`UnknownStepKindError` when ``step.kind`` isn't yet
    supported by this Dazzle version — caller should pre-filter via
    :func:`has_builder` when handling user-authored content.
    """
    kind = step.kind.value if hasattr(step.kind, "value") else str(step.kind)
    if kind == "popover":
        return _build_popover_step(step, guide_name=guide_name)
    raise UnknownStepKindError(
        f"No renderer for guide step kind {kind!r}; supported in this "
        f"version: {sorted(_SUPPORTED_KINDS)}"
    )


# ---------------------------------------------------------------------------
# Popover builder
# ---------------------------------------------------------------------------


def _build_popover_step(step: ir.GuideStep, *, guide_name: str) -> str:
    """Emit the HTML for a ``kind: popover`` step.

    Composition:

    - Outer ``<dz-onboarding-step>`` carries ``data-guide`` +
      ``data-step`` so client JS (v0.71.3) and CSS can scope to it.
    - ``data-placement`` mirrors the DSL setting; the v0.71.3 Alpine
      controller reads this to position the popover against its
      target element. v0.71.2 uses a fallback bottom-of-page slot via
      CSS — sufficient to verify end-to-end behaviour even before the
      positioning JS ships.
    - Title + body get HTML-escaped.
    - Two htmx-backed buttons: a primary CTA that posts to the
      ``/complete`` endpoint, and a ✕ dismiss button that posts to
      ``/dismiss``. Both use ``hx-target=closest dz-onboarding-step``
      + ``hx-swap=outerHTML`` so the response (empty body) removes the
      overlay from the DOM.
    """
    guide_attr = _html.escape(guide_name, quote=True)
    step_attr = _html.escape(step.name, quote=True)
    placement_attr = _html.escape(step.placement or "bottom", quote=True)
    title = _html.escape(step.title or "", quote=False)
    body = _html.escape(step.body or "", quote=False)
    cta_label = _html.escape(step.cta_label or "Got it", quote=False)

    # CTA href takes precedence over the htmx complete-post if the DSL
    # sets cta_target — pointing the user at a real surface is the
    # designed-for next action; the complete event fires server-side
    # via the cta_target page-load (page_routes.py wiring in v0.71.3
    # will emit the completion event when the target surface loads).
    cta_href = (
        f' href="/{_html.escape(step.cta_target.removeprefix("surface."), quote=True)}"'
        if step.cta_target
        else ""
    )
    cta_extra = (
        # If we have an explicit CTA href, click goes there; mark the
        # step complete via htmx before the navigation by adding
        # hx-post + hx-trigger=click.
        f' hx-post="/api/onboarding/{guide_attr}/{step_attr}/complete"'
        f' hx-target="closest dz-onboarding-step"'
        f' hx-swap="outerHTML"'
    )

    complete_url = f"/api/onboarding/{guide_attr}/{step_attr}/complete"
    dismiss_url = f"/api/onboarding/{guide_attr}/{step_attr}/dismiss"

    return (
        f"<dz-onboarding-step"
        f' class="dz-onboarding-popover"'
        f' data-guide="{guide_attr}"'
        f' data-step="{step_attr}"'
        f' data-kind="popover"'
        f' data-placement="{placement_attr}">'
        f'<div class="dz-onboarding-popover__chrome">'
        f'<h3 class="dz-onboarding-popover__title">{title}</h3>'
        f'<button type="button"'
        f' class="dz-onboarding-popover__dismiss"'
        f' aria-label="Dismiss"'
        f' hx-post="{dismiss_url}"'
        f' hx-target="closest dz-onboarding-step"'
        f' hx-swap="outerHTML">&times;</button>'
        f"</div>"
        f'<p class="dz-onboarding-popover__body">{body}</p>'
        f'<div class="dz-onboarding-popover__actions">'
        f"<a"
        f' class="dz-onboarding-popover__cta"'
        f"{cta_href}"
        f"{cta_extra}"
        f' data-complete-url="{complete_url}">{cta_label}</a>'
        f"</div>"
        f"</dz-onboarding-step>"
    )
