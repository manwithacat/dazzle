"""Typed Fragment renderer for guide steps (v0.71.4).

Pure HTML emission — each builder is a ``GuideStep -> str`` function.
The renderer doesn't fetch state, doesn't compose with surfaces, and
doesn't know about routing; that's the caller's job (the page-routes
wiring computes the active step + state then hands the result here).

v0.71.4 ships five kinds: ``popover``, ``spotlight``, ``inline_card``,
``empty_state``, ``banner``. Remaining kinds (``checklist_item``,
``blocking_task``, ``nudge``) are deferred — they have additional
runtime semantics (checklists need a parent component; blocking_task
needs a focus trap; nudge auto-dismisses on a timer) that warrant
their own slice.

Every step kind emits the same outer ``<dz-onboarding-step>`` custom
element with ``data-guide``/``data-step``/``data-kind``/``data-placement``
attributes — client CSS/JS scope to it. Both the CTA (when present)
and the dismiss button carry htmx hooks pointing at the routes
shipped in v0.71.2:

- ``POST /api/onboarding/<guide>/<step>/complete`` — marks the step
  completed; ``hx-swap=outerHTML`` removes the overlay from the DOM.
- ``POST /api/onboarding/<guide>/<step>/dismiss`` — same shape but
  records dismissal instead.

Card-safety invariants (per docs/reference/card-safety-invariants.md):
overlays carry their own chrome + title. The ``<dz-onboarding-step>``
wrapper keeps CSS specificity local so dropping an overlay into any
page is composition-safe.
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


# Step kinds with a builder shipped in this version. ``has_builder``
# is the stable predicate callers should use to pre-check.
_SUPPORTED_KINDS: frozenset[str] = frozenset(
    {"popover", "spotlight", "inline_card", "empty_state", "banner"}
)


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
    if kind == "spotlight":
        return _build_spotlight_step(step, guide_name=guide_name)
    if kind == "inline_card":
        return _build_inline_card_step(step, guide_name=guide_name)
    if kind == "empty_state":
        return _build_empty_state_step(step, guide_name=guide_name)
    if kind == "banner":
        return _build_banner_step(step, guide_name=guide_name)
    raise UnknownStepKindError(
        f"No renderer for guide step kind {kind!r}; supported in this "
        f"version: {sorted(_SUPPORTED_KINDS)}"
    )


# ---------------------------------------------------------------------------
# Shared helpers — every kind uses the same outer element + htmx hooks
# ---------------------------------------------------------------------------


def _outer_attrs(step: ir.GuideStep, *, guide_name: str, kind: str, css_class: str) -> str:
    """Build the ``<dz-onboarding-step …>`` attribute string.

    Shared so adding a new kind doesn't drift the data-* names. Single
    source of truth for how guides + steps map to DOM attributes.
    """
    return (
        f' class="{css_class}"'
        f' data-guide="{_html.escape(guide_name, quote=True)}"'
        f' data-step="{_html.escape(step.name, quote=True)}"'
        f' data-kind="{kind}"'
        f' data-placement="{_html.escape(step.placement or "bottom", quote=True)}"'
    )


def _hx_urls(step: ir.GuideStep, *, guide_name: str) -> tuple[str, str]:
    """Return ``(complete_url, dismiss_url)`` for htmx hooks."""
    guide_attr = _html.escape(guide_name, quote=True)
    step_attr = _html.escape(step.name, quote=True)
    return (
        f"/api/onboarding/{guide_attr}/{step_attr}/complete",
        f"/api/onboarding/{guide_attr}/{step_attr}/dismiss",
    )


def _dismiss_button(dismiss_url: str, *, css_class: str, label: str = "&times;") -> str:
    """The shared ✕ dismiss button. ``hx-swap=outerHTML`` so the
    server's empty response removes the overlay from the DOM."""
    return (
        f'<button type="button"'
        f' class="{css_class}"'
        f' aria-label="Dismiss"'
        f' hx-post="{dismiss_url}"'
        f' hx-target="closest dz-onboarding-step"'
        f' hx-swap="outerHTML">{label}</button>'
    )


