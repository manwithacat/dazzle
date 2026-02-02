#!/usr/bin/env python3
"""Tests for GraphQL BFF layer components."""

import pytest

from dazzle_back.specs import BackendSpec
from dazzle_back.specs.entity import EntitySpec, FieldSpec, FieldType, ScalarType

# Check if Strawberry is available
try:
    import importlib.util

    STRAWBERRY_AVAILABLE = importlib.util.find_spec("strawberry") is not None
except ImportError:
    STRAWBERRY_AVAILABLE = False


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def simple_entity() -> EntitySpec:
    """Create a simple Task entity for testing."""
    return EntitySpec(
        name="Task",
        description="A task entity",
        fields=[
            FieldSpec(
                name="id",
                type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                required=True,
                label="ID",
            ),
            FieldSpec(
                name="title",
                type=FieldType(kind="scalar", scalar_type=ScalarType.STR),
                required=True,
                label="Title",
            ),
            FieldSpec(
                name="description",
                type=FieldType(kind="scalar", scalar_type=ScalarType.TEXT),
                required=False,
                label="Description",
            ),
            FieldSpec(
                name="completed",
                type=FieldType(kind="scalar", scalar_type=ScalarType.BOOL),
                required=True,
                default=False,
                label="Completed",
            ),
        ],
    )


@pytest.fixture
def entity_with_enum() -> EntitySpec:
    """Create an entity with an enum field."""
    return EntitySpec(
        name="Issue",
        description="An issue entity",
        fields=[
            FieldSpec(
                name="id",
                type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                required=True,
                label="ID",
            ),
            FieldSpec(
                name="title",
                type=FieldType(kind="scalar", scalar_type=ScalarType.STR),
                required=True,
                label="Title",
            ),
            FieldSpec(
                name="priority",
                type=FieldType(kind="enum", enum_values=["low", "medium", "high"]),
                required=True,
                label="Priority",
            ),
        ],
    )


@pytest.fixture
def backend_spec(simple_entity: EntitySpec) -> BackendSpec:
    """Create a BackendSpec with a simple entity."""
    return BackendSpec(
        name="test_app",
        entities=[simple_entity],
        services=[],
        endpoints=[],
        roles=[],
    )


@pytest.fixture
def backend_spec_with_enum(entity_with_enum: EntitySpec) -> BackendSpec:
    """Create a BackendSpec with an enum entity."""
    return BackendSpec(
        name="test_app",
        entities=[entity_with_enum],
        services=[],
        endpoints=[],
        roles=[],
    )


# =============================================================================
# Context Tests
# =============================================================================


class TestGraphQLContext:
    """Tests for GraphQLContext class."""

    def test_context_creation(self) -> None:
        """Test basic context creation."""
        from dazzle_back.graphql.context import GraphQLContext

        ctx = GraphQLContext(
            tenant_id="tenant-123",
            user_id="user-456",
            roles=("admin", "user"),
        )
        assert ctx.tenant_id == "tenant-123"
        assert ctx.user_id == "user-456"
        assert ctx.roles == ("admin", "user")

    def test_anonymous_context(self) -> None:
        """Test anonymous context creation."""
        from dazzle_back.graphql.context import create_anonymous_context

        ctx = create_anonymous_context()
        assert ctx.tenant_id is None
        assert ctx.user_id is None
        assert ctx.roles == ()
        assert ctx.is_anonymous

    def test_system_context(self) -> None:
        """Test system context creation."""
        from dazzle_back.graphql.context import create_system_context

        ctx = create_system_context(tenant_id="tenant-123")
        assert ctx.tenant_id == "tenant-123"
        assert ctx.user_id == "system"
        assert "system" in ctx.roles
        assert ctx.session.get("is_system") is True

    def test_require_tenant_raises(self) -> None:
        """Test require_tenant raises when no tenant."""
        from dazzle_back.graphql.context import GraphQLContext

        ctx = GraphQLContext()
        with pytest.raises(PermissionError, match="Tenant context required"):
            ctx.require_tenant()

    def test_require_tenant_returns_id(self) -> None:
        """Test require_tenant returns tenant_id when present."""
        from dazzle_back.graphql.context import GraphQLContext

        ctx = GraphQLContext(tenant_id="tenant-123")
        assert ctx.require_tenant() == "tenant-123"

    def test_require_authenticated_raises(self) -> None:
        """Test require_authenticated raises when no user."""
        from dazzle_back.graphql.context import GraphQLContext

        ctx = GraphQLContext()
        with pytest.raises(PermissionError, match="Authentication required"):
            ctx.require_authenticated()

    def test_require_authenticated_succeeds(self) -> None:
        """Test require_authenticated succeeds when user_id present."""
        from dazzle_back.graphql.context import GraphQLContext

        ctx = GraphQLContext(user_id="user-456")
        # Should not raise
        ctx.require_authenticated()
        assert ctx.is_authenticated

    def test_has_role(self) -> None:
        """Test has_role method."""
        from dazzle_back.graphql.context import GraphQLContext

        ctx = GraphQLContext(roles=("admin", "user"))
        assert ctx.has_role("admin") is True
        assert ctx.has_role("user") is True
        assert ctx.has_role("superadmin") is False

    def test_has_any_role(self) -> None:
        """Test has_any_role method."""
        from dazzle_back.graphql.context import GraphQLContext

        ctx = GraphQLContext(roles=("user",))
        assert ctx.has_any_role("admin", "user") is True
        assert ctx.has_any_role("admin", "superadmin") is False

    def test_context_immutable(self) -> None:
        """Test context is immutable (frozen dataclass)."""
        from dataclasses import FrozenInstanceError

        from dazzle_back.graphql.context import GraphQLContext

        ctx = GraphQLContext(tenant_id="tenant-123")
        with pytest.raises(FrozenInstanceError):
            ctx.tenant_id = "new-tenant"  # type: ignore


