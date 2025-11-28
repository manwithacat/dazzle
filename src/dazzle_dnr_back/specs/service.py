"""
Service specification types for BackendSpec.

Defines domain services, operations, and business rules.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

# =============================================================================
# Schema Specifications
# =============================================================================


class SchemaFieldSpec(BaseModel):
    """
    Field in a schema (for service inputs/outputs).

    Simpler than entity FieldSpec - just name, type, and required flag.
    """

    name: str = Field(description="Field name")
    type: str = Field(description="Field type (str, int, bool, EntityName, etc.)")
    required: bool = Field(default=True, description="Is this field required?")
    description: str | None = Field(default=None, description="Field description")

    class Config:
        frozen = True


class SchemaSpec(BaseModel):
    """
    Schema specification for service inputs/outputs.

    Example:
        SchemaSpec(
            fields=[
                SchemaFieldSpec(name="client_id", type="uuid", required=True),
                SchemaFieldSpec(name="status", type="str", required=False),
            ]
        )
    """

    fields: list[SchemaFieldSpec] = Field(
        default_factory=list, description="Schema fields"
    )
    description: str | None = Field(default=None, description="Schema description")

    class Config:
        frozen = True

    def get_field(self, name: str) -> SchemaFieldSpec | None:
        """Get field by name."""
        for field in self.fields:
            if field.name == name:
                return field
        return None


# =============================================================================
# Domain Operations
# =============================================================================


class OperationKind(str, Enum):
    """Types of domain operations."""

    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    LIST = "list"
    SEARCH = "search"
    CUSTOM = "custom"


class DomainOperation(BaseModel):
    """
    Domain operation specification.

    Describes what the service does at a domain level.

    Example:
        DomainOperation(kind=OperationKind.CREATE, entity="Invoice")
        DomainOperation(kind=OperationKind.CUSTOM, name="calculate_total")
    """

    kind: OperationKind = Field(description="Operation type")
    entity: str | None = Field(
        default=None, description="Target entity (for CRUD operations)"
    )
    name: str | None = Field(
        default=None, description="Operation name (for custom operations)"
    )
    description: str | None = Field(default=None, description="Operation description")

    class Config:
        frozen = True


# =============================================================================
# Effects
# =============================================================================


class EffectKind(str, Enum):
    """Types of side effects."""

    SEND_EMAIL = "send_email"
    SEND_SMS = "send_sms"
    LOG = "log"
    NOTIFY = "notify"
    CALL_WEBHOOK = "call_webhook"
    CUSTOM = "custom"


class EffectSpec(BaseModel):
    """
    Side effect specification.

    Describes effects that occur when the service executes.

    Example:
        EffectSpec(kind=EffectKind.SEND_EMAIL, config={"template": "invoice_created"})
    """

    kind: EffectKind = Field(description="Effect type")
    config: dict[str, Any] = Field(
        default_factory=dict, description="Effect configuration"
    )
    description: str | None = Field(default=None, description="Effect description")

    class Config:
        frozen = True


# =============================================================================
# Business Rules
# =============================================================================


class RuleKind(str, Enum):
    """Types of business rules."""

    PRECONDITION = "precondition"
    POSTCONDITION = "postcondition"
    INVARIANT = "invariant"
    VALIDATION = "validation"


class BusinessRuleSpec(BaseModel):
    """
    Business rule specification.

    Defines constraints and invariants for service execution.

    Example:
        BusinessRuleSpec(
            kind=RuleKind.PRECONDITION,
            expr="client.credit_limit > invoice.total",
            message="Client credit limit exceeded"
        )
    """

    kind: RuleKind = Field(description="Rule type")
    expr: str = Field(description="Rule expression (evaluated at runtime)")
    message: str | None = Field(
        default=None, description="Error message if rule fails"
    )
    description: str | None = Field(default=None, description="Rule description")

    class Config:
        frozen = True


# =============================================================================
# Services
# =============================================================================


class ServiceSpec(BaseModel):
    """
    Service specification.

    A service represents a domain operation with inputs, outputs, and business logic.

    Example:
        ServiceSpec(
            name="create_invoice",
            description="Create a new invoice for a client",
            inputs=SchemaSpec(fields=[
                SchemaFieldSpec(name="client_id", type="uuid"),
                SchemaFieldSpec(name="items", type="list[InvoiceItem]"),
            ]),
            outputs=SchemaSpec(fields=[
                SchemaFieldSpec(name="invoice", type="Invoice"),
            ]),
            domain_operation=DomainOperation(kind=OperationKind.CREATE, entity="Invoice"),
            effects=[EffectSpec(kind=EffectKind.SEND_EMAIL, config={"template": "invoice_created"})],
            constraints=[BusinessRuleSpec(kind=RuleKind.PRECONDITION, expr="client.active == true")]
        )
    """

    name: str = Field(description="Service name")
    description: str | None = Field(default=None, description="Service description")
    inputs: SchemaSpec = Field(
        default_factory=SchemaSpec, description="Input schema"
    )
    outputs: SchemaSpec = Field(
        default_factory=SchemaSpec, description="Output schema"
    )
    domain_operation: DomainOperation = Field(description="Domain operation")
    effects: list[EffectSpec] = Field(
        default_factory=list, description="Side effects"
    )
    constraints: list[BusinessRuleSpec] = Field(
        default_factory=list, description="Business rules and constraints"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )

    class Config:
        frozen = True

    @property
    def is_crud(self) -> bool:
        """Check if this is a CRUD operation."""
        return self.domain_operation.kind in [
            OperationKind.CREATE,
            OperationKind.READ,
            OperationKind.UPDATE,
            OperationKind.DELETE,
            OperationKind.LIST,
        ]

    @property
    def target_entity(self) -> str | None:
        """Get target entity for CRUD operations."""
        return self.domain_operation.entity
