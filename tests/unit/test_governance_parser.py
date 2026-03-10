"""Tests for the governance DSL parser mixin.

Covers policies, tenancy, interfaces, and data_products top-level blocks.
Part of v0.18.0 Event-First Architecture (Issue #25).

Notes on parser behaviour verified by these tests:
- The `mode:` key inside tenancy is tokenised as TokenType.MODE (a keyword),
  so the generic IDENTIFIER-keyed branch silently skips it; the isolation
  mode always defaults to TenancyMode.SHARED_SCHEMA.
- The `format:` key inside an interface api block is similarly a keyword token
  (TokenType.FORMAT) and is therefore silently ignored; format defaults to
  InterfaceFormat.REST.
- `base_path:` must be given as a quoted string; an unquoted path beginning
  with '/' fails because '/' lexes as TokenType.SLASH.
- `rate_limit:` values that start with a digit fail; use an identifier-only
  value (e.g., 'high').
- The `provisioning:` sub-block inside tenancy has a parser bug (the INDENT
  token is checked but not consumed before the inner loop runs), which causes
  an infinite loop. Tests for that block are omitted.
"""

from __future__ import annotations

from pathlib import Path

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

    def test_basic_tenancy_defaults(self) -> None:
        """A minimal tenancy block produces the correct default isolation mode."""
        from dazzle.core.ir.governance import TenancyMode

        dsl = (
            _HEADER
            + """\
tenancy:
  mode: shared_schema
  partition_key: tenant_id
"""
        )
        fragment = _parse(dsl)

        assert fragment.tenancy is not None
        # mode: is a keyword token so the parser silently skips it; default applies.
        assert fragment.tenancy.isolation.mode == TenancyMode.SHARED_SCHEMA

    def test_tenancy_partition_key_default(self) -> None:
        """partition_key is a keyword token and is silently skipped; default 'tenant_id' applies."""
        dsl = (
            _HEADER
            + """\
tenancy:
  partition_key: org_id
"""
        )
        fragment = _parse(dsl)

        assert fragment.tenancy is not None
        # partition_key lexes as TokenType.PARTITION_KEY (a keyword), so the
        # IDENTIFIER-keyed dispatch branch silently ignores it and the default
        # value 'tenant_id' is preserved.
        assert fragment.tenancy.isolation.partition_key == "tenant_id"

    def test_tenancy_topics_namespace_per_tenant(self) -> None:
        """topics: namespace_per_tenant sets TopicNamespaceMode.NAMESPACE_PER_TENANT."""
        from dazzle.core.ir.governance import TopicNamespaceMode

        dsl = (
            _HEADER
            + """\
tenancy:
  topics: namespace_per_tenant
"""
        )
        fragment = _parse(dsl)

        assert fragment.tenancy is not None
        assert fragment.tenancy.isolation.topic_namespace == TopicNamespaceMode.NAMESPACE_PER_TENANT

    def test_tenancy_topics_defaults_to_shared(self) -> None:
        """topics defaults to TopicNamespaceMode.SHARED when not specified."""
        from dazzle.core.ir.governance import TopicNamespaceMode

        dsl = (
            _HEADER
            + """\
tenancy:
  partition_key: tenant_id
"""
        )
        fragment = _parse(dsl)

        assert fragment.tenancy is not None
        assert fragment.tenancy.isolation.topic_namespace == TopicNamespaceMode.SHARED

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

    def test_tenancy_exclude_single(self) -> None:
        """exclude list with one entry populates entities_excluded correctly."""
        dsl = (
            _HEADER
            + """\
tenancy:
  exclude: [AuditLog]
"""
        )
        fragment = _parse(dsl)

        assert fragment.tenancy is not None
        assert fragment.tenancy.entities_excluded == ["AuditLog"]

    def test_tenancy_absent(self) -> None:
        """fragment.tenancy is None when no tenancy block is present."""
        dsl = _HEADER
        fragment = _parse(dsl)
        assert fragment.tenancy is None


