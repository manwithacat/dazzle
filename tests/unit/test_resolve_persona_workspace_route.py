"""Tests for the cycle 227 `resolve_persona_workspace_route` helper.

Introduced to close EX-042: `_root_redirect` in page_routes.py previously
built its persona→workspace mapping by checking `persona.default_workspace`
alone, falling back to `workspaces[0]` for any persona that didn't declare
one. For most apps `workspaces[0]` is the privileged/admin workspace, so
non-admin personas would get 403 on login and be stuck in a dead-end loop.

Cycle 227's fix is a workspace-only variant of `_resolve_persona_route`
that skips the `default_route` step and climbs a 4-step fallback chain
ending at `workspaces[0]`. The workspace-only variant sidesteps a
regression cycle 227 discovered on simple_task: its DSL declares
``default_route: "/admin"`` values that are NOT registered as real
routes, so naïvely honouring `default_route` would redirect users to
404 pages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from dazzle_ui.converters.workspace_converter import (
    resolve_persona_workspace_route,
)


class _AccessLevel(str, Enum):
    PUBLIC = "public"
    AUTHENTICATED = "authenticated"
    PERSONA = "persona"


@dataclass
class _AccessStub:
    level: _AccessLevel = _AccessLevel.PERSONA
    allow_personas: list[str] = field(default_factory=list)
    deny_personas: list[str] = field(default_factory=list)


@dataclass
class _WorkspaceStub:
    name: str
    access: _AccessStub | None = None


@dataclass
class _PersonaStub:
    id: str
    label: str = "label"
    default_workspace: str | None = None
    default_route: str | None = None


class TestDefaultWorkspaceWins:
    """Rule 1 of the fallback chain."""

    def test_default_workspace_resolved_to_full_route(self) -> None:
        """When persona.default_workspace matches an existing workspace,
        return its `/app/workspaces/<name>` route."""
        ws = _WorkspaceStub(name="my_work")
        persona = _PersonaStub(id="member", default_workspace="my_work")
        assert resolve_persona_workspace_route(persona, [ws]) == "/app/workspaces/my_work"

    def test_default_workspace_skipped_when_not_found(self) -> None:
        """If persona.default_workspace doesn't match any workspace in the
        list, fall through to the next step (not crash)."""
        ws = _WorkspaceStub(name="my_work")
        persona = _PersonaStub(id="member", default_workspace="nonexistent")
        # Should fall through to step 4 (first workspace fallback)
        assert resolve_persona_workspace_route(persona, [ws]) == "/app/workspaces/my_work"


class TestExplicitAccessFallback:
    """Rule 2: first workspace whose access.allow_personas lists this persona."""

    def test_no_default_workspace_matches_on_explicit_access(self) -> None:
        """Persona with no default_workspace but explicit access match →
        return that workspace."""
        ws_admin = _WorkspaceStub(
            name="admin_only",
            access=_AccessStub(allow_personas=["admin"]),
        )
        ws_tester = _WorkspaceStub(
            name="tester_dashboard",
            access=_AccessStub(allow_personas=["tester"]),
        )
        persona = _PersonaStub(id="tester")  # no default_workspace
        assert (
            resolve_persona_workspace_route(persona, [ws_admin, ws_tester])
            == "/app/workspaces/tester_dashboard"
        )

    def test_explicit_access_wins_over_fallback_order(self) -> None:
        """Should skip workspaces_admin ([0]) and pick the one that lists
        the persona, not the first declared workspace."""
        ws_admin = _WorkspaceStub(
            name="admin_only",
            access=_AccessStub(allow_personas=["admin"]),
        )
        ws_engineer = _WorkspaceStub(
            name="engineering",
            access=_AccessStub(allow_personas=["engineer"]),
        )
        persona = _PersonaStub(id="engineer")
        assert (
            resolve_persona_workspace_route(persona, [ws_admin, ws_engineer])
            == "/app/workspaces/engineering"
        )


class TestAuthenticatedFallback:
    """Rule 3: first workspace with AUTHENTICATED access level."""

    def test_authenticated_workspace_used_when_no_persona_match(self) -> None:
        """If no workspace lists the persona explicitly and none matches
        default_workspace, but there's an AUTHENTICATED-level workspace,
        use that."""
        ws_admin = _WorkspaceStub(
            name="admin_only",
            access=_AccessStub(allow_personas=["admin"]),
        )
        ws_shared = _WorkspaceStub(
            name="shared",
            access=_AccessStub(level=_AccessLevel.AUTHENTICATED),
        )
        persona = _PersonaStub(id="customer")
        assert (
            resolve_persona_workspace_route(persona, [ws_admin, ws_shared])
            == "/app/workspaces/shared"
        )


class TestFirstWorkspaceFallback:
    """Rule 4: fallback to workspaces[0] when nothing else matches.

    This rule is the weakest and is the original source of EX-042. It
    still exists as a last-resort safety net, but the three earlier
    rules mean it should very rarely fire in practice for a properly
    DSL-specified app.
    """

    def test_first_workspace_used_as_last_resort(self) -> None:
        ws_first = _WorkspaceStub(name="first")
        ws_second = _WorkspaceStub(name="second")
        persona = _PersonaStub(id="nobody")
        assert (
            resolve_persona_workspace_route(persona, [ws_first, ws_second])
            == "/app/workspaces/first"
        )

    def test_empty_workspaces_returns_none(self) -> None:
        persona = _PersonaStub(id="anyone")
        assert resolve_persona_workspace_route(persona, []) is None


class TestDefaultRouteIsIgnoredDeliberately:
    """Regression test for the cycle 227 discovery.

    The earlier sibling helper `_resolve_persona_route` honours
    `persona.default_route` at step 1 and returns it verbatim. simple_task's
    DSL declares ``default_route: "/admin"`` for its admin persona —
    but ``/admin`` is NOT a registered route in simple_task, so if
    `_root_redirect` consumed the `default_route` value it would
    redirect admins to a 404 page.

    The workspace-only variant MUST ignore `default_route` entirely.
    This test locks that behaviour.
    """

    def test_default_route_is_ignored(self) -> None:
        ws = _WorkspaceStub(name="admin_dashboard")
        persona = _PersonaStub(
            id="admin",
            default_workspace="admin_dashboard",
            default_route="/admin",  # would be wrong to return this
        )
        # Must return the workspace route, NOT the default_route.
        assert resolve_persona_workspace_route(persona, [ws]) == "/app/workspaces/admin_dashboard"

    def test_default_route_ignored_even_without_default_workspace(self) -> None:
        ws_admin = _WorkspaceStub(
            name="admin_dashboard",
            access=_AccessStub(allow_personas=["admin"]),
        )
        persona = _PersonaStub(
            id="admin",
            default_route="/admin",  # DSL-declared but unregistered route
            # no default_workspace set
        )
        assert (
            resolve_persona_workspace_route(persona, [ws_admin])
            == "/app/workspaces/admin_dashboard"
        )


class TestFieldtestHubShape:
    """End-to-end shape matching fieldtest_hub's actual DSL.

    Originally surfaced EX-035 via cycle 223, which cascaded into cycle
    225's parser fix and cycle 227's structural cleanup. Each persona
    should deterministically land on the right workspace regardless of
    which path triggered the resolution.
    """

    def _fieldtest_hub(self) -> tuple[list[_WorkspaceStub], list[_PersonaStub]]:
        workspaces = [
            _WorkspaceStub(
                name="engineering_dashboard",
                access=_AccessStub(allow_personas=["engineer", "manager"]),
            ),
            _WorkspaceStub(
                name="tester_dashboard",
                access=_AccessStub(allow_personas=["tester"]),
            ),
            _WorkspaceStub(
                name="_platform_admin",
                access=_AccessStub(allow_personas=["admin", "super_admin"]),
            ),
        ]
        personas = [
            _PersonaStub(id="admin", default_workspace="_platform_admin"),
            _PersonaStub(id="engineer", default_workspace="engineering_dashboard"),
            _PersonaStub(id="tester", default_workspace="tester_dashboard"),
            _PersonaStub(id="manager", default_workspace="engineering_dashboard"),
        ]
        return workspaces, personas

    def test_each_persona_lands_on_own_workspace(self) -> None:
        workspaces, personas = self._fieldtest_hub()
        routes = {p.id: resolve_persona_workspace_route(p, workspaces) for p in personas}
        assert routes == {
            "admin": "/app/workspaces/_platform_admin",
            "engineer": "/app/workspaces/engineering_dashboard",
            "tester": "/app/workspaces/tester_dashboard",
            "manager": "/app/workspaces/engineering_dashboard",
        }

    def test_tester_still_lands_correctly_without_default_workspace(self) -> None:
        """The cycle 225 parser bug was silently blanking
        `persona.default_workspace`. Even with that field zeroed, the
        workspace-only resolver's rule-2 access-based fallback should
        still pick the right workspace because fieldtest_hub's DSL
        explicitly grants `tester` access to `tester_dashboard`."""
        workspaces, personas = self._fieldtest_hub()
        tester = next(p for p in personas if p.id == "tester")
        tester.default_workspace = None

        route = resolve_persona_workspace_route(tester, workspaces)
        assert route == "/app/workspaces/tester_dashboard"
