"""Tests for #956 cycle 2 — AuditEntry system entity auto-generation.

Cycle 1 captured `audit on Entity: ...` blocks onto
`ModuleFragment.audits`. Cycle 2 injects an `AuditEntry` entity into
the AppSpec so cycle 3's repository hooks have a destination table for
captured before/after pairs.

The shape mirrors AIJob: a single shared system entity discriminated
by `entity_type` + `entity_id`, with one row per tracked field change.
The injection is gated on the presence of at least one `audit:` block
— apps without auditing don't get the table.
"""

from __future__ import annotations

import pathlib
import textwrap

import pytest


@pytest.fixture()
def parse_dsl():
    from dazzle.core.linker import build_appspec
    from dazzle.core.parser import parse_modules

    def _parse(source: str, tmp_path: pathlib.Path):
        dsl_path = tmp_path / "test.dsl"
        dsl_path.write_text(textwrap.dedent(source).lstrip())
        modules = parse_modules([dsl_path])
        return build_appspec(modules, "test")

    return _parse


class TestInjection:
    def test_audit_block_triggers_entity_injection(self, parse_dsl, tmp_path):
        appspec = parse_dsl(
            """
            module test
            app a "A"

            entity Manuscript "M":
              id: uuid pk
              title: str(200) required
              status: str(50) required

            audit on Manuscript:
              track: status
              retention: 90d
            """,
            tmp_path,
        )
        names = [e.name for e in appspec.domain.entities]
        assert "AuditEntry" in names

    def test_no_audit_block_no_injection(self, parse_dsl, tmp_path):
        appspec = parse_dsl(
            """
            module test
            app a "A"

            entity Manuscript "M":
              id: uuid pk
              title: str(200) required
            """,
            tmp_path,
        )
        names = [e.name for e in appspec.domain.entities]
        assert "AuditEntry" not in names

    def test_multiple_audit_blocks_single_audit_entry(self, parse_dsl, tmp_path):
        # Multiple `audit on X:` declarations share one AuditEntry
        # table — discriminated by `entity_type` at insertion time.
        appspec = parse_dsl(
            """
            module test
            app a "A"

            entity Manuscript "M":
              id: uuid pk
              title: str(200) required
              status: str(50) required

            entity Order "O":
              id: uuid pk
              total: int required

            audit on Manuscript:
              track: status

            audit on Order:
              track: total
            """,
            tmp_path,
        )
        # Exactly one AuditEntry across all audit blocks.
        audit_entries = [e for e in appspec.domain.entities if e.name == "AuditEntry"]
        assert len(audit_entries) == 1


class TestAuditEntryShape:
    @pytest.fixture()
    def audit_entry(self, parse_dsl, tmp_path):
        appspec = parse_dsl(
            """
            module test
            app a "A"

            entity Manuscript "M":
              id: uuid pk
              status: str(50) required

            audit on Manuscript:
              track: status
            """,
            tmp_path,
        )
        return next(e for e in appspec.domain.entities if e.name == "AuditEntry")

    def test_required_fields(self, audit_entry):
        names = {f.name for f in audit_entry.fields}
        # Required for any audit row: what changed, when, who, type/id.
        assert {"id", "entity_type", "entity_id", "field_name", "operation", "at"} <= names

    def test_value_pair_fields(self, audit_entry):
        names = {f.name for f in audit_entry.fields}
        # before/after stored as text — JSON-encoded by cycle-3 to
        # round-trip any field type without a polymorphic column.
        assert {"before_value", "after_value"} <= names

    def test_by_user_field_present(self, audit_entry):
        names = {f.name for f in audit_entry.fields}
        # Not required (background jobs / system writes have no user).
        assert "by_user_id" in names

    def test_id_is_pk(self, audit_entry):
        from dazzle.core.ir.fields import FieldModifier

        id_field = next(f for f in audit_entry.fields if f.name == "id")
        assert FieldModifier.PK in id_field.modifiers

    def test_at_defaults_to_now(self, audit_entry):
        at_field = next(f for f in audit_entry.fields if f.name == "at")
        assert at_field.default == "now"

    def test_operation_is_enum(self, audit_entry):
        op_field = next(f for f in audit_entry.fields if f.name == "operation")
        # Enum values from AUDIT_ENTRY_FIELDS — check the type kind.
        assert op_field.type.kind.value == "enum"


class TestPlatformDomain:
    def test_audit_entry_is_platform_entity(self, parse_dsl, tmp_path):
        appspec = parse_dsl(
            """
            module test
            app a "A"

            entity Manuscript "M":
              id: uuid pk
              status: str(50) required

            audit on Manuscript:
              track: status
            """,
            tmp_path,
        )
        audit_entry = next(e for e in appspec.domain.entities if e.name == "AuditEntry")
        # Validators / drift gates skip platform-domain entities so
        # the framework can ship them without users having to add
        # scope rules etc.
        assert audit_entry.domain == "platform"

    def test_audit_entry_has_audit_pattern(self, parse_dsl, tmp_path):
        appspec = parse_dsl(
            """
            module test
            app a "A"

            entity Manuscript "M":
              id: uuid pk
              status: str(50) required

            audit on Manuscript:
              track: status
            """,
            tmp_path,
        )
        audit_entry = next(e for e in appspec.domain.entities if e.name == "AuditEntry")
        assert "audit" in audit_entry.patterns


class TestAccess:
    @pytest.fixture()
    def audit_entry(self, parse_dsl, tmp_path):
        appspec = parse_dsl(
            """
            module test
            app a "A"

            entity Manuscript "M":
              id: uuid pk
              status: str(50) required

            audit on Manuscript:
              track: status
            """,
            tmp_path,
        )
        return next(e for e in appspec.domain.entities if e.name == "AuditEntry")

    def test_no_update_or_delete_permissions(self, audit_entry):
        # Audit entries are immutable. Cycle-6 retention sweep uses a
        # different code path (bulk delete by age).
        from dazzle.core.ir.domain import PermissionKind

        ops = {p.operation for p in audit_entry.access.permissions}
        assert PermissionKind.UPDATE not in ops
        assert PermissionKind.DELETE not in ops

    def test_read_list_create_present(self, audit_entry):
        from dazzle.core.ir.domain import PermissionKind

        ops = {p.operation for p in audit_entry.access.permissions}
        assert {PermissionKind.READ, PermissionKind.LIST, PermissionKind.CREATE} <= ops
