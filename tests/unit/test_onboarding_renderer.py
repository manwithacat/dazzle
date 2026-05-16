"""Tests for the guide-step renderer (v0.71.2)."""

from __future__ import annotations

import pytest

from dazzle.core import ir
from dazzle.render.onboarding.renderer import (
    UnknownStepKindError,
    has_builder,
    render_step,
)


def _step(
    *,
    name: str = "s1",
    kind: ir.GuideStepKind = ir.GuideStepKind.POPOVER,
    title: str = "Hello",
    body: str = "World",
    target: str = "surface.task_list",
    placement: str = "bottom",
    cta_label: str | None = None,
    cta_target: str | None = None,
    complete_on: ir.GuideCompleteOn | None = None,
) -> ir.GuideStep:
    return ir.GuideStep(
        name=name,
        kind=kind,
        title=title,
        body=body,
        target=target,
        placement=placement,
        cta_label=cta_label,
        cta_target=cta_target,
        complete_on=complete_on or ir.GuideCompleteOn(kind=ir.GuideCompleteOnKind.CLICK),
    )


# ---------------------------------------------------------------------------
# Builder registry
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["popover", "spotlight", "inline_card", "empty_state", "banner"])
def test_has_builder_reports_v0_71_4_kinds_supported(kind: str) -> None:
    """v0.71.4 ships builders for these five kinds."""
    assert has_builder(kind) is True


@pytest.mark.parametrize("kind", ["checklist_item", "blocking_task", "nudge"])
def test_has_builder_reports_remaining_kinds_not_yet_supported(kind: str) -> None:
    """These three kinds have additional runtime semantics (checklists
    need a parent component; blocking_task needs a focus trap; nudge
    auto-dismisses). Deferred to a follow-up slice."""
    assert has_builder(kind) is False


def test_render_step_unknown_kind_raises_with_helpful_message() -> None:
    step = _step(kind=ir.GuideStepKind.CHECKLIST_ITEM)
    with pytest.raises(UnknownStepKindError) as exc:
        render_step(step, guide_name="g1")
    assert "checklist_item" in str(exc.value)
    assert "popover" in str(exc.value)  # lists what IS supported


# ---------------------------------------------------------------------------
# Popover HTML emission
# ---------------------------------------------------------------------------


def test_popover_renders_custom_element_with_data_attrs() -> None:
    step = _step(name="welcome", title="Welcome", body="Get started")
    html = render_step(step, guide_name="workspace_setup")
    assert "<dz-onboarding-step" in html
    assert 'data-guide="workspace_setup"' in html
    assert 'data-step="welcome"' in html
    assert 'data-kind="popover"' in html
    assert 'data-placement="bottom"' in html


def test_popover_emits_complete_and_dismiss_htmx_buttons() -> None:
    step = _step(name="s1")
    html = render_step(step, guide_name="g1")
    assert 'hx-post="/api/onboarding/g1/s1/complete"' in html
    assert 'hx-post="/api/onboarding/g1/s1/dismiss"' in html
    # Both swap outer HTML so the popover removes itself when the server
    # responds with an empty body.
    assert 'hx-target="closest dz-onboarding-step"' in html
    assert 'hx-swap="outerHTML"' in html


def test_popover_escapes_user_supplied_strings() -> None:
    """A guide author who puts ``<script>`` in title/body must NOT cause XSS.

    Both title and body are emitted into text-node positions (inside
    ``<h3>`` and ``<p>`` respectively), so `<` and `>` are the
    dangerous characters that have to escape — bare ``"`` in a text
    node is harmless.
    """
    step = _step(title="<script>alert(1)</script>", body='"><img src=x onerror=alert(1)>')
    html = render_step(step, guide_name="g1")
    # The raw script tag never lands in output.
    assert "<script>" not in html
    assert "</script>" not in html
    # Both surfaces get HTML-encoded.
    assert "&lt;script&gt;" in html
    assert "&lt;img" in html
    # And the dangerous unescaped substring from body never appears.
    assert "<img src=x" not in html


def test_popover_default_cta_label_when_unset() -> None:
    step = _step(cta_label=None)
    html = render_step(step, guide_name="g1")
    assert ">Got it</a>" in html


def test_popover_custom_cta_label_when_set() -> None:
    step = _step(cta_label="New Task")
    html = render_step(step, guide_name="g1")
    assert ">New Task</a>" in html


def test_popover_cta_href_when_target_set() -> None:
    step = _step(cta_target="surface.task_create")
    html = render_step(step, guide_name="g1")
    assert 'href="/task_create"' in html


def test_popover_no_href_when_target_absent() -> None:
    step = _step(cta_target=None)
    html = render_step(step, guide_name="g1")
    # No `href=` attribute on the CTA anchor when there's no cta_target.
    cta_chunk = html.split('class="dz-onboarding-popover__cta"')[1].split("</a>")[0]
    assert "href=" not in cta_chunk


def test_popover_placement_threads_into_data_attr() -> None:
    step = _step(placement="top")
    html = render_step(step, guide_name="g1")
    assert 'data-placement="top"' in html


