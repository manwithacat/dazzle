"""Tests for Stub Generator."""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from dazzle.stubs.generator import StubGenerator, generate_stub_file
from dazzle.stubs.models import DomainServiceSpec, ServiceField, ServiceKind


class TestStubGenerator:
    """Test the StubGenerator class."""

    @pytest.fixture
    def generator(self) -> StubGenerator:
        return StubGenerator()

    @pytest.fixture
    def sample_service(self) -> DomainServiceSpec:
        """Create a sample domain service specification."""
        return DomainServiceSpec(
            id="calculate_vat",
            title="Calculate VAT for invoice",
            kind=ServiceKind.DOMAIN_LOGIC,
            inputs=[
                ServiceField(name="invoice_id", type_name="uuid", required=True),
            ],
            outputs=[
                ServiceField(name="vat_amount", type_name="money"),
                ServiceField(name="breakdown", type_name="json"),
            ],
            guarantees=[
                "Must not mutate the invoice record.",
                "Must raise a domain error if configuration is incomplete.",
            ],
        )

    @pytest.fixture
    def complex_service(self) -> DomainServiceSpec:
        """Create a more complex service specification."""
        return DomainServiceSpec(
            id="process_order",
            title="Process an order for fulfillment",
            kind=ServiceKind.WORKFLOW,
            inputs=[
                ServiceField(name="order_id", type_name="uuid", required=True),
                ServiceField(name="customer_id", type_name="uuid", required=True),
                ServiceField(name="priority", type_name="int", required=False),
            ],
            outputs=[
                ServiceField(name="confirmation_number", type_name="str"),
                ServiceField(name="estimated_delivery", type_name="date"),
                ServiceField(name="total_cost", type_name="decimal"),
            ],
            guarantees=["Must validate inventory before processing."],
        )

    # === Python Stub Generation ===

    def test_generate_python_stub_header(
        self, generator: StubGenerator, sample_service: DomainServiceSpec
    ) -> None:
        """Python stub should have proper header."""
        stub = generator.generate_stub(sample_service, "python")

        assert "# === AUTO-GENERATED HEADER" in stub
        assert "Service ID: calculate_vat" in stub
        assert "Kind: domain_logic" in stub
        assert "Calculate VAT for invoice" in stub
        assert "invoice_id: uuid" in stub
        assert "vat_amount: money" in stub
        assert "Must not mutate the invoice record" in stub

    def test_generate_python_stub_types(
        self, generator: StubGenerator, sample_service: DomainServiceSpec
    ) -> None:
        """Python stub should have TypedDict for output."""
        stub = generator.generate_stub(sample_service, "python")

        assert "from typing import TypedDict" in stub
        assert "class CalculateVatResult(TypedDict):" in stub
        assert "vat_amount: float" in stub
        assert "breakdown: dict" in stub

    def test_generate_python_stub_signature(
        self, generator: StubGenerator, sample_service: DomainServiceSpec
    ) -> None:
        """Python stub should have correct function signature."""
        stub = generator.generate_stub(sample_service, "python")

        assert "def calculate_vat(invoice_id: str) -> CalculateVatResult:" in stub

    def test_generate_python_stub_implementation(
        self, generator: StubGenerator, sample_service: DomainServiceSpec
    ) -> None:
        """Python stub should have implementation placeholder."""
        stub = generator.generate_stub(sample_service, "python")

        assert "IMPLEMENTATION SECTION" in stub
        assert 'raise NotImplementedError("Implement this service")' in stub

    def test_generate_python_stub_complex(
        self, generator: StubGenerator, complex_service: DomainServiceSpec
    ) -> None:
        """Python stub should handle multiple inputs and outputs."""
        stub = generator.generate_stub(complex_service, "python")

        # Check function signature with multiple params
        assert "def process_order(" in stub
        assert "order_id: str" in stub
        assert "customer_id: str" in stub
        assert "priority: int" in stub

        # Check output type
        assert "class ProcessOrderResult(TypedDict):" in stub
        assert "confirmation_number: str" in stub
        assert "estimated_delivery: str" in stub
        assert "total_cost: float" in stub

    # === TypeScript Stub Generation ===

    def test_generate_typescript_stub_header(
        self, generator: StubGenerator, sample_service: DomainServiceSpec
    ) -> None:
        """TypeScript stub should have proper header."""
        stub = generator.generate_stub(sample_service, "typescript")

        assert "// === AUTO-GENERATED HEADER" in stub
        assert "Service ID: calculate_vat" in stub
        assert "Kind: domain_logic" in stub

    def test_generate_typescript_stub_types(
        self, generator: StubGenerator, sample_service: DomainServiceSpec
    ) -> None:
        """TypeScript stub should have interface for output."""
        stub = generator.generate_stub(sample_service, "typescript")

        assert "export interface CalculateVatResult {" in stub
        assert "vat_amount: number;" in stub
        assert "breakdown: Record<string, unknown>;" in stub

    def test_generate_typescript_stub_signature(
        self, generator: StubGenerator, sample_service: DomainServiceSpec
    ) -> None:
        """TypeScript stub should have correct function signature."""
        stub = generator.generate_stub(sample_service, "typescript")

        assert "export async function calculate_vat(" in stub
        assert "invoice_id: string" in stub
        assert "): Promise<CalculateVatResult>" in stub

    def test_generate_typescript_stub_implementation(
        self, generator: StubGenerator, sample_service: DomainServiceSpec
    ) -> None:
        """TypeScript stub should have implementation placeholder."""
        stub = generator.generate_stub(sample_service, "typescript")

        assert "IMPLEMENTATION SECTION" in stub
        assert 'throw new Error("Not implemented")' in stub

    # === Type Mappings ===

    def test_dsl_to_python_type_mappings(self, generator: StubGenerator) -> None:
        """DSL types should map correctly to Python types."""
        assert generator._dsl_to_python_type("uuid") == "str"
        assert generator._dsl_to_python_type("str") == "str"
        assert generator._dsl_to_python_type("str(200)") == "str"
        assert generator._dsl_to_python_type("int") == "int"
        assert generator._dsl_to_python_type("decimal") == "float"
        assert generator._dsl_to_python_type("decimal(10,2)") == "float"
        assert generator._dsl_to_python_type("money") == "float"
        assert generator._dsl_to_python_type("bool") == "bool"
        assert generator._dsl_to_python_type("json") == "dict"

    def test_dsl_to_typescript_type_mappings(self, generator: StubGenerator) -> None:
        """DSL types should map correctly to TypeScript types."""
        assert generator._dsl_to_typescript_type("uuid") == "string"
        assert generator._dsl_to_typescript_type("str") == "string"
        assert generator._dsl_to_typescript_type("int") == "number"
        assert generator._dsl_to_typescript_type("decimal") == "number"
        assert generator._dsl_to_typescript_type("money") == "number"
        assert generator._dsl_to_typescript_type("bool") == "boolean"
        assert generator._dsl_to_typescript_type("json") == "Record<string, unknown>"

    # === File Generation ===

    def test_generate_stub_file(self, sample_service: DomainServiceSpec) -> None:
        """generate_stub_file should create file on disk."""
        with TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            stub_path = generate_stub_file(sample_service, output_dir, "python")

            assert stub_path.exists()
            assert stub_path.name == "calculate_vat.py"

            content = stub_path.read_text()
            assert "def calculate_vat" in content

    def test_generate_typescript_stub_file(self, sample_service: DomainServiceSpec) -> None:
        """generate_stub_file should create TypeScript file."""
        with TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            stub_path = generate_stub_file(sample_service, output_dir, "typescript")

            assert stub_path.exists()
            assert stub_path.name == "calculate_vat.ts"

            content = stub_path.read_text()
            assert "export async function calculate_vat" in content

    # === Update Preservation ===

    def test_update_stub_preserves_implementation(
        self, generator: StubGenerator, sample_service: DomainServiceSpec
    ) -> None:
        """update_stub should preserve existing implementation."""
        with TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            stub_path = output_dir / "calculate_vat.py"

            # Generate initial stub
            initial = generator.generate_stub(sample_service, "python")
            stub_path.write_text(initial)

            # Simulate user adding implementation
            modified = initial.replace(
                'raise NotImplementedError("Implement this service")',
                """# Custom implementation
    invoice = get_invoice(invoice_id)
    vat_rate = 0.20
    return {
        "vat_amount": invoice.total * vat_rate,
        "breakdown": {"rate": vat_rate}
    }""",
            )
            stub_path.write_text(modified)

            # Update service with new description
            updated_service = DomainServiceSpec(
                id="calculate_vat",
                title="Calculate VAT for invoice (UPDATED)",
                kind=ServiceKind.DOMAIN_LOGIC,
                inputs=[
                    ServiceField(name="invoice_id", type_name="uuid", required=True),
                ],
                outputs=[
                    ServiceField(name="vat_amount", type_name="money"),
                    ServiceField(name="breakdown", type_name="json"),
                ],
                guarantees=["Updated guarantee"],
            )

            # Regenerate - should preserve implementation
            updated = generator.update_stub(updated_service, stub_path)

            # New header should be there
            assert "UPDATED" in updated
            assert "Updated guarantee" in updated

            # Implementation should be preserved
            assert "Custom implementation" in updated
            assert "get_invoice(invoice_id)" in updated

    # === Edge Cases ===

    def test_service_no_inputs(self, generator: StubGenerator) -> None:
        """Service with no inputs should generate valid stub."""
        service = DomainServiceSpec(
            id="get_system_time",
            outputs=[ServiceField(name="timestamp", type_name="datetime")],
        )
        stub = generator.generate_stub(service, "python")

        assert "def get_system_time() -> GetSystemTimeResult:" in stub

    def test_service_no_outputs(self, generator: StubGenerator) -> None:
        """Service with no outputs should return None."""
        service = DomainServiceSpec(
            id="send_notification",
            inputs=[ServiceField(name="message", type_name="str")],
        )
        stub = generator.generate_stub(service, "python")

        assert "def send_notification(message: str) -> None:" in stub

    def test_unsupported_language(
        self, generator: StubGenerator, sample_service: DomainServiceSpec
    ) -> None:
        """Unsupported language should raise error."""
        with pytest.raises(ValueError, match="Unsupported language"):
            generator.generate_stub(sample_service, "rust")


class TestDomainServiceSpec:
    """Test DomainServiceSpec model methods."""

    def test_python_function_name(self) -> None:
        """Function name should match service ID."""
        service = DomainServiceSpec(id="calculate_vat")
        assert service.python_function_name() == "calculate_vat"

    def test_result_type_name_simple(self) -> None:
        """Result type should be PascalCase + Result."""
        service = DomainServiceSpec(id="calculate_vat")
        assert service.result_type_name() == "CalculateVatResult"

    def test_result_type_name_complex(self) -> None:
        """Result type should handle multi-part names."""
        service = DomainServiceSpec(id="process_order_fulfillment")
        assert service.result_type_name() == "ProcessOrderFulfillmentResult"
