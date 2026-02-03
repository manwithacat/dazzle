"""
Data models for domain service stubs.

Domain services are business logic functions declared in DSL and implemented in stubs.
This is distinct from external ServiceSpec which represents third-party APIs.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ServiceKind(StrEnum):
    """Types of domain services."""

    DOMAIN_LOGIC = "domain_logic"  # Business calculations, transformations
    VALIDATION = "validation"  # Complex validation rules
    INTEGRATION = "integration"  # Orchestration of external calls
    WORKFLOW = "workflow"  # Multi-step business processes


class StubLanguage(StrEnum):
    """Supported stub implementation languages."""

    PYTHON = "python"
    TYPESCRIPT = "typescript"


class ServiceField(BaseModel):
    """
    A field in a service input or output contract.

    Attributes:
        name: Field name (snake_case)
        type_name: Type annotation (e.g., 'uuid', 'str', 'money', 'json')
        required: Whether the field is required (for inputs)
        description: Optional field description
    """

    name: str
    type_name: str
    required: bool = True
    description: str | None = None

    model_config = ConfigDict(frozen=True)


class DomainServiceSpec(BaseModel):
    """
    Specification for a domain service (business logic).

    Domain services are declared in DSL (contracts only) and implemented
    in stub files (Turing-complete logic). This is the extensibility mechanism.

    Attributes:
        id: Service identifier (snake_case)
        title: Human-readable title
        description: Detailed description
        kind: Type of service
        inputs: Input field specifications
        outputs: Output field specifications
        guarantees: Behavioral guarantees (documentation)
        stub_language: Target implementation language
    """

    id: str
    title: str | None = None
    description: str | None = None
    kind: ServiceKind = ServiceKind.DOMAIN_LOGIC
    inputs: list[ServiceField] = Field(default_factory=list)
    outputs: list[ServiceField] = Field(default_factory=list)
    guarantees: list[str] = Field(default_factory=list)
    stub_language: StubLanguage = StubLanguage.PYTHON

    model_config = ConfigDict(frozen=True)

    def python_function_name(self) -> str:
        """Return the Python function name for this service."""
        return self.id

    def result_type_name(self) -> str:
        """Return the TypedDict name for the result type."""
        # Convert snake_case to PascalCase and add Result
        parts = self.id.split("_")
        pascal = "".join(word.capitalize() for word in parts)
        return f"{pascal}Result"
