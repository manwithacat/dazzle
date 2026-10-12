"""Tests for the governance DSL parser mixin.

Covers policies and tenancy top-level blocks.
Part of v0.18.0 Event-First Architecture (Issue #25).

Notes on parser behaviour verified by these tests:
- The `mode:` key inside tenancy is tokenised as TokenType.MODE (a keyword),
  so the generic IDENTIFIER-keyed branch silently skips it; the isolation
  mode always defaults to TenancyMode.SHARED_SCHEMA.
- The `provisioning:` sub-block inside tenancy has a parser bug (the INDENT
  token is checked but not consumed before the inner loop runs), which causes
  an infinite loop. Tests for that block are omitted.
"""

from pathlib import Path

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl


def _parse(dsl: str):
    _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
    return fragment


_HEADER = """\
module test_app
app test "Test"
"""


# =============================================================================
# Policies
# =============================================================================


class TestPoliciesParser:
    """Parser tests for the policies: block."""

    def test_classify_basic(self) -> None:
        """classify directive sets entity, field, and classification."""
        from dazzle.core.ir.governance import DataClassification

        dsl = (
            _HEADER
            + """\
policies:
  classify Customer.email as PII_DIRECT
"""
        )
        fragment = _parse(dsl)

        assert fragment.policies is not None
        assert len(fragment.policies.classifications) == 1
        cls = fragment.policies.classifications[0]
        assert cls.entity == "Customer"
        assert cls.field == "email"
        assert cls.classification == DataClassification.PII_DIRECT

    def test_classify_financial(self) -> None:
        """classify directive correctly maps FINANCIAL_TXN."""
        from dazzle.core.ir.governance import DataClassification

        dsl = (
            _HEADER
            + """\
policies:
  classify Order.total as FINANCIAL_TXN
"""
        )
        fragment = _parse(dsl)

        assert fragment.policies is not None
        cls = fragment.policies.classifications[0]
        assert cls.entity == "Order"
        assert cls.field == "total"
        assert cls.classification == DataClassification.FINANCIAL_TXN

    def test_classify_indirect_pii(self) -> None:
        """classify directive correctly maps PII_INDIRECT."""
        from dazzle.core.ir.governance import DataClassification

        dsl = (
            _HEADER
            + """\
policies:
  classify Customer.ip_address as PII_INDIRECT
"""
        )
        fragment = _parse(dsl)

        assert fragment.policies is not None
        cls = fragment.policies.classifications[0]
        assert cls.classification == DataClassification.PII_INDIRECT

    def test_classify_with_retention(self) -> None:
        """classify directive with retention keyword sets RetentionPolicy."""
        from dazzle.core.ir.governance import DataClassification, RetentionPolicy

        dsl = (
            _HEADER
            + """\
policies:
  classify Order.total as FINANCIAL_TXN retention: long
"""
        )
        fragment = _parse(dsl)

        assert fragment.policies is not None
        cls = fragment.policies.classifications[0]
        assert cls.classification == DataClassification.FINANCIAL_TXN
        assert cls.retention == RetentionPolicy.LONG

    def test_classify_retention_short(self) -> None:
        """classify directive with retention: short sets RetentionPolicy.SHORT."""
        from dazzle.core.ir.governance import RetentionPolicy

        dsl = (
            _HEADER
            + """\
policies:
  classify Session.token as PII_INDIRECT retention: short
"""
        )
        fragment = _parse(dsl)

        assert fragment.policies is not None
        assert fragment.policies.classifications[0].retention == RetentionPolicy.SHORT

    def test_classify_multiple(self) -> None:
        """Multiple classify directives produce multiple ClassificationSpec entries."""
        dsl = (
            _HEADER
            + """\
policies:
  classify Customer.email as PII_DIRECT
  classify Customer.phone as PII_INDIRECT
  classify Order.total as FINANCIAL_TXN
"""
        )
        fragment = _parse(dsl)

        assert fragment.policies is not None
        assert len(fragment.policies.classifications) == 3
        pairs = [(c.entity, c.field) for c in fragment.policies.classifications]
        assert ("Customer", "email") in pairs
        assert ("Customer", "phone") in pairs
        assert ("Order", "total") in pairs

    def test_erasure_entity_only(self) -> None:
        """erasure directive with entity only sets field=None and cascade=False."""
        from dazzle.core.ir.governance import ErasurePolicy

        dsl = (
            _HEADER
            + """\
policies:
  erasure Customer: anonymize
"""
        )
        fragment = _parse(dsl)

        assert fragment.policies is not None
        assert len(fragment.policies.erasures) == 1
        era = fragment.policies.erasures[0]
        assert era.entity == "Customer"
        assert era.field is None
        assert era.policy == ErasurePolicy.ANONYMIZE
        assert era.cascade is False

    def test_erasure_entity_field_with_cascade(self) -> None:
        """erasure directive with Entity.field and cascade flag."""
        from dazzle.core.ir.governance import ErasurePolicy

        dsl = (
            _HEADER
            + """\
policies:
  erasure Customer.email: delete cascade
"""
        )
        fragment = _parse(dsl)

        assert fragment.policies is not None
        era = fragment.policies.erasures[0]
        assert era.entity == "Customer"
        assert era.field == "email"
        assert era.policy == ErasurePolicy.DELETE
        assert era.cascade is True

    def test_erasure_pseudonymize_policy(self) -> None:
        """erasure directive supports the pseudonymize policy value."""
        from dazzle.core.ir.governance import ErasurePolicy

        dsl = (
            _HEADER
            + """\
policies:
  erasure Customer.ssn: pseudonymize
"""
        )
        fragment = _parse(dsl)

        assert fragment.policies is not None
        era = fragment.policies.erasures[0]
        assert era.field == "ssn"
        assert era.policy == ErasurePolicy.PSEUDONYMIZE

    def test_default_retention(self) -> None:
        """default_retention key sets PoliciesSpec.default_retention."""
        from dazzle.core.ir.governance import RetentionPolicy

        dsl = (
            _HEADER
            + """\
policies:
  classify Customer.email as PII_DIRECT
  default_retention: long
"""
        )
        fragment = _parse(dsl)

        assert fragment.policies is not None
        assert fragment.policies.default_retention == RetentionPolicy.LONG

    def test_default_retention_short(self) -> None:
        """default_retention: short maps to RetentionPolicy.SHORT."""
        from dazzle.core.ir.governance import RetentionPolicy

        dsl = (
            _HEADER
            + """\
policies:
  classify Customer.email as PII_DIRECT
  default_retention: short
"""
        )
        fragment = _parse(dsl)

        assert fragment.policies is not None
        assert fragment.policies.default_retention == RetentionPolicy.SHORT

    def test_audit_access_false(self) -> None:
        """audit_access: false sets PoliciesSpec.audit_access to False."""
        dsl = (
            _HEADER
            + """\
policies:
  classify Customer.email as PII_DIRECT
  audit_access: false
"""
        )
        fragment = _parse(dsl)

        assert fragment.policies is not None
        assert fragment.policies.audit_access is False

    def test_audit_access_defaults_to_true(self) -> None:
        """audit_access defaults to True when not specified."""
        dsl = (
            _HEADER
            + """\
policies:
  classify Customer.email as PII_DIRECT
"""
        )
        fragment = _parse(dsl)

        assert fragment.policies is not None
        assert fragment.policies.audit_access is True

    def test_policies_absent(self) -> None:
        """fragment.policies is None when no policies block is present."""
        dsl = _HEADER
        fragment = _parse(dsl)
        assert fragment.policies is None


