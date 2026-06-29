"""ADR-0049 Phase 3a — substrate `FormStepper` parity with the legacy
`form_renderer.render_form_stepper` (wizard stage-tabs, widget 9/9).

The stepper is only rendered by the experience-flow form path
(`experience_renderer._render_form_step_body`); the main CREATE/EDIT form path
groups sections without one. This primitive is what the experience path
repoints to in Phase 3b once `form_renderer` (with `render_form_stepper`) is
deleted — so it must reproduce the dzWizard Alpine contract exactly.
"""

from __future__ import annotations

from dazzle.render.fragment import FormStepper, FragmentRenderer

_R = FragmentRenderer()


def test_stepper_renders_dzwizard_contract() -> None:
    html = _R.render(FormStepper(sections=("Basics", "Details", "Review")))
    assert '<ol class="dz-form-stepper" role="list" aria-label="Form progress">' in html
    # One item per section; Alpine click + aria-current wiring per index.
    assert html.count('class="dz-form-stepper-item') == 3
    assert '@click="goToStep(0)"' in html
    assert '@click="goToStep(2)"' in html
    assert "isCurrent(1)" in html
    # Completed-stage checkmark SVG + pending bare-index template branches.
    assert 'x-if="step > 0"' in html
    assert "M5 13l4 4L19 7" in html
    assert 'x-if="step <= 0"' in html
    # Connectors between stages (n-1 of them).
    assert html.count("dz-form-stepper-connector") == 2
    # Section titles.
    assert "Basics" in html and "Details" in html and "Review" in html


def test_single_section_has_no_connector() -> None:
    html = _R.render(FormStepper(sections=("Only",)))
    assert "dz-form-stepper-connector" not in html
    assert html.count('class="dz-form-stepper-item') == 1


# NOTE: the `def test_parity_with_legacy_stepper` legacy-vs-substrate parity test was removed in ADR-0049
# Phase 3b — `form_renderer` is deleted, so there is no legacy renderer left to
# compare against; the substrate is now the source of truth (parity is recorded
# in git history + the CHANGELOG). The substrate-only assertions above stand.
