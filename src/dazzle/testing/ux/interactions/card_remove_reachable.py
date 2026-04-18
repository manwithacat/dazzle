"""card_remove_reachable walk — keyboard reachability of the remove button.

Tabs from the card's drag handle into the action cluster and asserts
the focused remove button has a non-zero computed opacity. Closes the
regression class reported in #799 (opacity-0 hover-only reveal) at the
interaction level — the static gate INV-9 (``find_hidden_primary_actions``)
catches the template-level pattern; this walk verifies the pattern
actually reaches a real runtime on a real DOM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from dazzle.testing.ux.interactions.base import InteractionResult

if TYPE_CHECKING:
    from playwright.sync_api import Page


# Minimum opacity below which we consider the button "invisible". Small
# positive floor rather than 1.0 because the at-rest design uses
# opacity-60 (= 0.6) for de-emphasised-but-discoverable (see #799 fix).
_MIN_OPACITY = 0.2

# Max number of Tab presses we'll issue looking for the remove button.
# Bounded so a pathologically-broken page doesn't spin.
_MAX_TAB_STEPS = 15


@dataclass
class CardRemoveReachableInteraction:
    """Tab through the page until a ``[data-test-id="dz-card-remove"]``
    button receives focus, then assert its computed opacity is high
    enough to be discoverable.
    """

    card_id: str
    name: str = field(default="card_remove_reachable")

    def execute(self, page: Page) -> InteractionResult:
        selector = f"[data-card-id='{self.card_id}']"
        try:
            page.locator(selector).first.focus()
        except Exception as exc:
            return InteractionResult(
                name=self.name,
                passed=False,
                reason=f"card {self.card_id!r} not found: {exc}",
            )

        # Tab forward up to _MAX_TAB_STEPS looking for the remove button.
        for step in range(_MAX_TAB_STEPS):
            page.keyboard.press("Tab")
            focused_test_id = page.evaluate(
                "() => document.activeElement && document.activeElement.getAttribute('data-test-id')"
            )
            if focused_test_id == "dz-card-remove":
                opacity_raw = page.evaluate(
                    "() => getComputedStyle(document.activeElement).opacity"
                )
                try:
                    opacity = float(opacity_raw or "0")
                except (TypeError, ValueError):
                    opacity = 0.0
                passed = opacity >= _MIN_OPACITY
                reason = (
                    ""
                    if passed
                    else (
                        f"remove button reached at Tab step {step + 1} but "
                        f"its computed opacity is {opacity:.2f}, below the "
                        f"{_MIN_OPACITY} threshold — touch/keyboard users "
                        f"can't see it"
                    )
                )
                return InteractionResult(
                    name=self.name,
                    passed=passed,
                    reason=reason,
                    evidence={
                        "tab_steps": step + 1,
                        "opacity": opacity,
                    },
                )

        return InteractionResult(
            name=self.name,
            passed=False,
            reason=(
                f"remove button never received focus after {_MAX_TAB_STEPS} "
                f"Tab presses from the card — either the button isn't "
                f"focusable or data-test-id='dz-card-remove' is missing"
            ),
            evidence={"tab_steps": _MAX_TAB_STEPS, "opacity": None},
        )
