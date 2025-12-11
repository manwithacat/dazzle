"""
Unit tests for demo data generation (v0.8.5).

Tests the Faker-based data generator and data loader.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dazzle_dnr_back.demo_data.generator import DemoDataGenerator
from dazzle_dnr_back.demo_data.loader import DemoDataLoader
from dazzle_dnr_back.specs.entity import EntitySpec, FieldSpec, FieldType, ScalarType


class TestDemoDataGenerator:
    """Tests for DemoDataGenerator."""

    @pytest.fixture
    def generator(self) -> DemoDataGenerator:
        """Create a generator with fixed seed for reproducibility."""
        return DemoDataGenerator(seed=42)

    @pytest.fixture
    def task_entity(self) -> EntitySpec:
        """Create a sample Task entity."""
        return EntitySpec(
            name="Task",
            label="Task",
            fields=[
                FieldSpec(
                    name="id",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                ),
                FieldSpec(
                    name="title",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.STR, max_length=200),
                    required=True,
                ),
                FieldSpec(
                    name="description",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.TEXT),
                ),
                FieldSpec(
                    name="status",
                    type=FieldType(kind="enum", enum_values=["pending", "in_progress", "done"]),
                    default="pending",
                ),
                FieldSpec(
                    name="priority",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.INT),
                ),
                FieldSpec(
                    name="completed",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.BOOL),
                    default=False,
                ),
                FieldSpec(
                    name="due_date",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.DATE),
                ),
            ],
        )

    @pytest.fixture
    def contact_entity(self) -> EntitySpec:
        """Create a sample Contact entity with name hints."""
        return EntitySpec(
            name="Contact",
            label="Contact",
            fields=[
                FieldSpec(
                    name="id",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                ),
                FieldSpec(
                    name="name",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.STR),
                    required=True,
                ),
                FieldSpec(
                    name="email",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.EMAIL),
                    required=True,
                ),
                FieldSpec(
                    name="phone",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.STR),
                ),
                FieldSpec(
                    name="company",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.STR),
                ),
                FieldSpec(
                    name="city",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.STR),
                ),
            ],
        )

    def test_generate_string_field(self, generator: DemoDataGenerator) -> None:
        """Test generating a string field."""
        field = FieldSpec(
            name="title",
            type=FieldType(kind="scalar", scalar_type=ScalarType.STR),
        )
        value = generator.generate_value(field)
        assert isinstance(value, str)
        assert len(value) > 0

    def test_generate_int_field(self, generator: DemoDataGenerator) -> None:
        """Test generating an integer field."""
        field = FieldSpec(
            name="count",
            type=FieldType(kind="scalar", scalar_type=ScalarType.INT),
        )
        value = generator.generate_value(field)
        assert isinstance(value, int)

    def test_generate_bool_field(self, generator: DemoDataGenerator) -> None:
        """Test generating a boolean field."""
        field = FieldSpec(
            name="active",
            type=FieldType(kind="scalar", scalar_type=ScalarType.BOOL),
        )
        value = generator.generate_value(field)
        assert isinstance(value, bool)

    def test_generate_enum_field(self, generator: DemoDataGenerator) -> None:
        """Test generating an enum field."""
        field = FieldSpec(
            name="status",
            type=FieldType(kind="enum", enum_values=["draft", "active", "closed"]),
        )
        value = generator.generate_value(field)
        assert value in ["draft", "active", "closed"]

    def test_generate_email_field(self, generator: DemoDataGenerator) -> None:
        """Test generating an email field."""
        field = FieldSpec(
            name="email",
            type=FieldType(kind="scalar", scalar_type=ScalarType.EMAIL),
        )
        value = generator.generate_value(field)
        assert isinstance(value, str)
        assert "@" in value

    def test_generate_date_field(self, generator: DemoDataGenerator) -> None:
        """Test generating a date field."""
        from datetime import date

        field = FieldSpec(
            name="due_date",
            type=FieldType(kind="scalar", scalar_type=ScalarType.DATE),
        )
        value = generator.generate_value(field)
        assert isinstance(value, date)

    def test_generate_entity(self, generator: DemoDataGenerator, task_entity: EntitySpec) -> None:
        """Test generating a complete entity."""
        data = generator.generate_entity(task_entity)

        assert "title" in data  # required field
        assert isinstance(data["title"], str)
        assert "status" in data
        assert data["status"] in ["pending", "in_progress", "done"]

    def test_generate_entity_with_overrides(
        self, generator: DemoDataGenerator, task_entity: EntitySpec
    ) -> None:
        """Test generating an entity with overrides."""
        data = generator.generate_entity(
            task_entity,
            overrides={"title": "My Custom Title", "status": "done"},
        )

        assert data["title"] == "My Custom Title"
        assert data["status"] == "done"

    def test_generate_entities_batch(
        self, generator: DemoDataGenerator, task_entity: EntitySpec
    ) -> None:
        """Test generating multiple entities."""
        entities = generator.generate_entities(task_entity, count=5)

        assert len(entities) == 5
        for entity in entities:
            assert "title" in entity
            assert isinstance(entity["title"], str)

    def test_field_name_hints(
        self, generator: DemoDataGenerator, contact_entity: EntitySpec
    ) -> None:
        """Test that field names influence generated values."""
        data = generator.generate_entity(contact_entity)

        # Email field should have @ symbol
        assert "@" in data["email"]

        # Name field should have a value (Faker generates names)
        assert isinstance(data["name"], str)
        assert len(data["name"]) > 0

    def test_reproducible_with_seed(self, task_entity: EntitySpec) -> None:
        """Test that using the same seed produces the same results."""
        gen1 = DemoDataGenerator(seed=123)
        gen2 = DemoDataGenerator(seed=123)

        data1 = gen1.generate_entity(task_entity)
        data2 = gen2.generate_entity(task_entity)

        # With the same seed, the same data should be generated
        assert data1["status"] == data2["status"]


class TestDemoDataLoader:
    """Tests for DemoDataLoader."""

    @pytest.fixture
    def loader(self, tmp_path: Path) -> DemoDataLoader:
        """Create a loader with temp directory as project root."""
        return DemoDataLoader(project_root=tmp_path)

    def test_load_from_json_file(self, loader: DemoDataLoader, tmp_path: Path) -> None:
        """Test loading demo data from a JSON file."""
        # Create test JSON file
        demo_data = {
            "Task": [
                {"title": "Task 1", "status": "pending"},
                {"title": "Task 2", "status": "done"},
            ],
            "Contact": [
                {"name": "John Doe", "email": "john@example.com"},
            ],
        }
        json_path = tmp_path / "demo.json"
        json_path.write_text(json.dumps(demo_data))

        # Load and verify
        loaded = loader.load_from_json_file(json_path)

        assert "Task" in loaded
        assert len(loaded["Task"]) == 2
        assert loaded["Task"][0]["title"] == "Task 1"
        assert "Contact" in loaded
        assert len(loaded["Contact"]) == 1

    def test_load_from_json_file_not_found(self, loader: DemoDataLoader) -> None:
        """Test error when file doesn't exist."""
        with pytest.raises(FileNotFoundError):
            loader.load_from_json_file("nonexistent.json")

    def test_load_from_json_dir(self, loader: DemoDataLoader, tmp_path: Path) -> None:
        """Test loading demo data from a directory of JSON files."""
        # Create directory with entity JSON files
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        (data_dir / "Task.json").write_text(json.dumps([{"title": "Task 1"}, {"title": "Task 2"}]))
        (data_dir / "Contact.json").write_text(
            json.dumps([{"name": "John Doe", "email": "john@example.com"}])
        )

        # Load and verify
        loaded = loader.load_from_json_dir(data_dir)

        assert "Task" in loaded
        assert len(loaded["Task"]) == 2
        assert "Contact" in loaded
        assert len(loaded["Contact"]) == 1

    def test_load_inline_demo(self, loader: DemoDataLoader) -> None:
        """Test loading inline demo data."""
        demo_data = {
            "Task": [{"title": "Inline Task"}],
        }

        loaded = loader.load_inline_demo(demo_data)

        assert "Task" in loaded
        assert loaded["Task"][0]["title"] == "Inline Task"

    def test_merge_demo_data(self, loader: DemoDataLoader) -> None:
        """Test merging multiple demo data sources."""
        source1 = {
            "Task": [{"title": "Task 1"}],
            "Contact": [{"name": "Contact 1"}],
        }
        source2 = {
            "Task": [{"title": "Task 2"}],
        }

        merged = loader.merge_demo_data(source1, source2)

        assert len(merged["Task"]) == 2
        assert len(merged["Contact"]) == 1

    def test_load_scenario_data_with_inline(self, loader: DemoDataLoader) -> None:
        """Test loading scenario data with inline demo."""
        inline_demo = {"Task": [{"title": "Inline Task"}]}

        loaded = loader.load_scenario_data(
            scenario_id="test",
            inline_demo=inline_demo,
        )

        assert "Task" in loaded
        assert loaded["Task"][0]["title"] == "Inline Task"

    def test_load_scenario_data_fallback_to_empty(self, loader: DemoDataLoader) -> None:
        """Test that scenario data falls back to empty dict."""
        loaded = loader.load_scenario_data(scenario_id="test")

        assert loaded == {}