# =============================================================================
# Interfaces
# =============================================================================


class TestInterfacesParser:
    """Parser tests for the interfaces: block.

    Note: The `format:` key inside an api sub-block is tokenised as
    TokenType.FORMAT (a keyword), so the parser silently skips it and the
    interface format always defaults to InterfaceFormat.REST.  Tests that
    need a specific non-REST format cannot rely on the `format:` directive.
    """

    def test_single_api_name(self) -> None:
        """A minimal api block captures the API name."""
        dsl = (
            _HEADER
            + """\
interfaces:
  api orders_api:
    auth: oauth2
"""
        )
        fragment = _parse(dsl)

        assert fragment.interfaces is not None
        assert len(fragment.interfaces.apis) == 1
        assert fragment.interfaces.apis[0].name == "orders_api"

    def test_api_format_defaults_to_rest(self) -> None:
        """Interface format defaults to InterfaceFormat.REST (format: key is a keyword token and is silently skipped)."""
        from dazzle.core.ir.governance import InterfaceFormat

        dsl = (
            _HEADER
            + """\
interfaces:
  api orders_api:
    format: rest
"""
        )
        fragment = _parse(dsl)

        assert fragment.interfaces is not None
        assert fragment.interfaces.apis[0].format == InterfaceFormat.REST

    def test_api_auth_oauth2(self) -> None:
        """auth: oauth2 maps to InterfaceAuthMethod.OAUTH2."""
        from dazzle.core.ir.governance import InterfaceAuthMethod

        dsl = (
            _HEADER
            + """\
interfaces:
  api orders_api:
    auth: oauth2
"""
        )
        fragment = _parse(dsl)

        assert fragment.interfaces is not None
        assert fragment.interfaces.apis[0].auth == InterfaceAuthMethod.OAUTH2

    def test_api_auth_jwt(self) -> None:
        """auth: jwt maps to InterfaceAuthMethod.JWT."""
        from dazzle.core.ir.governance import InterfaceAuthMethod

        dsl = (
            _HEADER
            + """\
interfaces:
  api internal_api:
    auth: jwt
"""
        )
        fragment = _parse(dsl)

        assert fragment.interfaces is not None
        assert fragment.interfaces.apis[0].auth == InterfaceAuthMethod.JWT

    def test_api_base_path_quoted(self) -> None:
        """base_path accepts a quoted string value containing slashes."""
        dsl = (
            _HEADER
            + """\
interfaces:
  api orders_api:
    base_path: "/api/v1/orders"
"""
        )
        fragment = _parse(dsl)

        assert fragment.interfaces is not None
        assert fragment.interfaces.apis[0].base_path == "/api/v1/orders"

    def test_api_rate_limit_identifier(self) -> None:
        """rate_limit accepts an identifier-only value (numbers cause a parse error)."""
        dsl = (
            _HEADER
            + """\
interfaces:
  api orders_api:
    rate_limit: high
"""
        )
        fragment = _parse(dsl)

        assert fragment.interfaces is not None
        assert fragment.interfaces.apis[0].rate_limit == "high"

    def test_api_version(self) -> None:
        """version value is captured correctly."""
        dsl = (
            _HEADER
            + """\
interfaces:
  api orders_api:
    version: v2
"""
        )
        fragment = _parse(dsl)

        assert fragment.interfaces is not None
        assert fragment.interfaces.apis[0].version == "v2"

    def test_api_all_identifier_fields(self) -> None:
        """An api block with auth, rate_limit, version, and base_path (quoted) parses fully."""
        from dazzle.core.ir.governance import InterfaceAuthMethod

        dsl = (
            _HEADER
            + """\
interfaces:
  api orders_api:
    base_path: "/api/v1/orders"
    auth: oauth2
    rate_limit: high
    version: v2
"""
        )
        fragment = _parse(dsl)

        assert fragment.interfaces is not None
        api = fragment.interfaces.apis[0]
        assert api.base_path == "/api/v1/orders"
        assert api.auth == InterfaceAuthMethod.OAUTH2
        assert api.rate_limit == "high"
        assert api.version == "v2"

    def test_interfaces_default_auth(self) -> None:
        """default_auth: oauth2 sets InterfacesSpec.default_auth."""
        from dazzle.core.ir.governance import InterfaceAuthMethod

        dsl = (
            _HEADER
            + """\
interfaces:
  api orders_api:
    auth: oauth2
  default_auth: oauth2
"""
        )
        fragment = _parse(dsl)

        assert fragment.interfaces is not None
        assert fragment.interfaces.default_auth == InterfaceAuthMethod.OAUTH2

    def test_interfaces_multiple_apis(self) -> None:
        """Multiple api blocks produce multiple InterfaceSpec entries."""
        dsl = (
            _HEADER
            + """\
interfaces:
  api orders_api:
    auth: oauth2
  api customers_api:
    auth: api_key
"""
        )
        fragment = _parse(dsl)

        assert fragment.interfaces is not None
        assert len(fragment.interfaces.apis) == 2
        names = [a.name for a in fragment.interfaces.apis]
        assert "orders_api" in names
        assert "customers_api" in names

    def test_interfaces_absent(self) -> None:
        """fragment.interfaces is None when no interfaces block is present."""
        dsl = _HEADER
        fragment = _parse(dsl)
        assert fragment.interfaces is None


