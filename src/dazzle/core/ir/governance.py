"""
Data governance IR types for DAZZLE.

This module contains IR types for:
- policies: Field classification, data governance rules
- tenancy: Multi-tenancy configuration
- data_products: Curated data pipelines

Part of v0.18.0 Event-First Architecture (Issue #25).
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

# =============================================================================
# Field Classification (policies section)
# =============================================================================


class DataClassification(str, Enum):
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


class RetentionPolicy(str, Enum):
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


class ErasurePolicy(str, Enum):
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
    cascade: bool = False  # Cascade to related entities

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
    default_retention: RetentionPolicy = RetentionPolicy.MEDIUM
    audit_access: bool = True  # Log all access to classified fields

    model_config = ConfigDict(frozen=True)


# =============================================================================
# Tenancy Configuration (tenancy section)
# =============================================================================


class TenancyMode(str, Enum):
    """Multi-tenancy isolation mode."""

    SINGLE = "single"  # Single tenant (no isolation)
    SHARED_SCHEMA = "shared_schema"  # Shared tables with tenant_id column
    SCHEMA_PER_TENANT = "schema_per_tenant"  # Separate schema per tenant
    DATABASE_PER_TENANT = "database_per_tenant"  # Separate database per tenant


class TopicNamespaceMode(str, Enum):
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
    enforce_in_queries: bool = True  # Auto-add tenant filter to queries
    cross_tenant_access: bool = False  # Allow cross-tenant data access

    model_config = ConfigDict(frozen=True)


class TenantProvisioningSpec(BaseModel):
    """
    Tenant provisioning configuration.

    DSL syntax:
        tenancy:
          provisioning:
            auto_create: true
            default_limits:
              users: 100
              storage_gb: 10
    """

    auto_create: bool = True
    require_approval: bool = False
    default_limits: dict[str, int] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True)


class TenancySpec(BaseModel):
    """
    Complete tenancy specification.

    DSL syntax:
        tenancy:
          mode: shared_schema
          partition_key: tenant_id
          topics: namespace_per_tenant
          provisioning:
            auto_create: true
    """

    isolation: TenantIsolationSpec = Field(default_factory=TenantIsolationSpec)
    provisioning: TenantProvisioningSpec = Field(default_factory=TenantProvisioningSpec)
    entities_excluded: list[str] = Field(default_factory=list)  # Entities not tenant-scoped

    model_config = ConfigDict(frozen=True)


# =============================================================================
# Interfaces (interfaces section)
# =============================================================================


class InterfaceFormat(str, Enum):
    """Supported interface formats."""

    REST = "rest"
    GRAPHQL = "graphql"
    GRPC = "grpc"
    ASYNCAPI = "asyncapi"  # Event-driven
    SOAP = "soap"  # Legacy
    EDIFACT = "edifact"  # EDI


class InterfaceAuthMethod(str, Enum):
    """Authentication methods for interfaces."""

    NONE = "none"
    API_KEY = "api_key"
    OAUTH2 = "oauth2"
    JWT = "jwt"
    MUTUAL_TLS = "mtls"
    BASIC = "basic"


class InterfaceEndpointSpec(BaseModel):
    """
    Single interface endpoint specification.

    DSL syntax:
        interfaces:
          api orders_api:
            format: rest
            base_path: /api/v1/orders
            auth: oauth2
            operations:
              list: GET /
              create: POST /
              get: GET /{id}
    """

    name: str
    method: str  # GET, POST, etc.
    path: str
    description: str | None = None
    request_entity: str | None = None
    response_entity: str | None = None

    model_config = ConfigDict(frozen=True)


class InterfaceSpec(BaseModel):
    """
    External interface specification.

    DSL syntax:
        interfaces:
          api orders_api:
            format: rest
            base_path: /api/v1
            auth: oauth2
            rate_limit: 1000/hour
    """

    name: str
    title: str | None = None
    format: InterfaceFormat = InterfaceFormat.REST
    base_path: str = "/"
    auth: InterfaceAuthMethod = InterfaceAuthMethod.API_KEY
    rate_limit: str | None = None  # e.g., "1000/hour"
    endpoints: list[InterfaceEndpointSpec] = Field(default_factory=list)
    version: str = "v1"

    model_config = ConfigDict(frozen=True)


class InterfacesSpec(BaseModel):
    """
    Complete interfaces specification.

    DSL syntax:
        interfaces:
          api orders_api:
            format: rest
            ...
          api customers_api:
            format: graphql
            ...
    """

    apis: list[InterfaceSpec] = Field(default_factory=list)
    default_auth: InterfaceAuthMethod = InterfaceAuthMethod.API_KEY
    default_rate_limit: str | None = None

    model_config = ConfigDict(frozen=True)


# =============================================================================
# Data Products (data_products section)
# =============================================================================


class DataProductTransform(str, Enum):
    """Transformations applied to data products."""

    NONE = "none"  # Pass through
    MINIMISE = "minimise"  # Remove unnecessary fields
    PSEUDONYMISE = "pseudonymise"  # Replace identifiers
    AGGREGATE = "aggregate"  # Aggregate to remove individual records
    MASK = "mask"  # Partial masking (e.g., email -> j***@example.com)


class DataProductSpec(BaseModel):
    """
    A curated data product specification.

    DSL syntax:
        data_products:
          data_product analytics_v1:
            source: [orders, customers]
            allow: [FINANCIAL_TXN]
            deny: [PII_DIRECT, PII_SENSITIVE]
            transforms: [minimise, aggregate]
            retention: 24_months
            refresh: daily
    """

    name: str
    title: str | None = None
    description: str | None = None
    source_entities: list[str] = Field(default_factory=list)
    source_streams: list[str] = Field(default_factory=list)
    allow_classifications: list[DataClassification] = Field(default_factory=list)
    deny_classifications: list[DataClassification] = Field(default_factory=list)
    transforms: list[DataProductTransform] = Field(default_factory=list)
    retention: str | None = None  # e.g., "24_months"
    refresh: str = "realtime"  # realtime, hourly, daily, weekly
    output_topic: str | None = None  # Curated topic for this product
    cross_tenant: bool = False  # Allow cross-tenant aggregation

    model_config = ConfigDict(frozen=True)


class DataProductsSpec(BaseModel):
    """
    Complete data products specification.

    DSL syntax:
        data_products:
          data_product analytics_v1:
            ...
          data_product reporting_v1:
            ...
    """

    products: list[DataProductSpec] = Field(default_factory=list)
    default_namespace: str = "curated"  # Topic namespace for data products

    model_config = ConfigDict(frozen=True)
