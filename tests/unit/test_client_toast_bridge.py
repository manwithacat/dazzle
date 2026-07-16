"""Structural ratchets for the client-initiated toast path (C3 orphan sweep).

The bug this pins against: `window.dz.toast()` and the optimistic-rollback
path dispatched events whose ONLY listener was the `dzToast` Alpine
component — which no layout ever mounted, so client-initiated toasts
(CSV-export failures, optimistic rollback nudges) were silently swallowed.
The vanilla host in `dz-toast.js` now owns both event shapes and renders
into the shell's `#dz-toast` stack with the same markup the server's
`with_toast` OOB emits (one dismiss path, one CSS contract).

HM dual-lock: packages/hatchi-maxchi/controllers/dz-toast.js is the
canonical host; this file is kept in sync for the Dazzle static bundle.
"""

from __future__ import annotations

from pathlib import Path

JS_FILE = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "page"
    / "runtime"
    / "static"
    / "js"
    / "dz-toast.js"
)

HM_JS = (
    Path(__file__).resolve().parents[2]
    / "packages"
    / "hatchi-maxchi"
    / "controllers"
    / "dz-toast.js"
)


class TestClientToastBridge:
    def test_listens_for_both_event_shapes(self) -> None:
        """`showToast` (document/body dispatches: optimistic rollback,
        server HX-Trigger) and `toast` on the stack (`window.dz.toast`)."""
        content = JS_FILE.read_text()
        assert '"showToast"' in content, "the showToast listener is missing"
        assert '"toast"' in content, "the dz.toast event listener is missing"

    def test_renders_server_parity_markup_into_the_stack(self) -> None:
        """Client toasts must be indistinguishable from server OOB toasts:
        same class, same tone attribute, same auto-dismiss attribute, into
        the same `#dz-toast` stack."""
        content = JS_FILE.read_text()
        assert 'getElementById("dz-toast")' in content
        assert "dz-toast-level" in content
        assert "data-dz-remove-after" in content
        assert "dz-toast__title" in content
        assert "dz-toast__message" in content
        assert "dz-toast__actions" in content

    def test_message_is_text_not_html(self) -> None:
        """The message travels via textContent — event detail is caller
        data and must never be interpreted as HTML."""
        content = JS_FILE.read_text()
        assert "textContent" in content
        assert "innerHTML" not in content

    def test_pause_resume_and_cap_are_present(self) -> None:
        content = JS_FILE.read_text()
        assert "__dzToastPause" in content
        assert "__dzToastResume" in content
        assert "data-dz-toast-cap" in content
        assert "data-dz-toast-dismiss" in content

    def test_default_delay_is_eight_seconds(self) -> None:
        """Readable default aligned with common toast UX (not a blink)."""
        content = JS_FILE.read_text()
        assert 'DEFAULT_DELAY = "8s"' in content

    def test_leave_motion_before_remove(self) -> None:
        content = JS_FILE.read_text()
        assert "dz-toast-leave" in content
        assert "dismissToast" in content
        assert "animationend" in content

    def test_ttl_progress_and_error_delay(self) -> None:
        content = JS_FILE.read_text()
        assert "dz-toast__progress" in content
        assert 'ERROR_DELAY = "10s"' in content
        assert "ensureProgress" in content

    def test_dazzle_host_matches_hm_controller(self) -> None:
        """Dual-lock: Dazzle static copy must not drift from HM controller."""
        assert JS_FILE.read_text() == HM_JS.read_text()