# =============================================================================
# Schema Generator Tests (require Strawberry)
# =============================================================================


@pytest.mark.skipif(not STRAWBERRY_AVAILABLE, reason="Strawberry not installed")
class TestSchemaGenerator:
    """Tests for SchemaGenerator class."""

    def test_generate_types(self, backend_spec: BackendSpec) -> None:
        """Test type generation from BackendSpec."""
        from dazzle_back.graphql.schema_generator import SchemaGenerator

        gen = SchemaGenerator(backend_spec)
        types = gen.generate_types()

        assert "Task" in types
        task_type = types["Task"]
        assert hasattr(task_type, "__strawberry_definition__")

    def test_generate_input_types(self, backend_spec: BackendSpec) -> None:
        """Test input type generation."""
        from dazzle_back.graphql.schema_generator import SchemaGenerator

        gen = SchemaGenerator(backend_spec)
        gen.generate_types()

        assert "TaskCreateInput" in gen.input_types
        assert "TaskUpdateInput" in gen.input_types

    def test_generate_enum_types(self, backend_spec_with_enum: BackendSpec) -> None:
        """Test enum type generation."""
        from dazzle_back.graphql.schema_generator import SchemaGenerator

        gen = SchemaGenerator(backend_spec_with_enum)
        gen.generate_types()

        # Enum should be generated with entity+field name
        assert "IssuePriorityEnum" in gen.enum_types

    def test_get_type(self, backend_spec: BackendSpec) -> None:
        """Test get_type method."""
        from dazzle_back.graphql.schema_generator import SchemaGenerator

        gen = SchemaGenerator(backend_spec)
        gen.generate_types()

        assert gen.get_type("Task") is not None
        assert gen.get_type("NonExistent") is None

    def test_get_input_type(self, backend_spec: BackendSpec) -> None:
        """Test get_input_type method."""
        from dazzle_back.graphql.schema_generator import SchemaGenerator

        gen = SchemaGenerator(backend_spec)
        gen.generate_types()

        assert gen.get_input_type("TaskCreateInput") is not None
        assert gen.get_input_type("NonExistent") is None


