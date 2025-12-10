"""
Unit tests for the ejection module.

Tests the config parsing, adapters, runner, and OpenAPI generation.
"""

from pathlib import Path
from textwrap import dedent

import pytest

from dazzle.core.ir import (
    AppSpec,
    DomainSpec,
    EntitySpec,
    FieldSpec,
    FieldType,
    FieldTypeKind,
    FieldModifier,
    InvariantSpec,
    InvariantFieldRef,
    InvariantLiteral,
    ComparisonExpr,
    InvariantComparisonOperator,
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
def entity_with_invariants() -> EntitySpec:
    """Create an entity with invariants for testing."""
    return EntitySpec(
        name="Account",
        title="User account with balance",
        fields=[
            FieldSpec(
                name="id",
                type=FieldType(kind=FieldTypeKind.UUID),
                modifiers=[FieldModifier.PK],
            ),
            FieldSpec(
                name="balance",
                type=FieldType(kind=FieldTypeKind.DECIMAL),
                modifiers=[FieldModifier.REQUIRED],
            ),
            FieldSpec(
                name="credit_limit",
                type=FieldType(kind=FieldTypeKind.DECIMAL),
                default=0,
            ),
        ],
        invariants=[
            InvariantSpec(
                expression=ComparisonExpr(
                    left=InvariantFieldRef(path=["balance"]),
                    operator=InvariantComparisonOperator.GE,
                    right=InvariantLiteral(value=0),
                ),
                message="Account balance cannot be negative",
                code="NEGATIVE_BALANCE",
            ),
        ],
    )


@pytest.fixture
def simple_appspec(simple_entity: EntitySpec) -> AppSpec:
    """Create a simple AppSpec for testing."""
    return AppSpec(
        name="Test App",
        title="A test application",
        domain=DomainSpec(entities=[simple_entity]),
    )


@pytest.fixture
def complex_appspec(
    simple_entity: EntitySpec,
    entity_with_state: EntitySpec,
    entity_with_invariants: EntitySpec,
) -> AppSpec:
    """Create a complex AppSpec for testing."""
    return AppSpec(
        name="Complex App",
        title="A complex application with state machines and invariants",
        domain=DomainSpec(
            entities=[simple_entity, entity_with_state, entity_with_invariants]
        ),
    )


@pytest.fixture
def temp_project(tmp_path: Path) -> Path:
    """Create a temporary project directory with dazzle.toml."""
    toml_content = dedent('''
        [project]
        name = "test-project"

        [ejection]
        enabled = true

        [ejection.backend]
        framework = "fastapi"
        models = "pydantic-v2"

        [ejection.frontend]
        framework = "react"
        api_client = "zod-fetch"

        [ejection.testing]
        contract = "schemathesis"
        unit = "pytest"

        [ejection.ci]
        template = "github-actions"

        [ejection.output]
        directory = "generated/"
        clean = true
    ''')

    dsl_content = dedent('''
        module test
        app test "Test App"

        entity Task "Task":
            id: uuid pk
            title: str(200) required
            completed: bool=false
    ''')

    project_dir = tmp_path / "project"
    project_dir.mkdir()

    (project_dir / "dazzle.toml").write_text(toml_content)

    dsl_dir = project_dir / "dsl"
    dsl_dir.mkdir()
    (dsl_dir / "app.dsl").write_text(dsl_content)

    return project_dir


# =============================================================================
# Config Tests
# =============================================================================


class TestEjectionConfig:
    """Test ejection configuration parsing."""

    def test_load_default_config(self, tmp_path: Path) -> None:
        """Test loading default config when no file exists."""
        from dazzle.eject.config import load_ejection_config

        config = load_ejection_config(tmp_path / "nonexistent.toml")

        assert config.enabled is False
        assert config.backend.framework.value == "fastapi"
        assert config.frontend.framework.value == "react"

    def test_load_config_from_toml(self, temp_project: Path) -> None:
        """Test loading config from dazzle.toml."""
        from dazzle.eject.config import load_ejection_config

        config = load_ejection_config(temp_project / "dazzle.toml")

        assert config.enabled is True
        assert config.backend.framework.value == "fastapi"
        assert config.frontend.framework.value == "react"
        assert config.testing.contract.value == "schemathesis"
        assert config.ci.template.value == "github-actions"

    def test_output_path_resolution(self, temp_project: Path) -> None:
        """Test output path resolution."""
        from dazzle.eject.config import load_ejection_config

        config = load_ejection_config(temp_project / "dazzle.toml")
        output_path = config.get_output_path(temp_project)

        assert output_path == temp_project / "generated"

    def test_config_enums(self) -> None:
        """Test configuration enum values."""
        from dazzle.eject.config import (
            BackendFramework,
            FrontendFramework,
            TestingContract,
            CITemplate,
        )

        assert BackendFramework.FASTAPI.value == "fastapi"
        assert BackendFramework.DJANGO.value == "django"
        assert FrontendFramework.REACT.value == "react"
        assert FrontendFramework.VUE.value == "vue"
        assert TestingContract.SCHEMATHESIS.value == "schemathesis"
        assert CITemplate.GITHUB_ACTIONS.value == "github-actions"


# =============================================================================
# Adapter Tests
# =============================================================================


class TestAdapterRegistry:
    """Test adapter registry."""

    def test_backend_adapters_registered(self) -> None:
        """Test that backend adapters are registered."""
        from dazzle.eject.adapters import AdapterRegistry

        backends = AdapterRegistry.list_backends()
        assert "fastapi" in backends

    def test_frontend_adapters_registered(self) -> None:
        """Test that frontend adapters are registered."""
        from dazzle.eject.adapters import AdapterRegistry

        frontends = AdapterRegistry.list_frontends()
        assert "react" in frontends

    def test_testing_adapters_registered(self) -> None:
        """Test that testing adapters are registered."""
        from dazzle.eject.adapters import AdapterRegistry

        testing = AdapterRegistry.list_testing()
        assert "schemathesis" in testing
        assert "pytest" in testing

    def test_ci_adapters_registered(self) -> None:
        """Test that CI adapters are registered."""
        from dazzle.eject.adapters import AdapterRegistry

        ci = AdapterRegistry.list_ci()
        assert "github-actions" in ci
        assert "gitlab-ci" in ci

    def test_get_adapter(self) -> None:
        """Test getting adapter by name."""
        from dazzle.eject.adapters import AdapterRegistry, FastAPIAdapter

        adapter = AdapterRegistry.get_backend("fastapi")
        assert adapter is FastAPIAdapter

    def test_get_unknown_adapter(self) -> None:
        """Test getting unknown adapter returns None."""
        from dazzle.eject.adapters import AdapterRegistry

        adapter = AdapterRegistry.get_backend("unknown")
        assert adapter is None


# =============================================================================
# FastAPI Adapter Tests
# =============================================================================


class TestFastAPIAdapter:
    """Test FastAPI backend adapter."""

    def test_generate_models(
        self,
        simple_appspec: AppSpec,
        tmp_path: Path,
    ) -> None:
        """Test model generation."""
        from dazzle.eject.adapters import FastAPIAdapter
        from dazzle.eject.config import EjectionBackendConfig

        config = EjectionBackendConfig()
        adapter = FastAPIAdapter(simple_appspec, tmp_path, config)

        result = adapter.generate_models()

        # Check files were created
        assert result.files_created
        # Check at least one model file exists
        model_files = [p for p in result.files_created if "model" in str(p).lower()]
        assert len(model_files) > 0

    def test_generate_schemas(
        self,
        simple_appspec: AppSpec,
        tmp_path: Path,
    ) -> None:
        """Test schema generation."""
        from dazzle.eject.adapters import FastAPIAdapter
        from dazzle.eject.config import EjectionBackendConfig

        config = EjectionBackendConfig()
        adapter = FastAPIAdapter(simple_appspec, tmp_path, config)

        result = adapter.generate_schemas()

        # Check files were created
        assert result.files_created
        # Check at least one schema file exists
        schema_files = [p for p in result.files_created if "schema" in str(p).lower()]
        assert len(schema_files) > 0

    def test_generate_guards(
        self,
        entity_with_state: EntitySpec,
        tmp_path: Path,
    ) -> None:
        """Test guard generation for state machines."""
        from dazzle.eject.adapters import FastAPIAdapter
        from dazzle.eject.config import EjectionBackendConfig

        spec = AppSpec(
            name="Test",
            domain=DomainSpec(entities=[entity_with_state]),
        )
        config = EjectionBackendConfig()
        adapter = FastAPIAdapter(spec, tmp_path, config)

        result = adapter.generate_guards()

        # Check files were created
        assert result.files_created
        # Check at least one guard file exists
        guard_files = [p for p in result.files_created if "guard" in str(p).lower()]
        assert len(guard_files) > 0

    def test_generate_validators(
        self,
        entity_with_invariants: EntitySpec,
        tmp_path: Path,
    ) -> None:
        """Test validator generation for invariants."""
        from dazzle.eject.adapters import FastAPIAdapter
        from dazzle.eject.config import EjectionBackendConfig

        spec = AppSpec(
            name="Test",
            domain=DomainSpec(entities=[entity_with_invariants]),
        )
        config = EjectionBackendConfig()
        adapter = FastAPIAdapter(spec, tmp_path, config)

        result = adapter.generate_validators()

        # Check files were created
        assert result.files_created


# =============================================================================
# React Adapter Tests
# =============================================================================


class TestReactAdapter:
    """Test React frontend adapter."""

    def test_generate_types(
        self,
        simple_appspec: AppSpec,
        tmp_path: Path,
    ) -> None:
        """Test TypeScript type generation."""
        from dazzle.eject.adapters import ReactAdapter
        from dazzle.eject.config import EjectionFrontendConfig

        config = EjectionFrontendConfig()
        adapter = ReactAdapter(simple_appspec, tmp_path, config)

        result = adapter.generate_types()

        # Check files were created
        assert result.files_created
        # Check types file exists
        types_files = [p for p in result.files_created if "types" in str(p).lower()]
        assert len(types_files) > 0

    def test_generate_schemas(
        self,
        simple_appspec: AppSpec,
        tmp_path: Path,
    ) -> None:
        """Test Zod schema generation."""
        from dazzle.eject.adapters import ReactAdapter
        from dazzle.eject.config import EjectionFrontendConfig

        config = EjectionFrontendConfig()
        adapter = ReactAdapter(simple_appspec, tmp_path, config)

        result = adapter.generate_schemas()

        # Check files were created
        assert result.files_created

    def test_generate_hooks(
        self,
        simple_appspec: AppSpec,
        tmp_path: Path,
    ) -> None:
        """Test TanStack Query hooks generation."""
        from dazzle.eject.adapters import ReactAdapter
        from dazzle.eject.config import EjectionFrontendConfig

        config = EjectionFrontendConfig()
        adapter = ReactAdapter(simple_appspec, tmp_path, config)

        result = adapter.generate_hooks()

        # Check files were created
        assert result.files_created


# =============================================================================
# OpenAPI Tests
# =============================================================================


class TestOpenAPIGeneration:
    """Test OpenAPI specification generation."""

    def test_generate_openapi_basic(self, simple_appspec: AppSpec) -> None:
        """Test basic OpenAPI generation."""
        from dazzle.eject.openapi import generate_openapi

        openapi = generate_openapi(simple_appspec)

        assert openapi["openapi"] == "3.1.0"
        assert openapi["info"]["title"] == "Test App"
        assert "Task" in openapi["components"]["schemas"]
        assert "/api/tasks" in openapi["paths"]

    def test_generate_openapi_crud_endpoints(self, simple_appspec: AppSpec) -> None:
        """Test CRUD endpoint generation."""
        from dazzle.eject.openapi import generate_openapi

        openapi = generate_openapi(simple_appspec)

        # List endpoint
        assert "get" in openapi["paths"]["/api/tasks"]
        assert "post" in openapi["paths"]["/api/tasks"]

        # Item endpoints
        assert "get" in openapi["paths"]["/api/tasks/{task_id}"]
        assert "put" in openapi["paths"]["/api/tasks/{task_id}"]
        assert "delete" in openapi["paths"]["/api/tasks/{task_id}"]

    def test_generate_openapi_schemas(self, simple_appspec: AppSpec) -> None:
        """Test schema generation in OpenAPI."""
        from dazzle.eject.openapi import generate_openapi

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
        from dazzle.eject.openapi import generate_openapi

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

        from dazzle.eject.openapi import generate_openapi, openapi_to_json

        openapi = generate_openapi(simple_appspec)
        json_str = openapi_to_json(openapi)

        # Should be valid JSON
        parsed = json.loads(json_str)
        assert parsed["openapi"] == "3.1.0"

    def test_openapi_to_yaml(self, simple_appspec: AppSpec) -> None:
        """Test YAML output."""
        from dazzle.eject.openapi import generate_openapi, openapi_to_yaml

        openapi = generate_openapi(simple_appspec)
        yaml_str = openapi_to_yaml(openapi)

        # Should contain expected content
        assert "openapi:" in yaml_str or '"openapi"' in yaml_str


# =============================================================================
# Runner Tests
# =============================================================================


class TestEjectionRunner:
    """Test ejection runner."""

    def test_runner_initialization(
        self,
        simple_appspec: AppSpec,
        temp_project: Path,
    ) -> None:
        """Test runner initialization."""
        from dazzle.eject import EjectionRunner

        runner = EjectionRunner(simple_appspec, temp_project)

        assert runner.spec == simple_appspec
        assert runner.project_root == temp_project
        assert runner.config.enabled is True

    def test_runner_output_directory(
        self,
        simple_appspec: AppSpec,
        temp_project: Path,
    ) -> None:
        """Test runner output directory resolution."""
        from dazzle.eject import EjectionRunner

        runner = EjectionRunner(simple_appspec, temp_project)

        assert runner.output_dir == temp_project / "generated"

    def test_ejection_result(self) -> None:
        """Test EjectionResult class."""
        from dazzle.eject import EjectionResult

        result = EjectionResult()
        result.add_file(Path("/test/file.py"), "content")
        result.add_error("test error")
        result.add_warning("test warning")

        assert len(result.files) == 1
        assert len(result.errors) == 1
        assert len(result.warnings) == 1
        assert result.success is False

    def test_ejection_result_merge(self) -> None:
        """Test merging ejection results."""
        from dazzle.eject import EjectionResult

        result1 = EjectionResult()
        result1.add_file(Path("/test/file1.py"), "content1")

        result2 = EjectionResult()
        result2.add_file(Path("/test/file2.py"), "content2")
        result2.add_error("error")

        result1.merge(result2)

        assert len(result1.files) == 2
        assert len(result1.errors) == 1


# =============================================================================
# Verification Tests
# =============================================================================


class TestVerification:
    """Test ejection verification functionality."""

    def test_verification_passes_clean_code(self, tmp_path: Path) -> None:
        """Test verification passes for code with no Dazzle dependencies."""
        from dazzle.eject.runner import VerificationResult, EjectionRunner
        from dazzle.eject.config import EjectionConfig

        # Create clean Python file
        py_file = tmp_path / "clean.py"
        py_file.write_text("""
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class User(BaseModel):
    name: str
""")

        # Create clean TypeScript file
        ts_file = tmp_path / "clean.ts"
        ts_file.write_text("""
import { useState } from 'react';

export function useUser() {
    const [user, setUser] = useState(null);
    return { user, setUser };
}
""")

        # Create a minimal spec and runner
        spec = AppSpec(
            name="Test",
            domain=DomainSpec(entities=[]),
        )
        config = EjectionConfig()
        config.output.directory = str(tmp_path)

        runner = EjectionRunner(spec, tmp_path, config)
        runner.output_dir = tmp_path

        result = runner.verify()

        assert result.verified
        assert len(result.errors) == 0

    def test_verification_detects_python_imports(self, tmp_path: Path) -> None:
        """Test verification detects forbidden Python imports."""
        from dazzle.eject.runner import EjectionRunner
        from dazzle.eject.config import EjectionConfig

        # Create Python file with forbidden import
        py_file = tmp_path / "bad.py"
        py_file.write_text("""
from dazzle.core import AppSpec
from dazzle import something

import dazzle
""")

        spec = AppSpec(
            name="Test",
            domain=DomainSpec(entities=[]),
        )
        config = EjectionConfig()
        config.output.directory = str(tmp_path)

        runner = EjectionRunner(spec, tmp_path, config)
        runner.output_dir = tmp_path

        result = runner.verify()

        assert not result.verified
        assert len(result.errors) == 3  # Three forbidden imports

    def test_verification_detects_js_imports(self, tmp_path: Path) -> None:
        """Test verification detects forbidden JavaScript imports."""
        from dazzle.eject.runner import EjectionRunner
        from dazzle.eject.config import EjectionConfig

        # Create JS file with forbidden import
        js_file = tmp_path / "bad.ts"
        js_file.write_text("""
import { useEntity } from '@dazzle/core';
import something from 'dazzle';
""")

        spec = AppSpec(
            name="Test",
            domain=DomainSpec(entities=[]),
        )
        config = EjectionConfig()
        config.output.directory = str(tmp_path)

        runner = EjectionRunner(spec, tmp_path, config)
        runner.output_dir = tmp_path

        result = runner.verify()

        assert not result.verified
        assert len(result.errors) >= 2  # At least two forbidden imports

    def test_verification_detects_template_markers(self, tmp_path: Path) -> None:
        """Test verification detects template merge markers."""
        from dazzle.eject.runner import EjectionRunner
        from dazzle.eject.config import EjectionConfig

        # Create file with template markers
        py_file = tmp_path / "marked.py"
        py_file.write_text("""
# BEGIN DAZZLE GENERATED
def something():
    pass
# END DAZZLE GENERATED
""")

        spec = AppSpec(
            name="Test",
            domain=DomainSpec(entities=[]),
        )
        config = EjectionConfig()
        config.output.directory = str(tmp_path)

        runner = EjectionRunner(spec, tmp_path, config)
        runner.output_dir = tmp_path

        result = runner.verify()

        assert not result.verified
        assert len(result.errors) >= 2  # BEGIN and END markers

    def test_verification_detects_runtime_loaders(self, tmp_path: Path) -> None:
        """Test verification detects runtime DSL/AppSpec loaders."""
        from dazzle.eject.runner import EjectionRunner
        from dazzle.eject.config import EjectionConfig

        # Create file with runtime loaders
        py_file = tmp_path / "loader.py"
        py_file.write_text("""
spec = load_appspec("app.dsl")
data = parse_appspec(content)
""")

        spec = AppSpec(
            name="Test",
            domain=DomainSpec(entities=[]),
        )
        config = EjectionConfig()
        config.output.directory = str(tmp_path)

        runner = EjectionRunner(spec, tmp_path, config)
        runner.output_dir = tmp_path

        result = runner.verify()

        assert not result.verified
        assert len(result.errors) >= 2  # load_appspec and parse_appspec

    def test_ejection_metadata_generated(self, tmp_path: Path) -> None:
        """Test that .ejection.json metadata is generated."""
        import json
        from dazzle.eject.runner import EjectionRunner, EJECTION_VERSION
        from dazzle.eject.config import EjectionConfig

        spec = AppSpec(
            name="TestApp",
            domain=DomainSpec(entities=[]),
        )
        config = EjectionConfig()
        config.output.directory = str(tmp_path)

        runner = EjectionRunner(spec, tmp_path, config)

        # Run ejection (without actual adapters generating files)
        result = runner._generate_ejection_metadata()

        # Check metadata file is in result
        metadata_path = tmp_path / ".ejection.json"
        assert metadata_path in result.files

        # Parse and validate metadata
        metadata = json.loads(result.files[metadata_path])

        assert metadata["generated_by"] == "dazzle"
        assert metadata["dazzle_version"] == EJECTION_VERSION
        assert metadata["app_name"] == "TestApp"
        assert "timestamp" in metadata
        assert "config" in metadata

    def test_verification_result_properties(self) -> None:
        """Test VerificationResult properties."""
        from dazzle.eject.runner import VerificationResult

        result = VerificationResult()

        # Initially verified (no errors)
        assert result.verified

        # Add an error
        result.add_error("test error")
        assert not result.verified
        assert len(result.errors) == 1

    def test_ejection_result_verified_field(self) -> None:
        """Test EjectionResult has verified field."""
        from dazzle.eject import EjectionResult

        result = EjectionResult()

        # Initially not verified (verification hasn't run)
        assert result.verified is False
        assert result.verification_errors == []

        # Simulate verification
        result.verified = True
        assert result.verified is True
