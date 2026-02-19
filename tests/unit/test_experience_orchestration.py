"""Tests for experience flow entity orchestration (context, saves_to, prefill, when)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir import (
    AppSpec,
    DomainSpec,
    ExperienceSpec,
    ExperienceStep,
    FlowContextVar,
    StepKind,
    StepPrefill,
    StepTransition,
)

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _parse_fragment(dsl: str):
    """Parse a DSL string and return the ModuleFragment."""
    _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
    return fragment


_FULL_DSL = """\
module test_app
app test "Test"

entity Company "Company":
  id: uuid pk
  name: str(200) required
  is_vat_registered: bool=false

entity Contact "Contact":
  id: uuid pk
  name: str(200) required

surface company_create "Create Company":
  uses entity Company
  mode: create
  section main:
    field name "Name"

surface contact_create "Create Contact":
  uses entity Contact
  mode: create
  section main:
    field name "Name"

surface onboarding_done "Done":
  uses entity Company
  mode: view
  section main:
    field name "Name"

experience client_onboarding "Client Onboarding":
  context:
    company: Company
    contact: Contact

  start at step company_setup

  step company_setup:
    kind: surface
    surface company_create
    saves_to: context.company
    on success -> step contact_setup

  step contact_setup:
    kind: surface
    surface contact_create
    saves_to: context.contact
    prefill:
      company: context.company.id
    on success -> step vat_check

  step vat_check:
    kind: surface
    surface onboarding_done
    when: context.company.is_vat_registered = true
    on success -> step done

  step done:
    kind: surface
    surface onboarding_done
"""


def _parse_full_appspec():
    """Parse _FULL_DSL into an AppSpec via linker."""
    import os
    import tempfile

    from dazzle.core.linker import build_appspec
    from dazzle.core.parser import parse_modules

    with tempfile.NamedTemporaryFile(mode="w", suffix=".dsl", delete=False) as f:
        f.write(_FULL_DSL)
        f.flush()
        fpath = Path(f.name)
    try:
        modules = parse_modules([fpath])
        return build_appspec(modules, modules[0].name)
    finally:
        os.unlink(fpath)


# ===========================================================================
# Parser Tests
# ===========================================================================


class TestParseContextBlock:
    def test_parse_context_block(self):
        fragment = _parse_fragment(_FULL_DSL)
        exp = fragment.experiences[0]
        assert len(exp.context) == 2
        assert exp.context[0] == FlowContextVar(name="company", entity_ref="Company")
        assert exp.context[1] == FlowContextVar(name="contact", entity_ref="Contact")

    def test_parse_saves_to(self):
        fragment = _parse_fragment(_FULL_DSL)
        exp = fragment.experiences[0]
        step = exp.get_step("company_setup")
        assert step is not None
        assert step.saves_to == "context.company"

    def test_parse_prefill_block(self):
        fragment = _parse_fragment(_FULL_DSL)
        exp = fragment.experiences[0]
        step = exp.get_step("contact_setup")
        assert step is not None
        assert len(step.prefills) == 1
        assert step.prefills[0] == StepPrefill(field="company", expression="context.company.id")

    def test_parse_prefill_string_literal(self):
        dsl = """\
module test_app
app test "Test"

entity Task "Task":
  id: uuid pk
  title: str(200) required

surface task_create "Create Task":
  uses entity Task
  mode: create
  section main:
    field title "Title"

experience simple "Simple":
  context:
    task: Task

  start at step intake

  step intake:
    kind: surface
    surface task_create
    prefill:
      title: "default title"
    on success -> step done

  step done:
    kind: surface
    surface task_create
"""
        fragment = _parse_fragment(dsl)
        exp = fragment.experiences[0]
        step = exp.get_step("intake")
        assert step is not None
        assert step.prefills[0].expression == '"default title"'

    def test_parse_when_guard(self):
        fragment = _parse_fragment(_FULL_DSL)
        exp = fragment.experiences[0]
        step = exp.get_step("vat_check")
        assert step is not None
        assert "is_vat_registered" in step.when
        assert "true" in step.when

    def test_parse_full_orchestration(self):
        """Full DSL round-trip: context, saves_to, prefill, when all parse correctly."""
        fragment = _parse_fragment(_FULL_DSL)
        exp = fragment.experiences[0]
        assert exp.name == "client_onboarding"
        assert len(exp.context) == 2
        assert len(exp.steps) == 4
        assert exp.get_step("company_setup").saves_to == "context.company"
        assert exp.get_step("contact_setup").saves_to == "context.contact"
        assert len(exp.get_step("contact_setup").prefills) == 1
        assert exp.get_step("vat_check").when is not None

    def test_parse_no_context_backward_compat(self):
        """Experiences without context block still parse fine."""
        dsl = """\
module test_app
app test "Test"

entity Task "Task":
  id: uuid pk
  title: str(200) required

surface task_list "Tasks":
  uses entity Task
  mode: list
  section main:
    field title "Title"

experience simple "Simple":
  start at step listing

  step listing:
    kind: surface
    surface task_list
