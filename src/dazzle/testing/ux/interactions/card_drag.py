"""card_drag walk — scripted drag gesture + bounding-box delta assertion.

Pointerdown on the drag handle, move over ``dy`` pixels in ``steps``
increments, pointerup. Assert the card's bounding box moved. Closes
the regression class reported in #797 at the interaction level.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from dazzle.testing.ux.interactions.base import InteractionResult

if TYPE_CHECKING:
    from playwright.sync_api import Page


# Any dy below this is noise — sub-pixel rounding, animation snap, etc.
# Well below the 4px drag-threshold the dashboard builder enforces, so
# a successful drag reports at least this much.
_MIN_MOVE_PIXELS = 5.0


@dataclass
class CardDragInteraction:
    """Drag a specific card by ``dy`` pixels vertically and assert its
    rendered position changed.

    Uses ``data-test-id="dz-card-drag-handle"`` inside the card to
    anchor the pointerdown — stable under copy/class changes as long
    as the test-id stays.
    """

    card_id: str
    dy: int = 200
    steps: int = 10
    settle_ms: int = 400
    name: str = field(default="card_drag")

    def execute(self, page: Page) -> InteractionResult:
        card = page.locator(f"[data-card-id='{self.card_id}']").first
        handle = card.locator("[data-test-id='dz-card-drag-handle']").first
        try:
            before_box = card.bounding_box()
            handle_box = handle.bounding_box()
        except Exception as exc:
            return InteractionResult(
                name=self.name,
                passed=False,
                reason=f"card {self.card_id!r} not found: {exc}",
            )
        if before_box is None or handle_box is None:
            return InteractionResult(
                name=self.name,
                passed=False,
                reason=f"card {self.card_id!r} or its drag handle has no bounding box",
            )

        start_x = handle_box["x"] + handle_box["width"] / 2
        start_y = handle_box["y"] + min(handle_box["height"] / 2, 20)
        page.mouse.move(start_x, start_y)
        page.mouse.down()
        for i in range(1, self.steps + 1):
            page.mouse.move(start_x, start_y + (self.dy * i / self.steps))
            page.wait_for_timeout(max(1, 400 // self.steps))
        page.mouse.up()

        page.wait_for_timeout(self.settle_ms)

        after_box = card.bounding_box()
        if after_box is None:
            return InteractionResult(
                name=self.name,
                passed=False,
                reason=f"card {self.card_id!r} disappeared during drag",
            )

        dy_actual = after_box["y"] - before_box["y"]
        dx_actual = after_box["x"] - before_box["x"]
        moved = abs(dy_actual) >= _MIN_MOVE_PIXELS or abs(dx_actual) >= _MIN_MOVE_PIXELS

        return InteractionResult(
            name=self.name,
            passed=moved,
            reason=(
                ""
                if moved
                else (
                    f"card didn't move — gesture completed but bounding box "
                    f"delta was dx={dx_actual:.1f}, dy={dy_actual:.1f} "
                    f"(need >= {_MIN_MOVE_PIXELS}px). Likely a regression in "
                    f"the dashboard drag lifecycle (see issue #797)."
                )
            ),
            evidence={
                "dx": dx_actual,
                "dy": dy_actual,
                "requested_dy": self.dy,
            },
        )