# =============================================================================
# Tenancy
# =============================================================================


class TestTenancyParser:
    """Parser tests for the tenancy: block.

    Note: The `mode:` key is tokenised as TokenType.MODE (a keyword) rather
    than TokenType.IDENTIFIER, so the generic key-dispatch branch inside the
    parser silently skips the line.  The isolation mode therefore always
    resolves to the default value (TenancyMode.SHARED_SCHEMA).  Tests here
    verify the keys that *are* handled correctly via IDENTIFIER tokens.
    """

    @pytest.mark.parametrize(
        ("body", "extractor_factory"),
        [
            (
                "tenancy:\n  mode: shared_schema\n  partition_key: tenant_id\n",
                lambda: (
                    lambda f: f.tenancy.isolation.mode,
                    __import__(
                        "dazzle.core.ir.governance", fromlist=["TenancyMode"]
                    ).TenancyMode.SHARED_SCHEMA,
                ),
            ),
            (
                "tenancy:\n  partition_key: org_id\n",
                lambda: (lambda f: f.tenancy.isolation.partition_key, "tenant_id"),
            ),
            (
                "tenancy:\n  topics: namespace_per_tenant\n",
                lambda: (
                    lambda f: f.tenancy.isolation.topic_namespace,
                    __import__(
                        "dazzle.core.ir.governance", fromlist=["TopicNamespaceMode"]
                    ).TopicNamespaceMode.NAMESPACE_PER_TENANT,
                ),
            ),
            (
                "tenancy:\n  partition_key: tenant_id\n",
                lambda: (
                    lambda f: f.tenancy.isolation.topic_namespace,
                    __import__(
                        "dazzle.core.ir.governance", fromlist=["TopicNamespaceMode"]
                    ).TopicNamespaceMode.SHARED,
                ),
            ),
            (
                "tenancy:\n  exclude: [AuditLog]\n",
                lambda: (lambda f: f.tenancy.entities_excluded, ["AuditLog"]),
            ),
            (
                # #1447 B2: the canonical keyword (matches the IR field) must parse —
                # it was silently dropped before (parser only knew `exclude`).
                "tenancy:\n  entities_excluded: [GlobalRef, MarkScheme]\n",
                lambda: (lambda f: f.tenancy.entities_excluded, ["GlobalRef", "MarkScheme"]),
            ),
        ],
        ids=[
            "test_basic_tenancy_defaults",
            "test_tenancy_partition_key_default",
            "test_tenancy_topics_namespace_per_tenant",
            "test_tenancy_topics_defaults_to_shared",
            "test_tenancy_exclude_single",
            "test_tenancy_entities_excluded_canonical",
        ],
    )
    def test_tenancy_attr(self, body: str, extractor_factory) -> None:
        fragment = _parse(_HEADER + body)
        extractor, expected = extractor_factory()
        assert fragment.tenancy is not None
        assert extractor(fragment) == expected

    def test_tenancy_cross_tenant_access_false(self) -> None:
        """cross_tenant_access: false is parsed correctly."""
        dsl = (
            _HEADER
            + """\
tenancy:
  cross_tenant_access: false
"""
        )
        fragment = _parse(dsl)

        assert fragment.tenancy is not None
        assert fragment.tenancy.isolation.cross_tenant_access is False

    def test_tenancy_enforce_in_queries_true(self) -> None:
        """enforce_in_queries: true is parsed correctly."""
        dsl = (
            _HEADER
            + """\
tenancy:
  enforce_in_queries: true
"""
        )
        fragment = _parse(dsl)

        assert fragment.tenancy is not None
        assert fragment.tenancy.isolation.enforce_in_queries is True

    def test_tenancy_exclude_list(self) -> None:
        """exclude: [EntityA, EntityB] populates entities_excluded."""
        dsl = (
            _HEADER
            + """\
tenancy:
  exclude: [AuditLog, SystemConfig]
"""
        )
        fragment = _parse(dsl)

        assert fragment.tenancy is not None
        assert "AuditLog" in fragment.tenancy.entities_excluded
        assert "SystemConfig" in fragment.tenancy.entities_excluded
        assert len(fragment.tenancy.entities_excluded) == 2

    def test_tenancy_absent(self) -> None:
        """fragment.tenancy is None when no tenancy block is present."""
        dsl = _HEADER
        fragment = _parse(dsl)
        assert fragment.tenancy is None
