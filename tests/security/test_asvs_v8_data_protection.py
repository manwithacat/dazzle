"""ASVS V8: Data Protection security tests."""

from __future__ import annotations

from dazzle.core import ir


class TestSensitiveData:
    """V8.3: Sensitive Private Data."""

    def test_sensitive_modifier_exists(self):
        """V8.3.1: DSL supports marking fields as sensitive."""
        assert "sensitive" in [m.value for m in ir.FieldModifier]

    def test_field_is_sensitive_property(self):
        """V8.3.2: FieldSpec exposes is_sensitive property."""
        field = ir.FieldSpec(
            name="ssn",
            type=ir.FieldType(kind=ir.FieldTypeKind.STR),
            modifiers=[ir.FieldModifier.SENSITIVE],
        )
        assert field.is_sensitive is True

    def test_non_sensitive_field(self):
        """V8.3.3: Regular fields are not marked sensitive."""
        field = ir.FieldSpec(
            name="name",
            type=ir.FieldType(kind=ir.FieldTypeKind.STR),
        )
        assert field.is_sensitive is False


class TestDataClassification:
    """V8.1: General Data Protection."""

    def test_pii_classification_types(self):
        """V8.1.1: Data classification covers PII categories."""
        from dazzle.core.ir.governance import DataClassification

        names = {c.value for c in DataClassification}
        assert "pii_direct" in names
        assert "pii_indirect" in names or "pii_sensitive" in names

    def test_erasure_policies_exist(self):
        """V8.1.2: Erasure policy types are defined."""
        from dazzle.core.ir.governance import ErasurePolicy

        names = {p.value for p in ErasurePolicy}
        assert "delete" in names
        assert "anonymize" in names


class TestTenantIsolation:
    """V8.2: Client-side Data Protection."""

    def test_tenancy_config_exists(self):
        """V8.2.1: Multi-tenancy isolation configuration exists."""
        from dazzle.core.ir.governance import TenancyMode

        modes = {m.value for m in TenancyMode}
        assert len(modes) >= 2, "Must support multiple tenancy modes"
