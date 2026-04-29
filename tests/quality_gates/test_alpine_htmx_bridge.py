"""Alpine × HTMX bridge quality gates (#947).

Cycle 2: stress gate. Repeats the destroy+init pattern that
``htmx:afterSettle`` triggers (the #945 fix) and verifies the
``$data`` proxy identity changes each time. The
``window.dzDebug.dataIdentity()`` helper from #947 cycle 1 makes
this measurement a stable string compare.

Cycle 3: cross-URL behaviour. Documents (and pins) that the
destroy+init handler in ``dz-alpine.js`` triggers regardless of
which workspace the morph swapped to — same code path as
same-URL morph. The pre-#948 staleness bug was specifically
same-URL because the ``[x-data]`` element survived; cross-URL
morph replaced the element entirely and Alpine re-init'd via
the global ``initTree`` bridge. Post-#948 the cards array is
gone so neither path can manifest the staleness, but the
destroy+init defense-in-depth pattern is still load-bearing for
ephemeral state (saveState, showPicker, grid event delegation).

The fixtures in this file mirror ``test_dashboard_gates.py``:
shared port, static harness, no backend.
"""

from __future__ import annotations

import subprocess
import time

import pytest

pytest.importorskip("playwright.sync_api")

from playwright.sync_api import sync_playwright  # noqa: E402


