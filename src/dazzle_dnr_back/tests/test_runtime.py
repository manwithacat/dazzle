"""
Tests for DNR-Back runtime module.
"""

from uuid import uuid4

import pytest
from pydantic import BaseModel

pytestmark = pytest.mark.asyncio(loop_scope="function")

from dazzle_dnr_back.runtime.model_generator import (  # noqa: E402
    generate_all_entity_models,
    generate_create_schema,
    generate_entity_model,
    generate_update_schema,
)
from dazzle_dnr_back.runtime.service_generator import (  # noqa: E402
    CRUDService,
    CustomService,
    ServiceFactory,
)
from dazzle_dnr_back.specs import (  # noqa: E402
    BackendSpec,
    DomainOperation,
    EndpointSpec,
    EntitySpec,
    FieldSpec,
    FieldType,
    HttpMethod,
    OperationKind,
    ScalarType,
    SchemaFieldSpec,
    SchemaSpec,
    ServiceSpec,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def task_entity() -> EntitySpec:
    """Create a sample Task entity."""
    return EntitySpec(
        name="Task",
        label="Task",
        description="A task to be completed",
        fields=[
            FieldSpec(
                name="id",
                type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                required=True,
            ),
            FieldSpec(
                name="title",
                type=FieldType(kind="scalar", scalar_type=ScalarType.STR, max_length=200),
                required=True,
            ),
            FieldSpec(
                name="description",
                type=FieldType(kind="scalar", scalar_type=ScalarType.TEXT),
                required=False,
            ),
            FieldSpec(
                name="status",
                type=FieldType(kind="enum", enum_values=["pending", "in_progress", "done"]),
                required=True,
                default="pending",
            ),
            FieldSpec(
                name="priority",
                type=FieldType(kind="scalar", scalar_type=ScalarType.INT),
                required=False,
                default=1,
            ),
        ],
    )


@pytest.fixture
def user_entity() -> EntitySpec:
    """Create a sample User entity."""
    return EntitySpec(
        name="User",
        label="User",
        fields=[
            FieldSpec(
                name="id",
                type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                required=True,
            ),
            FieldSpec(
                name="email",
                type=FieldType(kind="scalar", scalar_type=ScalarType.EMAIL),
                required=True,
                unique=True,
            ),
            FieldSpec(
                name="name",
                type=FieldType(kind="scalar", scalar_type=ScalarType.STR),
                required=True,
            ),
        ],
    )


@pytest.fixture
def list_tasks_service() -> ServiceSpec:
    """Create a list tasks service spec."""
    return ServiceSpec(
        name="list_tasks",
        description="List all tasks",
        inputs=SchemaSpec(
            fields=[
                SchemaFieldSpec(name="page", type="int", required=False),
                SchemaFieldSpec(name="page_size", type="int", required=False),
            ]
        ),
        outputs=SchemaSpec(
            fields=[
                SchemaFieldSpec(name="items", type="list[Task]", required=True),
                SchemaFieldSpec(name="total", type="int", required=True),
            ]
        ),
        domain_operation=DomainOperation(kind=OperationKind.LIST, entity="Task"),
    )


# =============================================================================
# Model Generator Tests
# =============================================================================


class TestModelGenerator:
    """Tests for model generation."""

    def test_generate_entity_model(self, task_entity: EntitySpec) -> None:
        """Test generating a Pydantic model from EntitySpec."""
        TaskModel = generate_entity_model(task_entity)

        # Check model name
        assert TaskModel.__name__ == "Task"

        # Check fields exist
        field_names = set(TaskModel.model_fields.keys())
        assert "title" in field_names
        assert "description" in field_names
        assert "status" in field_names
        assert "priority" in field_names
        assert "id" in field_names

    def test_model_instance_creation(self, task_entity: EntitySpec) -> None:
        """Test creating an instance of a generated model."""
        TaskModel = generate_entity_model(task_entity)

        # Create instance with required fields
        task_id = uuid4()
        task = TaskModel(id=task_id, title="Test Task", status="pending")

        assert task.title == "Test Task"
        assert task.status == "pending"
        assert task.description is None

    def test_model_with_defaults(self, task_entity: EntitySpec) -> None:
        """Test that default values are applied."""
        TaskModel = generate_entity_model(task_entity)

        # Create instance - priority should get default value when not provided
        task_id = uuid4()
        task = TaskModel(id=task_id, title="Test2", status="done")
        assert task.priority == 1

    def test_generate_all_entity_models(
        self, task_entity: EntitySpec, user_entity: EntitySpec
    ) -> None:
        """Test generating multiple models."""
        models = generate_all_entity_models([task_entity, user_entity])

        assert "Task" in models
        assert "User" in models
        assert models["Task"].__name__ == "Task"
        assert models["User"].__name__ == "User"

    def test_generate_create_schema(self, task_entity: EntitySpec) -> None:
        """Test generating a create schema."""
        CreateSchema = generate_create_schema(task_entity)

        # Should not have id field
        field_names = set(CreateSchema.model_fields.keys())
        assert "id" not in field_names
        assert "title" in field_names

    def test_generate_update_schema(self, task_entity: EntitySpec) -> None:
        """Test generating an update schema."""
        UpdateSchema = generate_update_schema(task_entity)

        # All fields should be optional
        field_names = set(UpdateSchema.model_fields.keys())
        assert "id" not in field_names
        assert "title" in field_names

        # Should be able to create with partial data
        update = UpdateSchema(title="New Title")
        assert update.title == "New Title"


# =============================================================================
# Service Generator Tests
# =============================================================================


class TestServiceGenerator:
    """Tests for service generation."""

    @pytest.mark.asyncio
    async def test_crud_service_create(self, task_entity: EntitySpec) -> None:
        """Test CRUD service create operation."""
        TaskModel = generate_entity_model(task_entity)
        CreateSchema = generate_create_schema(task_entity)

        service: CRUDService[BaseModel, BaseModel, BaseModel] = CRUDService(
            entity_name="Task",
            model_class=TaskModel,
            create_schema=CreateSchema,
            update_schema=CreateSchema,  # Simplified
        )

        # Create a task
        create_data = CreateSchema(title="New Task", status="pending")
        task = await service.create(create_data)

        assert task.title == "New Task"
        assert task.status == "pending"
        assert task.id is not None

    @pytest.mark.asyncio
    async def test_crud_service_read(self, task_entity: EntitySpec) -> None:
        """Test CRUD service read operation."""
        TaskModel = generate_entity_model(task_entity)
        CreateSchema = generate_create_schema(task_entity)

        service: CRUDService[BaseModel, BaseModel, BaseModel] = CRUDService(
            entity_name="Task",
            model_class=TaskModel,
            create_schema=CreateSchema,
            update_schema=CreateSchema,
        )

        # Create and then read
        create_data = CreateSchema(title="Test Task", status="pending")
        created = await service.create(create_data)

        task = await service.read(created.id)

        assert task is not None
        assert task.title == "Test Task"

    @pytest.mark.asyncio
    async def test_crud_service_update(self, task_entity: EntitySpec) -> None:
        """Test CRUD service update operation."""
        TaskModel = generate_entity_model(task_entity)
        CreateSchema = generate_create_schema(task_entity)
        UpdateSchema = generate_update_schema(task_entity)

        service: CRUDService[BaseModel, BaseModel, BaseModel] = CRUDService(
            entity_name="Task",
            model_class=TaskModel,
            create_schema=CreateSchema,
            update_schema=UpdateSchema,
        )

        # Create a task
        create_data = CreateSchema(title="Original", status="pending")
        created = await service.create(create_data)

        # Update it
        update_data = UpdateSchema(title="Updated")
        updated = await service.update(created.id, update_data)

        assert updated is not None
        assert updated.title == "Updated"
        assert updated.status == "pending"  # Unchanged

    @pytest.mark.asyncio
    async def test_crud_service_delete(self, task_entity: EntitySpec) -> None:
        """Test CRUD service delete operation."""
        TaskModel = generate_entity_model(task_entity)
        CreateSchema = generate_create_schema(task_entity)

        service: CRUDService[BaseModel, BaseModel, BaseModel] = CRUDService(
            entity_name="Task",
            model_class=TaskModel,
            create_schema=CreateSchema,
            update_schema=CreateSchema,
        )

        # Create and delete
        create_data = CreateSchema(title="To Delete", status="pending")
        created = await service.create(create_data)

        result = await service.delete(created.id)
        assert result is True

        # Verify deleted
        task = await service.read(created.id)
        assert task is None

    @pytest.mark.asyncio
    async def test_crud_service_list(self, task_entity: EntitySpec) -> None:
        """Test CRUD service list operation."""
        TaskModel = generate_entity_model(task_entity)
        CreateSchema = generate_create_schema(task_entity)

        service: CRUDService[BaseModel, BaseModel, BaseModel] = CRUDService(
            entity_name="Task",
            model_class=TaskModel,
            create_schema=CreateSchema,
            update_schema=CreateSchema,
        )

        # Create multiple tasks
        for i in range(5):
            await service.create(CreateSchema(title=f"Task {i}", status="pending"))

        # List with pagination
        result = await service.list(page=1, page_size=3)

        assert result["total"] == 5
        assert len(result["items"]) == 3
        assert result["page"] == 1
        assert result["page_size"] == 3

    @pytest.mark.asyncio
    async def test_custom_service(self) -> None:
        """Test custom service execution."""
        service = CustomService(service_name="calculate_total")

        result = await service.execute()

        assert result["status"] == "ok"
        assert result["service"] == "calculate_total"

    @pytest.mark.asyncio
    async def test_custom_service_with_handler(self) -> None:
        """Test custom service with a handler."""
        service = CustomService(service_name="add_numbers")

        async def add_handler(a: int, b: int) -> dict[str, int]:
            return {"sum": a + b}

        service.set_handler(add_handler)

        result = await service.execute(a=5, b=3)
        assert result["sum"] == 8

    def test_service_factory(
        self, task_entity: EntitySpec, list_tasks_service: ServiceSpec
    ) -> None:
        """Test service factory creates appropriate services."""
        models = generate_all_entity_models([task_entity])
        factory = ServiceFactory(models)

        service = factory.create_service(list_tasks_service)

        assert service is not None
        assert factory.get_service("list_tasks") is service


# =============================================================================
# Integration Tests
# =============================================================================


class TestRuntimeIntegration:
    """Integration tests for the complete runtime."""

    def test_backend_spec_to_models(self) -> None:
        """Test converting a complete BackendSpec to models."""
        spec = BackendSpec(
            name="test_app",
            version="1.0.0",
            entities=[
                EntitySpec(
                    name="Item",
                    fields=[
                        FieldSpec(
                            name="name",
                            type=FieldType(kind="scalar", scalar_type=ScalarType.STR),
                            required=True,
                        ),
                    ],
                ),
            ],
            services=[
                ServiceSpec(
                    name="list_items",
                    domain_operation=DomainOperation(kind=OperationKind.LIST, entity="Item"),
                ),
            ],
            endpoints=[
                EndpointSpec(
                    name="list_items_endpoint",
                    service="list_items",
                    method=HttpMethod.GET,
                    path="/api/items",
                ),
            ],
        )

        # Generate models
        models = generate_all_entity_models(spec.entities)
        assert "Item" in models

        # Create services
        factory = ServiceFactory(models)
        services = factory.create_all_services(spec.services)
        assert "list_items" in services


# =============================================================================
# Server Integration Tests (with SQLite)
# =============================================================================

# Check if FastAPI is available
try:
    import fastapi  # noqa: F401

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
class TestServerWithSQLite:
    """Integration tests for server with SQLite persistence."""

    @pytest.fixture
    def simple_backend_spec(self) -> BackendSpec:
        """Create a simple BackendSpec for testing."""
        return BackendSpec(
            name="test_app",
            version="1.0.0",
            entities=[
                EntitySpec(
                    name="Task",
                    fields=[
                        FieldSpec(
                            name="id",
                            type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                            required=True,
                        ),
                        FieldSpec(
                            name="title",
                            type=FieldType(kind="scalar", scalar_type=ScalarType.STR, max_length=200),
                            required=True,
                        ),
                        FieldSpec(
                            name="status",
                            type=FieldType(kind="enum", enum_values=["pending", "done"]),
                            required=True,
                            default="pending",
                        ),
                    ],
                ),
            ],
            services=[
                ServiceSpec(
                    name="task_service",
                    is_crud=True,
                    target_entity="Task",
                    domain_operation=DomainOperation(kind=OperationKind.LIST, entity="Task"),
                ),
            ],
            endpoints=[
                EndpointSpec(
                    name="list_tasks",
                    service="task_service",
                    method=HttpMethod.GET,
                    path="/api/tasks",
                ),
            ],
        )

    def test_server_creates_database(self, simple_backend_spec: BackendSpec, tmp_path):
        """Test that server creates SQLite database."""
        from dazzle_dnr_back.runtime.server import DNRBackendApp

        db_path = tmp_path / "test.db"
        app_builder = DNRBackendApp(
            simple_backend_spec,
            db_path=db_path,
            use_database=True,
        )
        app_builder.build()  # Triggers database setup

        # Database should be created
        assert db_path.exists()

        # Check for database manager
        assert app_builder._db_manager is not None

    def test_server_without_database(self, simple_backend_spec: BackendSpec, tmp_path):
        """Test that server works without database (in-memory mode)."""
        from dazzle_dnr_back.runtime.server import DNRBackendApp

        db_path = tmp_path / "no_db.db"
        app_builder = DNRBackendApp(
            simple_backend_spec,
            db_path=db_path,
            use_database=False,
        )
        app_builder.build()  # Build without database

        # Database should NOT be created
        assert not db_path.exists()

        # Database manager should not be set
        assert app_builder._db_manager is None

    def test_crud_service_with_repository(self, simple_backend_spec: BackendSpec, tmp_path):
        """Test that CRUD service is wired up to repository."""
        from dazzle_dnr_back.runtime.server import DNRBackendApp

        db_path = tmp_path / "test.db"
        app_builder = DNRBackendApp(
            simple_backend_spec,
            db_path=db_path,
            use_database=True,
        )
        app_builder.build()

        # Get the task service
        task_service = app_builder.get_service("task_service")
        assert task_service is not None
        assert isinstance(task_service, CRUDService)

        # Repository should be set
        assert task_service._repository is not None

    @pytest.mark.asyncio
    async def test_crud_operations_persist_to_sqlite(
        self, simple_backend_spec: BackendSpec, tmp_path
    ):
        """Test that CRUD operations persist data to SQLite."""
        from dazzle_dnr_back.runtime.server import DNRBackendApp

        db_path = tmp_path / "test.db"
        app_builder = DNRBackendApp(
            simple_backend_spec,
            db_path=db_path,
            use_database=True,
        )
        app_builder.build()

        task_service = app_builder.get_service("task_service")
        assert isinstance(task_service, CRUDService)

        # Create schema for test
        CreateSchema = generate_create_schema(simple_backend_spec.entities[0])

        # Create a task
        create_data = CreateSchema(title="Test Task", status="pending")
        task = await task_service.create(create_data)

        task_id = task.id

        # Read it back
        read_task = await task_service.read(task_id)
        assert read_task is not None
        assert read_task.title == "Test Task"

        # Create a new app instance to verify persistence
        app_builder2 = DNRBackendApp(
            simple_backend_spec,
            db_path=db_path,
            use_database=True,
        )
        app_builder2.build()

        task_service2 = app_builder2.get_service("task_service")

        # Should still be able to read the task
        persisted_task = await task_service2.read(task_id)
        assert persisted_task is not None
        assert persisted_task.title == "Test Task"
