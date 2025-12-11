"""Tests for Dazzle Bar IR types (v0.8.5)."""

from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir import (
    DemoFixture,
    PersonaScenarioEntry,
    PersonaSpec,
    ScenarioSpec,
)


class TestPersonaSpec:
    """Tests for PersonaSpec IR type."""

    def test_basic_persona(self) -> None:
        """Test creating a basic persona."""
        persona = PersonaSpec(id="teacher", label="Teacher")
        assert persona.id == "teacher"
        assert persona.label == "Teacher"
        assert persona.description is None
        assert persona.goals == []
        assert persona.proficiency_level == "intermediate"

    def test_full_persona(self) -> None:
        """Test creating a persona with all fields."""
        persona = PersonaSpec(
            id="teacher",
            label="Teacher",
            description="A classroom teacher",
            goals=["Grade papers", "Track attendance"],
            proficiency_level="expert",
            default_workspace="classroom_view",
            default_route="/classes",
        )
        assert persona.id == "teacher"
        assert persona.label == "Teacher"
        assert persona.description == "A classroom teacher"
        assert persona.goals == ["Grade papers", "Track attendance"]
        assert persona.proficiency_level == "expert"
        assert persona.default_workspace == "classroom_view"
        assert persona.default_route == "/classes"

    def test_persona_str(self) -> None:
        """Test persona string representation."""
        persona = PersonaSpec(id="student", label="Student")
        assert str(persona) == "Persona(student: Student)"


class TestScenarioSpec:
    """Tests for ScenarioSpec IR type."""

    def test_basic_scenario(self) -> None:
        """Test creating a basic scenario."""
        scenario = ScenarioSpec(id="empty", name="Empty State")
        assert scenario.id == "empty"
        assert scenario.name == "Empty State"
        assert scenario.description is None
        assert scenario.persona_entries == []
        assert scenario.demo_fixtures == []

    def test_scenario_with_persona_entries(self) -> None:
        """Test scenario with persona-specific configurations."""
        entries = [
            PersonaScenarioEntry(
                persona_id="teacher",
                start_route="/classes",
                seed_script="scenarios/teacher.json",
            ),
            PersonaScenarioEntry(
                persona_id="student",
                start_route="/my-assignments",
            ),
        ]
        scenario = ScenarioSpec(
            id="busy_term",
            name="Busy Term",
            description="Mid-year state",
            persona_entries=entries,
        )
        assert len(scenario.persona_entries) == 2
        assert scenario.get_persona_entry("teacher") is not None
        assert scenario.get_persona_entry("teacher").start_route == "/classes"
        assert scenario.get_start_route("student") == "/my-assignments"
        assert scenario.get_persona_entry("admin") is None

    def test_scenario_with_demo_fixtures(self) -> None:
        """Test scenario with inline demo fixtures."""
        fixtures = [
            DemoFixture(
                entity="Task",
                records=[
                    {"title": "Grade papers", "status": "pending"},
                    {"title": "Prepare lecture", "status": "done"},
                ],
            ),
        ]
        scenario = ScenarioSpec(
            id="demo",
            name="Demo",
            demo_fixtures=fixtures,
        )
        assert len(scenario.demo_fixtures) == 1
        assert scenario.demo_fixtures[0].entity == "Task"
        assert len(scenario.demo_fixtures[0].records) == 2


class TestDemoFixture:
    """Tests for DemoFixture IR type."""

    def test_basic_fixture(self) -> None:
        """Test creating a basic fixture."""
        fixture = DemoFixture(entity="User", records=[{"name": "Alice"}])
        assert fixture.entity == "User"
        assert len(fixture.records) == 1
        assert fixture.records[0]["name"] == "Alice"

    def test_fixture_with_multiple_records(self) -> None:
        """Test fixture with multiple records."""
        fixture = DemoFixture(
            entity="Task",
            records=[
                {"title": "Task 1", "completed": False},
                {"title": "Task 2", "completed": True},
                {"title": "Task 3", "completed": False},
            ],
        )
        assert len(fixture.records) == 3


