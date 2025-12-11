"""
Unit tests for the ejection module.

Tests the config parsing, adapters, runner, and OpenAPI generation.
"""

from pathlib import Path
from textwrap import dedent

import pytest

from dazzle.core.ir import (
    AppSpec,
    ComparisonExpr,
    DomainSpec,
    EntitySpec,
    FieldModifier,
    FieldSpec,
    FieldType,
    FieldTypeKind,
    InvariantComparisonOperator,
    InvariantFieldRef,
    InvariantLiteral,
    InvariantSpec,
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
        domain=DomainSpec(entities=[simple_entity, entity_with_state, entity_with_invariants]),
    )


@pytest.fixture
def temp_project(tmp_path: Path) -> Path:
    """Create a temporary project directory with dazzle.toml."""
    toml_content = dedent("""
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
    """)

    dsl_content = dedent("""
        module test
        app test "Test App"

        entity Task "Task":
            id: uuid pk
            title: str(200) required
            completed: bool=false
    """)

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
            CITemplate,
            FrontendFramework,
            TestingContract,
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
        from dazzle.eject.config import EjectionConfig
        from dazzle.eject.runner import EjectionRunner

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
        from dazzle.eject.config import EjectionConfig
        from dazzle.eject.runner import EjectionRunner

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
        from dazzle.eject.config import EjectionConfig
        from dazzle.eject.runner import EjectionRunner

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
        from dazzle.eject.config import EjectionConfig
        from dazzle.eject.runner import EjectionRunner

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
        from dazzle.eject.config import EjectionConfig
        from dazzle.eject.runner import EjectionRunner

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

        from dazzle.eject.config import EjectionConfig
        from dazzle.eject.runner import EJECTION_VERSION, EjectionRunner

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


# =============================================================================
# Testing Adapter Tests
# =============================================================================


class TestSchemathesisAdapter:
    """Test Schemathesis contract testing adapter."""

    def test_generate_returns_result(
        self,
        simple_appspec: AppSpec,
        tmp_path: Path,
    ) -> None:
        """Test that generate returns a GeneratorResult."""
        from dazzle.eject.adapters import SchemathesisAdapter
        from dazzle.eject.config import EjectionTestingConfig

        config = EjectionTestingConfig()
        adapter = SchemathesisAdapter(simple_appspec, tmp_path, config)

        result = adapter.generate()

        assert result is not None
        assert result.success

    def test_generate_conftest(
        self,
        simple_appspec: AppSpec,
        tmp_path: Path,
    ) -> None:
        """Test conftest.py generation for Schemathesis."""
        from dazzle.eject.adapters import SchemathesisAdapter
        from dazzle.eject.config import EjectionTestingConfig

        config = EjectionTestingConfig()
        adapter = SchemathesisAdapter(simple_appspec, tmp_path, config)

        result = adapter._generate_conftest()

        assert result.success
        conftest_path = tmp_path / "tests" / "contract" / "conftest.py"
        assert conftest_path in result.files_created
        assert conftest_path.exists()

        content = conftest_path.read_text()
        assert "pytest" in content
        assert "schemathesis" in content
        assert "TestClient" in content
        assert "openapi_schema" in content

    def test_generate_contract_tests(
        self,
        simple_appspec: AppSpec,
        tmp_path: Path,
    ) -> None:
        """Test contract test file generation."""
        from dazzle.eject.adapters import SchemathesisAdapter
        from dazzle.eject.config import EjectionTestingConfig

        config = EjectionTestingConfig()
        adapter = SchemathesisAdapter(simple_appspec, tmp_path, config)

        result = adapter._generate_contract_tests()

        assert result.success
        test_path = tmp_path / "tests" / "contract" / "test_contract.py"
        assert test_path in result.files_created
        assert test_path.exists()

        content = test_path.read_text()
        assert "schemathesis" in content
        assert "test_api_contract" in content
        assert "test_task_api" in content.lower()  # Entity-specific test
        assert "validate_response" in content

    def test_generate_includes_all_entities(
        self,
        complex_appspec: AppSpec,
        tmp_path: Path,
    ) -> None:
        """Test that contract tests are generated for all entities."""
        from dazzle.eject.adapters import SchemathesisAdapter
        from dazzle.eject.config import EjectionTestingConfig

        config = EjectionTestingConfig()
        adapter = SchemathesisAdapter(complex_appspec, tmp_path, config)

        adapter._generate_contract_tests()

        test_path = tmp_path / "tests" / "contract" / "test_contract.py"
        content = test_path.read_text()

        # Should have tests for all entities
        assert "test_task_api" in content.lower()
        assert "test_order_api" in content.lower()
        assert "test_account_api" in content.lower()


