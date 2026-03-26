"""
Tests for admin entity field definitions and the admin entity builder.

Covers:
  - Task 1: ADMIN_ENTITY_DEFS and individual FIELDS constants
  - Task 2: _build_admin_entities profile-gating and EntitySpec shape
"""

from __future__ import annotations

from dazzle.core.ir.admin_entities import (
    ADMIN_ENTITY_DEFS,
    VIRTUAL_ENTITY_NAMES,
)
from dazzle.core.ir.security import SecurityConfig, SecurityProfile

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_security(profile: SecurityProfile, *, multi_tenant: bool = False) -> SecurityConfig:
    """Construct a SecurityConfig from a profile shortcut."""
    return SecurityConfig.from_profile(profile, multi_tenant=multi_tenant)


# ---------------------------------------------------------------------------
# Task 1 — Field tuple shape tests
# ---------------------------------------------------------------------------


class TestFieldTuples:
    """Shape and content tests for the individual FIELDS constants."""

    def _all_field_tuples(
        self,
    ) -> list[tuple[str, str, tuple[str, ...], str | None]]:
        """Collect every field tuple across all entity defs."""
        result = []
        for _name, _title, _intent, fields_tuple, _patterns, _gate in ADMIN_ENTITY_DEFS:
            result.extend(fields_tuple)
        return result

    def test_field_tuples_have_correct_shape(self) -> None:
        """Every field tuple is (str, str, tuple, str|None)."""
        for entry in self._all_field_tuples():
            assert len(entry) == 4, f"Expected 4-tuple, got {entry!r}"
            name, type_str, modifiers, default = entry
            assert isinstance(name, str)
            assert isinstance(type_str, str)
            assert isinstance(modifiers, tuple)
            assert default is None or isinstance(default, str)

    def test_all_entities_have_pk(self) -> None:
        """Every entity definition has exactly one 'pk' field named 'id'."""
        for ent_name, _title, _intent, fields_tuple, _patterns, _gate in ADMIN_ENTITY_DEFS:
            pk_fields = [f for f in fields_tuple if "pk" in f[2]]
            assert len(pk_fields) == 1, (
                f"{ent_name}: expected exactly one pk field, got {pk_fields}"
            )
            assert pk_fields[0][0] == "id", (
                f"{ent_name}: pk field should be named 'id', got {pk_fields[0][0]!r}"
            )

    def test_admin_entity_defs_count(self) -> None:
        """ADMIN_ENTITY_DEFS contains exactly 5 entity definitions."""
        assert len(ADMIN_ENTITY_DEFS) == 5

    def test_virtual_entities_are_subset(self) -> None:
        """VIRTUAL_ENTITY_NAMES is a subset of all entity names in ADMIN_ENTITY_DEFS."""
        all_names = {entry[0] for entry in ADMIN_ENTITY_DEFS}
        assert VIRTUAL_ENTITY_NAMES <= all_names, (
            f"Virtual names not subset: {VIRTUAL_ENTITY_NAMES - all_names}"
        )


# ---------------------------------------------------------------------------
# Task 2 — _build_admin_entities tests
# ---------------------------------------------------------------------------


class TestBuildAdminEntities:
    """_build_admin_entities profile-gating and EntitySpec correctness."""

    def test_basic_profile_gets_all_profile_entities(self) -> None:
        """BASIC profile receives only entities with no profile gate (3 of 5)."""
        from dazzle.core.admin_builder import _build_admin_entities

        security = _make_security(SecurityProfile.BASIC)
        entities = _build_admin_entities(security)
        names = {e.name for e in entities}
        # profile_gate=None entities (available on all profiles)
        assert "SystemHealth" in names
        assert "DeployHistory" in names
        # profile_gate="standard" entities should NOT be present for basic
        assert "ProcessRun" not in names
        assert "SessionInfo" not in names

    def test_standard_profile_gets_all_entities(self) -> None:
        """STANDARD profile receives all 5 admin entities."""
        from dazzle.core.admin_builder import _build_admin_entities

        security = _make_security(SecurityProfile.STANDARD)
        entities = _build_admin_entities(security)
        assert len(entities) == 5

    def test_strict_profile_gets_all_entities(self) -> None:
        """STRICT profile receives all 5 admin entities."""
        from dazzle.core.admin_builder import _build_admin_entities

        security = _make_security(SecurityProfile.STRICT)
        entities = _build_admin_entities(security)
        assert len(entities) == 5

    def test_entities_have_platform_domain(self) -> None:
        """All generated entities carry domain='platform'."""
        from dazzle.core.admin_builder import _build_admin_entities

        security = _make_security(SecurityProfile.STRICT)
        for entity in _build_admin_entities(security):
            assert entity.domain == "platform", (
                f"{entity.name}: expected domain='platform', got {entity.domain!r}"
            )

    def test_entities_have_system_pattern(self) -> None:
        """All generated entities include 'system' in their patterns list."""
        from dazzle.core.admin_builder import _build_admin_entities

        security = _make_security(SecurityProfile.STRICT)
        for entity in _build_admin_entities(security):
            assert "system" in entity.patterns, (
                f"{entity.name}: 'system' not in patterns {entity.patterns!r}"
            )

    def test_entities_are_read_only(self) -> None:
        """Generated entities only have READ and LIST permissions (no CREATE/UPDATE/DELETE)."""
        from dazzle.core.admin_builder import _build_admin_entities
        from dazzle.core.ir.domain import PermissionKind

        security = _make_security(SecurityProfile.STRICT)
        write_ops = {PermissionKind.CREATE, PermissionKind.UPDATE, PermissionKind.DELETE}

        for entity in _build_admin_entities(security):
            assert entity.access is not None, f"{entity.name}: access is None"
            ops = {rule.operation for rule in entity.access.permissions}
            illegal = ops & write_ops
            assert not illegal, (
                f"{entity.name}: found write operations {illegal!r} — should be read-only"
            )
            assert PermissionKind.READ in ops, f"{entity.name}: missing READ permission"
            assert PermissionKind.LIST in ops, f"{entity.name}: missing LIST permission"

    def test_entities_require_admin_personas(self) -> None:
        """All permission rules are scoped to ['admin', 'super_admin']."""
        from dazzle.core.admin_builder import _build_admin_entities

        security = _make_security(SecurityProfile.STRICT)
        expected_personas = ["admin", "super_admin"]

        for entity in _build_admin_entities(security):
            assert entity.access is not None, f"{entity.name}: access is None"
            for rule in entity.access.permissions:
                assert rule.personas == expected_personas, (
                    f"{entity.name} op={rule.operation}: "
                    f"expected personas {expected_personas!r}, got {rule.personas!r}"
                )