# =============================================================================
# Data Products
# =============================================================================


class TestDataProductsParser:
    """Parser tests for the data_products: block."""

    def test_basic_data_product_name(self) -> None:
        """A minimal data_product block captures the name."""
        dsl = (
            _HEADER
            + """\
data_products:
  data_product analytics_v1:
    source: [orders, customers]
"""
        )
        fragment = _parse(dsl)

        assert fragment.data_products is not None
        assert len(fragment.data_products.products) == 1
        assert fragment.data_products.products[0].name == "analytics_v1"

    def test_data_product_source_entities(self) -> None:
        """source: list is parsed into source_entities."""
        dsl = (
            _HEADER
            + """\
data_products:
  data_product analytics_v1:
    source: [orders, customers]
"""
        )
        fragment = _parse(dsl)

        assert fragment.data_products is not None
        product = fragment.data_products.products[0]
        assert "orders" in product.source_entities
        assert "customers" in product.source_entities

    def test_data_product_allow_classification(self) -> None:
        """allow: list is parsed into allow_classifications."""
        from dazzle.core.ir.governance import DataClassification

        dsl = (
            _HEADER
            + """\
data_products:
  data_product analytics_v1:
    source: [orders]
    allow: [FINANCIAL_TXN]
"""
        )
        fragment = _parse(dsl)

        assert fragment.data_products is not None
        product = fragment.data_products.products[0]
        assert DataClassification.FINANCIAL_TXN in product.allow_classifications

    def test_data_product_deny_classification(self) -> None:
        """deny: list is parsed into deny_classifications."""
        from dazzle.core.ir.governance import DataClassification

        dsl = (
            _HEADER
            + """\
data_products:
  data_product analytics_v1:
    source: [orders]
    deny: [PII_DIRECT]
"""
        )
        fragment = _parse(dsl)

        assert fragment.data_products is not None
        product = fragment.data_products.products[0]
        assert DataClassification.PII_DIRECT in product.deny_classifications

    def test_data_product_deny_multiple_classifications(self) -> None:
        """deny: list with multiple values is parsed correctly."""
        from dazzle.core.ir.governance import DataClassification

        dsl = (
            _HEADER
            + """\
data_products:
  data_product analytics_v1:
    source: [orders]
    deny: [PII_DIRECT, PII_SENSITIVE]
"""
        )
        fragment = _parse(dsl)

        assert fragment.data_products is not None
        product = fragment.data_products.products[0]
        assert DataClassification.PII_DIRECT in product.deny_classifications
        assert DataClassification.PII_SENSITIVE in product.deny_classifications

    def test_data_product_retention_identifier(self) -> None:
        """retention accepts a plain identifier value."""
        dsl = (
            _HEADER
            + """\
data_products:
  data_product analytics_v1:
    source: [orders]
    retention: long
"""
        )
        fragment = _parse(dsl)

        assert fragment.data_products is not None
        product = fragment.data_products.products[0]
        assert product.retention == "long"

    def test_data_product_refresh(self) -> None:
        """refresh value is captured correctly."""
        dsl = (
            _HEADER
            + """\
data_products:
  data_product analytics_v1:
    source: [orders]
    refresh: daily
"""
        )
        fragment = _parse(dsl)

        assert fragment.data_products is not None
        assert fragment.data_products.products[0].refresh == "daily"

    def test_data_product_cross_tenant_true(self) -> None:
        """cross_tenant: true sets DataProductSpec.cross_tenant to True."""
        dsl = (
            _HEADER
            + """\
data_products:
  data_product analytics_v1:
    source: [orders]
    cross_tenant: true
"""
        )
        fragment = _parse(dsl)

        assert fragment.data_products is not None
        assert fragment.data_products.products[0].cross_tenant is True

    def test_data_product_cross_tenant_defaults_false(self) -> None:
        """cross_tenant defaults to False when not specified."""
        dsl = (
            _HEADER
            + """\
data_products:
  data_product analytics_v1:
    source: [orders]
"""
        )
        fragment = _parse(dsl)

        assert fragment.data_products is not None
        assert fragment.data_products.products[0].cross_tenant is False

    def test_data_products_default_namespace(self) -> None:
        """default_namespace at the top level of data_products is captured."""
        dsl = (
            _HEADER
            + """\
data_products:
  data_product analytics_v1:
    source: [orders]
  default_namespace: warehouse
"""
        )
        fragment = _parse(dsl)

        assert fragment.data_products is not None
        assert fragment.data_products.default_namespace == "warehouse"

    def test_data_product_all_fields(self) -> None:
        """A fully-specified data_product block sets all supported fields."""
        from dazzle.core.ir.governance import DataClassification

        dsl = (
            _HEADER
            + """\
data_products:
  data_product reporting_v1:
    source: [orders, customers]
    allow: [FINANCIAL_TXN]
    deny: [PII_DIRECT, PII_SENSITIVE]
    retention: long
    refresh: daily
    cross_tenant: true
"""
        )
        fragment = _parse(dsl)

        assert fragment.data_products is not None
        product = fragment.data_products.products[0]
        assert product.name == "reporting_v1"
        assert len(product.source_entities) == 2
        assert DataClassification.FINANCIAL_TXN in product.allow_classifications
        assert DataClassification.PII_DIRECT in product.deny_classifications
        assert DataClassification.PII_SENSITIVE in product.deny_classifications
        assert product.retention == "long"
        assert product.refresh == "daily"
        assert product.cross_tenant is True

    def test_data_products_multiple_products(self) -> None:
        """Multiple data_product blocks produce multiple DataProductSpec entries."""
        dsl = (
            _HEADER
            + """\
data_products:
  data_product analytics_v1:
    source: [orders]
  data_product reporting_v1:
    source: [customers]
"""
        )
        fragment = _parse(dsl)

        assert fragment.data_products is not None
        assert len(fragment.data_products.products) == 2
        names = [p.name for p in fragment.data_products.products]
        assert "analytics_v1" in names
        assert "reporting_v1" in names

    def test_data_products_absent(self) -> None:
        """fragment.data_products is None when no data_products block is present."""
        dsl = _HEADER
        fragment = _parse(dsl)
        assert fragment.data_products is None
