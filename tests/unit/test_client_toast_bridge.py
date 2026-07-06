"""Structural ratchets for the client-initiated toast path (C3 orphan sweep).

The bug this pins against: `window.dz.toast()` and the optimistic-rollback
path dispatched events whose ONLY listener was the `dzToast` Alpine
component — which no layout ever mounted, so client-initiated toasts
(CSV-export failures, optimistic rollback nudges) were silently swallowed.
The vanilla bridge in `dz-toast.js` now owns both event shapes and renders
into the shell's `#dz-toast` stack with the same markup the server's
`with_toast` OOB emits (one dismiss path, one CSS contract).

Behavioural coverage arrives with the HM `toast` Hyperpart (Bucket C-T2);
these source pins hold the seam until then.
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

    def test_message_is_text_not_html(self) -> None:
        """The message travels via textContent — event detail is caller
        data and must never be interpreted as HTML."""
        content = JS_FILE.read_text()
        assert "textContent" in content
        assert "innerHTML" not in content
