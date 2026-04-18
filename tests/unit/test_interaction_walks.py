"""Unit tests for the v1 INTERACTION_WALK walks.

A real Playwright run against ``dazzle serve`` belongs in tests/e2e/
and needs Postgres + Redis. Here we use a stub Page to verify each
walk's *logic*: does it interpret bounding boxes correctly, does it
issue the right clicks, does it capture the right network requests,
does it produce a well-formed ``InteractionResult``.

The stubs are intentionally minimal — just enough of Playwright's
sync API surface to drive each walk. Adding a new walk means adding
the corresponding stub methods here, not in every test.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from dazzle.testing.ux.interactions import (
    CardAddInteraction,
    CardDragInteraction,
    CardRemoveReachableInteraction,
)

# ---------------------------------------------------------------------------
# Stub Page machinery
# ---------------------------------------------------------------------------


@dataclass
class _StubLocator:
    """Minimal Playwright Locator stand-in."""

    _bbox: dict[str, float] | None = None
    _child_locators: dict[str, _StubLocator] = field(default_factory=dict)
    _click_raises: Exception | None = None
    _inner_text: str = ""

    @property
    def first(self) -> _StubLocator:
        return self

    def bounding_box(self) -> dict[str, float] | None:
        return self._bbox

    def focus(self) -> None:
        pass

    def click(self) -> None:
        if self._click_raises is not None:
            raise self._click_raises

    def inner_text(self) -> str:
        return self._inner_text

    def locator(self, selector: str) -> _StubLocator:
        return self._child_locators.get(selector, _StubLocator())


@dataclass
class _StubMouse:
    positions: list[tuple[float, float]] = field(default_factory=list)
    down_called: bool = False
    up_called: bool = False

    def move(self, x: float, y: float) -> None:
        self.positions.append((x, y))

    def down(self) -> None:
        self.down_called = True

    def up(self) -> None:
        self.up_called = True


@dataclass
class _StubKeyboard:
    presses: list[str] = field(default_factory=list)

    def press(self, key: str) -> None:
        self.presses.append(key)


@dataclass
class _StubPage:
    """Minimal sync Playwright Page stand-in for walk unit tests."""

    locators: dict[str, _StubLocator] = field(default_factory=dict)
    mouse: _StubMouse = field(default_factory=_StubMouse)
    keyboard: _StubKeyboard = field(default_factory=_StubKeyboard)
    _eval_returns: list[Any] = field(default_factory=list)
    _eval_history: list[str] = field(default_factory=list)
    _request_listeners: list[Any] = field(default_factory=list)

    def locator(self, selector: str) -> _StubLocator:
        return self.locators.get(selector, _StubLocator())

    def evaluate(self, script: str) -> Any:
        self._eval_history.append(script)
        if self._eval_returns:
            return self._eval_returns.pop(0)
        return None

    def wait_for_timeout(self, ms: int) -> None:
        pass

    def on(self, event: str, listener: Any) -> None:
        if event == "request":
            self._request_listeners.append(listener)

    def remove_listener(self, event: str, listener: Any) -> None:
        if event == "request":
            try:
                self._request_listeners.remove(listener)
            except ValueError:
                pass

    def _fire_request(self, url: str) -> None:
        """Fake a network request event for the card_add walk."""

        @dataclass
        class _Req:
            url: str

        req = _Req(url=url)
        for listener in self._request_listeners:
            listener(req)


# ---------------------------------------------------------------------------
# card_remove_reachable
# ---------------------------------------------------------------------------


class TestCardRemoveReachable:
    def test_passes_when_opacity_above_floor(self) -> None:
        page = _StubPage()
        # Tab once → active element is dz-card-remove with opacity 0.6
        page._eval_returns = ["dz-card-remove", "0.6"]
        page.locators["[data-card-id='card-0']"] = _StubLocator()

        result = CardRemoveReachableInteraction(card_id="card-0").execute(page)

        assert result.passed
        assert result.evidence["opacity"] == 0.6
        assert result.evidence["tab_steps"] == 1

    def test_fails_when_opacity_below_floor(self) -> None:
        page = _StubPage()
        page._eval_returns = ["dz-card-remove", "0.0"]
        page.locators["[data-card-id='card-0']"] = _StubLocator()

        result = CardRemoveReachableInteraction(card_id="card-0").execute(page)

        assert not result.passed
        assert "below the" in result.reason
        assert result.evidence["opacity"] == 0.0

    def test_fails_when_button_never_reached(self) -> None:
        # Every Tab press lands on something that isn't dz-card-remove.
        page = _StubPage()
        page._eval_returns = ["something-else"] * 20
        page.locators["[data-card-id='card-0']"] = _StubLocator()

        result = CardRemoveReachableInteraction(card_id="card-0").execute(page)

        assert not result.passed
        assert "never received focus" in result.reason


# ---------------------------------------------------------------------------
# card_drag
# ---------------------------------------------------------------------------


class TestCardDrag:
    def _card_locator_with_handle(
        self, bbox_before: dict[str, float], bbox_after: dict[str, float]
    ) -> _StubLocator:
        """Build a locator whose bounding_box() returns `before` first,
        then `after` on the second call.
        """
        calls: list[int] = [0]

        def bbox_fn() -> dict[str, float]:
            idx = calls[0]
            calls[0] += 1
            return bbox_before if idx == 0 else bbox_after

        handle = _StubLocator(_bbox={"x": 100, "y": 10, "width": 200, "height": 36})
        card = _StubLocator()
        card._child_locators = {"[data-test-id='dz-card-drag-handle']": handle}
        # Monkey-patch bounding_box to return before/after across calls.
        card.bounding_box = bbox_fn  # type: ignore[method-assign]
        return card

    def test_passes_when_card_moves(self) -> None:
        page = _StubPage()
        card = self._card_locator_with_handle(
            bbox_before={"x": 100, "y": 100, "width": 300, "height": 200},
            bbox_after={"x": 100, "y": 300, "width": 300, "height": 200},
        )
        page.locators["[data-card-id='card-0']"] = card

        result = CardDragInteraction(card_id="card-0", dy=200, steps=5).execute(page)

        assert result.passed
        assert result.evidence["dy"] == 200.0
        assert page.mouse.down_called and page.mouse.up_called

    def test_fails_when_card_stays_still(self) -> None:
        # bbox before == bbox after (the #797 symptom).
        page = _StubPage()
        same_bbox = {"x": 100, "y": 100, "width": 300, "height": 200}
        card = self._card_locator_with_handle(bbox_before=same_bbox, bbox_after=same_bbox)
        page.locators["[data-card-id='card-0']"] = card

        result = CardDragInteraction(card_id="card-0", dy=200, steps=5).execute(page)

        assert not result.passed
        assert "didn't move" in result.reason
        assert result.evidence["dy"] == 0.0

    def test_fails_when_card_missing(self) -> None:
        page = _StubPage()  # no locator registered
        result = CardDragInteraction(card_id="ghost", dy=200).execute(page)
        assert not result.passed
        assert "no bounding box" in result.reason or "not found" in result.reason


# ---------------------------------------------------------------------------
# card_add
# ---------------------------------------------------------------------------


class TestCardAdd:
    def test_passes_when_body_populated_and_fetch_observed(self) -> None:
        page = _StubPage()
        trigger = _StubLocator()
        entry = _StubLocator()
        new_card = _StubLocator(_inner_text="Alert Severity Breakdown\nopen: 3\nclosed: 7\n")
        page.locators["[data-test-id='dz-add-card-trigger']"] = trigger
        page.locators[
            "[data-test-id='dz-card-picker-entry'][data-test-region='alert_severity']"
        ] = entry
        page.locators["[data-card-id='card-9999']"] = new_card

        # evaluate returns: card ids list, then inner text (not used —
        # inner_text comes from the locator), so only one eval.
        page._eval_returns = [["card-0", "card-1", "card-9999"]]

        walk = CardAddInteraction(region="alert_severity", settle_ms=0)

        # Kick off the walk, then fire the request while it's settling.
        # Since settle_ms=0 we simulate the fetch happening synchronously
        # by pre-injecting the request listener and firing during the
        # on() callback. Cleaner approach: override page.on to fire
        # immediately.
        original_on = page.on

        def on_request_fire(event: str, listener: Any) -> None:
            original_on(event, listener)
            # Fire a fake request event now so the walk sees it when
            # it drains the captured URLs.
            page._fire_request("http://test/api/workspaces/ws/regions/alert_severity")

        page.on = on_request_fire  # type: ignore[method-assign]

        result = walk.execute(page)

        assert result.passed, result.reason
        assert result.evidence["new_card_id"] == "card-9999"
        assert result.evidence["region_fetch_count"] == 1

    def test_fails_when_body_stays_skeleton(self) -> None:
        page = _StubPage()
        page.locators["[data-test-id='dz-add-card-trigger']"] = _StubLocator()
        page.locators[
            "[data-test-id='dz-card-picker-entry'][data-test-region='alert_severity']"
        ] = _StubLocator()
        page.locators["[data-card-id='card-9999']"] = _StubLocator(_inner_text="...")
        page._eval_returns = [["card-9999"]]

        result = CardAddInteraction(region="alert_severity", settle_ms=0).execute(page)

        assert not result.passed
        assert "skeleton" in result.reason

    def test_fails_when_no_region_fetch_observed(self) -> None:
        page = _StubPage()
        page.locators["[data-test-id='dz-add-card-trigger']"] = _StubLocator()
        page.locators[
            "[data-test-id='dz-card-picker-entry'][data-test-region='alert_severity']"
        ] = _StubLocator()
        page.locators["[data-card-id='card-9999']"] = _StubLocator(
            _inner_text="Alert Severity Breakdown\nopen: 3\nclosed: 7\nmore content"
        )
        page._eval_returns = [["card-9999"]]
        # Don't fire any requests.

        result = CardAddInteraction(region="alert_severity", settle_ms=0).execute(page)

        assert not result.passed
        assert "no GET" in result.reason

    def test_fails_when_trigger_not_clickable(self) -> None:
        page = _StubPage()
        page.locators["[data-test-id='dz-add-card-trigger']"] = _StubLocator(
            _click_raises=RuntimeError("not visible")
        )
        result = CardAddInteraction(region="alert_severity", settle_ms=0).execute(page)
        assert not result.passed
        assert "not clickable" in result.reason

    def test_fails_when_picker_entry_missing(self) -> None:
        page = _StubPage()
        page.locators["[data-test-id='dz-add-card-trigger']"] = _StubLocator()
        # No picker-entry locator registered — default _StubLocator raises
        # nothing on click, so we explicitly make it raise.
        page.locators["[data-test-id='dz-card-picker-entry'][data-test-region='ghost']"] = (
            _StubLocator(_click_raises=RuntimeError("not found"))
        )

        result = CardAddInteraction(region="ghost", settle_ms=0).execute(page)

        assert not result.passed
        assert "picker entry" in result.reason
