"""Tests for manwithacat/dazzle#775 fix: workspace_allowed_personas shared helper.

The cycle-199/201/216/217 ``/ux-cycle`` explore loop found that 4 different
example apps exhibited the same defect: sidebar nav showed workspace
links that the current persona could not actually access. Root cause:
the enforcement path (``_workspace_handler``) and the sidebar nav
generator (``template_compiler``) used **different** rules for resolving
"who can see this workspace", and only the enforcement path considered
``persona.default_workspace`` when no explicit ``access:`` declaration
existed.

The fix introduces ``workspace_allowed_personas`` as the single source
of truth. Both paths now call it, so the sidebar and the 403 enforcer
agree byte-for-byte.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from dazzle_ui.converters.workspace_converter import workspace_allowed_personas


@dataclass
class _AccessStub:
    allow_personas: list[str] = field(default_factory=list)
    deny_personas: list[str] = field(default_factory=list)


@dataclass
class _WorkspaceStub:
    name: str
    access: _AccessStub | None = None


@dataclass
class _PersonaStub:
    id: str
    default_workspace: str | None = None


class TestExplicitAllowPersonas:
    """Rule 1: explicit access.allow_personas wins."""

    def test_allow_list_returns_verbatim(self) -> None:
        ws = _WorkspaceStub(
            name="ticket_queue",
            access=_AccessStub(allow_personas=["admin", "agent"]),
        )
        personas = [
            _PersonaStub("admin"),
            _PersonaStub("agent"),
            _PersonaStub("customer"),
        ]
        result = workspace_allowed_personas(ws, personas)
        assert result == ["admin", "agent"]

    def test_allow_takes_precedence_over_deny(self) -> None:
        ws = _WorkspaceStub(
            name="ticket_queue",
            access=_AccessStub(
                allow_personas=["admin"],
                deny_personas=["customer"],
            ),
        )
        personas = [
            _PersonaStub("admin"),
            _PersonaStub("customer"),
        ]
        result = workspace_allowed_personas(ws, personas)
        assert result == ["admin"]

    def test_allow_preserves_order(self) -> None:
        """DSL-declared ordering is preserved for deterministic nav rendering."""
        ws = _WorkspaceStub(
            name="ticket_queue",
            access=_AccessStub(allow_personas=["agent", "admin", "manager"]),
        )
        personas = [
            _PersonaStub("manager"),
            _PersonaStub("admin"),
            _PersonaStub("agent"),
        ]
        result = workspace_allowed_personas(ws, personas)
        assert result == ["agent", "admin", "manager"]


class TestExplicitDenyPersonas:
    """Rule 2: explicit access.deny_personas inverts the persona list."""

    def test_deny_excludes_only_denied(self) -> None:
        ws = _WorkspaceStub(
            name="ticket_queue",
            access=_AccessStub(deny_personas=["customer"]),
        )
        personas = [
            _PersonaStub("admin"),
            _PersonaStub("agent"),
            _PersonaStub("customer"),
            _PersonaStub("manager"),
        ]
        result = workspace_allowed_personas(ws, personas)
        assert result == ["admin", "agent", "manager"]

    def test_deny_of_all_personas_returns_empty_list(self) -> None:
        """Denying everyone produces an empty list (legitimate but unusual)."""
        ws = _WorkspaceStub(
            name="locked",
            access=_AccessStub(deny_personas=["admin", "agent"]),
        )
        personas = [_PersonaStub("admin"), _PersonaStub("agent")]
        result = workspace_allowed_personas(ws, personas)
        assert result == []


class TestImplicitDefaultWorkspace:
    """Rule 3: persona.default_workspace inference when no explicit access."""

    def test_only_claimant_personas(self) -> None:
        """support_tickets-style scenario: no access: declaration but
        each persona claims a default_workspace."""
        ws = _WorkspaceStub(name="ticket_queue")  # no access declared
        personas = [
            _PersonaStub("admin", default_workspace="admin_dashboard"),
            _PersonaStub("agent", default_workspace="ticket_queue"),
            _PersonaStub("customer", default_workspace="my_tickets"),
        ]
        result = workspace_allowed_personas(ws, personas)
        assert result == ["agent"]

    def test_multiple_claimants(self) -> None:
        """Several personas can share a default workspace."""
        ws = _WorkspaceStub(name="shared_dashboard")
        personas = [
            _PersonaStub("admin", default_workspace="shared_dashboard"),
            _PersonaStub("agent", default_workspace="shared_dashboard"),
            _PersonaStub("customer", default_workspace="my_tickets"),
        ]
        result = workspace_allowed_personas(ws, personas)
        assert result == ["admin", "agent"]


class TestFallbackAllPersonas:
    """Rule 4: fallback when no explicit access and no default_workspace claim."""

    def test_returns_none_for_truly_open_workspace(self) -> None:
        """A workspace nobody claims as default and with no access: returns None
        meaning 'visible to every authenticated user' (backward compat)."""
        ws = _WorkspaceStub(name="orphan_workspace")
        personas = [
            _PersonaStub("admin", default_workspace="admin_dashboard"),
            _PersonaStub("agent", default_workspace="ticket_queue"),
        ]
        result = workspace_allowed_personas(ws, personas)
        assert result is None

    def test_returns_none_with_no_personas(self) -> None:
        """Degenerate case: no personas at all → fall through to None."""
        ws = _WorkspaceStub(name="anything")
        result = workspace_allowed_personas(ws, [])
        assert result is None


class TestEdgeCases:
    """Defensive checks for the kinds of inputs real AppSpecs produce."""

    def test_empty_access_object_is_treated_as_no_access(self) -> None:
        """An access object with empty allow AND empty deny should fall through
        to the default_workspace inference (or None if no claimants)."""
        ws = _WorkspaceStub(
            name="ticket_queue",
            access=_AccessStub(allow_personas=[], deny_personas=[]),
        )
        personas = [
            _PersonaStub("agent", default_workspace="ticket_queue"),
            _PersonaStub("admin", default_workspace="admin_dashboard"),
        ]
        result = workspace_allowed_personas(ws, personas)
        assert result == ["agent"]

    def test_access_none_falls_through_to_inference(self) -> None:
        """Workspace with ``access=None`` (no DSL block) must not crash."""
        ws = _WorkspaceStub(name="public_landing", access=None)
        personas = [
            _PersonaStub("admin", default_workspace="admin_dashboard"),
        ]
        result = workspace_allowed_personas(ws, personas)
        assert result is None


class TestSupportTicketsScenario:
    """End-to-end fixture matching the actual support_tickets shape that
    originally surfaced manwithacat/dazzle#775 in cycle 199."""

    def test_agent_only_sees_agent_workspaces(self) -> None:
        """support_tickets has 3 workspaces, no explicit access: declarations,
        and personas with distinct default_workspace values. The agent should
        only see ticket_queue + agent_dashboard (their claimed workspaces)."""
        tickets = _WorkspaceStub(name="ticket_queue")  # agent claims
        agent_db = _WorkspaceStub(name="agent_dashboard")  # agent claims
        customer_db = _WorkspaceStub(name="my_tickets")  # customer claims

        personas = [
            _PersonaStub("admin", default_workspace="agent_dashboard"),
            _PersonaStub("agent", default_workspace="ticket_queue"),
            _PersonaStub("customer", default_workspace="my_tickets"),
            _PersonaStub("manager", default_workspace="agent_dashboard"),
        ]

        # Agent should appear in ticket_queue (claimed as default)
        assert "agent" in (workspace_allowed_personas(tickets, personas) or [])
        # Agent should NOT appear in my_tickets
        assert "agent" not in (workspace_allowed_personas(customer_db, personas) or [])
        # Agent should NOT appear in agent_dashboard (admin+manager claim it)
        assert "agent" not in (workspace_allowed_personas(agent_db, personas) or [])
        # Admin + manager DO appear in agent_dashboard
        ad_allowed = workspace_allowed_personas(agent_db, personas)
        assert ad_allowed is not None
        assert "admin" in ad_allowed
        assert "manager" in ad_allowed
