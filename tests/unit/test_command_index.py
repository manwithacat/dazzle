"""Command-palette index — persona-scoped destinations, filtering."""

from types import SimpleNamespace

import pytest

from dazzle.core.ir import PersonaSpec
from dazzle.core.ir.workspaces import (
    WorkspaceAccessLevel,
    WorkspaceAccessSpec,
    WorkspaceSpec,
)
from dazzle.page.command_index import (
    CommandEntry,
    build_command_index,
    filter_command_index,
)

pytestmark = pytest.mark.gate


def _appspec() -> SimpleNamespace:
    admin_ws = WorkspaceSpec(
        name="admin_ws",
        title="Admin",
        access=WorkspaceAccessSpec(level=WorkspaceAccessLevel.PERSONA, allow_personas=["admin"]),
    )
    open_ws = WorkspaceSpec(name="open_ws", title="Overview")
    entity = SimpleNamespace(name="Invoice", title="Invoice")
    surface = SimpleNamespace(mode=SimpleNamespace(value="list"), entity_ref="Invoice")
    return SimpleNamespace(
        workspaces=[admin_ws, open_ws],
        personas=[PersonaSpec(id="admin", label="Admin"), PersonaSpec(id="viewer", label="Viewer")],
        surfaces=[surface],
        domain=SimpleNamespace(entities=[entity]),
    )


def test_viewer_sees_only_open_workspace_and_records() -> None:
    idx = build_command_index(_appspec(), roles=["role_viewer"])
    ws = {e.label for e in idx if e.group == "Workspaces"}
    assert ws == {"Overview"}  # admin_ws gated out
    records = {e.label for e in idx if e.group == "Records"}
    assert records == {"Invoice"}


def test_admin_sees_gated_workspace() -> None:
    idx = build_command_index(_appspec(), roles=["role_admin"])
    assert "Admin" in {e.label for e in idx}


def test_superuser_sees_everything() -> None:
    idx = build_command_index(_appspec(), roles=[], is_superuser=True)
    assert {"Admin", "Overview"} <= {e.label for e in idx}


def test_entries_carry_registry_icons_and_urls() -> None:
    idx = build_command_index(_appspec(), roles=["role_admin"], app_prefix="/app")
    inv = next(e for e in idx if e.label == "Invoice")
    assert inv.url == "/app/invoices"
    assert inv.icon  # inferred, registry-closed by nav_icons
    ws = next(e for e in idx if e.label == "Overview")
    assert ws.url == "/app/workspaces/open_ws"


def test_filter_prefix_ranks_before_midstring() -> None:
    entries = [
        CommandEntry("Invoices", "/a", "receipt", "Records"),
        CommandEntry("Overdue invoices", "/b", "receipt", "Records"),
    ]
    got = filter_command_index(entries, "inv")
    assert [e.label for e in got] == ["Invoices", "Overdue invoices"]


def test_filter_empty_returns_all() -> None:
    entries = [CommandEntry("X", "/x", "list", "Records")]
    assert filter_command_index(entries, "  ") == entries
