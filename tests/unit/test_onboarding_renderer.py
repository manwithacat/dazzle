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


@pytest.mark.parametrize(
    "kind",
    [
        "popover",
        "spotlight",
        "inline_card",
        "empty_state",
        "banner",
        "checklist_item",
        "blocking_task",
        "nudge",
    ],
)
def test_has_builder_reports_all_v0_71_5_kinds_supported(kind: str) -> None:
    """v0.71.5 ships builders for all eight defined step kinds."""
    assert has_builder(kind) is True


def test_render_step_unknown_kind_raises_with_helpful_message() -> None:
    """A future Dazzle release might add a new IR kind; an older
    runtime should raise with the supported list in the message rather
    than silently render nothing. Simulate via a SimpleNamespace that
    bypasses the IR enum."""
    from types import SimpleNamespace

    step = SimpleNamespace(
        kind=SimpleNamespace(value="future_kind"),
        name="s1",
        title="",
        body="",
        target="surface.task_list",
        placement="bottom",
        cta_label=None,
        cta_target=None,
    )
    with pytest.raises(UnknownStepKindError) as exc:
        render_step(step, guide_name="g1")
    assert "future_kind" in str(exc.value)
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


# CTA label resolution is one contract across kinds: an explicit
# ``cta_label`` wins; otherwise each kind supplies its own action prompt
# (popover "Got it"; checklist "Do this" — action-oriented; blocking_task
# "Continue"; nudge "OK").
@pytest.mark.parametrize(
    ("kind", "cta_label", "expected"),
    [
        pytest.param(ir.GuideStepKind.POPOVER, None, "Got it", id="popover-default-got-it"),
        pytest.param(
            ir.GuideStepKind.POPOVER, "New Task", "New Task", id="popover-custom-label-wins"
        ),
        pytest.param(
            ir.GuideStepKind.CHECKLIST_ITEM,
            None,
            "Do this",
            id="checklist-item-default-do-this",
        ),
        pytest.param(
            ir.GuideStepKind.BLOCKING_TASK, None, "Continue", id="blocking-task-default-continue"
        ),
        pytest.param(ir.GuideStepKind.NUDGE, None, "OK", id="nudge-default-ok"),
    ],
)
def test_cta_label_resolution(kind: ir.GuideStepKind, cta_label: str | None, expected: str) -> None:
    html = render_step(_step(kind=kind, cta_label=cta_label), guide_name="g1")
    assert f">{expected}</a>" in html


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


_ALL_SUPPORTED_KINDS = [
    ir.GuideStepKind.POPOVER,
    ir.GuideStepKind.SPOTLIGHT,
    ir.GuideStepKind.INLINE_CARD,
    ir.GuideStepKind.EMPTY_STATE,
    ir.GuideStepKind.BANNER,
    ir.GuideStepKind.CHECKLIST_ITEM,
    ir.GuideStepKind.BLOCKING_TASK,
    ir.GuideStepKind.NUDGE,
]


@pytest.mark.parametrize("kind", _ALL_SUPPORTED_KINDS)
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


@pytest.mark.parametrize("kind", _ALL_SUPPORTED_KINDS)
def test_every_supported_kind_emits_htmx_complete(kind: ir.GuideStepKind) -> None:
    """Every kind has a CTA that posts to the complete route — that's
    the runtime contract for progression."""
    step = _step(kind=kind)
    html = render_step(step, guide_name="g1")
    assert 'hx-post="/api/onboarding/g1/s1/complete"' in html


# blocking_task is the only kind WITHOUT a dismiss button by design —
# users can't dismiss a blocking task, only complete it. Every other
# kind has both a complete CTA and a dismiss escape hatch.
_DISMISSABLE_KINDS = [k for k in _ALL_SUPPORTED_KINDS if k != ir.GuideStepKind.BLOCKING_TASK]


@pytest.mark.parametrize("kind", _DISMISSABLE_KINDS)
def test_every_dismissable_kind_emits_htmx_dismiss(kind: ir.GuideStepKind) -> None:
    step = _step(kind=kind)
    html = render_step(step, guide_name="g1")
    assert 'hx-post="/api/onboarding/g1/s1/dismiss"' in html


def test_blocking_task_has_no_dismiss_button() -> None:
    """blocking_task is designed to NOT be dismissable — the only way
    past is the CTA. Apps that need an escape hatch should declare a
    popover or inline_card instead."""
    step = _step(kind=ir.GuideStepKind.BLOCKING_TASK)
    html = render_step(step, guide_name="g1")
    assert "/dismiss" not in html


@pytest.mark.parametrize("kind", _ALL_SUPPORTED_KINDS)
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


def test_checklist_item_has_listitem_role_and_indicator() -> None:
    """A checklist_item renders as a list row with a checkbox-shaped
    indicator on the left + content in the middle + CTA on the right."""
    html = render_step(_step(kind=ir.GuideStepKind.CHECKLIST_ITEM), guide_name="g1")
    assert 'role="listitem"' in html
    assert 'aria-checked="false"' in html
    assert "dz-onboarding-checklist-item__indicator" in html
    assert "dz-onboarding-checklist-item__content" in html


def test_checklist_item_dismiss_hidden_by_default() -> None:
    """checklist items hide individual-item dismissal by default; the
    parent guide owns the dismiss escape hatch."""
    html = render_step(_step(kind=ir.GuideStepKind.CHECKLIST_ITEM), guide_name="g1")
    assert "dz-onboarding-checklist-item__dismiss--hidden" in html


def test_blocking_task_uses_native_dialog_element() -> None:
    """blocking_task uses <dialog open> so browsers provide focus
    trap + Escape handling natively, without client JS."""
    html = render_step(_step(kind=ir.GuideStepKind.BLOCKING_TASK), guide_name="g1")
    assert "<dialog open" in html
    assert 'aria-modal="true"' in html
    assert 'aria-labelledby="dz-blocking-title-s1"' in html
    # Backdrop renders as a separate layer for browsers that don't
    # implement the ::backdrop pseudo-element.
    assert "dz-onboarding-blocking-task__backdrop" in html


def test_nudge_carries_autodismiss_data_attr() -> None:
    """nudge advertises its auto-dismiss timer via data attribute so
    client JS can fire the dismiss POST after the delay."""
    html = render_step(_step(kind=ir.GuideStepKind.NUDGE), guide_name="g1")
    assert 'data-autodismiss-ms="6000"' in html  # default
    # Toast semantics for screen readers.
    assert 'role="status"' in html
    assert 'aria-live="polite"' in html


def test_nudge_autodismiss_ms_pulled_from_placement_when_numeric() -> None:
    """A nudge with ``placement: "3000"`` should auto-dismiss in 3s."""
    step = _step(kind=ir.GuideStepKind.NUDGE, placement="3000")
    html = render_step(step, guide_name="g1")
    assert 'data-autodismiss-ms="3000"' in html


def test_nudge_autodismiss_falls_back_when_placement_invalid() -> None:
    """Non-numeric / zero / negative placement falls back to the
    default — protects against pathological values that fire instantly."""
    for placement in ["nonsense", "0", "-100", ""]:
        step = _step(kind=ir.GuideStepKind.NUDGE, placement=placement)
        html = render_step(step, guide_name="g1")
        assert 'data-autodismiss-ms="6000"' in html, (
            f"placement={placement!r} should fall back to default"
        )
