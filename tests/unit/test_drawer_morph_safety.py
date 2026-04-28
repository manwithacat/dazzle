"""Tests for `workspace/_content.html` drawer morph-safety (issue #934).

This is a source-grep regression test (the IIFE runs in the browser
under htmx morph swaps; full behaviour belongs in a Playwright gate).
We pin the three correctness invariants:

1. Init guard — every event listener registers exactly once across
   the session, not once per workspace render.
2. Element lookups fresh on every call — `dzDrawer.open` / `.close`
   re-read `document.getElementById` so they don't operate on
   detached nodes after a morph swap replaces the drawer DOM.
3. `htmx:afterSettle` defensive close — if a swap landed anywhere
   other than `#dz-detail-drawer-content`, close the drawer. Prevents
   stale `is-open` state from leaking across workspace→workspace nav.
"""

from pathlib import Path

CONTENT_PATH = Path("src/dazzle_ui/templates/workspace/_content.html")


def _read_iife() -> str:
    """Return the body of the drawer IIFE script block."""
    src = CONTENT_PATH.read_text()
    # The IIFE sits inside a <script> tag with the dzDrawer setup.
    start = src.index("window.dzDrawer = {")
    end = src.index("</script>", start)
    return src[start:end]


class TestDrawerInitGuard:
    """The IIFE must not re-bind listeners on every render."""

    def test_init_guard_flag_present(self) -> None:
        body = _read_iife()
        assert "window.__dzDrawerInit" in body, (
            "IIFE must use a session-level flag to prevent listener "
            "duplication on htmx morph re-execution"
        )

    def test_listeners_registered_inside_guard(self) -> None:
        """All addEventListener calls for the bus events must be on
        the guarded side of the early-return."""
        body = _read_iife()
        guard_idx = body.index("window.__dzDrawerInit = true;")
        post_guard = body[guard_idx:]
        # All four event registrations live after the guard.
        assert "addEventListener('dz:drawerOpen'" in post_guard
        assert "addEventListener('click'" in post_guard
        assert "addEventListener('keydown'" in post_guard
        assert "addEventListener('htmx:afterSettle'" in post_guard


class TestFreshElementLookup:
    """`dzDrawer.open` / `.close` must look up the drawer / backdrop
    elements via `document.getElementById` each call — capturing them
    in a closure breaks after morph swap replaces the drawer DOM."""

    def test_open_looks_up_drawer_freshly(self) -> None:
        body = _read_iife()
        # Locate the open() body.
        open_idx = body.index("open: function(url)")
        open_body = body[open_idx : open_idx + 600]
        # Must NOT use closure-captured references — those would be
        # the bare names `drawer` / `backdrop` without a fresh lookup.
        assert (
            "_qd('dz-detail-drawer')" in open_body
            or "getElementById('dz-detail-drawer')" in open_body
        )
        assert (
            "_qd('dz-drawer-backdrop')" in open_body
            or "getElementById('dz-drawer-backdrop')" in open_body
        )

    def test_close_looks_up_drawer_freshly(self) -> None:
        body = _read_iife()
        close_idx = body.index("close: function()")
        close_body = body[close_idx : close_idx + 400]
        assert (
            "_qd('dz-detail-drawer')" in close_body
            or "getElementById('dz-detail-drawer')" in close_body
        )
        assert (
            "_qd('dz-drawer-backdrop')" in close_body
            or "getElementById('dz-drawer-backdrop')" in close_body
        )


class TestAfterSettleDefensiveClose:
    """The `htmx:afterSettle` listener is the user-visible bug fix —
    it forces the drawer closed when a swap targets anything other
    than the drawer's content element."""

    def test_listener_present(self) -> None:
        body = _read_iife()
        assert "addEventListener('htmx:afterSettle'" in body

    def test_skips_drawer_target(self) -> None:
        """The drawer-targeting path opens via `dz:drawerOpen` AFTER
        `htmx:afterSettle` fires. The defensive close must skip it
        otherwise the drawer would close itself during open."""
        body = _read_iife()
        # Find the afterSettle listener body.
        idx = body.index("addEventListener('htmx:afterSettle'")
        block = body[idx : idx + 600]
        assert "dz-detail-drawer-content" in block
        # And it must short-circuit (return) when the target IS the drawer.
        assert "return;" in block

    def test_only_closes_when_open(self) -> None:
        """Don't toggle close on a drawer that's already closed —
        avoids spurious DOM mutation on every swap."""
        body = _read_iife()
        idx = body.index("addEventListener('htmx:afterSettle'")
        block = body[idx : idx + 600]
        assert "isOpen" in block
