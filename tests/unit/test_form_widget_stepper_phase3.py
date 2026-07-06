"""ADR-0049 Phase 3a — substrate `FormStepper` parity with the legacy
`form_renderer.render_form_stepper` (wizard stage-tabs, widget 9/9).

The stepper is only rendered by the experience-flow form path
(`experience_renderer._render_form_step_body`); the main CREATE/EDIT form path
groups sections without one. This primitive is what the experience path
repoints to in Phase 3b once `form_renderer` (with `render_form_stepper`) is
deleted — it now carries the HM dz-wizard.js state-in-DOM contract (Tier F4d).
"""

from __future__ import annotations

from dazzle.render.fragment import FormStepper, FragmentRenderer

_R = FragmentRenderer()


def test_stepper_renders_hm_wizard_contract() -> None:
    """F4d: the stepper is state-in-DOM — each item carries
    data-dz-step-to for the delegated dz-wizard.js controller, per-item
    state rides data-dz-state="current|pending|complete" (SSR: first
    current, rest pending; the complete checkmark is CSS off the state
    attribute), and the SR status span mirrors the state. No Alpine."""
    html = _R.render(FormStepper(sections=("Basics", "Details", "Review")))
    assert '<ol class="dz-form-stepper" role="list" aria-label="Form progress">' in html
    assert html.count('class="dz-form-stepper-item') == 3
    assert "x-data" not in html and "@click" not in html
    assert "x-if" not in html and "x-text" not in html
    # keyboard-operable: the trigger is a real <button> inside the li
    assert '<button type="button" class="dz-form-stepper-button" data-dz-step-to="0">' in html
    assert 'data-dz-step-to="2"' in html
    # SSR state: first item current (+active visuals), rest pending.
    assert 'data-dz-state="current"' in html
    assert html.count('data-dz-state="pending"') == 2
    assert 'aria-current="step"' in html
    assert 'class="dz-form-stepper-circle is-active"' in html
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
