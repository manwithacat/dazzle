"""Integration tests for OpenAPI backend."""

import json
from pathlib import Path

import pytest
import yaml as pyyaml

from dazzle.core.linker import build_appspec
from dazzle.core.parser import parse_modules
from dazzle.stacks.openapi import OpenAPIBackend


@pytest.fixture
def simple_test_dsl_path() -> Path:
    """Path to simple_test.dsl fixture."""
    return Path(__file__).parent.parent / "fixtures" / "dsl" / "simple_test.dsl"


@pytest.fixture
def simple_appspec(simple_test_dsl_path: Path):
    """Parse simple_test.dsl and return AppSpec."""
    modules = parse_modules([simple_test_dsl_path])
    return build_appspec(modules, "test.simple")


def test_openapi_backend_generates_yaml(simple_appspec, tmp_path: Path):
    """Test OpenAPI backend generates valid YAML."""
    backend = OpenAPIBackend()
    output_dir = tmp_path / "output"

    backend.generate(simple_appspec, output_dir, format="yaml")

    # Check file exists
    yaml_file = output_dir / "openapi.yaml"
    assert yaml_file.exists()

    # Check it's valid YAML
    with yaml_file.open() as f:
        doc = pyyaml.safe_load(f)

    # Basic OpenAPI structure checks
    assert doc["openapi"] == "3.0.0"
    assert "info" in doc
    assert "paths" in doc
    assert "components" in doc


def test_openapi_backend_generates_json(simple_appspec, tmp_path: Path):
    """Test OpenAPI backend generates valid JSON."""
    backend = OpenAPIBackend()
    output_dir = tmp_path / "output"

    backend.generate(simple_appspec, output_dir, format="json")

    # Check file exists
    json_file = output_dir / "openapi.json"
    assert json_file.exists()

    # Check it's valid JSON
    with json_file.open() as f:
        doc = json.load(f)

    # Basic OpenAPI structure checks
    assert doc["openapi"] == "3.0.0"
    assert "info" in doc
    assert "paths" in doc
    assert "components" in doc


def test_openapi_output_has_correct_structure(simple_appspec, tmp_path: Path):
    """Test generated OpenAPI has correct structure."""
    backend = OpenAPIBackend()
    output_dir = tmp_path / "output"

    backend.generate(simple_appspec, output_dir, format="json")

    with (output_dir / "openapi.json").open() as f:
        doc = json.load(f)

    # Check info section
    assert doc["info"]["title"] == "Simple Test App"
    assert doc["info"]["version"] == "0.1.0"

    # Check paths
    paths = doc["paths"]
    assert "/tasks" in paths
    assert "/tasks/{id}" in paths

    # Check methods
    assert "get" in paths["/tasks"]  # list
    assert "post" in paths["/tasks"]  # create
    assert "get" in paths["/tasks/{id}"]  # view
    assert "put" in paths["/tasks/{id}"]  # edit

    # Check schemas
    schemas = doc["components"]["schemas"]
    assert "Task" in schemas

    # Check Task schema
    task_schema = schemas["Task"]
    assert task_schema["type"] == "object"
    assert "properties" in task_schema
    assert "id" in task_schema["properties"]
    assert "title" in task_schema["properties"]
    assert "status" in task_schema["properties"]

    # Check required fields
    assert "required" in task_schema
    assert "title" in task_schema["required"]


def test_openapi_field_type_mapping(simple_appspec, tmp_path: Path):
    """Test that DAZZLE field types map correctly to OpenAPI."""
    backend = OpenAPIBackend()
    output_dir = tmp_path / "output"

    backend.generate(simple_appspec, output_dir, format="json")

    with (output_dir / "openapi.json").open() as f:
        doc = json.load(f)

    task_props = doc["components"]["schemas"]["Task"]["properties"]

    # UUID
    assert task_props["id"]["type"] == "string"
    assert task_props["id"]["format"] == "uuid"

    # String with max_length
    assert task_props["title"]["type"] == "string"
    assert task_props["title"]["maxLength"] == 200

    # Text
    assert task_props["description"]["type"] == "string"

    # Enum
    assert task_props["status"]["type"] == "string"
    assert set(task_props["status"]["enum"]) == {"todo", "in_progress", "done"}

    # DateTime
    assert task_props["created_at"]["type"] == "string"
    assert task_props["created_at"]["format"] == "date-time"


def test_openapi_operations_have_correct_ids(simple_appspec, tmp_path: Path):
    """Test that operations have correct operationIds."""
    backend = OpenAPIBackend()
    output_dir = tmp_path / "output"

    backend.generate(simple_appspec, output_dir, format="json")

    with (output_dir / "openapi.json").open() as f:
        doc = json.load(f)

    paths = doc["paths"]

    # Check operationIds
    assert paths["/tasks"]["get"]["operationId"] == "listTask"
    assert paths["/tasks"]["post"]["operationId"] == "createTask"
    assert paths["/tasks/{id}"]["get"]["operationId"] == "getTask"
    assert paths["/tasks/{id}"]["put"]["operationId"] == "updateTask"


def test_openapi_responses_structure(simple_appspec, tmp_path: Path):
    """Test that responses have correct structure."""
    backend = OpenAPIBackend()
    output_dir = tmp_path / "output"

    backend.generate(simple_appspec, output_dir, format="json")

    with (output_dir / "openapi.json").open() as f:
        doc = json.load(f)

    # Check list operation response
    list_response = doc["paths"]["/tasks"]["get"]["responses"]["200"]
    assert list_response["description"] == "Successful response"
    list_schema = list_response["content"]["application/json"]["schema"]
    assert list_schema["type"] == "array"
    assert list_schema["items"]["$ref"] == "#/components/schemas/Task"

    # Check create operation response
    create_response = doc["paths"]["/tasks"]["post"]["responses"]["201"]
    assert "Task created successfully" in create_response["description"]
    create_schema = create_response["content"]["application/json"]["schema"]
    assert create_schema["$ref"] == "#/components/schemas/Task"


def test_openapi_yaml_and_json_equivalent(simple_appspec, tmp_path: Path):
    """Test that YAML and JSON outputs are equivalent."""
    backend = OpenAPIBackend()

    # Generate YAML
    yaml_dir = tmp_path / "yaml"
    backend.generate(simple_appspec, yaml_dir, format="yaml")
    with (yaml_dir / "openapi.yaml").open() as f:
        yaml_doc = pyyaml.safe_load(f)

    # Generate JSON
    json_dir = tmp_path / "json"
    backend.generate(simple_appspec, json_dir, format="json")
    with (json_dir / "openapi.json").open() as f:
        json_doc = json.load(f)

    # Should be equivalent
    assert yaml_doc == json_doc