def _cta_anchor(
    step: ir.GuideStep, *, complete_url: str, css_class: str, default_label: str = "Got it"
) -> str:
    """Shared CTA anchor. Posts to ``/complete`` via htmx; navigates to
    ``cta_target`` when set so the user lands on the next surface."""
    label = _html.escape(step.cta_label or default_label, quote=False)
    href = (
        f' href="/{_html.escape(step.cta_target.removeprefix("surface."), quote=True)}"'
        if step.cta_target
        else ""
    )
    return (
        f"<a"
        f' class="{css_class}"'
        f"{href}"
        f' hx-post="{complete_url}"'
        f' hx-target="closest dz-onboarding-step"'
        f' hx-swap="outerHTML"'
        f' data-complete-url="{complete_url}">{label}</a>'
    )


# ---------------------------------------------------------------------------
# Individual builders
# ---------------------------------------------------------------------------


def _build_popover_step(step: ir.GuideStep, *, guide_name: str) -> str:
    """``kind: popover`` — floating overlay anchored against a target element."""
    title = _html.escape(step.title or "", quote=False)
    body = _html.escape(step.body or "", quote=False)
    complete_url, dismiss_url = _hx_urls(step, guide_name=guide_name)
    return (
        f"<dz-onboarding-step{_outer_attrs(step, guide_name=guide_name, kind='popover', css_class='dz-onboarding-popover')}>"
        f'<div class="dz-onboarding-popover__chrome">'
        f'<h3 class="dz-onboarding-popover__title">{title}</h3>'
        f"{_dismiss_button(dismiss_url, css_class='dz-onboarding-popover__dismiss')}"
        f"</div>"
        f'<p class="dz-onboarding-popover__body">{body}</p>'
        f'<div class="dz-onboarding-popover__actions">'
        f"{_cta_anchor(step, complete_url=complete_url, css_class='dz-onboarding-popover__cta')}"
        f"</div>"
        f"</dz-onboarding-step>"
    )


def _build_spotlight_step(step: ir.GuideStep, *, guide_name: str) -> str:
    """``kind: spotlight`` — dims the page + halos the target element.

    Two visual layers:
    - Full-viewport backdrop that scrims everything outside the spotlight.
    - Highlight ring positioned around the target element (client JS
      reads ``data-step`` + the target attached via the surface element
      to compute coords; v0.71.4 ships a fallback centred ring via CSS).

    The callout card sits adjacent to the spotlight with title/body/CTA.
    """
    title = _html.escape(step.title or "", quote=False)
    body = _html.escape(step.body or "", quote=False)
    complete_url, dismiss_url = _hx_urls(step, guide_name=guide_name)
    return (
        f"<dz-onboarding-step{_outer_attrs(step, guide_name=guide_name, kind='spotlight', css_class='dz-onboarding-spotlight')}>"
        f'<div class="dz-onboarding-spotlight__backdrop" aria-hidden="true"></div>'
        f'<div class="dz-onboarding-spotlight__ring" aria-hidden="true"></div>'
        f'<div class="dz-onboarding-spotlight__card" role="dialog" aria-labelledby="dz-spot-title-{_html.escape(step.name, quote=True)}">'
        f'<h3 id="dz-spot-title-{_html.escape(step.name, quote=True)}"'
        f' class="dz-onboarding-spotlight__title">{title}</h3>'
        f"{_dismiss_button(dismiss_url, css_class='dz-onboarding-spotlight__dismiss')}"
        f'<p class="dz-onboarding-spotlight__body">{body}</p>'
        f"{_cta_anchor(step, complete_url=complete_url, css_class='dz-onboarding-spotlight__cta')}"
        f"</div>"
        f"</dz-onboarding-step>"
    )


