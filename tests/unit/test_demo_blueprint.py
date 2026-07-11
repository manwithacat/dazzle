"""
Unit tests for Demo Data Blueprint types and generation.

Tests the blueprint IR types, persistence layer, and data generation.
"""

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


def test_blueprint_ir_types_combined() -> None:
    """Combined construction tests for the demo-blueprint IR types
    (FieldPattern, EntityBlueprint, TenantBlueprint, PersonaBlueprint,
    DemoDataBlueprint, BlueprintContainer) — defaults + populated fields."""
    from pydantic import ValidationError

    # FieldPattern — explicit + every FieldStrategy enum constructable.
    pattern = FieldPattern(
        field_name="title",
        strategy=FieldStrategy.FREE_TEXT_LOREM,
        params={"min_words": 3, "max_words": 8},
    )
    assert pattern.field_name == "title"
    assert pattern.strategy == FieldStrategy.FREE_TEXT_LOREM
    assert pattern.params["min_words"] == 3
    for strategy in FieldStrategy:
        assert FieldPattern(field_name="t", strategy=strategy).strategy == strategy

    # EntityBlueprint — populated + defaults.
    entity = EntityBlueprint(
        name="Task",
        row_count_default=50,
        notes="Task entity",
        tenant_scoped=False,
        field_patterns=[
            FieldPattern(field_name="id", strategy=FieldStrategy.UUID_GENERATE),
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
    # defaults
    e_default = EntityBlueprint(name="Simple")
    assert e_default.row_count_default == 10
    assert e_default.notes is None
    assert e_default.tenant_scoped is False
    assert e_default.field_patterns == []

    # TenantBlueprint — full + minimal.
    tenant = TenantBlueprint(
        name="Alpha Solar Ltd", slug="alpha-solar", notes="Primary demo tenant"
    )
    assert (tenant.name, tenant.slug, tenant.notes) == (
        "Alpha Solar Ltd",
        "alpha-solar",
        "Primary demo tenant",
    )
    minimal_tenant = TenantBlueprint(name="Test Co")
    assert minimal_tenant.name == "Test Co"
    assert minimal_tenant.slug is None
    assert minimal_tenant.notes is None

    # PersonaBlueprint.
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

    # DemoDataBlueprint — full populated + immutability.
    blueprint = DemoDataBlueprint(
        project_id="simple_task",
        domain_description="Simple task management",
        seed=42,
        tenants=[TenantBlueprint(name="Alpha Tasks Ltd"), TenantBlueprint(name="Bravo Tasks Ltd")],
        personas=[
            PersonaBlueprint(persona_name="Staff", description="Staff users", default_user_count=2)
        ],
        entities=[
            EntityBlueprint(
                name="Task",
                row_count_default=20,
                field_patterns=[
                    FieldPattern(field_name="title", strategy=FieldStrategy.FREE_TEXT_LOREM)
                ],
            )
        ],
    )
    assert blueprint.project_id == "simple_task"
    assert blueprint.seed == 42
    assert len(blueprint.tenants) == 2
    assert len(blueprint.personas) == 1
    assert len(blueprint.entities) == 1
    # Frozen — pydantic raises ValidationError on field mutation.
    with pytest.raises(ValidationError):
        blueprint.project_id = "changed"

    # BlueprintContainer wrapper.
    container = BlueprintContainer(
        blueprint=DemoDataBlueprint(project_id="test", domain_description="Test")
    )
    assert container.version == "1.0"


def test_blueprint_persistence_combined() -> None:
    """Combined persistence-layer contract:
    - get_blueprint_dir resolves to <project>/.dazzle/demo_data.
    - load_blueprint returns None when no file exists.
    - save+load round-trips a populated blueprint with fields preserved.
    - JSON format wraps the blueprint under 'blueprint' with version '1.0'.
    - delete_blueprint returns True when present, False when absent.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        project = Path(tmpdir)

        # 1) Directory resolution.
        assert get_blueprint_dir(project) == project / ".dazzle" / "demo_data"

        # 2) load with no file → None.
        assert load_blueprint(project) is None

        # 3) save + load round trip with fields intact.
        bp = DemoDataBlueprint(
            project_id="test_project",
            domain_description="Test domain",
            seed=42,
            tenants=[TenantBlueprint(name="Alpha Ltd")],
            personas=[PersonaBlueprint(persona_name="User", description="Regular user")],
            entities=[EntityBlueprint(name="Item", row_count_default=10)],
        )
        save_blueprint(project, bp)
        blueprint_file = get_blueprint_file(project)
        assert blueprint_file.exists()
        loaded = load_blueprint(project)
        assert loaded is not None
        assert loaded.project_id == "test_project"
        assert loaded.seed == 42
        assert len(loaded.tenants) == 1
        assert loaded.tenants[0].name == "Alpha Ltd"

        # 4) JSON wrap shape.
        content = json.loads(blueprint_file.read_text())
        assert content["version"] == "1.0"
        assert content["blueprint"]["project_id"] == "test_project"
        assert content["blueprint"]["domain_description"] == "Test domain"

        # 5) delete returns True when present; subsequent load is None;
        # second delete returns False.
        assert delete_blueprint(project) is True
        assert load_blueprint(project) is None
        assert delete_blueprint(project) is False


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

    def test_field_strategy_generation_combined(self, simple_blueprint):
        """Combined per-strategy field generation contract:
        - generator construction carries blueprint + seed.
        - UUID_GENERATE → 36-char string.
        - STATIC_LIST → value drawn from the list.
        - ENUM_WEIGHTED → values from enum_values, weights skew the distribution.
        - NUMERIC_RANGE → int within [min,max].
        - CURRENCY_AMOUNT → float within [min,max].
        - BOOLEAN_WEIGHTED → distribution skewed by true_weight.
        - DATE_RELATIVE → valid ISO date <= today (with anchor='today', max=0).
        - EMAIL_FROM_NAME → ``<slug>.<4-digit>@<domain>`` shape.
        - generate_entity → row_count rows with all field_patterns populated.
        """
        from datetime import date

        generator = BlueprintDataGenerator(simple_blueprint)
        # Construction
        assert generator.blueprint == simple_blueprint
        assert generator.seed == 42

        # UUID
        uuid_val = generator.generate_field_value(
            FieldPattern(field_name="id", strategy=FieldStrategy.UUID_GENERATE), {}
        )
        assert isinstance(uuid_val, str)
        assert len(uuid_val) == 36

        # STATIC_LIST
        static_val = generator.generate_field_value(
            FieldPattern(
                field_name="status",
                strategy=FieldStrategy.STATIC_LIST,
                params={"values": ["active", "inactive", "pending"]},
            ),
            {},
        )
        assert static_val in ["active", "inactive", "pending"]

        # ENUM_WEIGHTED — distribution skews to "published" (0.8 weight).
        enum_pattern = FieldPattern(
            field_name="status",
            strategy=FieldStrategy.ENUM_WEIGHTED,
            params={"enum_values": ["draft", "published"], "weights": [0.2, 0.8]},
        )
        enum_vals = [generator.generate_field_value(enum_pattern, {}) for _ in range(100)]
        assert all(v in ["draft", "published"] for v in enum_vals)
        assert sum(1 for v in enum_vals if v == "published") > 50

        # NUMERIC_RANGE
        num_val = generator.generate_field_value(
            FieldPattern(
                field_name="count",
                strategy=FieldStrategy.NUMERIC_RANGE,
                params={"min": 10, "max": 20},
            ),
            {},
        )
        assert isinstance(num_val, int)
        assert 10 <= num_val <= 20

        # CURRENCY_AMOUNT
        cur_val = generator.generate_field_value(
            FieldPattern(
                field_name="amount",
                strategy=FieldStrategy.CURRENCY_AMOUNT,
                params={"min": 100, "max": 1000, "decimals": 2},
            ),
            {},
        )
        assert isinstance(cur_val, float)
        assert 100 <= cur_val <= 1000

        # BOOLEAN_WEIGHTED — true_weight=0.9 skews True.
        bool_pattern = FieldPattern(
            field_name="active",
            strategy=FieldStrategy.BOOLEAN_WEIGHTED,
            params={"true_weight": 0.9},
        )
        bool_vals = [generator.generate_field_value(bool_pattern, {}) for _ in range(100)]
        assert sum(1 for v in bool_vals if v is True) > 70

        # DATE_RELATIVE
        date_val = generator.generate_field_value(
            FieldPattern(
                field_name="created_at",
                strategy=FieldStrategy.DATE_RELATIVE,
                params={"anchor": "today", "min_offset_days": -30, "max_offset_days": 0},
            ),
            {},
        )
        assert isinstance(date_val, str)
        assert date.fromisoformat(date_val) <= date.today()

        # EMAIL_FROM_NAME — shape <slug>.<4-digit-suffix>@<domain> for uniqueness.
        email_val = generator.generate_field_value(
            FieldPattern(
                field_name="email",
                strategy=FieldStrategy.EMAIL_FROM_NAME,
                params={"source_field": "full_name", "domains": ["test.com"]},
            ),
            {"full_name": "John Smith"},
        )
        assert email_val.startswith("john.smith.")
        assert email_val.endswith("@test.com")
        suffix = email_val.removeprefix("john.smith.").removesuffix("@test.com")
        assert suffix.isdigit() and 1000 <= int(suffix) <= 9999

        # generate_entity — populates all field_patterns × row_count_default.
        rows = generator.generate_entity(simple_blueprint.entities[0])
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

    def test_generate_all_combined(self, simple_blueprint, temp_output_dir):
        """generate_all writes per-entity files in CSV or JSONL format with
        the right suffix and a populated header / per-line shape."""
        gen = BlueprintDataGenerator(simple_blueprint)

        # CSV
        csv_files = gen.generate_all(temp_output_dir / "csv", format="csv")
        assert "Task" in csv_files
        assert csv_files["Task"].exists()
        assert csv_files["Task"].suffix == ".csv"
        assert "id,title,completed" in csv_files["Task"].read_text()

        # JSONL
        jsonl_files = gen.generate_all(temp_output_dir / "jsonl", format="jsonl")
        assert "Task" in jsonl_files
        assert jsonl_files["Task"].exists()
        assert jsonl_files["Task"].suffix == ".jsonl"
        for line in jsonl_files["Task"].read_text().strip().split("\n"):
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

    def test_sequential_strategy_cycles_evenly(self):
        """SEQUENTIAL cycles `values` by row index — guarantees an even spread
        where STATIC_LIST's random pick would cluster (#1182)."""
        blueprint = DemoDataBlueprint(
            project_id="test",
            domain_description="Test",
            seed=42,
            entities=[
                EntityBlueprint(
                    name="Invoice",
                    row_count_default=6,
                    field_patterns=[
                        FieldPattern(field_name="id", strategy=FieldStrategy.UUID_GENERATE),
                        FieldPattern(
                            field_name="bucket",
                            strategy=FieldStrategy.SEQUENTIAL,
                            params={"values": ["a", "b", "c"]},
                        ),
                    ],
                ),
            ],
        )
        generator = BlueprintDataGenerator(blueprint, seed=42)
        rows = generator.generate_entity(blueprint.entities[0])
        buckets = [r["bucket"] for r in rows]
        # 6 rows over 3 values: deterministic round-robin, two of each.
        assert buckets == ["a", "b", "c", "a", "b", "c"]

    def test_sequential_strategy_empty_values_falls_back(self):
        """SEQUENTIAL with no `values` returns the safe default, no crash."""
        generator = BlueprintDataGenerator(
            DemoDataBlueprint(project_id="t", domain_description="t", seed=1)
        )
        value = generator.generate_field_value(
            FieldPattern(
                field_name="bucket",
                strategy=FieldStrategy.SEQUENTIAL,
                params={"values": []},
            ),
            {"__row_index__": 3},
        )
        assert value == "default"

    def test_foreign_key_within_tenant_keeps_reference_tenant_consistent(self):
        """FOREIGN_KEY with `within_tenant` restricts the pick to target rows
        sharing the current row's tenant_id — no cross-tenant FK (#1182)."""
        generator = BlueprintDataGenerator(
            DemoDataBlueprint(project_id="t", domain_description="t", seed=42)
        )
        # Two tenants, two projects each.
        generator._generated_data["Project"] = [
            {"id": "p-a1", "tenant_id": "tenant-A"},
            {"id": "p-a2", "tenant_id": "tenant-A"},
            {"id": "p-b1", "tenant_id": "tenant-B"},
            {"id": "p-b2", "tenant_id": "tenant-B"},
        ]
        fk_pattern = FieldPattern(
            field_name="project_id",
            strategy=FieldStrategy.FOREIGN_KEY,
            params={"target_entity": "Project", "within_tenant": True},
        )
        # Every pick for a tenant-A row must land on a tenant-A project.
        for _ in range(40):
            value = generator.generate_field_value(fk_pattern, {"tenant_id": "tenant-A"})
            assert value in ("p-a1", "p-a2")
        for _ in range(40):
            value = generator.generate_field_value(fk_pattern, {"tenant_id": "tenant-B"})
            assert value in ("p-b1", "p-b2")

    def test_foreign_key_within_tenant_falls_back_when_no_tenant_match(self):
        """`within_tenant` falls back to the full pool when the current row has
        no tenant_id (or none matches) — single-tenant blueprints unaffected."""
        generator = BlueprintDataGenerator(
            DemoDataBlueprint(project_id="t", domain_description="t", seed=42)
        )
        generator._generated_data["Project"] = [
            {"id": "p-a1", "tenant_id": "tenant-A"},
            {"id": "p-b1", "tenant_id": "tenant-B"},
        ]
        fk_pattern = FieldPattern(
            field_name="project_id",
            strategy=FieldStrategy.FOREIGN_KEY,
            params={"target_entity": "Project", "within_tenant": True},
        )
        # No tenant_id in context → full pool is eligible.
        seen = {generator.generate_field_value(fk_pattern, {}) for _ in range(40)}
        assert seen == {"p-a1", "p-b1"}


def test_created_at_not_after_updated_at_enforced() -> None:
    """TR-58: independent date_relative draws must still yield created ≤ updated."""
    entity = EntityBlueprint(
        name="Contact",
        row_count_default=40,
        field_patterns=[
            FieldPattern(
                field_name="created_at",
                strategy=FieldStrategy.DATE_RELATIVE,
                params={"anchor": "today", "min_offset_days": -365, "max_offset_days": 0},
            ),
            FieldPattern(
                field_name="updated_at",
                strategy=FieldStrategy.DATE_RELATIVE,
                params={"anchor": "today", "min_offset_days": -365, "max_offset_days": 0},
            ),
        ],
    )
    gen = BlueprintDataGenerator(
        DemoDataBlueprint(
            project_id="t",
            domain_description="t",
            entities=[entity],
        ),
        seed=42,
    )
    rows = gen.generate_entity(entity)
    assert len(rows) == 40
    for row in rows:
        assert row["updated_at"][:10] >= row["created_at"][:10], row


def test_job_title_free_text_lorem_is_not_lorem_ipsum() -> None:
    """TR-58: free_text_lorem on job_title must not emit Latin filler."""
    entity = EntityBlueprint(
        name="Contact",
        row_count_default=5,
        field_patterns=[
            FieldPattern(
                field_name="job_title",
                strategy=FieldStrategy.FREE_TEXT_LOREM,
                params={"min_words": 3, "max_words": 8},
            ),
        ],
    )
    gen = BlueprintDataGenerator(
        DemoDataBlueprint(
            project_id="t",
            domain_description="t",
            entities=[entity],
        ),
        seed=7,
    )
    rows = gen.generate_entity(entity)
    lorem_markers = ("lorem", "ipsum", "dolor", "sit amet", "consectetur")
    for row in rows:
        title = row["job_title"].lower()
        assert not any(m in title for m in lorem_markers), row
        assert len(row["job_title"].strip()) > 0


def test_date_relative_not_before_field() -> None:
    """date_relative not_before_field floors the sample at a sibling date."""
    entity = EntityBlueprint(
        name="Contact",
        row_count_default=20,
        field_patterns=[
            FieldPattern(
                field_name="created_at",
                strategy=FieldStrategy.DATE_RELATIVE,
                params={"anchor": "today", "min_offset_days": -10, "max_offset_days": -5},
            ),
            FieldPattern(
                field_name="updated_at",
                strategy=FieldStrategy.DATE_RELATIVE,
                params={
                    "anchor": "today",
                    "min_offset_days": -365,
                    "max_offset_days": 0,
                    "not_before_field": "created_at",
                },
            ),
        ],
    )
    gen = BlueprintDataGenerator(
        DemoDataBlueprint(
            project_id="t",
            domain_description="t",
            entities=[entity],
        ),
        seed=99,
    )
    for row in gen.generate_entity(entity):
        assert row["updated_at"][:10] >= row["created_at"][:10], row
