"""
Unit tests for the specs module (OpenAPI and AsyncAPI generation).
"""

import pytest

from dazzle.core.ir import (
    AppSpec,
    DomainSpec,
    EntitySpec,
    FieldModifier,
    FieldSpec,
    FieldType,
    FieldTypeKind,
    StateMachineSpec,
    StateTransition,
    TransitionGuard,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def simple_entity() -> EntitySpec:
    """Create a simple entity for testing."""
    return EntitySpec(
        name="Task",
        title="A task item",
        fields=[
            FieldSpec(
                name="id",
                type=FieldType(kind=FieldTypeKind.UUID),
                modifiers=[FieldModifier.PK],
            ),
            FieldSpec(
                name="title",
                type=FieldType(kind=FieldTypeKind.STR, max_length=200),
                modifiers=[FieldModifier.REQUIRED],
            ),
            FieldSpec(
                name="description",
                type=FieldType(kind=FieldTypeKind.TEXT),
            ),
            FieldSpec(
                name="completed",
                type=FieldType(kind=FieldTypeKind.BOOL),
                default=False,
            ),
            FieldSpec(
                name="created_at",
                type=FieldType(kind=FieldTypeKind.DATETIME),
            ),
        ],
    )


@pytest.fixture
def entity_with_state() -> EntitySpec:
    """Create an entity with state machine for testing."""
    return EntitySpec(
        name="Order",
        title="An order with status workflow",
        fields=[
            FieldSpec(
                name="id",
                type=FieldType(kind=FieldTypeKind.UUID),
                modifiers=[FieldModifier.PK],
            ),
            FieldSpec(
                name="total",
                type=FieldType(kind=FieldTypeKind.DECIMAL),
                modifiers=[FieldModifier.REQUIRED],
            ),
            FieldSpec(
                name="status",
                type=FieldType(
                    kind=FieldTypeKind.ENUM,
                    enum_values=["draft", "pending", "approved", "shipped"],
                ),
                default="draft",
            ),
        ],
        state_machine=StateMachineSpec(
            status_field="status",
            states=["draft", "pending", "approved", "shipped"],
            transitions=[
                StateTransition(from_state="draft", to_state="pending"),
                StateTransition(
                    from_state="pending",
                    to_state="approved",
                    guards=[TransitionGuard(condition="total < 1000")],
                ),
                StateTransition(from_state="approved", to_state="shipped"),
            ],
        ),
    )


@pytest.fixture
def simple_appspec(simple_entity: EntitySpec) -> AppSpec:
    """Create a simple AppSpec for testing."""
    return AppSpec(
        name="Test App",
        title="A test application",
        domain=DomainSpec(entities=[simple_entity]),
    )


# =============================================================================
# OpenAPI Tests
# =============================================================================


class TestOpenAPIGeneration:
    """Test OpenAPI specification generation."""

    def test_generate_openapi_basic(self, simple_appspec: AppSpec) -> None:
        """Test basic OpenAPI generation."""
        from dazzle.specs.openapi import generate_openapi

        openapi = generate_openapi(simple_appspec)

        assert openapi["openapi"] == "3.1.0"
        assert openapi["info"]["title"] == "Test App"
        assert "Task" in openapi["components"]["schemas"]
        assert "/tasks" in openapi["paths"]

    def test_generate_openapi_crud_endpoints(self, simple_appspec: AppSpec) -> None:
        """Test CRUD endpoint generation."""
        from dazzle.specs.openapi import generate_openapi

        openapi = generate_openapi(simple_appspec)

        # List endpoint
        assert "get" in openapi["paths"]["/tasks"]
        assert "post" in openapi["paths"]["/tasks"]

        # Item endpoints
        assert "get" in openapi["paths"]["/tasks/{task_id}"]
        assert "put" in openapi["paths"]["/tasks/{task_id}"]
        assert "delete" in openapi["paths"]["/tasks/{task_id}"]

    def test_generate_openapi_schemas(self, simple_appspec: AppSpec) -> None:
        """Test schema generation in OpenAPI."""
        from dazzle.specs.openapi import generate_openapi

        openapi = generate_openapi(simple_appspec)
        schemas = openapi["components"]["schemas"]

        assert "Task" in schemas
        assert "TaskCreate" in schemas
        assert "TaskUpdate" in schemas
        assert "TaskRead" in schemas
        assert "TaskList" in schemas

    def test_generate_openapi_with_state_machine(
        self,
        entity_with_state: EntitySpec,
    ) -> None:
        """Test OpenAPI generation with state machine."""
        from dazzle.specs.openapi import generate_openapi

        spec = AppSpec(
            name="Test",
            domain=DomainSpec(entities=[entity_with_state]),
        )
        openapi = generate_openapi(spec)

        # Check for action endpoints
        paths = openapi["paths"]
        action_paths = [p for p in paths if "/actions/" in p]
        assert len(action_paths) > 0

    def test_openapi_to_json(self, simple_appspec: AppSpec) -> None:
        """Test JSON output."""
        import json

        from dazzle.specs.openapi import generate_openapi, openapi_to_json

        openapi = generate_openapi(simple_appspec)
        json_str = openapi_to_json(openapi)

        # Should be valid JSON
        parsed = json.loads(json_str)
        assert parsed["openapi"] == "3.1.0"

    def test_openapi_to_yaml(self, simple_appspec: AppSpec) -> None:
        """Test YAML output."""
        from dazzle.specs.openapi import generate_openapi, openapi_to_yaml

        openapi = generate_openapi(simple_appspec)
        yaml_str = openapi_to_yaml(openapi)

        # Should contain expected content
        assert "openapi:" in yaml_str or '"openapi"' in yaml_str

    def test_openapi_sensitive_field_extension(self) -> None:
        """Test that sensitive fields get x-sensitive: true in OpenAPI."""
        from dazzle.core.ir import FieldModifier, FieldType, FieldTypeKind
        from dazzle.specs.openapi import generate_openapi

        entity = EntitySpec(
            name="Employee",
            title="Employee",
            fields=[
                FieldSpec(
                    name="id",
                    type=FieldType(kind=FieldTypeKind.UUID),
                    modifiers=[FieldModifier.PK],
                ),
                FieldSpec(
                    name="name",
                    type=FieldType(kind=FieldTypeKind.STR, max_length=200),
                    modifiers=[FieldModifier.REQUIRED],
                ),
                FieldSpec(
                    name="bank_account",
                    type=FieldType(kind=FieldTypeKind.STR, max_length=8),
                    modifiers=[FieldModifier.SENSITIVE],
                ),
            ],
        )
        spec = AppSpec(
            name="Test",
            domain=DomainSpec(entities=[entity]),
        )
        openapi = generate_openapi(spec)

        schema = openapi["components"]["schemas"]["Employee"]
        props = schema["properties"]

        # bank_account should have x-sensitive
        assert props["bank_account"].get("x-sensitive") is True
        # name should NOT have x-sensitive
        assert "x-sensitive" not in props["name"]
