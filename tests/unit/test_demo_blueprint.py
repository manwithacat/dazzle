"""
Unit tests for Demo Data Blueprint types and generation.

Tests the blueprint IR types, persistence layer, and data generation.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from dazzle.core.demo_blueprint_persistence import (
    delete_blueprint,
    get_blueprint_dir,
    get_blueprint_file,
    load_blueprint,
    save_blueprint,
)
from dazzle.core.ir.demo_blueprint import (
    BlueprintContainer,
    DemoDataBlueprint,
    EntityBlueprint,
    FieldPattern,
    FieldStrategy,
    PersonaBlueprint,
    TenantBlueprint,
)
from dazzle.demo_data.blueprint_generator import BlueprintDataGenerator


class TestFieldPattern:
    """Tests for FieldPattern IR type."""

    def test_create_field_pattern(self):
        """Test creating a field pattern."""
        pattern = FieldPattern(
            field_name="title",
            strategy=FieldStrategy.FREE_TEXT_LOREM,
            params={"min_words": 3, "max_words": 8},
        )

        assert pattern.field_name == "title"
        assert pattern.strategy == FieldStrategy.FREE_TEXT_LOREM
        assert pattern.params["min_words"] == 3

    def test_all_strategies_valid(self):
        """Test all field strategies are valid."""
        strategies = [
            FieldStrategy.STATIC_LIST,
            FieldStrategy.ENUM_WEIGHTED,
            FieldStrategy.PERSON_NAME,
            FieldStrategy.COMPANY_NAME,
            FieldStrategy.EMAIL_FROM_NAME,
            FieldStrategy.USERNAME_FROM_NAME,
            FieldStrategy.HASHED_PASSWORD_PLACEHOLDER,
            FieldStrategy.FREE_TEXT_LOREM,
            FieldStrategy.NUMERIC_RANGE,
            FieldStrategy.CURRENCY_AMOUNT,
            FieldStrategy.DATE_RELATIVE,
            FieldStrategy.BOOLEAN_WEIGHTED,
            FieldStrategy.FOREIGN_KEY,
            FieldStrategy.COMPOSITE,
            FieldStrategy.CUSTOM_PROMPT,
            FieldStrategy.UUID_GENERATE,
        ]

        for strategy in strategies:
            pattern = FieldPattern(
                field_name="test",
                strategy=strategy,
            )
            assert pattern.strategy == strategy


class TestEntityBlueprint:
    """Tests for EntityBlueprint IR type."""

    def test_create_entity_blueprint(self):
        """Test creating an entity blueprint."""
        entity = EntityBlueprint(
            name="Task",
            row_count_default=50,
            notes="Task entity",
            tenant_scoped=False,
            field_patterns=[
                FieldPattern(
                    field_name="id",
                    strategy=FieldStrategy.UUID_GENERATE,
                ),
                FieldPattern(
                    field_name="title",
                    strategy=FieldStrategy.FREE_TEXT_LOREM,
                    params={"min_words": 3, "max_words": 8},
                ),
            ],
        )

        assert entity.name == "Task"
        assert entity.row_count_default == 50
        assert len(entity.field_patterns) == 2
        assert entity.tenant_scoped is False

    def test_entity_defaults(self):
        """Test entity blueprint defaults."""
        entity = EntityBlueprint(name="Simple")

        assert entity.row_count_default == 10
        assert entity.notes is None
        assert entity.tenant_scoped is False
        assert entity.field_patterns == []


class TestTenantBlueprint:
    """Tests for TenantBlueprint IR type."""

    def test_create_tenant_blueprint(self):
        """Test creating a tenant blueprint."""
        tenant = TenantBlueprint(
            name="Alpha Solar Ltd",
            slug="alpha-solar",
            notes="Primary demo tenant",
        )

        assert tenant.name == "Alpha Solar Ltd"
        assert tenant.slug == "alpha-solar"
        assert tenant.notes == "Primary demo tenant"

    def test_tenant_minimal(self):
        """Test minimal tenant blueprint."""
        tenant = TenantBlueprint(name="Test Co")

        assert tenant.name == "Test Co"
        assert tenant.slug is None
        assert tenant.notes is None


class TestPersonaBlueprint:
    """Tests for PersonaBlueprint IR type."""

    def test_create_persona_blueprint(self):
        """Test creating a persona blueprint."""
        persona = PersonaBlueprint(
            persona_name="Staff",
            description="Regular staff users",
            default_role="role_staff",
            default_user_count=3,
        )

        assert persona.persona_name == "Staff"
        assert persona.description == "Regular staff users"
        assert persona.default_role == "role_staff"
        assert persona.default_user_count == 3


class TestDemoDataBlueprint:
    """Tests for DemoDataBlueprint IR type."""

    def test_create_full_blueprint(self):
        """Test creating a complete blueprint."""
        blueprint = DemoDataBlueprint(
            project_id="simple_task",
            domain_description="Simple task management",
            seed=42,
            tenants=[
                TenantBlueprint(name="Alpha Tasks Ltd"),
                TenantBlueprint(name="Bravo Tasks Ltd"),
            ],
            personas=[
                PersonaBlueprint(
                    persona_name="Staff",
                    description="Staff users",
                    default_user_count=2,
                ),
            ],
            entities=[
                EntityBlueprint(
                    name="Task",
                    row_count_default=20,
                    field_patterns=[
                        FieldPattern(
                            field_name="title",
                            strategy=FieldStrategy.FREE_TEXT_LOREM,
                        ),
                    ],
                ),
            ],
        )

        assert blueprint.project_id == "simple_task"
        assert blueprint.seed == 42
        assert len(blueprint.tenants) == 2
        assert len(blueprint.personas) == 1
        assert len(blueprint.entities) == 1

    def test_blueprint_is_frozen(self):
        """Test that blueprint is immutable."""
        from pydantic import ValidationError

        blueprint = DemoDataBlueprint(
            project_id="test",
            domain_description="Test",
        )

        with pytest.raises(ValidationError):
            blueprint.project_id = "changed"


class TestBlueprintContainer:
    """Tests for BlueprintContainer."""

    def test_create_container(self):
        """Test creating a container."""
        blueprint = DemoDataBlueprint(
            project_id="test",
            domain_description="Test",
        )
        container = BlueprintContainer(blueprint=blueprint)

        assert container.version == "1.0"
        assert container.blueprint == blueprint


class TestBlueprintPersistence:
    """Tests for blueprint persistence layer."""

    @pytest.fixture
    def temp_project(self):
        """Create a temporary project directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_get_blueprint_dir(self, temp_project):
        """Test getting blueprint directory path."""
        blueprint_dir = get_blueprint_dir(temp_project)

        assert blueprint_dir == temp_project / ".dazzle" / "demo_data"

    def test_load_nonexistent_blueprint(self, temp_project):
        """Test loading when no blueprint exists."""
        blueprint = load_blueprint(temp_project)

        assert blueprint is None

    def test_save_and_load_blueprint(self, temp_project):
        """Test saving and loading a blueprint."""
        blueprint = DemoDataBlueprint(
            project_id="test_project",
            domain_description="Test domain",
            seed=42,
            tenants=[TenantBlueprint(name="Alpha Ltd")],
            personas=[
                PersonaBlueprint(
                    persona_name="User",
                    description="Regular user",
                ),
            ],
            entities=[
                EntityBlueprint(
                    name="Item",
                    row_count_default=10,
                ),
            ],
        )

        # Save
        save_blueprint(temp_project, blueprint)

        # Verify file exists
        blueprint_file = get_blueprint_file(temp_project)
        assert blueprint_file.exists()

        # Load and verify
        loaded = load_blueprint(temp_project)
        assert loaded is not None
        assert loaded.project_id == "test_project"
        assert loaded.seed == 42
        assert len(loaded.tenants) == 1
        assert loaded.tenants[0].name == "Alpha Ltd"

    def test_blueprint_json_format(self, temp_project):
        """Test that blueprint is saved in correct JSON format."""
        blueprint = DemoDataBlueprint(
            project_id="test",
            domain_description="Test domain",
        )
        save_blueprint(temp_project, blueprint)

        blueprint_file = get_blueprint_file(temp_project)
        content = json.loads(blueprint_file.read_text())

        assert content["version"] == "1.0"
        assert content["blueprint"]["project_id"] == "test"
        assert content["blueprint"]["domain_description"] == "Test domain"

    def test_delete_blueprint(self, temp_project):
        """Test deleting a blueprint."""
        blueprint = DemoDataBlueprint(
            project_id="test",
            domain_description="Test",
        )
        save_blueprint(temp_project, blueprint)

        # Delete
        result = delete_blueprint(temp_project)
        assert result is True

        # Verify deleted
        assert load_blueprint(temp_project) is None

    def test_delete_nonexistent_blueprint(self, temp_project):
        """Test deleting a blueprint that doesn't exist."""
        result = delete_blueprint(temp_project)
        assert result is False