class TestPersonaScenarioEntry:
    """Tests for PersonaScenarioEntry IR type."""

    def test_basic_entry(self) -> None:
        """Test creating a basic entry."""
        entry = PersonaScenarioEntry(
            persona_id="admin",
            start_route="/dashboard",
        )
        assert entry.persona_id == "admin"
        assert entry.start_route == "/dashboard"
        assert entry.seed_script is None

    def test_entry_with_seed_script(self) -> None:
        """Test entry with seed script."""
        entry = PersonaScenarioEntry(
            persona_id="tester",
            start_route="/test-cases",
            seed_script="scenarios/tester_fixtures.json",
        )
        assert entry.seed_script == "scenarios/tester_fixtures.json"


class TestPersonaScenarioParsing:
    """Tests for parsing persona and scenario DSL blocks."""

    def test_parse_persona_block(self) -> None:
        """Test parsing a persona declaration."""
        dsl = """
module test

app test_app "Test"

entity User "User":
  id: uuid pk
  name: str(200) required

persona teacher "Teacher":
  description: "A classroom teacher"
  goals: "Grade papers", "Track attendance"
  proficiency: expert
"""
        module_name, app_name, app_title, uses, fragment = parse_dsl(dsl, Path("test.dsl"))

        assert len(fragment.personas) == 1
        persona = fragment.personas[0]
        assert persona.id == "teacher"
        assert persona.label == "Teacher"
        assert persona.description == "A classroom teacher"
        assert persona.goals == ["Grade papers", "Track attendance"]
        assert persona.proficiency_level == "expert"

    def test_parse_scenario_block(self) -> None:
        """Test parsing a scenario declaration."""
        dsl = """
module test

app test_app "Test"

entity Task "Task":
  id: uuid pk
  title: str(200) required

scenario busy_term "Busy Term":
  description: "Mid-year state"
  seed_script: "scenarios/busy_term.json"

  for persona teacher:
    start_route: "/classes"
    seed_script: "scenarios/teacher.json"

  for persona student:
    start_route: "/assignments"
"""
        module_name, app_name, app_title, uses, fragment = parse_dsl(dsl, Path("test.dsl"))

        assert len(fragment.scenarios) == 1
        scenario = fragment.scenarios[0]
        assert scenario.id == "busy_term"
        assert scenario.name == "Busy Term"
        assert scenario.description == "Mid-year state"
        assert scenario.seed_data_path == "scenarios/busy_term.json"
        assert len(scenario.persona_entries) == 2

        teacher_entry = scenario.get_persona_entry("teacher")
        assert teacher_entry is not None
        assert teacher_entry.start_route == "/classes"
        assert teacher_entry.seed_script == "scenarios/teacher.json"

    def test_parse_demo_block(self) -> None:
        """Test parsing a standalone demo block."""
        dsl = """
module test

app test_app "Test"

entity Task "Task":
  id: uuid pk
  title: str(200) required
  completed: bool=false

demo:
  Task:
    - title: "Grade papers", completed: false
    - title: "Prepare lecture", completed: true
"""
        module_name, app_name, app_title, uses, fragment = parse_dsl(dsl, Path("test.dsl"))

        # Demo blocks create a default scenario
        assert len(fragment.scenarios) == 1
        scenario = fragment.scenarios[0]
        assert scenario.id == "default"
        assert len(scenario.demo_fixtures) == 1

        fixture = scenario.demo_fixtures[0]
        assert fixture.entity == "Task"
        assert len(fixture.records) == 2
        assert fixture.records[0]["title"] == "Grade papers"
        assert fixture.records[0]["completed"] is False
        assert fixture.records[1]["completed"] is True

    def test_parse_multiple_personas(self) -> None:
        """Test parsing multiple persona declarations."""
        dsl = """
module test

app test_app "Test"

entity User "User":
  id: uuid pk

persona admin "Administrator":
  proficiency: expert

persona viewer "Viewer":
  proficiency: novice
"""
        module_name, app_name, app_title, uses, fragment = parse_dsl(dsl, Path("test.dsl"))

        assert len(fragment.personas) == 2
        assert fragment.personas[0].id == "admin"
        assert fragment.personas[1].id == "viewer"
