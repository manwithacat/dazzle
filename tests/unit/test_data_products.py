"""
Unit tests for Data Products module.

Tests for:
- Curated topic generation
- Data transformation (mask, pseudonymise, minimise)
- Cross-tenant validation

Part of v0.18.0 Event-First Architecture (Issue #25, Phase G).
"""

import pytest

from dazzle.core.ir import AppSpec
from dazzle.core.ir.domain import DomainSpec, EntitySpec, FieldSpec
from dazzle.core.ir.fields import FieldType, FieldTypeKind
from dazzle.core.ir.governance import (
    ClassificationSpec,
    DataClassification,
    DataProductSpec,
    DataProductsSpec,
    DataProductTransform,
    PoliciesSpec,
)
from dazzle_dnr_back.data_products import (
    CrossTenantPolicy,
    CrossTenantValidator,
    CuratedTopicGenerator,
    DataProductTransformer,
    PolicyTestGenerator,
    generate_curated_topics,
)
from dazzle_dnr_back.data_products.cross_tenant import (
    CrossTenantAuditAction,
    CrossTenantPermission,
)


@pytest.fixture
def sample_entity() -> EntitySpec:
    """Create a sample entity for testing."""
    return EntitySpec(
        name="Customer",
        title="Customer",
        fields=[
            FieldSpec(name="id", type=FieldType(kind=FieldTypeKind.UUID)),
            FieldSpec(name="name", type=FieldType(kind=FieldTypeKind.STR)),
            FieldSpec(name="email", type=FieldType(kind=FieldTypeKind.STR)),
            FieldSpec(name="phone", type=FieldType(kind=FieldTypeKind.STR)),
            FieldSpec(name="total_purchases", type=FieldType(kind=FieldTypeKind.DECIMAL)),
        ],
    )


@pytest.fixture
def sample_policies() -> PoliciesSpec:
    """Create sample policies for testing."""
    return PoliciesSpec(
        classifications=[
            ClassificationSpec(
                entity="Customer",
                field="email",
                classification=DataClassification.PII_DIRECT,
            ),
            ClassificationSpec(
                entity="Customer",
                field="phone",
                classification=DataClassification.PII_DIRECT,
            ),
            ClassificationSpec(
                entity="Customer",
                field="total_purchases",
                classification=DataClassification.FINANCIAL_TXN,
            ),
        ],
    )


@pytest.fixture
def sample_data_products() -> DataProductsSpec:
    """Create sample data products for testing."""
    return DataProductsSpec(
        products=[
            DataProductSpec(
                name="analytics_v1",
                source_entities=["Customer"],
                allow_classifications=[DataClassification.FINANCIAL_TXN],
                deny_classifications=[DataClassification.PII_DIRECT],
                transforms=[DataProductTransform.MASK],
                cross_tenant=False,
            ),
            DataProductSpec(
                name="aggregate_report",
                source_entities=["Customer"],
                allow_classifications=[],  # Allow all non-denied
                deny_classifications=[DataClassification.PII_DIRECT],
                transforms=[DataProductTransform.AGGREGATE],
                cross_tenant=True,
            ),
        ],
        default_namespace="curated",
    )


@pytest.fixture
def sample_appspec(
    sample_entity: EntitySpec,
    sample_policies: PoliciesSpec,
    sample_data_products: DataProductsSpec,
) -> AppSpec:
    """Create a sample AppSpec for testing."""
    return AppSpec(
        name="test_app",
        title="Test Application",
        domain=DomainSpec(entities=[sample_entity]),
        policies=sample_policies,
        data_products=sample_data_products,
    )