class TestPytestAdapter:
    """Test Pytest unit testing adapter."""

    def test_generate_returns_result(
        self,
        simple_appspec: AppSpec,
        tmp_path: Path,
    ) -> None:
        """Test that generate returns a GeneratorResult."""
        from dazzle.eject.adapters import PytestAdapter
        from dazzle.eject.config import EjectionTestingConfig

        config = EjectionTestingConfig()
        adapter = PytestAdapter(simple_appspec, tmp_path, config)

        result = adapter.generate()

        assert result is not None
        assert result.success

    def test_generate_conftest(
        self,
        simple_appspec: AppSpec,
        tmp_path: Path,
    ) -> None:
        """Test conftest.py generation for pytest."""
        from dazzle.eject.adapters import PytestAdapter
        from dazzle.eject.config import EjectionTestingConfig

        config = EjectionTestingConfig()
        adapter = PytestAdapter(simple_appspec, tmp_path, config)

        result = adapter._generate_conftest()

        assert result.success
        conftest_path = tmp_path / "tests" / "unit" / "conftest.py"
        assert conftest_path in result.files_created
        assert conftest_path.exists()

        content = conftest_path.read_text()
        assert "pytest" in content
        assert "sqlalchemy" in content
        assert "db_session" in content
        assert "TestClient" in content

    def test_generate_conftest_entity_fixtures(
        self,
        simple_appspec: AppSpec,
        tmp_path: Path,
    ) -> None:
        """Test that conftest includes fixtures for each entity."""
        from dazzle.eject.adapters import PytestAdapter
        from dazzle.eject.config import EjectionTestingConfig

        config = EjectionTestingConfig()
        adapter = PytestAdapter(simple_appspec, tmp_path, config)

        adapter._generate_conftest()

        conftest_path = tmp_path / "tests" / "unit" / "conftest.py"
        content = conftest_path.read_text()

        # Should have entity-specific fixtures
        assert "task_data" in content.lower()
        assert "task_instance" in content.lower()

    def test_generate_entity_tests(
        self,
        simple_appspec: AppSpec,
        tmp_path: Path,
    ) -> None:
        """Test CRUD test generation for entities."""
        from dazzle.eject.adapters import PytestAdapter
        from dazzle.eject.config import EjectionTestingConfig

        config = EjectionTestingConfig()
        adapter = PytestAdapter(simple_appspec, tmp_path, config)

        result = adapter._generate_entity_tests()

        assert result.success
        test_path = tmp_path / "tests" / "unit" / "test_task.py"
        assert test_path in result.files_created
        assert test_path.exists()

        content = test_path.read_text()
        assert "TestTaskCRUD" in content
        assert "test_create_task" in content
        assert "test_get_task" in content
        assert "test_list_tasks" in content
        assert "test_update_task" in content
        assert "test_delete_task" in content
        assert "test_get_task_not_found" in content
        assert "TestTaskValidation" in content

    def test_generate_entity_tests_multiple_entities(
        self,
        complex_appspec: AppSpec,
        tmp_path: Path,
    ) -> None:
        """Test CRUD test generation for multiple entities."""
        from dazzle.eject.adapters import PytestAdapter
        from dazzle.eject.config import EjectionTestingConfig

        config = EjectionTestingConfig()
        adapter = PytestAdapter(complex_appspec, tmp_path, config)

        adapter._generate_entity_tests()

        # Should create test files for each entity
        assert (tmp_path / "tests" / "unit" / "test_task.py").exists()
        assert (tmp_path / "tests" / "unit" / "test_order.py").exists()
        assert (tmp_path / "tests" / "unit" / "test_account.py").exists()

    def test_generate_guard_tests_with_state_machine(
        self,
        entity_with_state: EntitySpec,
        tmp_path: Path,
    ) -> None:
        """Test guard test generation for entities with state machines."""
        from dazzle.eject.adapters import PytestAdapter
        from dazzle.eject.config import EjectionTestingConfig

        spec = AppSpec(
            name="Test",
            domain=DomainSpec(entities=[entity_with_state]),
        )
        config = EjectionTestingConfig()
        adapter = PytestAdapter(spec, tmp_path, config)

        result = adapter._generate_guard_tests()

        assert result.success
        test_path = tmp_path / "tests" / "unit" / "test_guards.py"
        assert test_path in result.files_created
        assert test_path.exists()

        content = test_path.read_text()
        assert "TestStateGuards" in content
        # Should have transition tests
        assert "draft" in content.lower() or "pending" in content.lower()

    def test_generate_guard_tests_without_state_machine(
        self,
        simple_appspec: AppSpec,
        tmp_path: Path,
    ) -> None:
        """Test guard test generation when no state machines exist."""
        from dazzle.eject.adapters import PytestAdapter
        from dazzle.eject.config import EjectionTestingConfig

        config = EjectionTestingConfig()
        adapter = PytestAdapter(simple_appspec, tmp_path, config)

        result = adapter._generate_guard_tests()

        assert result.success
        test_path = tmp_path / "tests" / "unit" / "test_guards.py"
        assert test_path.exists()

        content = test_path.read_text()
        # Should have placeholder test
        assert "test_no_guards" in content or "TestStateGuards" in content

    def test_generate_validator_tests_with_invariants(
        self,
        entity_with_invariants: EntitySpec,
        tmp_path: Path,
    ) -> None:
        """Test validator test generation for entities with invariants."""
        from dazzle.eject.adapters import PytestAdapter
        from dazzle.eject.config import EjectionTestingConfig

        spec = AppSpec(
            name="Test",
            domain=DomainSpec(entities=[entity_with_invariants]),
        )
        config = EjectionTestingConfig()
        adapter = PytestAdapter(spec, tmp_path, config)

        result = adapter._generate_validator_tests()

        assert result.success
        test_path = tmp_path / "tests" / "unit" / "test_validators.py"
        assert test_path in result.files_created
        assert test_path.exists()

        content = test_path.read_text()
        assert "TestInvariantValidators" in content
        assert "AccountValidator" in content
        assert "NEGATIVE_BALANCE" in content

    def test_generate_validator_tests_without_invariants(
        self,
        simple_appspec: AppSpec,
        tmp_path: Path,
    ) -> None:
        """Test validator test generation when no invariants exist."""
        from dazzle.eject.adapters import PytestAdapter
        from dazzle.eject.config import EjectionTestingConfig

        config = EjectionTestingConfig()
        adapter = PytestAdapter(simple_appspec, tmp_path, config)

        result = adapter._generate_validator_tests()

        assert result.success
        test_path = tmp_path / "tests" / "unit" / "test_validators.py"
        assert test_path.exists()

        content = test_path.read_text()
        # Should have placeholder test
        assert "test_no_invariants" in content or "TestInvariantValidators" in content

    def test_generate_access_tests_without_access_rules(
        self,
        simple_appspec: AppSpec,
        tmp_path: Path,
    ) -> None:
        """Test access test generation when no access rules exist."""
        from dazzle.eject.adapters import PytestAdapter
        from dazzle.eject.config import EjectionTestingConfig

        config = EjectionTestingConfig()
        adapter = PytestAdapter(simple_appspec, tmp_path, config)

        result = adapter._generate_access_tests()

        assert result.success
        test_path = tmp_path / "tests" / "unit" / "test_access.py"
        assert test_path.exists()

        content = test_path.read_text()
        assert "TestAccessPolicies" in content
        assert "RequestContext" in content
        # Should have placeholder test
        assert "test_no_access_rules" in content

    def test_full_generate_creates_all_files(
        self,
        complex_appspec: AppSpec,
        tmp_path: Path,
    ) -> None:
        """Test that full generate creates all expected test files."""
        from dazzle.eject.adapters import PytestAdapter
        from dazzle.eject.config import EjectionTestingConfig

        config = EjectionTestingConfig()
        adapter = PytestAdapter(complex_appspec, tmp_path, config)

        result = adapter.generate()

        assert result.success

        # Check all expected files exist
        expected_files = [
            "tests/unit/conftest.py",
            "tests/unit/test_task.py",
            "tests/unit/test_order.py",
            "tests/unit/test_account.py",
            "tests/unit/test_guards.py",
            "tests/unit/test_validators.py",
            "tests/unit/test_access.py",
        ]

        for file_path in expected_files:
            full_path = tmp_path / file_path
            assert full_path.exists(), f"Expected {file_path} to exist"


