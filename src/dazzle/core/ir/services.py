"""
Service types for DAZZLE IR.

This module contains:
- APISpec: External service specifications (third-party APIs)
- DomainServiceSpec: Internal domain services (business logic stubs)
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class AuthKind(StrEnum):
    """Authentication profile types."""

    OAUTH2_LEGACY = "oauth2_legacy"
    OAUTH2_PKCE = "oauth2_pkce"
    JWT_STATIC = "jwt_static"
    API_KEY_HEADER = "api_key_header"
    API_KEY_QUERY = "api_key_query"
    NONE = "none"


class AuthProfile(BaseModel):
    """
    Authentication profile for a service.

    Attributes:
        kind: Type of authentication
        options: Additional auth options (scopes, etc.)
    """

    kind: AuthKind
    options: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True)


class APISpec(BaseModel):
    """
    Specification for an external API service.

    APIs represent third-party systems that the app integrates with.

    Attributes:
        name: API identifier
        title: Human-readable title
        spec_url: URL to API spec (often OpenAPI)
        spec_inline: Inline spec identifier
        auth_profile: Authentication configuration
        owner: API owner/provider
    """

    name: str
    title: str | None = None
    spec_url: str | None = None
    spec_inline: str | None = None
    auth_profile: AuthProfile
    owner: str | None = None

    model_config = ConfigDict(frozen=True)


# ============================================================================
# Domain Services (v0.5.0) - Business logic stubs
# ============================================================================


class DomainServiceKind(StrEnum):
    """Types of domain services."""

    DOMAIN_LOGIC = "domain_logic"  # Business calculations, transformations
    VALIDATION = "validation"  # Complex validation rules
    INTEGRATION = "integration"  # Orchestration of external calls
    WORKFLOW = "workflow"  # Multi-step business processes


class StubLanguage(StrEnum):
    """Supported stub implementation languages."""

    PYTHON = "python"
    TYPESCRIPT = "typescript"


class ServiceFieldSpec(BaseModel):
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

    DSL syntax:
        service calculate_vat "Calculate VAT for invoice":
          kind: domain_logic

          input:
            invoice_id: uuid required

          output:
            vat_amount: money
            breakdown: json

          guarantees:
            - "Must not mutate the invoice record."

          stub: python

    Attributes:
        name: Service identifier (snake_case)
        title: Human-readable title
        description: Detailed description
        kind: Type of service
        inputs: Input field specifications
        outputs: Output field specifications
        guarantees: Behavioral guarantees (documentation)
        stub_language: Target implementation language
    """

    name: str
    title: str | None = None
    description: str | None = None
    kind: DomainServiceKind = DomainServiceKind.DOMAIN_LOGIC
    inputs: list[ServiceFieldSpec] = Field(default_factory=list)
    outputs: list[ServiceFieldSpec] = Field(default_factory=list)
    guarantees: list[str] = Field(default_factory=list)
    stub_language: StubLanguage = StubLanguage.PYTHON

    model_config = ConfigDict(frozen=True)

    def python_function_name(self) -> str:
        """Return the Python function name for this service."""
        return self.name

    def result_type_name(self) -> str:
        """Return the TypedDict name for the result type."""
        # Convert snake_case to PascalCase and add Result
        parts = self.name.split("_")
        pascal = "".join(word.capitalize() for word in parts)
        return f"{pascal}Result"
