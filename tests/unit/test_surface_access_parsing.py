"""
Unit tests for surface and experience access control parsing.

Tests the parsing of access: declarations in DSL surface and experience blocks,
plus linker validation for persona references in access specs.
"""

from pathlib import Path

from dazzle.core import ir
from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.linker_impl import SymbolTable, validate_references


class TestSurfaceAccessParsing:
    """Tests for surface access: parsing."""

    def test_surface_access_public(self) -> None:
        """Test parsing access: public on a surface."""
        dsl = """
module test_app

entity Lead "Lead":
  id: uuid pk
  name: str(200) required

surface onboarding_welcome "Welcome":
  access: public
  uses entity Lead
  mode: create
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        assert len(fragment.surfaces) == 1
        surface = fragment.surfaces[0]
        assert surface.name == "onboarding_welcome"
        assert surface.access is not None
        assert surface.access.require_auth is False
        assert surface.access.allow_personas == []

    def test_surface_access_authenticated(self) -> None:
        """Test parsing access: authenticated on a surface."""
        dsl = """
module test_app

entity Task "Task":
  id: uuid pk
  title: str(200) required

surface dashboard "Dashboard":
  access: authenticated
  uses entity Task
  mode: list
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        surface = fragment.surfaces[0]
        assert surface.access is not None
        assert surface.access.require_auth is True
        assert surface.access.allow_personas == []

    def test_surface_access_persona(self) -> None:
        """Test parsing access: persona(admin, manager) on a surface."""
        dsl = """
module test_app

entity Config "Config":
  id: uuid pk
  key: str(200) required

surface admin_panel "Admin Panel":
  access: persona(admin, manager)
  uses entity Config
  mode: list
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        surface = fragment.surfaces[0]
        assert surface.access is not None
        assert surface.access.require_auth is True
        assert surface.access.allow_personas == ["admin", "manager"]

    def test_surface_no_access_defaults_none(self) -> None:
        """Test that existing surfaces without access: still have access=None."""
        dsl = """
module test_app

entity Task "Task":
  id: uuid pk
  title: str(200) required

surface task_list "Tasks":
  uses entity Task
  mode: list
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        surface = fragment.surfaces[0]
        assert surface.access is None

    def test_surface_access_single_persona(self) -> None:
        """Test parsing access: persona(admin) with a single persona."""
        dsl = """
module test_app

entity Config "Config":
  id: uuid pk
  key: str(200) required

surface admin_only "Admin Only":
  access: persona(admin)
  uses entity Config
  mode: view
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        surface = fragment.surfaces[0]
        assert surface.access is not None
        assert surface.access.require_auth is True
        assert surface.access.allow_personas == ["admin"]

    def test_surface_access_with_sections(self) -> None:
        """Test that access: works alongside sections and actions."""
        dsl = """
module test_app

entity Task "Task":
  id: uuid pk
  title: str(200) required
  status: str(50)

surface task_detail "Task Detail":
  access: authenticated
  uses entity Task
  mode: view
  section main:
    field title "Title"
    field status "Status"
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        surface = fragment.surfaces[0]
        assert surface.access is not None
        assert surface.access.require_auth is True
        assert len(surface.sections) == 1
        assert surface.sections[0].name == "main"


class TestExperienceAccessParsing:
    """Tests for experience access: parsing."""

    def test_experience_access_default(self) -> None:
        """Test parsing experience-level access: public."""
        dsl = """
module test_app

entity Lead "Lead":
  id: uuid pk
  name: str(200) required

surface welcome "Welcome":
  uses entity Lead
  mode: create

experience onboarding "Onboarding":
  access: public
  start at step welcome

  step welcome:
    kind: surface
    surface welcome
    on continue -> step done

  step done:
    kind: surface
    surface welcome
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        assert len(fragment.experiences) == 1
        exp = fragment.experiences[0]
        assert exp.name == "onboarding"
        assert exp.access is not None
        assert exp.access.require_auth is False

    def test_experience_access_authenticated(self) -> None:
        """Test parsing experience-level access: authenticated."""
        dsl = """
module test_app

entity Task "Task":
  id: uuid pk
  title: str(200) required

surface setup_form "Setup":
  uses entity Task
  mode: create

