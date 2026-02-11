"""
DAZZLE Test Generator - Generate tests from AppSpec, DSL, and Stories.

This module generates executable test designs based on:
1. Entity definitions (CRUD tests)
2. State machines (transition tests)
3. Stories (user flow tests)
4. Personas (access control tests)

The generated tests are compatible with the test_runner.py harness.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from dazzle.core.strings import to_api_plural


@dataclass
class EntityField:
    """Entity field definition."""

    name: str
    field_type: str
    required: bool
    unique: bool
    default: Any = None
    enum_values: list[str] = field(default_factory=list)


@dataclass
class EntityDef:
    """Entity definition from AppSpec."""

    name: str
    label: str
    fields: list[EntityField]
    state_field: str | None = None
    state_values: list[str] = field(default_factory=list)


@dataclass
class PersonaDef:
    """Persona definition."""

    name: str
    description: str
    goals: list[str] = field(default_factory=list)


def parse_enum_type(type_str: str) -> list[str]:
    """Extract enum values from type string like 'enum(a, b, c)'."""
    match = re.search(r"enum\(([^)]+)\)", type_str)
    if match:
        values = match.group(1).split(",")
        return [v.strip() for v in values]
    return []


def generate_test_value(field_def: EntityField) -> Any:
    """Generate a valid test value for a field."""
    field_type = field_def.field_type.lower()

    if field_def.enum_values:
        return field_def.enum_values[0]

    if "uuid" in field_type:
        return str(uuid.uuid4())
    elif "str" in field_type:
        return f"Test {field_def.name}"
    elif "text" in field_type:
        return f"Test description for {field_def.name}"
    elif "int" in field_type:
        return 1
    elif "decimal" in field_type or "float" in field_type:
        return 10.0
    elif "bool" in field_type:
        return True
    elif "date" in field_type and "time" not in field_type:
        return datetime.now().strftime("%Y-%m-%d")
    elif "datetime" in field_type:
        return datetime.now().isoformat()
    elif "email" in field_type:
        return f"test_{field_def.name}@example.com"
    elif "url" in field_type:
        return "https://example.com"
    elif "enum" in field_type:
        values = parse_enum_type(field_type)
        return values[0] if values else "default"
    elif "ref" in field_type:
        return None  # References need special handling
    else:
        return f"test_{field_def.name}"


def generate_entity_data(entity: EntityDef, include_optional: bool = False) -> dict[str, Any]:
    """Generate valid test data for an entity."""
    data = {}
    for f in entity.fields:
        # Skip auto-generated fields
        if f.name in ("id", "created_at", "updated_at"):
            continue
        # Skip references for now
        if "ref" in f.field_type.lower():
            continue

        if f.required or include_optional:
            value = generate_test_value(f)
            if value is not None:
                data[f.name] = value

    return data


class TestGenerator:
    """Generate test designs from AppSpec."""

    def __init__(self, api_url: str):
        self.api_url = api_url.rstrip("/")
        self.client = httpx.Client(timeout=10.0)
        self.entities: dict[str, EntityDef] = {}
        self.personas: list[PersonaDef] = []

    def close(self) -> None:
        self.client.close()

    def load_spec(self) -> bool:
        """Load the app spec from the running server."""
        try:
            # Get entity list
            resp = self.client.get(f"{self.api_url}/_dazzle/spec")
            if resp.status_code != 200:
                return False

            spec = resp.json()
            entity_names = spec.get("entities", [])

            # Load each entity's details
            for name in entity_names:
                entity_resp = self.client.get(f"{self.api_url}/_dazzle/entity/{name}")
                if entity_resp.status_code == 200:
                    entity_data = entity_resp.json()
                    self.entities[name] = self._parse_entity(entity_data)

            return True

        except Exception as e:
            print(f"Error loading spec: {e}")
            return False

    def _parse_entity(self, data: dict[str, Any]) -> EntityDef:
        """Parse entity data into EntityDef."""
        fields = []
        state_field = None
        state_values = []

        for f in data.get("fields", []):
            field_type = f.get("type", "str")
            enum_values = parse_enum_type(field_type)

            field_def = EntityField(
                name=f.get("name", ""),
                field_type=field_type,
                required=f.get("required", False),
                unique=f.get("unique", False),
                enum_values=enum_values,
            )
            fields.append(field_def)

            # Detect state field (common patterns)
            if f.get("name") == "status" and enum_values:
                state_field = "status"
                state_values = enum_values

        return EntityDef(
            name=data.get("name", ""),
            label=data.get("label", data.get("name", "")),
            fields=fields,
            state_field=state_field,
            state_values=state_values,
        )

    def generate_crud_tests(self, entity_name: str) -> list[dict[str, Any]]:
        """Generate CRUD tests for an entity."""
        entity = self.entities.get(entity_name)
        if not entity:
            return []

        tests = []
        test_data = generate_entity_data(entity)

        # CREATE test
        tests.append(
            {
                "test_id": f"CRUD_{entity_name.upper()}_CREATE",
                "title": f"Create {entity.label}",
                "description": f"Test creating a new {entity.label} via API",
                "trigger": "user_click",
                "steps": [
                    {
                        "action": "create",
                        "target": f"entity:{entity_name}",
                        "data": test_data,
                        "rationale": f"Create new {entity.label}",
                    },
                    {
                        "action": "assert_count",
                        "target": f"entity:{entity_name}",
                        "data": {"min": 1},
                        "rationale": f"Verify {entity.label} was created",
                    },
                ],
                "expected_outcomes": [
                    f"{entity.label} created successfully",
                    f"{entity.label} appears in list",
                ],
                "entities": [entity_name],
                "tags": ["crud", "create", "generated"],
                "status": "accepted",
            }
        )

        # READ test
        tests.append(
            {
                "test_id": f"CRUD_{entity_name.upper()}_READ",
                "title": f"Read {entity.label} list",
                "description": f"Test reading {entity.label} list via API",
                "trigger": "page_load",
                "steps": [
                    {
                        "action": "navigate_to",
                        "target": f"/{to_api_plural(entity_name)}",
                        "rationale": f"Navigate to {entity.label} list",
                    },
                    {
                        "action": "assert_visible",
                        "target": "list",
                        "rationale": "Verify list is visible",
                    },
                ],
                "expected_outcomes": [f"{entity.label} list loads successfully"],
                "entities": [entity_name],
                "tags": ["crud", "read", "generated"],
                "status": "accepted",
            }
        )

        return tests

    def generate_state_machine_tests(self, entity_name: str) -> list[dict[str, Any]]:
        """Generate state machine transition tests."""
        entity = self.entities.get(entity_name)
        if not entity or not entity.state_field:
            return []

        tests = []
        test_data = generate_entity_data(entity)

        # Test each valid transition
        for i, state in enumerate(entity.state_values[:-1]):
            next_state = entity.state_values[i + 1]

            tests.append(
                {
                    "test_id": f"SM_{entity_name.upper()}_{state.upper()}_TO_{next_state.upper()}",
                    "title": f"{entity.label} transition: {state} → {next_state}",
                    "description": f"Test state transition from {state} to {next_state}",
                    "trigger": "user_click",
                    "steps": [
                        {
                            "action": "create",
                            "target": f"entity:{entity_name}",
                            "data": {**test_data, entity.state_field: state},
                            "rationale": f"Create {entity.label} in {state} state",
                        },
                        {
                            "action": "trigger_transition",
                            "target": f"entity:{entity_name}",
                            "data": {"from_state": state, "to_state": next_state},
                            "rationale": f"Transition to {next_state}",
                        },
                    ],
                    "expected_outcomes": [f"State changes from {state} to {next_state}"],
                    "entities": [entity_name],
                    "tags": ["state_machine", "transition", "generated"],
                    "status": "accepted",
                }
            )

        return tests

    def generate_api_health_test(self) -> dict[str, Any]:
        """Generate a basic API health test."""
        return {
            "test_id": "API_HEALTH",
            "title": "API Health Check",
            "description": "Verify API is healthy and responding",
            "trigger": "page_load",
            "steps": [
                {
                    "action": "assert_visible",
                    "target": "api_health",
                    "rationale": "Check API health endpoint",
                }
            ],
            "expected_outcomes": ["API returns healthy status"],
            "entities": [],
            "tags": ["health", "api", "generated"],
            "status": "accepted",
        }

    def generate_ui_load_test(self) -> dict[str, Any]:
        """Generate a basic UI load test."""
        return {
            "test_id": "UI_LOAD",
            "title": "UI Load Check",
            "description": "Verify UI loads successfully",
            "trigger": "page_load",
            "steps": [
                {"action": "navigate_to", "target": "/", "rationale": "Navigate to home page"},
                {
                    "action": "assert_visible",
                    "target": "app_title",
                    "rationale": "Verify app title is visible",
                },
            ],
            "expected_outcomes": ["UI loads with title"],
            "entities": [],
            "tags": ["ui", "load", "generated"],
            "status": "accepted",
        }

    def generate_all_tests(self) -> list[dict[str, Any]]:
        """Generate all tests for the app."""
        tests = []

        # Health tests
        tests.append(self.generate_api_health_test())
        tests.append(self.generate_ui_load_test())

        # Entity tests
        for entity_name in self.entities:
            tests.extend(self.generate_crud_tests(entity_name))
            tests.extend(self.generate_state_machine_tests(entity_name))

        return tests


def generate_tests_for_project(project_path: Path, api_port: int = 8000) -> dict[str, Any]:
    """Generate tests for a project from its running server."""
    generator = TestGenerator(f"http://localhost:{api_port}")

    try:
        if not generator.load_spec():
            return {"error": "Failed to load spec", "designs": []}

        tests = generator.generate_all_tests()

        return {
            "version": "1.0",
            "project_name": project_path.name,
            "generated_at": datetime.now().isoformat(),
            "source": "test_generator",
            "designs": tests,
        }

    finally:
        generator.close()


def save_generated_tests(project_path: Path, tests: dict[str, Any]) -> Path:
    """Save generated tests to the project."""
    output_dir = project_path / "dsl" / "tests"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / "generated_tests.json"
    with open(output_file, "w") as f:
        json.dump(tests, f, indent=2, default=str)

    print(f"Saved {len(tests.get('designs', []))} tests to {output_file}")
    return output_file


if __name__ == "__main__":
    import argparse
    import subprocess
    import sys
    import time

    parser = argparse.ArgumentParser(description="Generate tests from AppSpec")
    parser.add_argument("project_path", help="Path to the project")
    parser.add_argument("--port", type=int, default=8000, help="API port")
    parser.add_argument("--start-server", action="store_true", help="Start server first")

    args = parser.parse_args()
    project_path = Path(args.project_path).resolve()

    if args.start_server:
        # Start the server
        print(f"Starting server for {project_path.name}...")
        subprocess.run(["pkill", "-f", "dazzle serve"], capture_output=True)
        time.sleep(1)

        proc = subprocess.Popen(
            [sys.executable, "-m", "dazzle", "dazzle", "serve", "--local"],
            cwd=project_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        time.sleep(5)

        # Extract port from output
        # ... simplified for now

    tests = generate_tests_for_project(project_path, args.port)
    if "error" not in tests:
        save_generated_tests(project_path, tests)
    else:
        print(f"Error: {tests['error']}")
        sys.exit(1)