class TestCuratedTopicGenerator:
    """Tests for CuratedTopicGenerator."""

    def test_generate_creates_topics_for_all_products(
        self, sample_appspec: AppSpec
    ) -> None:
        """Test that topics are generated for all data products."""
        generator = CuratedTopicGenerator(sample_appspec)
        configs = generator.generate()

        assert len(configs) == 2
        assert configs[0].product_name == "analytics_v1"
        assert configs[1].product_name == "aggregate_report"

    def test_topic_naming_uses_namespace(
        self, sample_appspec: AppSpec
    ) -> None:
        """Test that topics use the curated namespace."""
        configs = generate_curated_topics(sample_appspec)

        assert configs[0].topic_name == "curated.analytics_v1"
        assert configs[1].topic_name == "curated.aggregate_report"

    def test_denied_fields_are_excluded(
        self, sample_appspec: AppSpec
    ) -> None:
        """Test that PII_DIRECT fields are excluded when denied."""
        configs = generate_curated_topics(sample_appspec)

        # analytics_v1 denies PII_DIRECT
        analytics = configs[0]

        # Check email and phone are denied
        denied_names = {f.field_name for f in analytics.field_filters if not f.allowed}
        assert "email" in denied_names
        assert "phone" in denied_names

    def test_allowed_fields_based_on_classification(
        self, sample_appspec: AppSpec
    ) -> None:
        """Test that fields are allowed based on classification."""
        configs = generate_curated_topics(sample_appspec)

        # analytics_v1 allows FINANCIAL_TXN
        analytics = configs[0]

        # Find total_purchases filter
        total_filter = next(
            (f for f in analytics.field_filters if f.field_name == "total_purchases"),
            None,
        )
        assert total_filter is not None
        assert total_filter.allowed

    def test_cross_tenant_flag_is_set(
        self, sample_appspec: AppSpec
    ) -> None:
        """Test that cross_tenant flag is propagated."""
        configs = generate_curated_topics(sample_appspec)

        assert configs[0].cross_tenant is False
        assert configs[1].cross_tenant is True


class TestDataProductTransformer:
    """Tests for DataProductTransformer."""

    def test_mask_email(self) -> None:
        """Test email masking."""
        transformer = DataProductTransformer()
        result = transformer._mask_email("john.doe@example.com")
        assert result == "j***@example.com"

    def test_mask_phone(self) -> None:
        """Test phone masking."""
        transformer = DataProductTransformer()
        result = transformer._mask_phone("555-123-4567")
        assert result == "***-***-4567"

    def test_mask_card(self) -> None:
        """Test card number masking."""
        transformer = DataProductTransformer()
        result = transformer._mask_card("4111-1111-1111-1234")
        assert result == "****-****-****-1234"

    def test_pseudonymise_consistency(self) -> None:
        """Test that pseudonymisation is consistent."""
        transformer = DataProductTransformer()

        result1 = transformer._pseudonymise_value("user_123")
        result2 = transformer._pseudonymise_value("user_123")

        assert result1 == result2
        assert result1.startswith("PSEUDO_")

    def test_pseudonymise_different_values(self) -> None:
        """Test that different values get different pseudonyms."""
        transformer = DataProductTransformer()

        result1 = transformer._pseudonymise_value("user_123")
        result2 = transformer._pseudonymise_value("user_456")

        assert result1 != result2

    def test_minimise_truncates_long_strings(self) -> None:
        """Test that minimise truncates long strings."""
        transformer = DataProductTransformer()

        long_string = "A" * 100
        result = transformer._minimise_value(long_string)

        assert len(result) == 50
        assert result.endswith("...")

    def test_minimise_rounds_floats(self) -> None:
        """Test that minimise rounds floats."""
        transformer = DataProductTransformer()

        result = transformer._minimise_value(123.456789)

        assert result == 123.46

    def test_transform_filters_denied_fields(
        self, sample_appspec: AppSpec
    ) -> None:
        """Test that transform excludes denied fields."""
        configs = generate_curated_topics(sample_appspec)
        transformer = DataProductTransformer()

        payload = {
            "id": "123",
            "name": "John Doe",
            "email": "john@example.com",
            "phone": "555-1234",
            "total_purchases": 100.00,
        }

        result = transformer.transform(
            payload,
            configs[0],  # analytics_v1
            entity_name="Customer",
        )

        # email and phone should be excluded
        assert "email" not in result.data
        assert "phone" not in result.data

        # total_purchases should be included
        assert "total_purchases" in result.data