class TestGeneratorResult:
    """Test GeneratorResult helper class."""

    def test_add_file_without_content(self, tmp_path: Path) -> None:
        """Test add_file records path without writing."""
        from dazzle.eject.generator import GeneratorResult

        result = GeneratorResult()
        test_path = tmp_path / "test.py"

        result.add_file(test_path)

        assert test_path in result.files_created
        assert not test_path.exists()  # File not written

    def test_add_file_with_content(self, tmp_path: Path) -> None:
        """Test add_file writes content and records path."""
        from dazzle.eject.generator import GeneratorResult

        result = GeneratorResult()
        test_path = tmp_path / "test.py"
        content = "print('hello')"

        result.add_file(test_path, content)

        assert test_path in result.files_created
        assert test_path.exists()
        assert test_path.read_text() == content

    def test_add_file_creates_parent_directories(self, tmp_path: Path) -> None:
        """Test add_file creates parent directories when writing."""
        from dazzle.eject.generator import GeneratorResult

        result = GeneratorResult()
        test_path = tmp_path / "deep" / "nested" / "dir" / "test.py"
        content = "# test"

        result.add_file(test_path, content)

        assert test_path.exists()
        assert test_path.read_text() == content


# =============================================================================
# CI Adapter Tests
# =============================================================================