def _build_inline_card_step(step: ir.GuideStep, *, guide_name: str) -> str:
    """``kind: inline_card`` — solid card embedded in the page flow.

    Not a floating overlay — sits in the document flow above the
    surface body. Page content below scrolls underneath if the card
    is tall. Designed for contextual guidance that doesn't need to
    grab full attention.
    """
    title = _html.escape(step.title or "", quote=False)
    body = _html.escape(step.body or "", quote=False)
    complete_url, dismiss_url = _hx_urls(step, guide_name=guide_name)
    return (
        f"<dz-onboarding-step{_outer_attrs(step, guide_name=guide_name, kind='inline_card', css_class='dz-onboarding-inline-card')}>"
        f'<div class="dz-onboarding-inline-card__chrome">'
        f'<h3 class="dz-onboarding-inline-card__title">{title}</h3>'
        f"{_dismiss_button(dismiss_url, css_class='dz-onboarding-inline-card__dismiss')}"
        f"</div>"
        f'<p class="dz-onboarding-inline-card__body">{body}</p>'
        f'<div class="dz-onboarding-inline-card__actions">'
        f"{_cta_anchor(step, complete_url=complete_url, css_class='dz-onboarding-inline-card__cta')}"
        f"</div>"
        f"</dz-onboarding-step>"
    )


def _build_empty_state_step(step: ir.GuideStep, *, guide_name: str) -> str:
    """``kind: empty_state`` — large-format prompt for empty list/region.

    Higher visual weight than inline_card. Designed to fill the screen
    space normally occupied by a list when that list is empty (zero
    Tasks, zero Workspaces, etc.). Title uses ``<h2>`` because it's
    the dominant element on the page. Includes a Skip button alongside
    the dismiss for explicit user agency.
    """
    title = _html.escape(step.title or "", quote=False)
    body = _html.escape(step.body or "", quote=False)
    complete_url, dismiss_url = _hx_urls(step, guide_name=guide_name)
    return (
        f"<dz-onboarding-step{_outer_attrs(step, guide_name=guide_name, kind='empty_state', css_class='dz-onboarding-empty-state')}>"
        f'<div class="dz-onboarding-empty-state__icon" aria-hidden="true"></div>'
        f'<h2 class="dz-onboarding-empty-state__title">{title}</h2>'
        f'<p class="dz-onboarding-empty-state__body">{body}</p>'
        f'<div class="dz-onboarding-empty-state__actions">'
        f"{_cta_anchor(step, complete_url=complete_url, css_class='dz-onboarding-empty-state__cta')}"
        # Empty-state gets a labelled Skip rather than a bare ✕ — the
        # surface IS empty, so dismiss is the explicit decline.
        f"{_dismiss_button(dismiss_url, css_class='dz-onboarding-empty-state__dismiss', label='Skip')}"
        f"</div>"
        f"</dz-onboarding-step>"
    )


def _build_banner_step(step: ir.GuideStep, *, guide_name: str) -> str:
    """``kind: banner`` — full-width strip across the top of the page.

    Persistent until dismissed. Title + body share a single line in
    bold-prefix form ("**Title** — body text") to keep the strip
    compact. CTA + dismiss live at the right edge.
    """
    title = _html.escape(step.title or "", quote=False)
    body = _html.escape(step.body or "", quote=False)
    complete_url, dismiss_url = _hx_urls(step, guide_name=guide_name)
    return (
        f"<dz-onboarding-step{_outer_attrs(step, guide_name=guide_name, kind='banner', css_class='dz-onboarding-banner')}>"
        f'<div class="dz-onboarding-banner__message">'
        f'<strong class="dz-onboarding-banner__title">{title}</strong>'
        f'<span class="dz-onboarding-banner__separator" aria-hidden="true"> — </span>'
        f'<span class="dz-onboarding-banner__body">{body}</span>'
        f"</div>"
        f'<div class="dz-onboarding-banner__actions">'
        f"{_cta_anchor(step, complete_url=complete_url, css_class='dz-onboarding-banner__cta')}"
        f"{_dismiss_button(dismiss_url, css_class='dz-onboarding-banner__dismiss')}"
        f"</div>"
        f"</dz-onboarding-step>"
    )
