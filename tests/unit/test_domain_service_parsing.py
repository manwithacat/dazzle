"""
Unit tests for Domain Service DSL parsing (v0.5.0).

Tests the parsing of domain service declarations in DSL files.
"""

from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir import (
    DomainServiceKind,
    StubLanguage,
)


class TestDomainServiceParsing:
    """Tests for domain service parsing."""

    def test_parse_minimal_domain_service(self) -> None:
        """Test parsing a minimal domain service."""
        dsl = """
module test_app

service calculate_vat "Calculate VAT":
  kind: domain_logic
"""
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        assert len(fragment.domain_services) == 1
        service = fragment.domain_services[0]
        assert service.name == "calculate_vat"
        assert service.title == "Calculate VAT"
        assert service.kind == DomainServiceKind.DOMAIN_LOGIC
        assert service.stub_language == StubLanguage.PYTHON  # default

    def test_parse_domain_service_with_inputs(self) -> None:
        """Test parsing domain service with input fields."""
        dsl = """
module test_app

service calculate_vat "Calculate VAT":
  kind: domain_logic
  input:
    invoice_id: uuid required
    country_code: str(2)
"""
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        service = fragment.domain_services[0]
        assert len(service.inputs) == 2
        assert service.inputs[0].name == "invoice_id"
        assert service.inputs[0].type_name == "uuid"
        assert service.inputs[0].required is True
        assert service.inputs[1].name == "country_code"
        assert service.inputs[1].type_name == "str(2)"
        assert service.inputs[1].required is False

    def test_parse_domain_service_with_outputs(self) -> None:
        """Test parsing domain service with output fields."""
        dsl = """
module test_app

service calculate_vat "Calculate VAT":
  kind: domain_logic
  output:
    vat_amount: money
    breakdown: json
"""
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        service = fragment.domain_services[0]
        assert len(service.outputs) == 2
        assert service.outputs[0].name == "vat_amount"
        assert service.outputs[0].type_name == "money"
        assert service.outputs[1].name == "breakdown"
        assert service.outputs[1].type_name == "json"

    def test_parse_domain_service_with_guarantees(self) -> None:
        """Test parsing domain service with guarantees."""
        dsl = """
module test_app

service calculate_vat "Calculate VAT":
  kind: domain_logic
  guarantees:
    - "Must not mutate the invoice record"
    - "Must raise domain error if config incomplete"
"""
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        service = fragment.domain_services[0]
        assert len(service.guarantees) == 2
        assert service.guarantees[0] == "Must not mutate the invoice record"
        assert service.guarantees[1] == "Must raise domain error if config incomplete"

    def test_parse_domain_service_with_stub(self) -> None:
        """Test parsing domain service with stub language."""
        dsl = """
module test_app

service calculate_vat "Calculate VAT":
  kind: domain_logic
  stub: python
"""
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        service = fragment.domain_services[0]
        assert service.stub_language == StubLanguage.PYTHON

    def test_parse_domain_service_with_typescript_stub(self) -> None:
        """Test parsing domain service with TypeScript stub."""
        dsl = """
module test_app

service send_email "Send Email":
  kind: integration
  stub: typescript
"""
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        service = fragment.domain_services[0]
        assert service.stub_language == StubLanguage.TYPESCRIPT

    def test_parse_complete_domain_service(self) -> None:
        """Test parsing a complete domain service with all sections."""
        dsl = """
module test_app

service calculate_vat "Calculate VAT for Invoice":
  kind: domain_logic
  input:
    invoice_id: uuid required
    country_code: str(2)
  output:
    vat_amount: money
    breakdown: json
  guarantees:
    - "Must not mutate the invoice record"
    - "Must raise domain error if config incomplete"
  stub: python
"""
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        assert len(fragment.domain_services) == 1
        service = fragment.domain_services[0]
        assert service.name == "calculate_vat"
        assert service.title == "Calculate VAT for Invoice"
        assert service.kind == DomainServiceKind.DOMAIN_LOGIC
        assert len(service.inputs) == 2
        assert len(service.outputs) == 2
        assert len(service.guarantees) == 2
        assert service.stub_language == StubLanguage.PYTHON


class TestDomainServiceKinds:
    """Tests for different domain service kinds."""

    def test_parse_validation_service(self) -> None:
        """Test parsing validation service kind."""
        dsl = """
module test_app

service validate_invoice "Validate Invoice":
  kind: validation
"""
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        service = fragment.domain_services[0]
        assert service.kind == DomainServiceKind.VALIDATION

    def test_parse_integration_service(self) -> None:
        """Test parsing integration service kind."""
        dsl = """
module test_app

service fetch_exchange_rate "Fetch Exchange Rate":
  kind: integration
"""
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        service = fragment.domain_services[0]
        assert service.kind == DomainServiceKind.INTEGRATION

    def test_parse_workflow_service(self) -> None:
        """Test parsing workflow service kind."""
        dsl = """
module test_app

service process_order "Process Order":
  kind: workflow
"""
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        service = fragment.domain_services[0]
        assert service.kind == DomainServiceKind.WORKFLOW


class TestDomainServiceWithEntities:
    """Tests for domain services alongside entities."""

    def test_parse_service_with_entity(self) -> None:
        """Test parsing service alongside entity."""
        dsl = """
module test_app

entity Invoice "Invoice":
  id: uuid pk
  total: decimal(10,2) required

service calculate_vat "Calculate VAT":
  kind: domain_logic
  input:
    invoice_id: uuid required
  output:
    vat_amount: decimal(10,2)
"""
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        assert len(fragment.entities) == 1
        assert len(fragment.domain_services) == 1
        assert fragment.entities[0].name == "Invoice"
        assert fragment.domain_services[0].name == "calculate_vat"

    def test_parse_multiple_services(self) -> None:
        """Test parsing multiple domain services."""
        dsl = """
module test_app

service calculate_vat "Calculate VAT":
  kind: domain_logic

service send_invoice "Send Invoice":
  kind: integration

service validate_invoice "Validate Invoice":
  kind: validation
"""
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        assert len(fragment.domain_services) == 3
        assert fragment.domain_services[0].name == "calculate_vat"
        assert fragment.domain_services[1].name == "send_invoice"
        assert fragment.domain_services[2].name == "validate_invoice"


class TestExternalApiVsDomainService:
    """Tests to ensure external APIs and domain services are distinguished."""

    def test_external_api_not_parsed_as_domain_service(self) -> None:
        """External APIs (with spec:) should not be in domain_services."""
        dsl = """
module test_app

service stripe_api "Stripe API":
  spec: url "https://api.stripe.com/openapi.yaml"
  auth_profile: api_key_header
"""
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        # External APIs go to apis, not domain_services
        assert len(fragment.domain_services) == 0
        assert len(fragment.apis) == 1
        assert fragment.apis[0].name == "stripe_api"

    def test_mixed_services(self) -> None:
        """Test parsing both external APIs and domain services."""
        dsl = """
module test_app

service stripe_api "Stripe API":
  spec: url "https://api.stripe.com/openapi.yaml"
  auth_profile: api_key_header

service calculate_vat "Calculate VAT":
  kind: domain_logic
  input:
    amount: decimal(10,2) required
"""
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        assert len(fragment.apis) == 1
        assert len(fragment.domain_services) == 1
        assert fragment.apis[0].name == "stripe_api"
        assert fragment.domain_services[0].name == "calculate_vat"