class TestGitHubActionsAdapter:
    """Test GitHub Actions CI adapter."""

    def test_generate_returns_result(
        self,
        simple_appspec: AppSpec,
        tmp_path: Path,
    ) -> None:
        """Test that generate returns a GeneratorResult."""
        from dazzle.eject.adapters import GitHubActionsAdapter
        from dazzle.eject.config import EjectionCIConfig

        config = EjectionCIConfig()
        adapter = GitHubActionsAdapter(simple_appspec, tmp_path, config)

        result = adapter.generate()

        assert result is not None
        assert result.success

    def test_generate_ci_workflow(
        self,
        simple_appspec: AppSpec,
        tmp_path: Path,
    ) -> None:
        """Test main CI workflow generation."""
        from dazzle.eject.adapters import GitHubActionsAdapter
        from dazzle.eject.config import EjectionCIConfig

        config = EjectionCIConfig()
        adapter = GitHubActionsAdapter(simple_appspec, tmp_path, config)

        result = adapter._generate_ci_workflow()

        assert result.success
        ci_path = tmp_path / ".github" / "workflows" / "ci.yml"
        assert ci_path in result.files_created
        assert ci_path.exists()

        content = ci_path.read_text()
        assert "name: CI" in content
        assert "lint:" in content
        assert "typecheck:" in content
        assert "test:" in content
        assert "ruff" in content
        assert "mypy" in content
        assert "pytest" in content

    def test_generate_contract_workflow(
        self,
        simple_appspec: AppSpec,
        tmp_path: Path,
    ) -> None:
        """Test contract testing workflow generation."""
        from dazzle.eject.adapters import GitHubActionsAdapter
        from dazzle.eject.config import EjectionCIConfig

        config = EjectionCIConfig()
        adapter = GitHubActionsAdapter(simple_appspec, tmp_path, config)

        result = adapter._generate_contract_workflow()

        assert result.success
        contract_path = tmp_path / ".github" / "workflows" / "contract.yml"
        assert contract_path in result.files_created
        assert contract_path.exists()

        content = contract_path.read_text()
        assert "name: Contract Tests" in content
        assert "schemathesis" in content
        assert "openapi.json" in content

    def test_generate_docker_workflow(
        self,
        simple_appspec: AppSpec,
        tmp_path: Path,
    ) -> None:
        """Test Docker build workflow generation."""
        from dazzle.eject.adapters import GitHubActionsAdapter
        from dazzle.eject.config import EjectionCIConfig

        config = EjectionCIConfig()
        adapter = GitHubActionsAdapter(simple_appspec, tmp_path, config)

        result = adapter._generate_docker_workflow()

        assert result.success
        docker_path = tmp_path / ".github" / "workflows" / "docker.yml"
        assert docker_path in result.files_created
        assert docker_path.exists()

        content = docker_path.read_text()
        assert "name: Docker Build" in content
        assert "docker/build-push-action" in content
        assert "ghcr.io" in content

    def test_generate_deploy_workflow(
        self,
        simple_appspec: AppSpec,
        tmp_path: Path,
    ) -> None:
        """Test deployment workflow generation."""
        from dazzle.eject.adapters import GitHubActionsAdapter
        from dazzle.eject.config import EjectionCIConfig

        config = EjectionCIConfig()
        adapter = GitHubActionsAdapter(simple_appspec, tmp_path, config)

        result = adapter._generate_deploy_workflow()

        assert result.success
        deploy_path = tmp_path / ".github" / "workflows" / "deploy.yml"
        assert deploy_path in result.files_created
        assert deploy_path.exists()

        content = deploy_path.read_text()
        assert "name: Deploy" in content
        assert "staging" in content.lower()
        assert "production" in content.lower()
        assert "environment:" in content

    def test_generate_dependabot(
        self,
        simple_appspec: AppSpec,
        tmp_path: Path,
    ) -> None:
        """Test Dependabot configuration generation."""
        from dazzle.eject.adapters import GitHubActionsAdapter
        from dazzle.eject.config import EjectionCIConfig

        config = EjectionCIConfig()
        adapter = GitHubActionsAdapter(simple_appspec, tmp_path, config)

        result = adapter._generate_dependabot()

        assert result.success
        dependabot_path = tmp_path / ".github" / "dependabot.yml"
        assert dependabot_path in result.files_created
        assert dependabot_path.exists()

        content = dependabot_path.read_text()
        assert "version: 2" in content
        assert "package-ecosystem" in content
        assert "pip" in content
        assert "npm" in content
        assert "github-actions" in content
        assert "docker" in content

    def test_full_generate_creates_all_files(
        self,
        simple_appspec: AppSpec,
        tmp_path: Path,
    ) -> None:
        """Test that full generate creates all expected workflow files."""
        from dazzle.eject.adapters import GitHubActionsAdapter
        from dazzle.eject.config import EjectionCIConfig

        config = EjectionCIConfig()
        adapter = GitHubActionsAdapter(simple_appspec, tmp_path, config)

        result = adapter.generate()

        assert result.success

        expected_files = [
            ".github/workflows/ci.yml",
            ".github/workflows/contract.yml",
            ".github/workflows/docker.yml",
            ".github/workflows/deploy.yml",
            ".github/dependabot.yml",
        ]

        for file_path in expected_files:
            full_path = tmp_path / file_path
            assert full_path.exists(), f"Expected {file_path} to exist"

    def test_workflow_includes_app_name(
        self,
        simple_appspec: AppSpec,
        tmp_path: Path,
    ) -> None:
        """Test that workflows include the application name."""
        from dazzle.eject.adapters import GitHubActionsAdapter
        from dazzle.eject.config import EjectionCIConfig

        config = EjectionCIConfig()
        adapter = GitHubActionsAdapter(simple_appspec, tmp_path, config)

        adapter._generate_ci_workflow()

        ci_path = tmp_path / ".github" / "workflows" / "ci.yml"
        content = ci_path.read_text()

        # Should mention the app name
        assert simple_appspec.name in content or "Test App" in content


