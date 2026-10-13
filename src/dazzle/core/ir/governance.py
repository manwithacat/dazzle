"""
Data governance IR types for DAZZLE.

This module contains IR types for:
- policies: Field classification, data governance rules
- tenancy: Multi-tenancy configuration

Part of v0.18.0 Event-First Architecture (Issue #25).
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

# =============================================================================
# Field Classification (policies section)
# =============================================================================


class DataClassification(StrEnum):
    """
    Data classification levels for governance.

    Based on common data protection frameworks (GDPR, CCPA, etc.).
    """

    # PII Classifications
    PII_DIRECT = "pii_direct"  # Directly identifies a person (name, email, SSN)
    PII_INDIRECT = "pii_indirect"  # Can identify when combined (IP, device ID)
    PII_SENSITIVE = "pii_sensitive"  # Special category (health, religion, etc.)

    # Financial Classifications
    FINANCIAL_TXN = "financial_txn"  # Transaction data (amounts, payments)
    FINANCIAL_ACCOUNT = "financial_account"  # Account numbers, card details

    # Business Classifications
    BUSINESS_CONFIDENTIAL = "business_confidential"  # Trade secrets, strategies
    BUSINESS_INTERNAL = "business_internal"  # Internal use only

    # Public/Default
    PUBLIC = "public"  # No restrictions
    UNCLASSIFIED = "unclassified"  # Not yet classified


class RetentionPolicy(StrEnum):
    """Retention policy for classified data."""

    EPHEMERAL = "ephemeral"  # Delete immediately after use
    SESSION = "session"  # Delete at end of session
    SHORT = "short"  # 30 days
    MEDIUM = "medium"  # 1 year
    LONG = "long"  # 7 years (financial)
    PERMANENT = "permanent"  # Never delete (audit trails)
    LEGAL_HOLD = "legal_hold"  # Retained for legal purposes


class ClassificationSpec(BaseModel):
    """
    Field classification specification.

    DSL syntax:
        classify Customer.email as PII_DIRECT
        classify Order.total as FINANCIAL_TXN retention: 7_years
    """

    entity: str
    field: str
    classification: DataClassification
    retention: RetentionPolicy = RetentionPolicy.MEDIUM
    notes: str | None = None

    model_config = ConfigDict(frozen=True)


class ErasurePolicy(StrEnum):
    """How to handle data erasure requests (GDPR right to be forgotten)."""

    DELETE = "delete"  # Hard delete
    ANONYMIZE = "anonymize"  # Replace with anonymous values
    PSEUDONYMIZE = "pseudonymize"  # Replace with pseudonymous identifiers
    REDACT = "redact"  # Replace with redacted markers


class ErasureSpec(BaseModel):
    """
    Erasure policy for an entity or field.

    DSL syntax:
        erasure Customer: anonymize
        erasure Customer.email: delete
    """

    entity: str
    field: str | None = None  # None means entire entity
    policy: ErasurePolicy

    model_config = ConfigDict(frozen=True)


class PoliciesSpec(BaseModel):
    """
    Complete policies specification.

    DSL syntax:
        policies:
          classify Customer.email as PII_DIRECT
          classify Customer.phone as PII_DIRECT
          classify Order.total as FINANCIAL_TXN
          erasure Customer: anonymize
    """

    classifications: list[ClassificationSpec] = Field(default_factory=list)
    erasures: list[ErasureSpec] = Field(default_factory=list)
    audit_access: bool = True  # Log all access to classified fields

    model_config = ConfigDict(frozen=True)


# =============================================================================
# Tenancy Configuration (tenancy section)
# =============================================================================


class TenancyMode(StrEnum):
    """Multi-tenancy isolation mode."""

    SINGLE = "single"  # Single tenant (no isolation)
    SHARED_SCHEMA = "shared_schema"  # Shared tables with tenant_id column
    SCHEMA_PER_TENANT = "schema_per_tenant"  # Separate schema per tenant
    DATABASE_PER_TENANT = "database_per_tenant"  # Separate database per tenant


class TopicNamespaceMode(StrEnum):
    """How topics are namespaced for multi-tenancy."""

    SHARED = "shared"  # All tenants share topics (partition by tenant_id)
    NAMESPACE_PER_TENANT = "namespace_per_tenant"  # tenant.topic naming


class TenantIsolationSpec(BaseModel):
    """
    Tenant isolation requirements.

    DSL syntax:
        tenancy:
          mode: shared_schema
          partition_key: tenant_id
          topics: namespace_per_tenant
    """

    mode: TenancyMode = TenancyMode.SHARED_SCHEMA
    partition_key: str = "tenant_id"
    topic_namespace: TopicNamespaceMode = TopicNamespaceMode.SHARED

    model_config = ConfigDict(frozen=True)


class TenancySpec(BaseModel):
    """
    Complete tenancy specification.

    DSL syntax:
        tenancy:
          mode: shared_schema
          partition_key: tenant_id
          topics: namespace_per_tenant
          admin_personas: [super_admin, support]
          per_tenant_config:
            locale: str
            theme: str
            feature_billing: bool

    Attributes:
        isolation: How tenants are separated (mode + partition key etc).
        entities_excluded: Entities that are not tenant-scoped (e.g.
            framework-shared catalogues).
        admin_personas: Persona names whose grants bypass the tenant
            scope filter (#957). Cycle 2 wires this into Cedar policy
            generation; cycle 1 just captures the declaration.
        per_tenant_config: Key→type map for per-tenant configuration
            (#957). Cycle 4 stores these values on a framework
            ``Tenant`` entity and exposes them via
            ``request.state.tenant_config``. Type strings: ``str``,
            ``int``, ``bool``, ``locale``.
    """

    isolation: TenantIsolationSpec = Field(default_factory=TenantIsolationSpec)
    entities_excluded: list[str] = Field(default_factory=list)  # Entities not tenant-scoped
    # #957 cycle 1: persona-bypass + per-tenant config declarations
    admin_personas: list[str] = Field(default_factory=list)
    per_tenant_config: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True)