class TestBlueprintDataGenerator:
    """Tests for BlueprintDataGenerator."""

    @pytest.fixture
    def simple_blueprint(self):
        """Create a simple test blueprint."""
        return DemoDataBlueprint(
            project_id="test",
            domain_description="Simple test app",
            seed=42,
            tenants=[
                TenantBlueprint(name="Alpha Test Ltd", slug="alpha-test"),
            ],
            personas=[
                PersonaBlueprint(
                    persona_name="Staff",
                    description="Staff users",
                    default_user_count=2,
                ),
            ],
            entities=[
                EntityBlueprint(
                    name="Task",
                    row_count_default=5,
                    field_patterns=[
                        FieldPattern(
                            field_name="id",
                            strategy=FieldStrategy.UUID_GENERATE,
                        ),
                        FieldPattern(
                            field_name="title",
                            strategy=FieldStrategy.FREE_TEXT_LOREM,
                            params={"min_words": 2, "max_words": 5},
                        ),
                        FieldPattern(
                            field_name="completed",
                            strategy=FieldStrategy.BOOLEAN_WEIGHTED,
                            params={"true_weight": 0.3},
                        ),
                    ],
                ),
            ],
        )

    def test_create_generator(self, simple_blueprint):
        """Test creating a generator."""
        generator = BlueprintDataGenerator(simple_blueprint)

        assert generator.blueprint == simple_blueprint
        assert generator.seed == 42

    def test_generate_uuid(self, simple_blueprint):
        """Test UUID generation."""
        generator = BlueprintDataGenerator(simple_blueprint)
        pattern = FieldPattern(
            field_name="id",
            strategy=FieldStrategy.UUID_GENERATE,
        )

        value = generator.generate_field_value(pattern, {})

        assert isinstance(value, str)
        assert len(value) == 36  # UUID format

    def test_generate_static_list(self, simple_blueprint):
        """Test static list generation."""
        generator = BlueprintDataGenerator(simple_blueprint)
        pattern = FieldPattern(
            field_name="status",
            strategy=FieldStrategy.STATIC_LIST,
            params={"values": ["active", "inactive", "pending"]},
        )

        value = generator.generate_field_value(pattern, {})

        assert value in ["active", "inactive", "pending"]

    def test_generate_enum_weighted(self, simple_blueprint):
        """Test weighted enum generation."""
        generator = BlueprintDataGenerator(simple_blueprint)
        pattern = FieldPattern(
            field_name="status",
            strategy=FieldStrategy.ENUM_WEIGHTED,
            params={
                "enum_values": ["draft", "published"],
                "weights": [0.2, 0.8],
            },
        )

        # Generate many values to test distribution
        values = [generator.generate_field_value(pattern, {}) for _ in range(100)]

        assert all(v in ["draft", "published"] for v in values)
        # Should have more "published" due to weights
        published_count = sum(1 for v in values if v == "published")
        assert published_count > 50  # Should be around 80

    def test_generate_numeric_range(self, simple_blueprint):
        """Test numeric range generation."""
        generator = BlueprintDataGenerator(simple_blueprint)
        pattern = FieldPattern(
            field_name="count",
            strategy=FieldStrategy.NUMERIC_RANGE,
            params={"min": 10, "max": 20},
        )

        value = generator.generate_field_value(pattern, {})

        assert isinstance(value, int)
        assert 10 <= value <= 20

    def test_generate_currency_amount(self, simple_blueprint):
        """Test currency amount generation."""
        generator = BlueprintDataGenerator(simple_blueprint)
        pattern = FieldPattern(
            field_name="amount",
            strategy=FieldStrategy.CURRENCY_AMOUNT,
            params={"min": 100, "max": 1000, "decimals": 2},
        )

        value = generator.generate_field_value(pattern, {})

        assert isinstance(value, float)
        assert 100 <= value <= 1000

    def test_generate_boolean_weighted(self, simple_blueprint):
        """Test weighted boolean generation."""
        generator = BlueprintDataGenerator(simple_blueprint)
        pattern = FieldPattern(
            field_name="active",
            strategy=FieldStrategy.BOOLEAN_WEIGHTED,
            params={"true_weight": 0.9},
        )

        # Generate many values
        values = [generator.generate_field_value(pattern, {}) for _ in range(100)]

        true_count = sum(1 for v in values if v is True)
        assert true_count > 70  # Should be around 90

    def test_generate_date_relative(self, simple_blueprint):
        """Test relative date generation."""
        from datetime import date

        generator = BlueprintDataGenerator(simple_blueprint)
        pattern = FieldPattern(
            field_name="created_at",
            strategy=FieldStrategy.DATE_RELATIVE,
            params={"anchor": "today", "min_offset_days": -30, "max_offset_days": 0},
        )

        value = generator.generate_field_value(pattern, {})

        assert isinstance(value, str)
        # Should be a valid ISO date
        parsed_date = date.fromisoformat(value)
        assert parsed_date <= date.today()

    def test_generate_email_from_name(self, simple_blueprint):
        """Test email generation from name field."""
        generator = BlueprintDataGenerator(simple_blueprint)
        pattern = FieldPattern(
            field_name="email",
            strategy=FieldStrategy.EMAIL_FROM_NAME,
            params={"source_field": "full_name", "domains": ["test.com"]},
        )

        value = generator.generate_field_value(
            pattern, {"full_name": "John Smith"}
        )

        assert value == "john.smith@test.com"

    def test_generate_entity(self, simple_blueprint):
        """Test generating entity rows."""
        generator = BlueprintDataGenerator(simple_blueprint)
        entity = simple_blueprint.entities[0]  # Task entity

        rows = generator.generate_entity(entity)

        assert len(rows) == 5
        for row in rows:
            assert "id" in row
            assert "title" in row
            assert "completed" in row

    @pytest.fixture
    def temp_output_dir(self):
        """Create temporary output directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_generate_all_csv(self, simple_blueprint, temp_output_dir):
        """Test generating all entities to CSV."""
        generator = BlueprintDataGenerator(simple_blueprint)

        files = generator.generate_all(temp_output_dir, format="csv")

        assert "Task" in files
        assert files["Task"].exists()
        assert files["Task"].suffix == ".csv"

        # Check content
        content = files["Task"].read_text()
        assert "id,title,completed" in content

    def test_generate_all_jsonl(self, simple_blueprint, temp_output_dir):
        """Test generating all entities to JSONL."""
        generator = BlueprintDataGenerator(simple_blueprint)

        files = generator.generate_all(temp_output_dir, format="jsonl")

        assert "Task" in files
        assert files["Task"].exists()
        assert files["Task"].suffix == ".jsonl"

        # Check content - each line should be valid JSON
        lines = files["Task"].read_text().strip().split("\n")
        for line in lines:
            data = json.loads(line)
            assert "id" in data
            assert "title" in data

    def test_get_login_matrix(self, simple_blueprint, temp_output_dir):
        """Test generating login matrix."""
        # Add User entity to blueprint for user generation
        blueprint_with_users = DemoDataBlueprint(
            project_id="test",
            domain_description="Test",
            seed=42,
            tenants=[TenantBlueprint(name="Alpha Ltd", slug="alpha")],
            personas=[
                PersonaBlueprint(
                    persona_name="Staff",
                    description="Staff users",
                    default_user_count=2,
                ),
            ],
            entities=[
                EntityBlueprint(
                    name="Tenant",
                    row_count_default=0,
                ),
                EntityBlueprint(
                    name="User",
                    row_count_default=0,
                    tenant_scoped=True,
                ),
            ],
        )

        generator = BlueprintDataGenerator(blueprint_with_users)
        generator.generate_all(temp_output_dir)

        matrix = generator.get_login_matrix()

        assert "# Demo Login Matrix" in matrix
        assert "Tenant" in matrix
        assert "Persona" in matrix
        assert "Email" in matrix
        assert "Password" in matrix

    def test_reproducible_with_seed(self, temp_output_dir):
        """Test that same seed produces same entity data."""
        # Create identical blueprints with same seed
        blueprint = DemoDataBlueprint(
            project_id="test",
            domain_description="Test",
            seed=42,
            entities=[
                EntityBlueprint(
                    name="Item",
                    row_count_default=5,
                    field_patterns=[
                        FieldPattern(
                            field_name="id",
                            strategy=FieldStrategy.UUID_GENERATE,
                        ),
                        FieldPattern(
                            field_name="value",
                            strategy=FieldStrategy.NUMERIC_RANGE,
                            params={"min": 1, "max": 100},
                        ),
                    ],
                ),
            ],
        )

        # Generate with same seed - should produce consistent results
        generator = BlueprintDataGenerator(blueprint, seed=42)
        rows = generator.generate_entity(blueprint.entities[0])

        # Verify rows were generated with expected structure
        assert len(rows) == 5
        for row in rows:
            assert "id" in row
            assert "value" in row
            assert 1 <= row["value"] <= 100
