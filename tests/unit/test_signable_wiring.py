"""Phase 3 wiring tests for the `signable: true` DSL primitive (#1283).

Covers parser → IR roundtrip + linker auto-injection of the 11 signing
fields + default audit. Project-declared fields with the same name must
win over the auto-inject (explicit beats auto).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core import ir
from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.linker import _inject_signable_fields


def _parse_fragment(dsl: str) -> ir.ModuleFragment:
    _, _, _, _, _, frag = parse_dsl(dsl, Path("test.dz"))
    return frag


def _parse_entity(dsl: str, name: str = "Contract") -> ir.EntitySpec:
    frag = _parse_fragment(dsl)
    matches = [e for e in frag.entities if e.name == name]
    assert matches, f"entity {name!r} not found"
    return matches[0]


# -- Parser ------------------------------------------------------------


class TestSignableParser:
    def test_signable_true_sets_flag(self):
        e = _parse_entity(
            """\
module test
entity Contract "Contract":
  id: uuid pk
  party: str(200) required
  signable: true
"""
        )
        assert e.signable is True

    def test_signable_false_keeps_flag_off(self):
        e = _parse_entity(
            """\
module test
entity Contract "Contract":
  id: uuid pk
  party: str(200) required
  signable: false
"""
        )
        assert e.signable is False

    def test_signable_default_is_false(self):
        e = _parse_entity(
            """\
module test
entity Contract "Contract":
  id: uuid pk
  party: str(200) required
"""
        )
        assert e.signable is False

    def test_signing_validator_dotted_path(self):
        e = _parse_entity(
            """\
module test
entity Contract "Contract":
  id: uuid pk
  party: str(200) required
  signable: true
  signing_validator: app.signing.validators.verify_party_grant
"""
        )
        assert e.signing_validator == "app.signing.validators.verify_party_grant"

    def test_signing_validator_default_none(self):
        e = _parse_entity(
            """\
module test
entity Contract "Contract":
  id: uuid pk
  party: str(200) required
  signable: true
"""
        )
        assert e.signing_validator is None

    def test_signable_requires_true_or_false(self):
        with pytest.raises(Exception, match="signable"):
            _parse_fragment(
                """\
module test
entity Contract "Contract":
  id: uuid pk
  party: str(200) required
  signable: maybe
"""
            )


# -- Linker auto-injection --------------------------------------------


_EXPECTED_AUTO_FIELDS = (
    "status",
    "signing_service",
    "signing_url",
    "signed_document",
    "signing_token_hash",
    "signer_ip",
    "signer_user_agent",
    "sent_at",
    "viewed_at",
    "signed_at",
    "expires_at",
)


def _signable_entity(
    *,
    name: str = "Contract",
    extra_fields: list[ir.FieldSpec] | None = None,
    audit: ir.AuditConfig | None = None,
) -> ir.EntitySpec:
    """Build a minimal signable entity for linker tests."""
    base = [
        ir.FieldSpec(
            name="id",
            type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
            modifiers=[ir.FieldModifier.PK],
        ),
        ir.FieldSpec(
            name="party",
            type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=200),
            modifiers=[ir.FieldModifier.REQUIRED],
        ),
    ]
    return ir.EntitySpec(
        name=name,
        title=name,
        fields=base + (extra_fields or []),
        signable=True,
        audit=audit,
    )


class TestSignableLinker:
    def test_injects_all_11_auto_fields(self):
        entity = _signable_entity()
        [out] = _inject_signable_fields([entity])
        names = [f.name for f in out.fields]
        for expected in _EXPECTED_AUTO_FIELDS:
            assert expected in names

    def test_skips_entities_without_signable_flag(self):
        entity = ir.EntitySpec(
            name="Other",
            title="Other",
            fields=[
                ir.FieldSpec(
                    name="id",
                    type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                    modifiers=[ir.FieldModifier.PK],
                ),
            ],
            signable=False,
        )
        [out] = _inject_signable_fields([entity])
        assert out is entity  # untouched, same object

    def test_project_declared_field_wins(self):
        """A project-declared `signing_url` with a longer max_length keeps
        its definition; the auto-inject must NOT override."""
        existing = ir.FieldSpec(
            name="signing_url",
            type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=2000),
            modifiers=[ir.FieldModifier.REQUIRED],
        )
        entity = _signable_entity(extra_fields=[existing])
        [out] = _inject_signable_fields([entity])

        matching = [f for f in out.fields if f.name == "signing_url"]
        assert len(matching) == 1
        assert matching[0].type.max_length == 2000
        assert matching[0].modifiers == [ir.FieldModifier.REQUIRED]

    def test_status_field_has_seven_state_enum(self):
        [out] = _inject_signable_fields([_signable_entity()])
        status = next(f for f in out.fields if f.name == "status")
        assert status.type.kind == ir.FieldTypeKind.ENUM
        assert status.type.enum_values == [
            "draft",
            "sent",
            "viewed",
            "signed",
            "declined",
            "expired",
            "superseded",
        ]

    def test_signing_service_enum_native_or_manual(self):
        [out] = _inject_signable_fields([_signable_entity()])
        f = next(f for f in out.fields if f.name == "signing_service")
        assert f.type.kind == ir.FieldTypeKind.ENUM
        assert f.type.enum_values == ["native", "manual"]

    def test_signed_document_is_file_type(self):
        [out] = _inject_signable_fields([_signable_entity()])
        f = next(f for f in out.fields if f.name == "signed_document")
        assert f.type.kind == ir.FieldTypeKind.FILE

    def test_signer_ip_max_45_chars_ipv6_safe(self):
        [out] = _inject_signable_fields([_signable_entity()])
        f = next(f for f in out.fields if f.name == "signer_ip")
        assert f.type.max_length == 45

    def test_audit_defaults_to_enabled(self):
        """When audit is unset, signable entities default to audit
        enabled — signing is legally meaningful, so the trail is on
        by default."""
        [out] = _inject_signable_fields([_signable_entity(audit=None)])
        assert out.audit is not None
        assert out.audit.enabled is True

    def test_explicit_audit_config_preserved(self):
        explicit = ir.AuditConfig(enabled=False, operations=[])
        [out] = _inject_signable_fields([_signable_entity(audit=explicit)])
        assert out.audit == explicit

    def test_idempotent_on_already_injected_entity(self):
        """Running the inject pass twice produces the same entity —
        the second pass must not re-append the auto-fields."""
        once = _inject_signable_fields([_signable_entity()])
        twice = _inject_signable_fields(once)
        names_once = [f.name for f in once[0].fields]
        names_twice = [f.name for f in twice[0].fields]
        assert names_once == names_twice

    def test_field_order_existing_before_injected(self):
        """Project-declared fields come first; auto-injected fields are
        appended in the canonical order."""
        entity = _signable_entity()
        [out] = _inject_signable_fields([entity])
        names = [f.name for f in out.fields]
        # First two are the project-declared id + party
        assert names[:2] == ["id", "party"]
        # Auto-fields follow in declaration order
        assert names[2:] == list(_EXPECTED_AUTO_FIELDS)
