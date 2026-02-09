"""Shared pytest fixtures for DAZZLE tests."""

import os
from pathlib import Path

import pytest

from dazzle.core import ir
from dazzle.core.linker import build_appspec
from dazzle.core.parser import parse_modules

# Exclude e2e/docker tests from regular collection
# These tests require playwright which is only available in Docker containers
collect_ignore = ["e2e/docker"]


@pytest.fixture(autouse=True, scope="session")
def _skip_infra_check() -> None:
    """Disable startup infrastructure validation in unit tests."""
    os.environ.setdefault("DAZZLE_SKIP_INFRA_CHECK", "1")


# Suppress deprecation warnings from deprecated adapters used in tests
def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "filterwarnings",
        "ignore:DevBrokerSQLite is deprecated:DeprecationWarning",
    )
    config.addinivalue_line(
        "filterwarnings",
        "ignore:LiteProcessAdapter is deprecated:DeprecationWarning",
    )
    config.addinivalue_line(
        "filterwarnings",
        "ignore:SQLite event bus is deprecated:DeprecationWarning",
    )


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
                    kind=ir.FieldTypeKind.ENUM, enum_values=["todo", "in_progress", "done"]
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
