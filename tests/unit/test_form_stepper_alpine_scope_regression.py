"""Regression tests for #902 — multi-section ``mode: create`` surface
emits Alpine bindings (`isCurrent(N)`, `isActive(N)`, `step > N`,
`goToStep(N)`) outside any `x-data` scope, throwing 20+
ReferenceErrors per render.

Root cause: `components/form.html` placed `x-data="dzWizard(N)"` on
the `<form>` element, but the stepper include sits ABOVE the form.
The stepper's bindings landed outside the dzWizard scope, so
`isActive`/`isCurrent`/`step` were undefined.

Fix: move the dzWizard scope up to the outer ``<div class="max-w-2xl">``
wrapper so both stepper AND form share it. `dzWizard.validateStage`
still resolves `[data-dz-stage]` elements via
`$el.querySelectorAll(...)` — stages stay inside the wrapper.
"""

from __future__ import annotations

from pathlib import Path


class TestFormStepperScope:
    """Static-source guard pinning the #902 fix."""

    def _read_form_template(self) -> str:
        return (
            Path(__file__).resolve().parents[2] / "src/dazzle_ui/templates/components/form.html"
        ).read_text()

    def test_dzwizard_scope_wraps_both_stepper_and_form(self) -> None:
        """The dzWizard `x-data` must be on the outer wrapper div, NOT
        on the form element. The previous form-element-scoped binding
        left the stepper include (which sits before the form in
        source order) outside the scope.

        v0.62 CSS refactor: the wrapper's `max-w-2xl` Tailwind class
        moved to the semantic `.dz-form-shell` rule in
        components/fragments.css. Assertion updated accordingly."""
        contents = self._read_form_template()
        # The outer div opens with the dzWizard binding
        assert 'class="dz-form-shell"' in contents and 'x-data="dzWizard(' in contents, (
            "form.html missing dzWizard scope on the outer wrapper"
        )

        # And the form element no longer carries the dzWizard binding
        # (it's only on the wrapper). Find the <form ...> opening
        # element and confirm it doesn't include x-data="dzWizard.
        form_opening = contents.split("<form ")[1].split(">")[0]
        assert "dzWizard" not in form_opening, (
            "dzWizard scope found on the <form> element — #902 returns. "
            "Stepper sits above the form and would be outside scope again."
        )

    def test_stepper_include_sits_inside_dzwizard_scope(self) -> None:
        """Source-order check — the stepper include must come AFTER
        the wrapper opens its dzWizard scope and BEFORE the wrapper
        closes."""
        contents = self._read_form_template()
        # Find positions of the dzWizard scope opener, the stepper
        # include, and the wrapper close (the </div> that pairs with
        # `<div class="max-w-2xl"`)
        dzwizard_pos = contents.find('x-data="dzWizard(')
        stepper_pos = contents.find("'fragments/form_stepper.html'")
        assert dzwizard_pos > 0, "dzWizard scope binding missing"
        assert stepper_pos > 0, "form_stepper.html include missing"
        assert dzwizard_pos < stepper_pos, (
            "Stepper include precedes the dzWizard scope opener — "
            "#902 returns. Stepper bindings would be outside scope."
        )

    def test_fix_documented_with_issue_reference(self) -> None:
        """The fix comment must cite #902 so future edits know WHY
        the scope sits on the wrapper, not the form."""
        contents = self._read_form_template()
        assert "#902" in contents, (
            "form.html missing #902 reference — future edits may move "
            "the dzWizard scope back onto the <form> element"
        )


class TestStepperBindingsRequireScope:
    """The stepper template references Alpine functions that only
    exist on the dzWizard data object — pin that none have crept out
    of scope into the surrounding chrome."""

    def _read_stepper(self) -> str:
        return (
            Path(__file__).resolve().parents[2]
            / "src/dazzle_ui/templates/fragments/form_stepper.html"
        ).read_text()

    def test_stepper_uses_dzwizard_methods(self) -> None:
        """Sanity check — the stepper does in fact use the dzWizard
        helpers. If a future edit changes the stepper to inline
        helpers, this regression test should be revisited."""
        contents = self._read_stepper()
        for method in ("isActive(", "isCurrent(", "step ", "goToStep("):
            assert method in contents, (
                f"Stepper template no longer uses {method!r} — "
                "scope contract may have changed; re-evaluate the #902 fix"
            )