class TestCrossTenantValidator:
    """Tests for CrossTenantValidator."""

    def test_same_tenant_always_allowed(self) -> None:
        """Test that same-tenant access is always allowed."""
        validator = CrossTenantValidator()

        result = validator.check_access(
            requesting_tenant="tenant_a",
            target_tenants=["tenant_a"],
            product_name="analytics_v1",
        )

        assert result.permitted

    def test_cross_tenant_denied_without_policy(self) -> None:
        """Test that cross-tenant is denied without explicit policy."""
        validator = CrossTenantValidator()

        result = validator.check_access(
            requesting_tenant="tenant_a",
            target_tenants=["tenant_b"],
            product_name="analytics_v1",
        )

        assert not result.permitted
        assert "not permitted" in result.reason

    def test_cross_tenant_allowed_with_policy(self) -> None:
        """Test that cross-tenant is allowed with proper policy."""
        validator = CrossTenantValidator()
        validator.add_policy(
            CrossTenantPolicy(
                tenant_id="tenant_a",
                permission=CrossTenantPermission.READ_AGGREGATED,
            )
        )

        result = validator.check_access(
            requesting_tenant="tenant_a",
            target_tenants=["tenant_b"],
            product_name="analytics_v1",
        )

        assert result.permitted

    def test_product_denylist(self) -> None:
        """Test that product denylist is enforced."""
        validator = CrossTenantValidator()
        validator.add_policy(
            CrossTenantPolicy(
                tenant_id="tenant_a",
                permission=CrossTenantPermission.READ_AGGREGATED,
                denied_products=["sensitive_product"],
            )
        )

        result = validator.check_access(
            requesting_tenant="tenant_a",
            target_tenants=["tenant_b"],
            product_name="sensitive_product",
        )

        assert not result.permitted
        assert "explicitly denied" in result.reason

    def test_audit_logging(self) -> None:
        """Test that access is logged."""
        validator = CrossTenantValidator()

        entry = validator.audit_access(
            requesting_tenant="tenant_a",
            target_tenants=["tenant_b"],
            product_name="analytics_v1",
            action=CrossTenantAuditAction.QUERY,
            record_count=100,
        )

        assert entry.requesting_tenant == "tenant_a"
        assert entry.record_count == 100

        log = validator.get_audit_log()
        assert len(log) == 1

    def test_constraints_returned(self) -> None:
        """Test that constraints are returned with access check."""
        validator = CrossTenantValidator()
        validator.add_policy(
            CrossTenantPolicy(
                tenant_id="tenant_a",
                permission=CrossTenantPermission.READ_AGGREGATED,
                max_records_per_query=5000,
                require_aggregation=True,
            )
        )

        result = validator.check_access(
            requesting_tenant="tenant_a",
            target_tenants=["tenant_b"],
            product_name="analytics_v1",
        )

        assert result.constraints["max_records"] == 5000
        assert result.constraints["require_aggregation"] is True


class TestPolicyTestGenerator:
    """Tests for PolicyTestGenerator."""

    def test_generates_test_cases(self, sample_appspec: AppSpec) -> None:
        """Test that test cases are generated."""
        generator = PolicyTestGenerator(sample_appspec)
        suites = generator.generate_all()

        assert len(suites) == 2  # Two data products

        # Each suite should have test cases
        for suite in suites:
            assert len(suite.test_cases) > 0

    def test_generates_classification_tests(
        self, sample_appspec: AppSpec
    ) -> None:
        """Test that classification tests are generated."""
        generator = PolicyTestGenerator(sample_appspec)
        suites = generator.generate_all()

        analytics_suite = suites[0]
        classification_tests = [
            t for t in analytics_suite.test_cases if t.test_type == "classification"
        ]

        assert len(classification_tests) > 0

    def test_generates_pytest_code(self, sample_appspec: AppSpec) -> None:
        """Test that pytest code is generated."""
        generator = PolicyTestGenerator(sample_appspec)
        code = generator.generate_pytest_code()

        assert "import pytest" in code
        assert "class TestDataProduct" in code
        assert "def test_" in code
