"""Tests for the structured 403 detail helper (#808).

The helper turns a plain "Forbidden" response into a disclosure that
the error template can use to render "signed in as X; this page
requires Y". The rules the helper reads live on the CedarAccessSpec
— tests here synthesise the minimum shape the helper needs, not the
full spec.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import pytest

from dazzle_back.runtime.route_generator import _forbidden_detail


class _FakeOp(Enum):
    LIST = "list"
    READ = "read"
    CREATE = "create"


@dataclass
class _FakeRule:
    operation: _FakeOp
    personas: list[str] = field(default_factory=list)


@dataclass
class _FakeSpec:
    permissions: list[_FakeRule] = field(default_factory=list)


class TestForbiddenDetail:
    def test_returns_permitted_personas_for_matching_operation(self) -> None:
        spec = _FakeSpec(
            permissions=[
                _FakeRule(_FakeOp.LIST, ["agent", "manager"]),
                _FakeRule(_FakeOp.READ, ["agent", "customer"]),
                _FakeRule(_FakeOp.CREATE, ["admin"]),
            ]
        )
        detail = _forbidden_detail(
            entity_name="Ticket",
            operation=_FakeOp.LIST,
            cedar_access_spec=spec,
            current_roles=["customer"],
        )
        assert detail["entity"] == "Ticket"
        assert detail["operation"] == "list"
        assert detail["permitted_personas"] == ["agent", "manager"]
        assert detail["current_roles"] == ["customer"]

    def test_dedupes_personas_across_multiple_rules(self) -> None:
        spec = _FakeSpec(
            permissions=[
                _FakeRule(_FakeOp.LIST, ["agent"]),
                _FakeRule(_FakeOp.LIST, ["agent", "manager"]),
            ]
        )
        detail = _forbidden_detail(
            entity_name="Ticket",
            operation=_FakeOp.LIST,
            cedar_access_spec=spec,
            current_roles=[],
        )
        assert detail["permitted_personas"] == ["agent", "manager"]

    def test_accepts_string_operation(self) -> None:
        """Site 1 (per-entity gate) passes operation as a string like
        'create' rather than the enum."""
        spec = _FakeSpec(
            permissions=[_FakeRule(_FakeOp.CREATE, ["admin"])],
        )
        detail = _forbidden_detail(
            entity_name="Ticket",
            operation="create",
            cedar_access_spec=spec,
            current_roles=[],
        )
        assert detail["operation"] == "create"
        assert detail["permitted_personas"] == ["admin"]

    def test_empty_permissions_returns_empty_list(self) -> None:
        spec = _FakeSpec(permissions=[])
        detail = _forbidden_detail(
            entity_name="Ticket",
            operation=_FakeOp.LIST,
            cedar_access_spec=spec,
            current_roles=["customer"],
        )
        assert detail["permitted_personas"] == []

    def test_includes_humanised_message(self) -> None:
        spec = _FakeSpec(permissions=[])
        detail = _forbidden_detail(
            entity_name="Alert",
            operation=_FakeOp.READ,
            cedar_access_spec=spec,
            current_roles=[],
        )
        assert "read" in detail["message"].lower()
        assert "Alert" in detail["message"]

    def test_malformed_spec_does_not_shadow_the_403(self) -> None:
        """If the spec has a weird shape (misconfigured at generation
        time), the helper must still return a usable dict — we don't
        want to leak a secondary exception from an error-path helper."""

        class Broken:
            @property
            def permissions(self) -> list[_FakeRule]:
                raise RuntimeError("boom")

        detail = _forbidden_detail(
            entity_name="Ticket",
            operation=_FakeOp.LIST,
            cedar_access_spec=Broken(),
            current_roles=[],
        )
        assert detail["permitted_personas"] == []
        assert detail["entity"] == "Ticket"

    @pytest.mark.parametrize(
        "op, expected",
        [
            (_FakeOp.LIST, "list"),
            ("list", "list"),
            ("LIST", "list"),
        ],
    )
    def test_operation_string_is_normalised_lowercase(self, op: object, expected: str) -> None:
        spec = _FakeSpec(permissions=[])
        detail = _forbidden_detail(
            entity_name="X",
            operation=op,  # type: ignore[arg-type]
            cedar_access_spec=spec,
            current_roles=[],
        )
        assert detail["operation"] == expected