# ---------------------------------------------------------------------------
# Shared invariants — every kind carries the same outer wrapper + htmx hooks
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kind",
    [
        ir.GuideStepKind.POPOVER,
        ir.GuideStepKind.SPOTLIGHT,
        ir.GuideStepKind.INLINE_CARD,
        ir.GuideStepKind.EMPTY_STATE,
        ir.GuideStepKind.BANNER,
    ],
)
def test_every_supported_kind_emits_outer_wrapper_with_data_attrs(
    kind: ir.GuideStepKind,
) -> None:
    """Outer ``<dz-onboarding-step>`` + ``data-guide``/``data-step``/
    ``data-kind`` are invariant across every kind. Client CSS/JS scope
    to these — drift breaks every overlay at once."""
    step = _step(kind=kind, title=f"{kind} title", body=f"{kind} body")
    html = render_step(step, guide_name="g1")
    assert "<dz-onboarding-step" in html
    assert 'data-guide="g1"' in html
    assert 'data-step="s1"' in html
    expected_kind = kind.value if hasattr(kind, "value") else str(kind)
    assert f'data-kind="{expected_kind}"' in html


@pytest.mark.parametrize(
    "kind",
    [
        ir.GuideStepKind.POPOVER,
        ir.GuideStepKind.SPOTLIGHT,
        ir.GuideStepKind.INLINE_CARD,
        ir.GuideStepKind.EMPTY_STATE,
        ir.GuideStepKind.BANNER,
    ],
)
def test_every_supported_kind_emits_htmx_complete_and_dismiss(
    kind: ir.GuideStepKind,
) -> None:
    """Every kind has to point at the same complete + dismiss routes
    shipped in v0.71.2 — that's the runtime contract."""
    step = _step(kind=kind)
    html = render_step(step, guide_name="g1")
    assert 'hx-post="/api/onboarding/g1/s1/complete"' in html
    assert 'hx-post="/api/onboarding/g1/s1/dismiss"' in html


@pytest.mark.parametrize(
    "kind",
    [
        ir.GuideStepKind.POPOVER,
        ir.GuideStepKind.SPOTLIGHT,
        ir.GuideStepKind.INLINE_CARD,
        ir.GuideStepKind.EMPTY_STATE,
        ir.GuideStepKind.BANNER,
    ],
)
def test_every_supported_kind_escapes_title_and_body(kind: ir.GuideStepKind) -> None:
    """XSS-escape on every kind. Common helper means it's hard to drift
    but pin it anyway — the renderer is the only XSS surface."""
    step = _step(kind=kind, title="<script>", body="<img onerror=x>")
    html = render_step(step, guide_name="g1")
    assert "<script>" not in html
    assert "<img onerror" not in html
    assert "&lt;script&gt;" in html
    assert "&lt;img onerror" in html


# ---------------------------------------------------------------------------
# Kind-specific shape (one assertion per builder so the CSS class name
# can't silently drift)
# ---------------------------------------------------------------------------


def test_spotlight_has_backdrop_and_ring_layers() -> None:
    html = render_step(_step(kind=ir.GuideStepKind.SPOTLIGHT), guide_name="g1")
    assert "dz-onboarding-spotlight__backdrop" in html
    assert "dz-onboarding-spotlight__ring" in html
    assert "dz-onboarding-spotlight__card" in html
    # Dialog role + aria-labelledby on the card so screen readers can
    # announce the step properly.
    assert 'role="dialog"' in html
    assert "aria-labelledby" in html


def test_inline_card_uses_inline_card_class() -> None:
    html = render_step(_step(kind=ir.GuideStepKind.INLINE_CARD), guide_name="g1")
    assert "dz-onboarding-inline-card" in html
    assert "dz-onboarding-inline-card__title" in html
    assert "dz-onboarding-inline-card__body" in html


def test_empty_state_uses_h2_for_higher_visual_weight() -> None:
    """Empty-state takes over the visual space normally occupied by the
    surface body, so the title gets ``<h2>`` rather than ``<h3>``."""
    html = render_step(_step(kind=ir.GuideStepKind.EMPTY_STATE), guide_name="g1")
    assert '<h2 class="dz-onboarding-empty-state__title"' in html


def test_empty_state_dismiss_button_labeled_skip() -> None:
    """The empty-state surface IS empty by definition, so the dismiss
    is an explicit Skip rather than a bare ✕."""
    html = render_step(_step(kind=ir.GuideStepKind.EMPTY_STATE), guide_name="g1")
    assert ">Skip</button>" in html


def test_banner_uses_horizontal_message_layout() -> None:
    html = render_step(_step(kind=ir.GuideStepKind.BANNER), guide_name="g1")
    assert "dz-onboarding-banner__message" in html
    assert "dz-onboarding-banner__separator" in html
    # Title is bold-prefix (strong tag) so it reads as a single-line callout.
    assert '<strong class="dz-onboarding-banner__title"' in html
