"""Shared pytest fixtures for DAZZLE tests."""

from pathlib import Path
import pytest
from src.dazzle.core import ir
from src.dazzle.core.parser import parse_modules
from src.dazzle.core.linker import build_appspec


@pytest.fixture
def fixtures_dir() -> Path:
    """Return path to fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def dsl_fixtures_dir(fixtures_dir: Path) -> Path:
    """Return path to DSL fixtures directory."""
    return fixtures_dir / "dsl"


@pytest.fixture
def simple_entity() -> ir.EntitySpec:
    """Return a simple entity for testing."""
    return ir.EntitySpec(
        name="Task",
        title="Task",
        fields=[
            ir.FieldSpec(
                name="id",
                type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                modifiers=[ir.FieldModifier.PK],
            ),
            ir.FieldSpec(
                name="title",
                type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=200),
                modifiers=[ir.FieldModifier.REQUIRED],
            ),
            ir.FieldSpec(
                name="status",
                type=ir.FieldType(
                    kind=ir.FieldTypeKind.ENUM,
                    enum_values=["todo", "in_progress", "done"]
                ),
                modifiers=[],
            ),
        ],
    )


@pytest.fixture
def simple_appspec(simple_entity: ir.EntitySpec) -> ir.AppSpec:
    """Return a simple AppSpec for testing."""
    return ir.AppSpec(
        name="test_app",
        title="Test App",
        version="0.1.0",
        domain=ir.DomainSpec(entities=[simple_entity]),
    )


@pytest.fixture
def simple_test_dsl(dsl_fixtures_dir: Path) -> Path:
    """Return path to simple_test.dsl fixture."""
    return dsl_fixtures_dir / "simple_test.dsl"


def parse_dsl_fixture(dsl_path: Path) -> ir.AppSpec:
    """Helper to parse a DSL fixture and return AppSpec."""
    modules = parse_modules([dsl_path])
    # Infer root module name from first module
    root_module = modules[0].name if modules else "test.app"
    return build_appspec(modules, root_module)
