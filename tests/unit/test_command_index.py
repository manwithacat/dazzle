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


# ---------------------------------------------------------------------------
# #1539 — the palette derives from the SAME NavModel the sidebar renders
# (the "never surfaces a destination that would 403" contract), and the
# handler honours the app's auth posture.
# ---------------------------------------------------------------------------


def test_nav_model_entries_map_groups_and_links() -> None:
    from dazzle.page.command_index import nav_model_entries
    from dazzle.page.converters.nav_builder import NavGroup, NavLink, NavModel

    model = NavModel(
        groups=(
            NavGroup(
                label="Workspaces",
                icon=None,
                collapsed=False,
                links=(NavLink(label="Overview", route="/app/workspaces/open_ws"),),
            ),
            NavGroup(
                label="Records",
                icon=None,
                collapsed=False,
                links=(NavLink(label="Invoices", route="/app/invoices", icon="receipt"),),
            ),
        ),
        auto_discovered=True,
    )
    entries = nav_model_entries(model)
    assert [(e.label, e.url, e.group) for e in entries] == [
        ("Overview", "/app/workspaces/open_ws", "Workspaces"),
        ("Invoices", "/app/invoices", "Records"),
    ]
    assert entries[1].icon == "receipt"  # link icon wins over inference


class TestCommandHandlerPosture:
    def _handler(self, *, require_auth: bool, auth_ctx, persona_navs=None):
        from dazzle.http.runtime.page_routes import (
            _make_command_handler,
            _PageRouterConfig,
        )

        async def get_auth(request):
            return auth_ctx

        appspec = _appspec()
        deps = _PageRouterConfig(
            appspec=appspec,
            theme_css="",
            get_auth_context=get_auth,
            app_prefix="/app",
            require_auth_by_default=require_auth,
            persona_navs=persona_navs or {},
        )
        return _make_command_handler(deps, appspec, "/app")

    def _request(self):
        return SimpleNamespace(query_params={})

    def test_anonymous_denied_when_auth_enforced(self) -> None:
        import asyncio

        from fastapi import HTTPException

        handler = self._handler(require_auth=True, auth_ctx=None)
        with pytest.raises(HTTPException) as exc:
            asyncio.run(handler(self._request()))
        assert exc.value.status_code == 403

    def test_persona_gets_nav_derived_subset(self) -> None:
        import asyncio

        from dazzle.page.converters.nav_builder import NavGroup, NavLink, NavModel

        viewer_nav = NavModel(
            groups=(
                NavGroup(
                    label="Records",
                    icon=None,
                    collapsed=False,
                    links=(NavLink(label="Invoices", route="/app/invoices"),),
                ),
            ),
            auto_discovered=True,
        )
        auth_ctx = SimpleNamespace(
            is_authenticated=True,
            user=SimpleNamespace(roles=["role_viewer"], is_superuser=False),
        )
        handler = self._handler(
            require_auth=True, auth_ctx=auth_ctx, persona_navs={"viewer": viewer_nav}
        )
        html = asyncio.run(handler(self._request())).body.decode()
        assert "Invoices" in html
        # NOT the unfiltered index: the admin-gated workspace stays out
        assert "Admin" not in html

    def test_superuser_keeps_full_index(self) -> None:
        import asyncio

        auth_ctx = SimpleNamespace(
            is_authenticated=True,
            user=SimpleNamespace(roles=[], is_superuser=True),
        )
        handler = self._handler(require_auth=True, auth_ctx=auth_ctx)
        html = asyncio.run(handler(self._request())).body.decode()
        assert "Admin" in html and "Overview" in html and "Invoice" in html
