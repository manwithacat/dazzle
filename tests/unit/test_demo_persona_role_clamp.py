"""Persona default_role must clamp to User.role enum when generating demo users."""

from __future__ import annotations

from types import SimpleNamespace

from dazzle.demo_data.blueprint_generator import _resolve_persona_role


def _entity(enum_values: list[str] | None) -> SimpleNamespace:
    patterns = []
    if enum_values is not None:
        patterns.append(SimpleNamespace(field_name="role", params={"enum_values": enum_values}))
    return SimpleNamespace(field_patterns=patterns)


class TestResolvePersonaRole:
    def test_strips_role_prefix_into_enum(self) -> None:
        entity = _entity(["customer", "agent", "manager"])
        p = SimpleNamespace(default_role="role_staff", persona_name="Staff")
        assert _resolve_persona_role(entity, p) == "agent"

    def test_role_agent_maps(self) -> None:
        entity = _entity(["customer", "agent", "manager"])
        p = SimpleNamespace(default_role="role_agent", persona_name="Agent")
        assert _resolve_persona_role(entity, p) == "agent"

    def test_passthrough_when_valid(self) -> None:
        entity = _entity(["customer", "agent", "manager"])
        p = SimpleNamespace(default_role="manager", persona_name="Mgr")
        assert _resolve_persona_role(entity, p) == "manager"

    def test_no_enum_keeps_raw(self) -> None:
        entity = _entity(None)
        p = SimpleNamespace(default_role="role_staff", persona_name="Staff")
        assert _resolve_persona_role(entity, p) == "role_staff"