experience setup_flow "Setup Flow":
  access: authenticated
  start at step initial

  step initial:
    kind: surface
    surface setup_form
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        exp = fragment.experiences[0]
        assert exp.access is not None
        assert exp.access.require_auth is True

    def test_experience_step_access_override(self) -> None:
        """Test parsing step-level access: authenticated override."""
        dsl = """
module test_app

entity Lead "Lead":
  id: uuid pk
  name: str(200) required

surface welcome "Welcome":
  uses entity Lead
  mode: create

surface dashboard "Dashboard":
  uses entity Lead
  mode: list

experience onboarding "Onboarding":
  access: public
  start at step welcome

  step welcome:
    kind: surface
    surface welcome
    on continue -> step dashboard

  step dashboard:
    kind: surface
    surface dashboard
    access: authenticated
    on done -> step welcome
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        exp = fragment.experiences[0]
        assert exp.access is not None
        assert exp.access.require_auth is False

        # First step has no override
        welcome_step = exp.get_step("welcome")
        assert welcome_step is not None
        assert welcome_step.access is None

        # Second step has authenticated override
        dashboard_step = exp.get_step("dashboard")
        assert dashboard_step is not None
        assert dashboard_step.access is not None
        assert dashboard_step.access.require_auth is True

    def test_experience_step_access_persona(self) -> None:
        """Test parsing step-level access: persona(admin)."""
        dsl = """
module test_app

entity Config "Config":
  id: uuid pk
  key: str(200) required

surface admin_config "Admin Config":
  uses entity Config
  mode: edit

experience admin_flow "Admin Flow":
  start at step settings

  step settings:
    kind: surface
    surface admin_config
    access: persona(admin)
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        exp = fragment.experiences[0]
        assert exp.access is None  # no experience-level access

        settings_step = exp.get_step("settings")
        assert settings_step is not None
        assert settings_step.access is not None
        assert settings_step.access.require_auth is True
        assert settings_step.access.allow_personas == ["admin"]

    def test_experience_no_access_defaults_none(self) -> None:
        """Test that experiences without access: still have access=None."""
        dsl = """
module test_app

entity Task "Task":
  id: uuid pk
  title: str(200) required

surface task_form "Task Form":
  uses entity Task
  mode: create

experience basic_flow "Basic Flow":
  start at step begin

  step begin:
    kind: surface
    surface task_form
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        exp = fragment.experiences[0]
        assert exp.access is None
        assert exp.get_step("begin").access is None


class TestExperienceAccessLinkerValidation:
    """Tests for linker validation of persona references in experience access specs."""

    def _make_symbols_with_personas(self, *persona_ids: str) -> SymbolTable:
        """Create a SymbolTable with the given personas and a dummy entity/surface."""
        symbols = SymbolTable()
        symbols.add_entity(
            ir.EntitySpec(
                name="Task",
                fields=[
                    ir.FieldSpec(
                        name="id",
                        type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                        modifiers=[ir.FieldModifier.PK],
                    )
                ],
            ),
            "test",
        )
        symbols.add_surface(
            ir.SurfaceSpec(
                name="task_form",
                mode=ir.SurfaceMode.CREATE,
                entity_ref="Task",
            ),
            "test",
        )
        for pid in persona_ids:
            symbols.add_persona(
                ir.PersonaSpec(id=pid, label=pid.title()),
                "test",
            )
        return symbols

    def test_experience_access_persona_validated(self) -> None:
        """Unknown persona in experience access spec produces a linker error."""
        symbols = self._make_symbols_with_personas("admin")
        symbols.add_experience(
            ir.ExperienceSpec(
                name="flow",
                start_step="s1",
                steps=[
                    ir.ExperienceStep(
                        name="s1",
                        kind=ir.StepKind.SURFACE,
                        surface="task_form",
                    ),
                ],
                access=ir.SurfaceAccessSpec(
                    require_auth=True,
                    allow_personas=["admin", "nonexistent_persona"],
                ),
            ),
            "test",
        )
        errors = validate_references(symbols)
        assert any("nonexistent_persona" in e for e in errors)

    def test_experience_access_valid_persona_no_error(self) -> None:
        """Known persona in experience access spec produces no error."""
        symbols = self._make_symbols_with_personas("admin", "manager")
        symbols.add_experience(
            ir.ExperienceSpec(
                name="flow",
                start_step="s1",
                steps=[
                    ir.ExperienceStep(
                        name="s1",
                        kind=ir.StepKind.SURFACE,
                        surface="task_form",
                    ),
                ],
                access=ir.SurfaceAccessSpec(
                    require_auth=True,
                    allow_personas=["admin", "manager"],
                ),
            ),
            "test",
        )
        errors = validate_references(symbols)
        persona_errors = [e for e in errors if "persona" in e.lower()]
        assert len(persona_errors) == 0

    def test_step_access_persona_validated(self) -> None:
        """Unknown persona in step access spec produces a linker error."""
        symbols = self._make_symbols_with_personas("admin")
        symbols.add_experience(
            ir.ExperienceSpec(
                name="flow",
                start_step="s1",
                steps=[
                    ir.ExperienceStep(
                        name="s1",
                        kind=ir.StepKind.SURFACE,
                        surface="task_form",
                        access=ir.SurfaceAccessSpec(
                            require_auth=True,
                            allow_personas=["unknown_role"],
                        ),
                    ),
                ],
            ),
            "test",
        )
        errors = validate_references(symbols)
        assert any("unknown_role" in e for e in errors)
