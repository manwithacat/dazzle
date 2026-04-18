"""card_add walk — click Add Card, pick a region, assert the fetch fires.

Closes the regression class reported in #798 at the interaction level.
The static shape gates don't see this one — the initial page is fine;
the bug is that HTMX's ``intersect once`` trigger never fires for a
dynamically-appended in-viewport element, so the region fetch is
skipped and the user sees a permanent skeleton.

This walk watches the network: after clicking "Add Card" + picking
the target region, the card body must contain non-skeleton text AND
the harness must have observed a GET against the region endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from dazzle.testing.ux.interactions.base import InteractionResult

if TYPE_CHECKING:
    from playwright.sync_api import Page


# Body text threshold: a skeleton body is just whitespace + ARIA labels;
# a real region body has substantive content. 40 chars is well above
# the longest skeleton placeholder we've seen (roughly 10-12 chars).
_MIN_BODY_TEXT_LENGTH = 40

# Max time to wait for the HTMX region fetch to resolve after click.
_SETTLE_MS = 2000


@dataclass
class CardAddInteraction:
    """Add a new card for ``region`` and assert it renders populated.

    Uses ``data-test-id`` anchors so copy changes on the Add Card
    button or the picker entries don't break the walk.
    """

    region: str
    name: str = field(default="card_add")
    settle_ms: int = _SETTLE_MS

    def execute(self, page: Page) -> InteractionResult:
        # Start capturing network requests so we can verify the region
        # endpoint fires. Use a simple list accumulator; Playwright's
        # ``on("request")`` signature takes the request object.
        captured_urls: list[str] = []

        def _on_request(request: object) -> None:
            try:
                url = request.url  # type: ignore[attr-defined]
            except AttributeError:
                return
            captured_urls.append(url)

        # Snapshot existing card ids BEFORE the click so we can tell
        # whether the picker actually added a new one (vs. just
        # re-finding an existing card via max()).
        existing_card_ids = page.evaluate(
            "() => Array.from(document.querySelectorAll('[data-card-id]')).map(el => el.dataset.cardId)"
        )
        existing_set = set(existing_card_ids) if isinstance(existing_card_ids, list) else set()

        page.on("request", _on_request)
        try:
            try:
                page.locator("[data-test-id='dz-add-card-trigger']").first.click()
            except Exception as exc:
                return InteractionResult(
                    name=self.name,
                    passed=False,
                    reason=f"Add Card trigger not clickable: {exc}",
                )

            # The picker is inside an Alpine-conditional <template x-for>
            # that's only rendered after showPicker flips to true.
            # Alpine needs a tick to process the reactive update, then
            # render the catalog list, then attach @click handlers.
            # Wait for the specific entry to become visible before
            # attempting to click it — otherwise we race Alpine and the
            # click either no-ops or hits a stale DOM element.
            entry_selector = (
                f"[data-test-id='dz-card-picker-entry'][data-test-region='{self.region}']"
            )
            try:
                page.wait_for_selector(entry_selector, state="visible", timeout=5000)
            except Exception as exc:
                return InteractionResult(
                    name=self.name,
                    passed=False,
                    reason=(
                        f"picker entry for region {self.region!r} never "
                        f"became visible after clicking Add Card — is the "
                        f"region in the workspace catalog? ({exc})"
                    ),
                )

            entry = page.locator(entry_selector).first
            try:
                entry.click()
            except Exception as exc:
                return InteractionResult(
                    name=self.name,
                    passed=False,
                    reason=f"picker entry click failed: {exc}",
                )

            page.wait_for_timeout(self.settle_ms)

            # Find the card(s) that appeared AFTER our click by diffing
            # against the pre-click snapshot. Comparing to max() over
            # all ids was a false-positive trap — if the picker click
            # didn't add a card, max() returned an existing (already-
            # populated) card id and the walk silently reported a
            # pre-existing card's state as the "new" one.
            card_ids = page.evaluate(
                "() => Array.from(document.querySelectorAll('[data-card-id]')).map(el => el.dataset.cardId)"
            )
            post_set = set(card_ids) if isinstance(card_ids, list) else set()
            added_ids = sorted(post_set - existing_set)
            if not added_ids:
                return InteractionResult(
                    name=self.name,
                    passed=False,
                    reason=(
                        "picker click didn't add a new card — existing "
                        "cards unchanged. The Add Card flow is broken or "
                        "the picker entry no-op'd silently."
                    ),
                    evidence={
                        "existing_cards": sorted(existing_set),
                        "post_cards": sorted(post_set),
                    },
                )
            # If more than one appeared (unlikely), pick the highest id
            # since it has the latest Date.now() timestamp.
            new_card_id = max(added_ids)

            body_text = page.locator(f"[data-card-id='{new_card_id}']").inner_text()
            body_populated = len(body_text.strip()) > _MIN_BODY_TEXT_LENGTH

            region_path_fragment = f"/regions/{self.region}"
            region_fetches = [u for u in captured_urls if region_path_fragment in u]
            fetch_observed = bool(region_fetches)

            passed = body_populated and fetch_observed
            reason = ""
            if not passed:
                parts: list[str] = []
                if not body_populated:
                    parts.append(
                        f"card body text is {len(body_text.strip())} chars — "
                        f"likely still a skeleton"
                    )
                if not fetch_observed:
                    parts.append(
                        f"no GET against {region_path_fragment} observed — "
                        f"the HTMX region fetch didn't fire (see #798)"
                    )
                reason = "; ".join(parts)

            return InteractionResult(
                name=self.name,
                passed=passed,
                reason=reason,
                evidence={
                    "new_card_id": new_card_id,
                    "body_length": len(body_text.strip()),
                    "region_fetch_count": len(region_fetches),
                },
            )
        finally:
            try:
                page.remove_listener("request", _on_request)
            except Exception:
                pass