@pytest.mark.skipif(not STRAWBERRY_AVAILABLE, reason="Strawberry not installed")
class TestSchemaSDL:
    """Tests for SDL generation."""

    def test_generate_schema_sdl(self, backend_spec: BackendSpec) -> None:
        """Test SDL generation."""
        from dazzle_back.graphql.schema_generator import generate_schema_sdl

        sdl = generate_schema_sdl(backend_spec)

        assert "type Task {" in sdl
        assert "id: ID!" in sdl
        assert "title: String!" in sdl
        assert "description: String" in sdl
        assert "completed: Boolean!" in sdl

    def test_generate_schema_sdl_with_enum(self, backend_spec_with_enum: BackendSpec) -> None:
        """Test SDL generation with enum."""
        from dazzle_back.graphql.schema_generator import generate_schema_sdl

        sdl = generate_schema_sdl(backend_spec_with_enum)

        assert "enum IssuePriorityEnum {" in sdl
        assert "LOW" in sdl
        assert "MEDIUM" in sdl
        assert "HIGH" in sdl

    def test_generate_query_type(self, backend_spec: BackendSpec) -> None:
        """Test Query type in SDL."""
        from dazzle_back.graphql.schema_generator import generate_schema_sdl

        sdl = generate_schema_sdl(backend_spec)

        assert "type Query {" in sdl
        assert "task(id: ID!): Task" in sdl
        assert "tasks(limit: Int, offset: Int): [Task!]!" in sdl

    def test_generate_mutation_type(self, backend_spec: BackendSpec) -> None:
        """Test Mutation type in SDL."""
        from dazzle_back.graphql.schema_generator import generate_schema_sdl

        sdl = generate_schema_sdl(backend_spec)

        assert "type Mutation {" in sdl
        assert "createTask(input: TaskCreateInput!): Task!" in sdl
        assert "updateTask(id: ID!, input: TaskUpdateInput!): Task!" in sdl
        assert "deleteTask(id: ID!): Boolean!" in sdl


# =============================================================================
# Resolver Generator Tests (require Strawberry)
# =============================================================================


@pytest.mark.skipif(not STRAWBERRY_AVAILABLE, reason="Strawberry not installed")
class TestResolverGenerator:
    """Tests for ResolverGenerator class."""

    def test_generate_resolvers(self, backend_spec: BackendSpec) -> None:
        """Test resolver generation."""
        from dazzle_back.graphql.resolver_generator import ResolverGenerator

        gen = ResolverGenerator(backend_spec, services={}, repositories={})
        queries, mutations = gen.generate_resolvers()

        # Query resolvers
        assert "task" in queries
        assert "tasks" in queries

        # Mutation resolvers
        assert "createTask" in mutations
        assert "updateTask" in mutations
        assert "deleteTask" in mutations

    def test_resolvers_are_callable(self, backend_spec: BackendSpec) -> None:
        """Test that generated resolvers are callable."""
        from dazzle_back.graphql.resolver_generator import ResolverGenerator

        gen = ResolverGenerator(backend_spec, services={}, repositories={})
        queries, mutations = gen.generate_resolvers()

        for name, resolver in queries.items():
            assert callable(resolver), f"Query resolver {name} is not callable"

        for name, resolver in mutations.items():
            assert callable(resolver), f"Mutation resolver {name} is not callable"


# =============================================================================
# Integration Tests (require Strawberry and FastAPI)
# =============================================================================


@pytest.mark.skipif(not STRAWBERRY_AVAILABLE, reason="Strawberry not installed")
class TestIntegration:
    """Tests for FastAPI/Strawberry integration."""

    def test_create_schema(self, backend_spec: BackendSpec) -> None:
        """Test schema creation."""
        from dazzle_back.graphql.integration import create_schema

        schema = create_schema(backend_spec)
        assert schema is not None
        # Strawberry schema should have query type
        assert schema.query is not None

    def test_inspect_schema(self, backend_spec: BackendSpec) -> None:
        """Test schema inspection."""
        from dazzle_back.graphql.integration import inspect_schema

        info = inspect_schema(backend_spec)

        assert "entities" in info
        assert "Task" in info["entities"]
        assert "queries" in info
        assert "mutations" in info
        assert "stats" in info
        assert info["stats"]["entity_count"] == 1
        assert info["stats"]["query_count"] == 2  # task + tasks
        assert info["stats"]["mutation_count"] == 3  # create + update + delete

    def test_print_schema(self, backend_spec: BackendSpec) -> None:
        """Test schema printing."""
        from dazzle_back.graphql.integration import print_schema

        sdl = print_schema(backend_spec)
        assert isinstance(sdl, str)
        assert "type Task" in sdl


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_pascal_case(self) -> None:
        """Test _pascal_case helper."""
        from dazzle_back.graphql.schema_generator import _pascal_case

        assert _pascal_case("hello_world") == "HelloWorld"
        assert _pascal_case("priority") == "Priority"
        assert _pascal_case("user_id") == "UserId"

    def test_camel_case(self) -> None:
        """Test _camel_case helper."""
        from dazzle_back.graphql.resolver_generator import _camel_case

        assert _camel_case("Task") == "task"
        assert _camel_case("UserProfile") == "userProfile"
        assert _camel_case("") == ""
