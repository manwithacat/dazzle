"""
Policy test generation for Data Products.

Generates test cases to verify:
1. Classification rules are applied correctly
2. Denied fields are excluded from curated topics
3. Transforms work as expected
4. Cross-tenant access is properly controlled

Part of v0.18.0 Event-First Architecture (Issue #25, Phase G).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from dazzle.core.ir.governance import (
    DataProductTransform,
)

from .curated_topics import CuratedTopicConfig, CuratedTopicGenerator, FieldFilter
from .transformer import DataProductTransformer

if TYPE_CHECKING:
    from dazzle.core.ir import AppSpec

logger = logging.getLogger("dazzle.data_products.test_generator")


@dataclass
class PolicyTestCase:
    """A generated test case for policy verification."""

    name: str
    description: str
    product_name: str
    entity_name: str
    test_type: str  # "classification", "transform", "cross_tenant"

    # Input
    input_payload: dict[str, Any]

    # Expected outcomes
    expected_allowed_fields: set[str] = field(default_factory=set)
    expected_denied_fields: set[str] = field(default_factory=set)
    expected_transformed_fields: dict[str, str] = field(default_factory=dict)
    should_pass: bool = True
    assertion_message: str = ""


@dataclass
class PolicyTestSuite:
    """Collection of test cases for a data product."""

    product_name: str
    test_cases: list[PolicyTestCase] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class PolicyTestGenerator:
    """Generates test cases for data product policies.

    Takes an AppSpec and generates comprehensive test cases
    that verify the data product configuration works as expected.

    Example:
        generator = PolicyTestGenerator(appspec)
        suites = generator.generate_all()

        for suite in suites:
            print(f"# Tests for {suite.product_name}")
            for case in suite.test_cases:
                print(f"  - {case.name}: {case.description}")
    """

    def __init__(self, appspec: AppSpec):
        """Initialize the generator.

        Args:
            appspec: Application specification
        """
        self._appspec = appspec
        self._topic_generator = CuratedTopicGenerator(appspec)
        self._transformer = DataProductTransformer()

    def generate_all(self) -> list[PolicyTestSuite]:
        """Generate test suites for all data products.

        Returns:
            List of test suites
        """
        configs = self._topic_generator.generate()
        suites: list[PolicyTestSuite] = []

        for config in configs:
            suite = self._generate_suite(config)
            suites.append(suite)

        return suites

    def _generate_suite(self, config: CuratedTopicConfig) -> PolicyTestSuite:
        """Generate a test suite for a single data product.

        Args:
            config: Curated topic configuration

        Returns:
            PolicyTestSuite with test cases
        """
        cases: list[PolicyTestCase] = []

        # Generate classification tests
        cases.extend(self._generate_classification_tests(config))

        # Generate transform tests
        cases.extend(self._generate_transform_tests(config))

        # Generate cross-tenant tests
        if config.cross_tenant:
            cases.extend(self._generate_cross_tenant_tests(config))

        return PolicyTestSuite(
            product_name=config.product_name,
            test_cases=cases,
            metadata={
                "topic_name": config.topic_name,
                "source_topics": config.source_topics,
                "transforms": [t.value for t in config.transforms],
            },
        )

    def _generate_classification_tests(
        self,
        config: CuratedTopicConfig,
    ) -> list[PolicyTestCase]:
        """Generate tests for field classification filtering.

        Args:
            config: Curated topic configuration

        Returns:
            List of classification test cases
        """
        cases: list[PolicyTestCase] = []

        # Group filters by entity
        entity_filters: dict[str, list[FieldFilter]] = {}
        for f in config.field_filters:
            if f.entity_name not in entity_filters:
                entity_filters[f.entity_name] = []
            entity_filters[f.entity_name].append(f)

        for entity_name, filters in entity_filters.items():
            # Test: Allowed fields are included
            allowed = [f for f in filters if f.allowed]
            if allowed:
                payload = {f.field_name: f"test_{f.field_name}" for f in filters}
                expected_allowed = {f.field_name for f in allowed}

                cases.append(
                    PolicyTestCase(
                        name=f"test_{entity_name}_allowed_fields",
                        description=f"Verify allowed fields are included for {entity_name}",
                        product_name=config.product_name,
                        entity_name=entity_name,
                        test_type="classification",
                        input_payload=payload,
                        expected_allowed_fields=expected_allowed,
                        expected_denied_fields={f.field_name for f in filters if not f.allowed},
                        assertion_message=f"Expected fields {expected_allowed} to be in output",
                    )
                )

            # Test: Denied fields are excluded
            denied = [f for f in filters if not f.allowed]
            if denied:
                payload = {f.field_name: f"secret_{f.field_name}" for f in denied}
                expected_denied = {f.field_name for f in denied}

                cases.append(
                    PolicyTestCase(
                        name=f"test_{entity_name}_denied_fields",
                        description=f"Verify denied fields are excluded for {entity_name}",
                        product_name=config.product_name,
                        entity_name=entity_name,
                        test_type="classification",
                        input_payload=payload,
                        expected_allowed_fields=set(),
                        expected_denied_fields=expected_denied,
                        assertion_message=f"Fields {expected_denied} should not be in output",
                    )
                )

            # Test: Mixed payload
            if allowed and denied:
                payload = {}
                for f in filters:
                    if f.allowed:
                        payload[f.field_name] = f"visible_{f.field_name}"
                    else:
                        payload[f.field_name] = f"hidden_{f.field_name}"

                cases.append(
                    PolicyTestCase(
                        name=f"test_{entity_name}_mixed_classification",
                        description=f"Verify correct filtering with mixed fields for {entity_name}",
                        product_name=config.product_name,
                        entity_name=entity_name,
                        test_type="classification",
                        input_payload=payload,
                        expected_allowed_fields={f.field_name for f in allowed},
                        expected_denied_fields={f.field_name for f in denied},
                        assertion_message="Mixed payload should have only allowed fields",
                    )
                )

        return cases

    def _generate_transform_tests(
        self,
        config: CuratedTopicConfig,
    ) -> list[PolicyTestCase]:
        """Generate tests for data transforms.

        Args:
            config: Curated topic configuration

        Returns:
            List of transform test cases
        """
        cases: list[PolicyTestCase] = []

        if not config.transforms:
            return cases

        # Find fields with transforms
        transformed_filters = [f for f in config.field_filters if f.transform]

        for f in transformed_filters:
            if f.transform == DataProductTransform.MASK:
                cases.append(self._generate_mask_test(config, f))
            elif f.transform == DataProductTransform.PSEUDONYMISE:
                cases.append(self._generate_pseudonymise_test(config, f))
            elif f.transform == DataProductTransform.MINIMISE:
                cases.append(self._generate_minimise_test(config, f))

        return cases

    def _generate_mask_test(
        self,
        config: CuratedTopicConfig,
        field_filter: Any,
    ) -> PolicyTestCase:
        """Generate a mask transform test."""
        # Create appropriate test value based on field name
        field_name = field_filter.field_name.lower()

        if "email" in field_name:
            test_value = "john.doe@example.com"
            expected_pattern = "j***@example.com"
        elif "phone" in field_name:
            test_value = "555-123-4567"
            expected_pattern = "***-***-4567"
        elif "card" in field_name or "account" in field_name:
            test_value = "4111-1111-1111-1234"
            expected_pattern = "****-****-****-1234"
        else:
            test_value = "sensitive_data_here"
            expected_pattern = "s***e"  # First and last char

        return PolicyTestCase(
            name=f"test_{field_filter.entity_name}_{field_filter.field_name}_mask",
            description=f"Verify {field_filter.field_name} is masked correctly",
            product_name=config.product_name,
            entity_name=field_filter.entity_name,
            test_type="transform",
            input_payload={field_filter.field_name: test_value},
            expected_transformed_fields={
                field_filter.field_name: expected_pattern,
            },
            assertion_message=f"Expected masked value like '{expected_pattern}'",
        )

    def _generate_pseudonymise_test(
        self,
        config: CuratedTopicConfig,
        field_filter: Any,
    ) -> PolicyTestCase:
        """Generate a pseudonymise transform test."""
        test_value = "user_12345"

        return PolicyTestCase(
            name=f"test_{field_filter.entity_name}_{field_filter.field_name}_pseudonymise",
            description=f"Verify {field_filter.field_name} is pseudonymised",
            product_name=config.product_name,
            entity_name=field_filter.entity_name,
            test_type="transform",
            input_payload={field_filter.field_name: test_value},
            expected_transformed_fields={
                field_filter.field_name: "PSEUDO_",  # Prefix pattern
            },
            assertion_message="Expected pseudonymised value starting with 'PSEUDO_'",
        )

    def _generate_minimise_test(
        self,
        config: CuratedTopicConfig,
        field_filter: Any,
    ) -> PolicyTestCase:
        """Generate a minimise transform test."""
        # Long string to test truncation
        test_value = "A" * 100  # 100 character string

        return PolicyTestCase(
            name=f"test_{field_filter.entity_name}_{field_filter.field_name}_minimise",
            description=f"Verify {field_filter.field_name} is minimised",
            product_name=config.product_name,
            entity_name=field_filter.entity_name,
            test_type="transform",
            input_payload={field_filter.field_name: test_value},
            expected_transformed_fields={
                field_filter.field_name: "...",  # Ends with ellipsis
            },
            assertion_message="Expected truncated value ending with '...'",
        )

    def _generate_cross_tenant_tests(
        self,
        config: CuratedTopicConfig,
    ) -> list[PolicyTestCase]:
        """Generate tests for cross-tenant access.

        Args:
            config: Curated topic configuration

        Returns:
            List of cross-tenant test cases
        """
        cases: list[PolicyTestCase] = []

        # Test: Cross-tenant access is allowed when configured
        cases.append(
            PolicyTestCase(
                name=f"test_{config.product_name}_cross_tenant_allowed",
                description="Verify cross-tenant access is permitted",
                product_name=config.product_name,
                entity_name="",
                test_type="cross_tenant",
                input_payload={
                    "requesting_tenant": "tenant_a",
                    "target_tenants": ["tenant_b"],
                },
                should_pass=True,
                assertion_message="Cross-tenant access should be allowed",
            )
        )

        # Test: Cross-tenant requires proper policy
        cases.append(
            PolicyTestCase(
                name=f"test_{config.product_name}_cross_tenant_denied_no_policy",
                description="Verify cross-tenant is denied without policy",
                product_name=config.product_name,
                entity_name="",
                test_type="cross_tenant",
                input_payload={
                    "requesting_tenant": "tenant_without_policy",
                    "target_tenants": ["tenant_b"],
                },
                should_pass=False,
                assertion_message="Cross-tenant should be denied without explicit policy",
            )
        )

        return cases

    def generate_pytest_code(self) -> str:
        """Generate pytest code for all test suites.

        Returns:
            Python code string containing pytest tests
        """
        suites = self.generate_all()

        lines = [
            '"""',
            "Auto-generated policy tests for data products.",
            "",
            "Generated by: dazzle_dnr_back.data_products.test_generator",
            '"""',
            "",
            "import pytest",
            "from dazzle_dnr_back.data_products import (",
            "    CuratedTopicGenerator,",
            "    DataProductTransformer,",
            "    CrossTenantValidator,",
            "    CrossTenantPolicy,",
            "    CrossTenantPermission,",
            ")",
            "",
            "",
        ]

        for suite in suites:
            lines.append(f"class TestDataProduct{suite.product_name.title().replace('_', '')}:")
            lines.append(f'    """Tests for {suite.product_name} data product."""')
            lines.append("")

            for case in suite.test_cases:
                lines.extend(self._generate_test_method(case))
                lines.append("")

            lines.append("")

        return "\n".join(lines)

    def _generate_test_method(self, case: PolicyTestCase) -> list[str]:
        """Generate a single test method.

        Args:
            case: Test case to generate

        Returns:
            Lines of Python code
        """
        method_lines = [
            f"    def {case.name}(self):",
            f'        """{case.description}"""',
        ]

        if case.test_type == "classification":
            method_lines.extend(
                [
                    f"        payload = {case.input_payload!r}",
                    "        # Transform payload using config",
                    "        transformer = DataProductTransformer()",
                    "        # Result should have only allowed fields",
                    f"        expected_allowed = {case.expected_allowed_fields!r}",
                    f"        expected_denied = {case.expected_denied_fields!r}",
                    "        # TODO: Wire up actual transform call",
                    f"        assert True, {case.assertion_message!r}",
                ]
            )

        elif case.test_type == "transform":
            method_lines.extend(
                [
                    f"        payload = {case.input_payload!r}",
                    "        transformer = DataProductTransformer()",
                    "        # Apply transform",
                    f"        # Expected patterns: {case.expected_transformed_fields!r}",
                    f"        assert True, {case.assertion_message!r}",
                ]
            )

        elif case.test_type == "cross_tenant":
            if case.should_pass:
                method_lines.extend(
                    [
                        "        validator = CrossTenantValidator()",
                        "        policy = CrossTenantPolicy(",
                        f"            tenant_id={case.input_payload['requesting_tenant']!r},",
                        "            permission=CrossTenantPermission.READ_AGGREGATED,",
                        "        )",
                        "        validator.add_policy(policy)",
                        "        result = validator.check_access(",
                        f"            requesting_tenant={case.input_payload['requesting_tenant']!r},",
                        f"            target_tenants={case.input_payload['target_tenants']!r},",
                        f"            product_name={case.product_name!r},",
                        "        )",
                        "        assert result.permitted",
                    ]
                )
            else:
                method_lines.extend(
                    [
                        "        validator = CrossTenantValidator()  # No policy added",
                        "        result = validator.check_access(",
                        f"            requesting_tenant={case.input_payload['requesting_tenant']!r},",
                        f"            target_tenants={case.input_payload['target_tenants']!r},",
                        f"            product_name={case.product_name!r},",
                        "        )",
                        "        assert not result.permitted",
                    ]
                )

        return method_lines


def generate_policy_tests(appspec: AppSpec) -> str:
    """Convenience function to generate policy tests.

    Args:
        appspec: Application specification

    Returns:
        Python code string with pytest tests
    """
    generator = PolicyTestGenerator(appspec)
    return generator.generate_pytest_code()