class TestGitLabCIAdapter:
    """Test GitLab CI adapter."""

    def test_generate_returns_result(
        self,
        simple_appspec: AppSpec,
        tmp_path: Path,
    ) -> None:
        """Test that generate returns a GeneratorResult."""
        from dazzle.eject.adapters.ci import GitLabCIAdapter
        from dazzle.eject.config import EjectionCIConfig

        config = EjectionCIConfig()
        adapter = GitLabCIAdapter(simple_appspec, tmp_path, config)

        result = adapter.generate()

        assert result is not None
        assert result.success

    def test_generate_gitlab_ci_file(
        self,
        simple_appspec: AppSpec,
        tmp_path: Path,
    ) -> None:
        """Test GitLab CI configuration file generation."""
        from dazzle.eject.adapters.ci import GitLabCIAdapter
        from dazzle.eject.config import EjectionCIConfig

        config = EjectionCIConfig()
        adapter = GitLabCIAdapter(simple_appspec, tmp_path, config)

        result = adapter.generate()

        assert result.success
        gitlab_path = tmp_path / ".gitlab-ci.yml"
        assert gitlab_path in result.files_created
        assert gitlab_path.exists()

        content = gitlab_path.read_text()
        assert "stages:" in content
        assert "lint" in content
        assert "test" in content
        assert "build" in content
        assert "deploy" in content

    def test_gitlab_ci_has_lint_jobs(
        self,
        simple_appspec: AppSpec,
        tmp_path: Path,
    ) -> None:
        """Test GitLab CI includes lint jobs."""
        from dazzle.eject.adapters.ci import GitLabCIAdapter
        from dazzle.eject.config import EjectionCIConfig

        config = EjectionCIConfig()
        adapter = GitLabCIAdapter(simple_appspec, tmp_path, config)

        adapter.generate()

        gitlab_path = tmp_path / ".gitlab-ci.yml"
        content = gitlab_path.read_text()

        assert "lint:python:" in content
        assert "lint:frontend:" in content
        assert "typecheck:python:" in content
        assert "ruff" in content
        assert "mypy" in content

    def test_gitlab_ci_has_test_jobs(
        self,
        simple_appspec: AppSpec,
        tmp_path: Path,
    ) -> None:
        """Test GitLab CI includes test jobs."""
        from dazzle.eject.adapters.ci import GitLabCIAdapter
        from dazzle.eject.config import EjectionCIConfig

        config = EjectionCIConfig()
        adapter = GitLabCIAdapter(simple_appspec, tmp_path, config)

        adapter.generate()

        gitlab_path = tmp_path / ".gitlab-ci.yml"
        content = gitlab_path.read_text()

        assert "test:unit:" in content
        assert "test:contract:" in content
        assert "pytest" in content
        assert "schemathesis" in content

    def test_gitlab_ci_has_build_jobs(
        self,
        simple_appspec: AppSpec,
        tmp_path: Path,
    ) -> None:
        """Test GitLab CI includes build jobs."""
        from dazzle.eject.adapters.ci import GitLabCIAdapter
        from dazzle.eject.config import EjectionCIConfig

        config = EjectionCIConfig()
        adapter = GitLabCIAdapter(simple_appspec, tmp_path, config)

        adapter.generate()

        gitlab_path = tmp_path / ".gitlab-ci.yml"
        content = gitlab_path.read_text()

        assert "build:backend:" in content
        assert "build:frontend:" in content
        assert "docker" in content.lower()

    def test_gitlab_ci_has_deploy_jobs(
        self,
        simple_appspec: AppSpec,
        tmp_path: Path,
    ) -> None:
        """Test GitLab CI includes deploy jobs."""
        from dazzle.eject.adapters.ci import GitLabCIAdapter
        from dazzle.eject.config import EjectionCIConfig

        config = EjectionCIConfig()
        adapter = GitLabCIAdapter(simple_appspec, tmp_path, config)

        adapter.generate()

        gitlab_path = tmp_path / ".gitlab-ci.yml"
        content = gitlab_path.read_text()

        assert "deploy:staging:" in content
        assert "deploy:production:" in content
        assert "environment:" in content
        assert "when: manual" in content
