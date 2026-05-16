"""Tests for the guide-step renderer (v0.71.2)."""

from __future__ import annotations

import pytest

from dazzle.back.runtime.onboarding.renderer import (
    UnknownStepKindError,
    has_builder,
    render_step,
)
from dazzle.core import ir


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


def test_has_builder_reports_popover_supported() -> None:
    assert has_builder("popover") is True


@pytest.mark.parametrize(
    "kind", ["spotlight", "inline_card", "empty_state", "banner", "checklist_item"]
)
def test_has_builder_reports_other_kinds_not_yet_supported(kind: str) -> None:
    """All non-popover kinds are deferred to v0.71.3+ — keep the
    failure mode of ``render_step`` predictable."""
    assert has_builder(kind) is False


def test_render_step_unknown_kind_raises_with_helpful_message() -> None:
    step = _step(kind=ir.GuideStepKind.SPOTLIGHT)
    with pytest.raises(UnknownStepKindError) as exc:
        render_step(step, guide_name="g1")
    assert "spotlight" in str(exc.value)
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
