"""Tests for #959 cycle 1 — x-optimistic Alpine directive.

The directive applies a DOM change (currently `remove` only) before
the htmx response settles, then keeps the change on success or rolls
it back on 4xx/5xx + network error. Closes the perceived-latency gap
on click-to-delete actions.

Cycle 1 ships only the `remove` shape. Future cycles add prepend /
append / replace shapes plus reconciliation with server response.
"""

from __future__ import annotations

from pathlib import Path

import pytest

DZ_ALPINE_JS = Path(__file__).resolve().parents[2] / "src/dazzle_ui/runtime/static/js/dz-alpine.js"


@pytest.fixture(scope="module")
def js() -> str:
    assert DZ_ALPINE_JS.is_file(), f"dz-alpine.js not found at {DZ_ALPINE_JS}"
    return DZ_ALPINE_JS.read_text()


def test_directive_registered(js: str) -> None:
    """Alpine.directive('optimistic', ...) must be present so
    x-optimistic in templates resolves to the handler."""
    assert 'Alpine.directive("optimistic"' in js


def test_remove_shape_implemented(js: str) -> None:
    """Cycle 1 ships the remove shape — the workhorse for instant
    delete actions. Cycle 2 added prepend/append/replace; remove
    must still be in the verb set."""
    assert '"remove"' in js


def test_unknown_shape_warns(js: str) -> None:
    """Unknown verbs (typos, future-renamed shapes) should produce
    a visible console warning so adopters get feedback rather than
    silent no-ops. Cycle 2 changed the warning text to list all
    accepted shapes."""
    assert "console.warn" in js
    assert "not recognised" in js
    assert "Known shapes" in js


def test_supports_closest_selector_form(js: str) -> None:
    """Mirror htmx's `closest <selector>` semantics — most common
    pattern in DSL-rendered list rows where the button is inside
    the row it's deleting."""
    assert 'startsWith("closest ")' in js


def test_subscribes_to_htmx_lifecycle_events(js: str) -> None:
    """The directive needs all three htmx events:
    - beforeRequest: apply optimistic change
    - afterRequest: keep on success, rollback on error
    - sendError: rollback on network failure (no response)
    """
    assert 'addEventListener("htmx:beforeRequest"' in js
    assert 'addEventListener("htmx:afterRequest"' in js
    assert 'addEventListener("htmx:sendError"' in js


def test_only_reacts_to_own_events(js: str) -> None:
    """htmx events bubble. If the directive reacted to a child's
    htmx request it would rip the row out mid-handler. Filter via
    `ev.target !== el` so only the bound element's mutations
    trigger the directive."""
    assert "ev.target !== el" in js


def test_snapshots_parent_and_next_sibling_for_rollback(js: str) -> None:
    """Re-insert at the original position on rollback — not just
    appendChild. The snapshot needs both the parent and the
    nextSibling reference."""
    assert "parent" in js and "nextSibling" in js
    # Both keys must appear in the snapshot object construction.
    snapshot_idx = js.find("snapshot = {")
    assert snapshot_idx != -1
    snapshot_block = js[snapshot_idx : snapshot_idx + 200]
    assert "parent:" in snapshot_block
    assert "nextSibling:" in snapshot_block


def test_rollback_uses_insertBefore(js: str) -> None:
    """The standard DOM API for "insert at position" is
    parent.insertBefore(node, anchor). Falls back to appendChild
    when the original anchor is gone (defensive)."""
    assert "insertBefore" in js
    assert "appendChild" in js


def test_rollback_dispatches_custom_event(js: str) -> None:
    """Adopters may want custom recovery UI — dispatch a
    `dz:optimistic-rollback` event with the failure reason in detail
    so they can hook in."""
    assert '"dz:optimistic-rollback"' in js
    # bubbles:true so a parent list container can delegate.
    rollback_idx = js.find('"dz:optimistic-rollback"')
    bubbles_idx = js.find("bubbles: true", rollback_idx)
    assert 0 < bubbles_idx - rollback_idx < 200


def test_rollback_emits_toast(js: str) -> None:
    """Default UX: surface the failure via the existing toast
    system so the user knows the action didn't take effect."""
    assert "showToast" in js
    # Find the showToast dispatch near the restore() function.
    restore_idx = js.find("const restore = (reason)")
    if restore_idx != -1:
        restore_block = js[restore_idx : restore_idx + 1500]
        assert "showToast" in restore_block
        assert '"error"' in restore_block


def test_response_error_branch(js: str) -> None:
    """Response-error path: 4xx/5xx fires afterRequest with
    successful=false. The directive checks both `ev.detail.successful`
    (htmx 1.x convention) and falls back to xhr.status."""
    assert "successful" in js
    assert "xhr.status < 400" in js


def test_directive_listed_in_module_header(js: str) -> None:
    """Public-API list entry — discoverability for future readers."""
    assert "x-optimistic" in js


def test_directive_present_in_dist_bundle() -> None:
    """css_loader / build_dist must bundle the directive so customer
    apps that include the dist actually get it."""
    dist_js = (
        Path(__file__).resolve().parents[2] / "src/dazzle_ui/runtime/static/dist/dazzle.min.js"
    )
    if not dist_js.is_file():
        pytest.skip("dist not built")
    text = dist_js.read_text()
    # Minified — search by registration string fragment that survives.
    assert "optimistic" in text
    assert "dz:optimistic-rollback" in text