"""
        fragment = _parse_fragment(dsl)
        exp = fragment.experiences[0]
        assert exp.context == []
        assert exp.get_step("listing").saves_to is None
        assert exp.get_step("listing").prefills == []
        assert exp.get_step("listing").when is None


# ===========================================================================
# Compiler Tests
# ===========================================================================


class TestExperienceCompiler:
    def test_prefill_injects_initial_values(self):
        from dazzle_ui.converters.experience_compiler import compile_experience_context
        from dazzle_ui.runtime.experience_state import ExperienceState

        appspec = _parse_full_appspec()
        exp = appspec.experiences[0]
        state = ExperienceState(
            step="contact_setup",
            completed=["company_setup"],
            data={"company": {"id": "uuid-123", "name": "ACME"}},
        )
        ctx = compile_experience_context(exp, state, appspec)
        assert ctx.page_context is not None
        assert ctx.page_context.form is not None
        assert ctx.page_context.form.initial_values.get("company") == "uuid-123"

    def test_prefill_string_literal(self):
        from dazzle_ui.converters.experience_compiler import _resolve_prefill_expression

        result = _resolve_prefill_expression('"director"', {})
        assert result == "director"

    def test_prefill_missing_data_no_crash(self):
        from dazzle_ui.converters.experience_compiler import _resolve_prefill_expression

        result = _resolve_prefill_expression("context.company.id", {})
        assert result is None

    def test_prefill_nested_field(self):
        from dazzle_ui.converters.experience_compiler import _resolve_prefill_expression

        data = {"company": {"id": "uuid-123", "address": {"city": "London"}}}
        result = _resolve_prefill_expression("context.company.address.city", data)
        assert result == "London"


# ===========================================================================
# Route Helper Tests
# ===========================================================================


class TestRouteHelpers:
    def test_saves_to_resolves_full_entity(self):
        """saves_to should store the full response dict, not just the ID."""
        from dazzle_ui.runtime.experience_routes import _resolve_dotted_path

        data = {"company": {"id": "uuid-1", "name": "ACME", "is_vat_registered": True}}
        assert _resolve_dotted_path("context.company.id", data) == "uuid-1"
        assert _resolve_dotted_path("context.company.name", data) == "ACME"

    def test_backward_compat_entity_id(self):
        """The entity_ref_id key is still accessible via dotted path."""
        from dazzle_ui.runtime.experience_routes import _resolve_dotted_path

        data = {"Company_id": "uuid-1", "company": {"id": "uuid-1", "name": "ACME"}}
        assert _resolve_dotted_path("Company_id", data) == "uuid-1"

    def test_when_guard_skips_step(self):
        from dazzle_ui.runtime.experience_routes import _evaluate_when_guard

        data = {"company": {"is_vat_registered": False}}
        assert _evaluate_when_guard("context.company.is_vat_registered = true", data) is False

    def test_when_guard_shows_step(self):
        from dazzle_ui.runtime.experience_routes import _evaluate_when_guard

        data = {"company": {"is_vat_registered": True}}
        assert _evaluate_when_guard("context.company.is_vat_registered = true", data) is True

    def test_when_guard_not_equals(self):
        from dazzle_ui.runtime.experience_routes import _evaluate_when_guard

        data = {"company": {"status": "active"}}
        assert _evaluate_when_guard("context.company.status != active", data) is False
        assert _evaluate_when_guard("context.company.status != inactive", data) is True

    def test_when_guard_missing_data(self):
        from dazzle_ui.runtime.experience_routes import _evaluate_when_guard

        assert _evaluate_when_guard("context.company.missing = true", {}) is False


# ===========================================================================
# Validator Tests
# ===========================================================================


class TestValidatorOrchestration:
    def test_duplicate_context_vars(self):
        from dazzle.core.validator import validate_experiences

        exp = ExperienceSpec(
            name="test",
            context=[
                FlowContextVar(name="company", entity_ref="Company"),
                FlowContextVar(name="company", entity_ref="Contact"),
            ],
            start_step="s1",
            steps=[
                ExperienceStep(
                    name="s1",
                    kind=StepKind.SURFACE,
                    surface="some_surface",
                ),
            ],
        )
        appspec = AppSpec(name="test", domain=DomainSpec(), experiences=[exp])
        errors, warnings = validate_experiences(appspec)
        assert any("duplicate context variable 'company'" in e for e in errors)

    def test_saves_to_unknown_context_var(self):
        from dazzle.core.validator import validate_experiences

        exp = ExperienceSpec(
            name="test",
            context=[FlowContextVar(name="company", entity_ref="Company")],
            start_step="s1",
            steps=[
                ExperienceStep(
                    name="s1",
                    kind=StepKind.SURFACE,
                    surface="some_surface",
                    saves_to="context.unknown",
                    transitions=[StepTransition(event="success", next_step="s1")],
                ),
            ],
        )
        appspec = AppSpec(name="test", domain=DomainSpec(), experiences=[exp])
        errors, warnings = validate_experiences(appspec)
        assert any("unknown context variable 'unknown'" in e for e in errors)

    def test_saves_to_invalid_format(self):
        from dazzle.core.validator import validate_experiences

        exp = ExperienceSpec(
            name="test",
            start_step="s1",
            steps=[
                ExperienceStep(
                    name="s1",
                    kind=StepKind.SURFACE,
                    surface="some_surface",
                    saves_to="bad_format",
                    transitions=[StepTransition(event="success", next_step="s1")],
                ),
            ],
        )
        appspec = AppSpec(name="test", domain=DomainSpec(), experiences=[exp])
        errors, warnings = validate_experiences(appspec)
        assert any("saves_to must be 'context.<varname>'" in e for e in errors)

    def test_prefill_unknown_context_var(self):
        from dazzle.core.validator import validate_experiences

        exp = ExperienceSpec(
            name="test",
            context=[FlowContextVar(name="company", entity_ref="Company")],
            start_step="s1",
            steps=[
                ExperienceStep(
                    name="s1",
                    kind=StepKind.SURFACE,
                    surface="some_surface",
                    prefills=[StepPrefill(field="f", expression="context.nonexistent.id")],
                    transitions=[StepTransition(event="success", next_step="s1")],
                ),
            ],
        )
        appspec = AppSpec(name="test", domain=DomainSpec(), experiences=[exp])
        errors, warnings = validate_experiences(appspec)
        assert any("unknown context variable 'nonexistent'" in w for w in warnings)