@pytest.fixture(scope="module")
def server():
    """Static-files server for the dashboard harness."""
    static_dir = "src/dazzle_ui/runtime/static"
    # Different port from the dashboard gates so both modules can run
    # together without conflict.
    proc = subprocess.Popen(
        ["python3", "-m", "http.server", "8768", "--directory", static_dir],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(1)
    yield "http://localhost:8768/test-dashboard.html"
    proc.terminate()
    proc.wait()


@pytest.fixture(scope="module")
def browser_page(server):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(server)
        page.wait_for_function(
            "typeof Alpine !== 'undefined' "
            "&& document.querySelector('[data-card-id]') !== null"
            "&& typeof window.dzDebug !== 'undefined'",
            timeout=10000,
        )
        yield page
        browser.close()


# ---------------------------------------------------------------------------
# Cycle 2 — stress (rapid destroy+init cycles)
# ---------------------------------------------------------------------------


class TestProxyIdentityRefreshOnDestroyInit:
    """The cycle 945 destroy+init handler must produce a NEW $data
    proxy each time. Without that, the watcher graph would stay
    bound to the original proxy and reactive directives could go
    stale. dz-debug's `dataIdentity()` returns a stable string id
    per proxy instance; tests assert two consecutive readings
    differ across destroy+init."""

    def test_proxy_identity_changes_after_one_cycle(self, browser_page) -> None:
        """Single destroy+init cycle: id_after != id_before."""
        result = browser_page.evaluate(
            """() => {
                const before = window.dzDebug.dataIdentity('[data-workspace-name]');
                const root = document.querySelector('[data-workspace-name]');
                window.Alpine.destroyTree(root);
                window.Alpine.initTree(root);
                const after = window.dzDebug.dataIdentity('[data-workspace-name]');
                return { before, after };
            }"""
        )
        assert result["before"] is not None
        assert result["after"] is not None
        assert result["before"] != result["after"], (
            "Proxy identity should change after destroy+init — "
            f"got {result}. The watcher graph stayed bound to the "
            "old proxy (the #945 bug class)."
        )

    def test_proxy_identity_changes_each_cycle_in_a_run_of_ten(self, browser_page) -> None:
        """Stress: 10 rapid destroy+init cycles. Each cycle must
        produce a fresh proxy. If the framework caches or memoises
        the proxy somewhere, the chain of identities would collapse
        to fewer than 10 unique values — test fires."""
        ids = browser_page.evaluate(
            """() => {
                const ids = [];
                ids.push(window.dzDebug.dataIdentity('[data-workspace-name]'));
                const root = document.querySelector('[data-workspace-name]');
                for (let i = 0; i < 10; i++) {
                    window.Alpine.destroyTree(root);
                    window.Alpine.initTree(root);
                    ids.push(window.dzDebug.dataIdentity('[data-workspace-name]'));
                }
                return ids;
            }"""
        )
        # 11 readings (initial + 10 post-destroy+init), all unique
        assert len(ids) == 11
        assert len(set(ids)) == 11, (
            "Proxy identities collapsed across 10 destroy+init cycles. "
            f"Unique count: {len(set(ids))}/11. Got: {ids}"
        )

    def test_last_settle_at_advances_with_synthetic_settle_events(self, browser_page) -> None:
        """`dzDebug.lastSettleAt()` increases when an
        `htmx:afterSettle` event fires. Without this signal, tests
        polling for "morph completed" would have to sleep-and-pray.

        The dispatch is `new CustomEvent('htmx:afterSettle', ...)`
        on `document.body` — the same path htmx-ext-* uses
        internally."""
        before = browser_page.evaluate("window.dzDebug.lastSettleAt()")
        browser_page.evaluate(
            """() => {
                const evt = new CustomEvent('htmx:afterSettle', {
                    bubbles: true,
                    detail: { target: document.querySelector('[data-workspace-name]') }
                });
                document.body.dispatchEvent(evt);
            }"""
        )
        # Give the event loop a tick to update the timestamp
        browser_page.wait_for_function(
            f"window.dzDebug.lastSettleAt() > {before}",
            timeout=2000,
        )
        after = browser_page.evaluate("window.dzDebug.lastSettleAt()")
        assert after > before


# ---------------------------------------------------------------------------
# Cycle 3 — cross-URL invariants
# ---------------------------------------------------------------------------


class TestCrossUrlMorphInvariants:
    """The destroy+init handler triggers off `[data-workspace-name]`
    rather than the swap target's URL or specific workspace identity.
    Same code path runs whether the user clicks the active workspace's
    sidebar link (same-URL morph) or a different workspace (cross-URL
    morph). The harness only loads one workspace, so this test pins
    the contract via the JS handler's own selector logic rather than
    a real htmx swap."""

    def test_destroy_init_handler_uses_data_workspace_name_selector(self, browser_page) -> None:
        """The handler in dz-alpine.js looks for
        `[data-workspace-name]` — that selector is set by the
        framework on every workspace render, not just same-URL.
        So cross-URL morph triggers the same handler.

        Verifying this in-browser by reading the source of the
        registered listener... actually impossible since
        `addEventListener` doesn't expose its handler source.
        Instead, verify the handler runs by dispatching a synthetic
        afterSettle on a foreign workspace (different
        `data-workspace-name`) and confirming the proxy refreshes."""
        # Set up: stash the initial workspace name
        initial_ws = browser_page.evaluate(
            "document.querySelector('[data-workspace-name]').getAttribute('data-workspace-name')"
        )
        assert initial_ws == "test_dashboard"

        # Simulate a cross-URL morph by changing the data-workspace-name
        # attribute (cheap stand-in for a real htmx swap delivering
        # a different workspace) and dispatching afterSettle.
        result = browser_page.evaluate(
            """() => {
                const root = document.querySelector('[data-workspace-name]');
                const before = window.dzDebug.dataIdentity('[data-workspace-name]');
                // Pretend htmx morphed in a different workspace
                root.setAttribute('data-workspace-name', 'other_workspace');
                // Dispatch afterSettle as htmx would
                const evt = new CustomEvent('htmx:afterSettle', {
                    bubbles: true,
                    detail: { target: root }
                });
                document.body.dispatchEvent(evt);
                // Read post-morph
                const newWs = root.getAttribute('data-workspace-name');
                const after = window.dzDebug.dataIdentity('[data-workspace-name]');
                // Restore for downstream tests
                root.setAttribute('data-workspace-name', 'test_dashboard');
                return { before, after, newWs };
            }"""
        )
        assert result["newWs"] == "other_workspace"
        # The destroy+init handler ran (proxy refreshed) regardless
        # of which workspace name the root carried.
        assert result["before"] != result["after"]


# ---------------------------------------------------------------------------
# Cycle 4 — audit (no other reactive surfaces on morph paths warrant
# the same defense-in-depth)
# ---------------------------------------------------------------------------


class TestAuditOtherReactiveSurfaces:
    """The pre-#948 cards-collapse-to-0 bug was specifically:
    (a) reactive collection projected via `<template x-for>`,
    (b) projection survives morph but watcher graph detaches.

    Other Alpine `<template x-for>` directives in the framework
    are NOT on htmx swap-target boundaries — toasts (transient
    notifications), command palette (transient overlay), filter
    bar (per-component state). They live entirely within one
    component lifecycle and Alpine init runs once per mount.

    These source-grep tests pin that audit at test time."""

    def test_no_x_for_in_workspace_content(self) -> None:
        """The workspace shell must not regress to using x-for for
        cards — the whole point of #948 cycle 1 is server-rendered
        HTML. A regression here would re-introduce the bug class."""
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[2]
        text = (repo_root / "src/dazzle_ui/templates/workspace/_content.html").read_text()
        assert 'x-for="card in cards"' not in text
        assert 'x-for="r in regions"' not in text

    def test_x_for_only_in_transient_components(self) -> None:
        """Inventory: every template using `x-for` must be one of the
        known-safe transient components (toasts, command palette,
        filter bar, card picker, form widgets). Adding x-for elsewhere
        warrants a careful review for morph-path exposure."""
        import re
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[2]
        templates_dir = repo_root / "src/dazzle_ui/templates"
        # Known-safe x-for usages (transient overlays, in-component
        # state, never spans an htmx swap boundary)
        allowed = {
            "base.html",  # toasts
            "command_palette.html",  # transient command overlay
            "filter_bar.html",  # per-table filter chips
            "_card_picker.html",  # cycle 1 of #948 server-rendered;
            #                       picker still uses x-show but no x-for
            "form_field.html",  # form widget options
        }
        finds = []
        for path in templates_dir.rglob("*.html"):
            content = path.read_text()
            if not re.search(r'x-for="', content):
                continue
            if path.name not in allowed:
                finds.append(str(path.relative_to(repo_root)))
        assert not finds, (
            "New `x-for` usage detected outside the known-safe set:\n"
            + "\n".join(f"  - {p}" for p in finds)
            + "\n\nReview each for morph-path exposure. If the template "
            "renders inside an htmx swap target AND the x-for collection "
            "is reactive, the #945 watcher-staleness bug class can "
            "recur. Add to `allowed` here only after confirming the "
            "template lives entirely within one Alpine component "
            "lifecycle (no morph crossing) OR the collection is not "
            "actually reactive (e.g. always one element)."
        )
