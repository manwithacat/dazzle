"""context_select walk — pick a context_selector option, assert regions re-scope.

Closes the #1304 Defect A regression class at the interaction level. The
static shape gates can't see it: the `<select id="dz-context-selector">`
renders fine, but the gate is *runtime* — does choosing an option actually
drive the workspace's regions to refetch scoped to that context?

Two ways this broke historically, both guarded here:
  1. The options never populate. `context-options` listed the context entity
     through the full entity Pydantic model and 422'd on a single out-of-enum
     row, leaving the `<select>` empty → nothing to pick (#1304, fixed by the
     id+label projection).
  2. The change handler doesn't drive the regions. The selector IIFE rewrites
     each `[id^="region-"][hx-get]` element's `hx-get` to include
     `?context_id=<id>` and fires `htmx.ajax`.

The assertion is deliberately **data-independent** (it does not require seeded
rows): on selecting a non-default option, the harness must observe a GET
against a region endpoint carrying that option's `context_id`. That proves the
selector is populated AND wired, regardless of whether the tenant has data.
"""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from dazzle.testing.ux.interactions.base import InteractionResult

if TYPE_CHECKING:
    from playwright.sync_api import Page

# Max time to wait for the IIFE's context-options fetch to populate the
# <select>, and for the post-select region refetch to fire.
_SETTLE_MS = 3000


@dataclass
class ContextSelectInteraction:
    """Navigate to ``workspace``, pick a non-default context option, and assert
    the regions refetch scoped to it.

    Self-navigating (uses the page's current origin), so it runs independently
    of whichever workspace the persona lands on.
    """

    workspace: str
    name: str = field(default="context_select")
    settle_ms: int = _SETTLE_MS

    def execute(self, page: Page) -> InteractionResult:
        captured: list[str] = []

        def _on_request(request: object) -> None:
            with suppress(Exception):
                captured.append(getattr(request, "url", ""))

        page.on("request", _on_request)
        try:
            origin = page.evaluate("() => location.origin")
            url = f"{origin}/app/workspaces/{self.workspace}"
            try:
                page.goto(url, timeout=15_000)
                page.wait_for_load_state("networkidle", timeout=15_000)
            except Exception as exc:
                return InteractionResult(
                    name=self.name,
                    passed=False,
                    reason=f"could not load workspace {self.workspace!r}: {exc}",
                )

            sel = page.locator("#dz-context-selector")
            if sel.count() == 0:
                return InteractionResult(
                    name=self.name,
                    passed=False,
                    reason=f"workspace {self.workspace!r} has no #dz-context-selector",
                )

            # Guard #1: the options must populate (the IIFE fetches
            # context-options and appends <option>s). >1 means real options
            # beyond the hard-coded "All". If this times out, context-options
            # is failing (the #1304 422 class) and the selector is inert.
            try:
                page.wait_for_function(
                    "() => { const s = document.getElementById('dz-context-selector');"
                    " return s && s.options.length > 1; }",
                    timeout=self.settle_ms,
                )
            except Exception:
                opt_count = page.evaluate(
                    "() => { const s = document.getElementById('dz-context-selector');"
                    " return s ? s.options.length : 0; }"
                )
                return InteractionResult(
                    name=self.name,
                    passed=False,
                    reason=(
                        "context_selector did not populate "
                        f"(options={opt_count}); context-options likely failing "
                        "— the selector would be inert (#1304 Defect A)."
                    ),
                    evidence={"option_count": opt_count},
                )

            # Pick a real option distinct from the current selection. The IIFE
            # auto-selects the first real option on load and fires an initial
            # context_id'd fetch; we choose a *different* one and assert a NEW
            # fetch carries the NEW id, so we're not fooled by that initial load.
            option_values = page.evaluate(
                "() => Array.from(document.getElementById('dz-context-selector').options)"
                ".map(o => o.value).filter(v => v)"
            )
            if not isinstance(option_values, list) or not option_values:
                return InteractionResult(
                    name=self.name, passed=False, reason="no non-empty option values found"
                )
            current = page.evaluate("() => document.getElementById('dz-context-selector').value")
            target = next((v for v in option_values if v != current), option_values[0])

            # Select + assert a region refetch fires carrying this context_id.
            try:
                with page.expect_request(
                    lambda r: "/regions/" in r.url and f"context_id={target}" in r.url,
                    timeout=self.settle_ms,
                ):
                    page.select_option("#dz-context-selector", value=target)
            except Exception:
                region_reqs = [u for u in captured if "/regions/" in u]
                return InteractionResult(
                    name=self.name,
                    passed=False,
                    reason=(
                        "selecting an option did not drive a context-scoped "
                        f"region refetch (expected a /regions/ GET with "
                        f"context_id={target}). The selector populated but its "
                        "change handler isn't re-scoping the regions."
                    ),
                    evidence={
                        "target_context_id": target,
                        "region_requests": region_reqs[-5:],
                    },
                )

            return InteractionResult(
                name=self.name,
                passed=True,
                evidence={
                    "workspace": self.workspace,
                    "option_count": len(option_values),
                    "selected_context_id": target,
                },
            )
        finally:
            with suppress(Exception):
                page.remove_listener("request", _on_request)
