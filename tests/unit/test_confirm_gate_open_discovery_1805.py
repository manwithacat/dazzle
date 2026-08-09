"""Cycle 1805 — ConfirmGate + workspace heading open-discovery stamps.

Agents attr-read confirm / revoke / re-enable hops without scraping button
copy. Non-app paths (legacy ``/admin/…`` tests) stay unstamped — parity with
create/edit open-discovery path gate.
"""

from __future__ import annotations

from dazzle.render.fragment.context import RenderContext
from dazzle.render.fragment.primitives import (
    ConfirmCheckItem,
    ConfirmGate,
    Text,
    WorkspacePrimaryAction,
    WorkspaceShell,
)
from dazzle.render.fragment.renderer import FragmentRenderer
from dazzle.render.open_discovery import (
    confirm_action_open_attrs,
    open_hop_label,
)


def _render_confirm(gate: ConfirmGate) -> str:
    return FragmentRenderer()._emit_confirm_gate(gate, RenderContext())


def test_open_hop_label_confirm_revoke_reenable() -> None:
    assert open_hop_label("Integration", "confirm") == "Confirm Integration"
    assert open_hop_label("Integration", "revoke") == "Revoke Integration"
    assert open_hop_label("Integration", "re-enable") == "Re-enable Integration"
    assert open_hop_label("Integration", "reenable") == "Re-enable Integration"


def test_confirm_action_open_attrs_stamps_markers() -> None:
    primary = confirm_action_open_attrs("/app/integration/i-1/enable", via="confirm")
    assert "data-dz-confirm-drill" in primary
    assert 'data-dz-open-via="confirm"' in primary
    assert "Confirm Integration" in primary
    assert 'data-dz-open-chain="/app/integration/i-1/enable"' in primary

    revoke = confirm_action_open_attrs("/app/integration/i-1/disable", via="revoke")
    assert "data-dz-revoke-drill" in revoke
    assert 'data-dz-open-via="revoke"' in revoke
    assert "Revoke Integration" in revoke

    re_en = confirm_action_open_attrs("/app/integration/i-1/enable", via="re-enable")
    assert "data-dz-confirm-drill" in re_en
    assert 'data-dz-open-via="re-enable"' in re_en
    assert "Re-enable Integration" in re_en


def test_confirm_action_skips_non_app_paths() -> None:
    assert confirm_action_open_attrs("/admin/sync/confirm", via="confirm") == ""
    assert confirm_action_open_attrs("#", via="confirm") == ""


def test_confirm_gate_primary_secondary_stamps_open_discovery() -> None:
    html = _render_confirm(
        ConfirmGate(
            state="off",
            primary_action_url="/app/integration/i-1/enable",
            secondary_action_url="/app/integration/i-1",
            primary_label="Enable",
            secondary_label="Save draft",
        )
    )
    assert "data-dz-confirm-drill" in html
    assert 'data-dz-open-via="confirm"' in html
    assert "Confirm Integration" in html
    # secondary is VIEW-style ref hop on /app/integration/i-1
    assert "data-dz-ref-link-drill" in html
    assert 'data-dz-open-chain="/app/integration/i-1"' in html


def test_confirm_gate_checklist_disarmed_still_stamps_open_discovery() -> None:
    """Open attrs live on the element even when href is parked in confirm-href."""
    html = _render_confirm(
        ConfirmGate(
            state="off",
            primary_action_url="/app/integration/i-1/enable",
            primary_label="Commit",
            confirmations=(ConfirmCheckItem(title="OK", required=True),),
        )
    )
    assert 'data-dz-confirm-href="/app/integration/i-1/enable"' in html
    assert "data-dz-confirm-drill" in html
    assert 'data-dz-open-via="confirm"' in html
    assert "aria-disabled" in html


def test_confirm_gate_live_revoke_stamps_open_discovery() -> None:
    html = _render_confirm(
        ConfirmGate(
            state="live",
            revoke_url="/app/integration/i-1/disable",
            revoke_label="Disable",
        )
    )
    assert "data-dz-revoke-drill" in html
    assert 'data-dz-open-via="revoke"' in html
    assert "Revoke Integration" in html


def test_confirm_gate_revoked_reenable_stamps_open_discovery() -> None:
    html = _render_confirm(
        ConfirmGate(
            state="revoked",
            primary_action_url="/app/integration/i-1/enable",
            re_enable_label="Re-enable",
        )
    )
    assert "data-dz-confirm-drill" in html
    assert 'data-dz-open-via="re-enable"' in html
    assert "Re-enable Integration" in html


def test_confirm_gate_legacy_admin_paths_unstamped() -> None:
    """Existing /admin/… fixtures must not grow open-discovery attrs."""
    html = _render_confirm(
        ConfirmGate(
            state="off",
            primary_action_url="/admin/sync/confirm",
            secondary_action_url="/admin/sync/draft",
            confirmations=(ConfirmCheckItem(title="OK", required=True),),
        )
    )
    assert "data-dz-confirm-drill" not in html
    assert "data-dz-open-entity" not in html
    assert 'data-dz-confirm-href="/admin/sync/confirm"' in html


def test_workspace_primary_action_stamps_create_open_discovery() -> None:
    html = FragmentRenderer()._emit_workspace_shell(
        WorkspaceShell(
            workspace_name="dash",
            title="Dash",
            body=Text(body="hi"),
            primary_actions=(
                WorkspacePrimaryAction(label="New ticket", route="/app/ticket/create"),
            ),
        ),
        RenderContext(),
    )
    assert "dz-workspace-action" in html
    assert "data-dz-create-drill" in html
    assert 'data-dz-open-via="create"' in html
    assert "Create Ticket" in html
