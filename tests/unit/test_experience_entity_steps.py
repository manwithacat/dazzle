"""Tests for experience flow entity steps — entity:, creates:, defaults: syntax."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir import AppSpec, DomainSpec, EntitySpec, FieldSpec, FieldType, SurfaceSpec
from dazzle.core.ir.experiences import (
    ExperienceSpec,
    ExperienceStep,
    FlowContextVar,
    StepKind,
    StepPrefill,
    StepTransition,
)
from dazzle.core.ir.surfaces import SurfaceMode
from dazzle_ui.converters.experience_compiler import compile_experience_context
from dazzle_ui.runtime.experience_routes import create_experience_routes
from dazzle_ui.runtime.experience_state import (
    ExperienceState,
    cookie_name,
    sign_state,
    verify_state,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_fragment(dsl: str):
    """Parse a DSL string and return the ModuleFragment."""
    _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
    return fragment


def _make_entity(name: str = "Contact", extra_fields: list[FieldSpec] | None = None) -> EntitySpec:
    fields = [
        FieldSpec(name="id", type=FieldType(kind="uuid"), is_primary_key=True),
        FieldSpec(name="name", type=FieldType(kind="str"), is_required=True),
        FieldSpec(name="email", type=FieldType(kind="email")),
    ]
    if extra_fields:
        fields.extend(extra_fields)
    return EntitySpec(name=name, fields=fields)


# ---------------------------------------------------------------------------
# DSL Parsing Tests
# ---------------------------------------------------------------------------


class TestEntityStepParsing:
    """Verify entity:, creates:, and defaults: parse correctly."""

    def test_entity_step_parses(self) -> None:
        """entity: Contact sets entity_ref and infers kind=SURFACE."""
        dsl = """\
module test_app
app test "Test"

entity Contact "Contact":
  id: uuid pk
  name: str(200) required

experience onboarding "Onboarding":
  start at step add_contact

  step add_contact:
    entity: Contact
    on success -> step done

  step done:
    entity: Contact
"""
        frag = _parse_fragment(dsl)
        exp = frag.experiences[0]
        step = exp.get_step("add_contact")
        assert step is not None
        assert step.entity_ref == "Contact"
        assert step.kind == StepKind.SURFACE
        assert step.surface is None

    def test_creates_maps_to_saves_to(self) -> None:
        """creates: contact → saves_to='context.contact'."""
        dsl = """\
module test_app
app test "Test"

entity Contact "Contact":
  id: uuid pk
  name: str(200) required

experience onboarding "Onboarding":
  start at step add_contact

  step add_contact:
    entity: Contact
    creates: contact
    on success -> step done

  step done:
    entity: Contact
"""
        frag = _parse_fragment(dsl)
        exp = frag.experiences[0]
        step = exp.get_step("add_contact")
        assert step is not None
        assert step.saves_to == "context.contact"

    def test_creates_adds_context_var(self) -> None:
        """creates: contact auto-adds FlowContextVar to the experience."""
        dsl = """\
module test_app
app test "Test"

entity Contact "Contact":
  id: uuid pk
  name: str(200) required

experience onboarding "Onboarding":
  start at step add_contact

  step add_contact:
    entity: Contact
    creates: contact
    on success -> step done

  step done:
    entity: Contact
"""
        frag = _parse_fragment(dsl)
        exp = frag.experiences[0]
        assert len(exp.context) == 1
        assert exp.context[0].name == "contact"
        assert exp.context[0].entity_ref == "Contact"

    def test_creates_does_not_duplicate_explicit_context(self) -> None:
        """If context: already declares the var, creates: doesn't add a duplicate."""
        dsl = """\
module test_app
app test "Test"

entity Contact "Contact":
  id: uuid pk
  name: str(200) required

experience onboarding "Onboarding":
  context:
    contact: Contact

  start at step add_contact

  step add_contact:
    entity: Contact
    creates: contact
    on success -> step done

  step done:
    entity: Contact
"""
        frag = _parse_fragment(dsl)
        exp = frag.experiences[0]
        assert len(exp.context) == 1

    def test_defaults_with_dollar_syntax(self) -> None:
        """defaults: contact_id: $contact → prefill with context.contact.id."""
        dsl = """\
module test_app
app test "Test"

entity Company "Company":
  id: uuid pk
  name: str(200) required

entity Contact "Contact":
  id: uuid pk
  name: str(200) required
  company_id: ref Company

experience onboarding "Onboarding":
  start at step add_company

  step add_company:
    entity: Company
    creates: company
    on success -> step add_contact

  step add_contact:
    entity: Contact
    creates: contact
    defaults:
      company_id: $company
    on success -> step done

  step done:
    entity: Contact
"""
        frag = _parse_fragment(dsl)
        exp = frag.experiences[0]
        step = exp.get_step("add_contact")
        assert step is not None
        assert len(step.prefills) == 1
        assert step.prefills[0].field == "company_id"
        assert step.prefills[0].expression == "context.company.id"

    def test_defaults_with_string_literal(self) -> None:
        """defaults: role: "director" → prefill with quoted literal."""
        dsl = """\
module test_app
app test "Test"

entity Contact "Contact":
  id: uuid pk
  name: str(200) required

experience onboarding "Onboarding":
  start at step add_contact

  step add_contact:
    entity: Contact
    defaults:
      role: "director"
    on success -> step done

  step done:
    entity: Contact
"""
        frag = _parse_fragment(dsl)
        exp = frag.experiences[0]
        step = exp.get_step("add_contact")
        assert step is not None
        assert len(step.prefills) == 1
        assert step.prefills[0].field == "role"
        assert step.prefills[0].expression == '"director"'

    def test_full_flow_parses(self) -> None:
        """Multi-step flow with entity/creates/defaults parses end-to-end."""
        dsl = """\
module test_app
app test "Test"

entity Company "Company":
  id: uuid pk
  name: str(200) required

entity Contact "Contact":
  id: uuid pk
  name: str(200) required
  company_id: ref Company

entity Address "Address":
  id: uuid pk
  street: str(200) required
  contact_id: ref Contact

experience client_onboarding "Client Onboarding":
  start at step add_company

  step add_company:
    entity: Company
    creates: company
    on success -> step add_contact

  step add_contact:
    entity: Contact
    creates: contact
    defaults:
      company_id: $company
    on success -> step add_address
    on back -> step add_company

  step add_address:
    entity: Address
    creates: address
    defaults:
      contact_id: $contact
    on success -> step done
    on back -> step add_contact

  step done:
    entity: Company
"""
        frag = _parse_fragment(dsl)
        exp = frag.experiences[0]

        assert len(exp.steps) == 4
        assert len(exp.context) == 3  # company, contact, address auto-added

        step2 = exp.get_step("add_contact")
        assert step2 is not None
        assert step2.entity_ref == "Contact"
        assert step2.saves_to == "context.contact"
        assert step2.prefills[0].expression == "context.company.id"

        step3 = exp.get_step("add_address")
        assert step3 is not None
        assert step3.entity_ref == "Address"
        assert step3.saves_to == "context.address"
        assert step3.prefills[0].expression == "context.contact.id"

    def test_existing_kind_surface_syntax_unchanged(self) -> None:
        """Existing kind: surface / surface SurfaceName syntax still works."""
        dsl = """\
module test_app
app test "Test"

entity Contact "Contact":
  id: uuid pk
  name: str(200) required

surface contact_form "Contact Form":
  uses entity Contact
  mode: create
  section main:
    field name "Name"

experience onboarding "Onboarding":
  start at step add_contact

  step add_contact:
    kind: surface
    surface contact_form
    on success -> step done

  step done:
    kind: surface
    surface contact_form
"""
        frag = _parse_fragment(dsl)
        exp = frag.experiences[0]
        step = exp.get_step("add_contact")
        assert step is not None
        assert step.kind == StepKind.SURFACE
        assert step.surface == "contact_form"
        assert step.entity_ref is None


# ---------------------------------------------------------------------------
# Compiler Tests
# ---------------------------------------------------------------------------


class TestEntityStepCompiler:
    """Verify entity_ref steps generate correct page contexts."""

    def test_entity_step_generates_form(self) -> None:
        """Step with entity_ref but no surface generates a form PageContext."""
        entity = _make_entity("Contact")
        experience = ExperienceSpec(
            name="onboarding",
            title="Onboarding",
            start_step="add_contact",
            steps=[
                ExperienceStep(
                    name="add_contact",
                    kind=StepKind.SURFACE,
                    entity_ref="Contact",
                    transitions=[StepTransition(event="success", next_step="done")],
                ),
                ExperienceStep(
                    name="done",
                    kind=StepKind.SURFACE,
                    entity_ref="Contact",
                    transitions=[],
                ),
            ],
        )
        appspec = AppSpec(
            name="test_app",
            title="Test",
            domain=DomainSpec(entities=[entity]),
            experiences=[experience],
        )
        state = ExperienceState(step="add_contact")

        ctx = compile_experience_context(experience, state, appspec, app_prefix="/app")

        assert ctx.page_context is not None
        assert ctx.page_context.form is not None
        assert (
            ctx.page_context.form.action_url
            == "/app/experiences/onboarding/add_contact?event=success"
        )

    def test_entity_step_form_has_entity_fields(self) -> None:
        """Form generated from entity_ref contains entity fields."""
        entity = _make_entity("Contact")
        experience = ExperienceSpec(
            name="onboarding",
            title="Onboarding",
            start_step="add_contact",
            steps=[
                ExperienceStep(
                    name="add_contact",
                    kind=StepKind.SURFACE,
                    entity_ref="Contact",
                    transitions=[StepTransition(event="success", next_step="done")],
                ),
                ExperienceStep(
                    name="done",
                    kind=StepKind.SURFACE,
                    entity_ref="Contact",
                    transitions=[],
                ),
            ],
        )
        appspec = AppSpec(
            name="test_app",
            title="Test",
            domain=DomainSpec(entities=[entity]),
            experiences=[experience],
        )
        state = ExperienceState(step="add_contact")

        ctx = compile_experience_context(experience, state, appspec, app_prefix="/app")

        assert ctx.page_context is not None
        assert ctx.page_context.form is not None
        field_names = [f.name for f in ctx.page_context.form.fields]
        assert "name" in field_names

    def test_entity_step_prefill_resolves(self) -> None:
        """$var defaults resolve from state.data."""
        entity = _make_entity(
            "Contact",
            extra_fields=[FieldSpec(name="company_id", type=FieldType(kind="uuid"))],
        )
        experience = ExperienceSpec(
            name="onboarding",
            title="Onboarding",
            start_step="add_contact",
            steps=[
                ExperienceStep(
                    name="add_contact",
                    kind=StepKind.SURFACE,
                    entity_ref="Contact",
                    prefills=[StepPrefill(field="company_id", expression="context.company.id")],
                    transitions=[StepTransition(event="success", next_step="done")],
                ),
                ExperienceStep(
                    name="done",
                    kind=StepKind.SURFACE,
                    entity_ref="Contact",
                    transitions=[],
                ),
            ],
        )
        appspec = AppSpec(
            name="test_app",
            title="Test",
            domain=DomainSpec(entities=[entity]),
            experiences=[experience],
        )
        state = ExperienceState(
            step="add_contact",
            data={"company": {"id": "comp-123", "name": "Acme"}},
        )

        ctx = compile_experience_context(experience, state, appspec, app_prefix="/app")

        assert ctx.page_context is not None
        assert ctx.page_context.form is not None
        assert ctx.page_context.form.initial_values.get("company_id") == "comp-123"

    def test_surface_step_still_works(self) -> None:
        """Existing surface-based steps still compile correctly."""
        entity = _make_entity("Contact")
        surface = SurfaceSpec(name="contact_form", entity_ref="Contact", mode=SurfaceMode.CREATE)
        experience = ExperienceSpec(
            name="onboarding",
            title="Onboarding",
            start_step="add_contact",
            steps=[
                ExperienceStep(
                    name="add_contact",
                    kind=StepKind.SURFACE,
                    surface="contact_form",
                    transitions=[StepTransition(event="success", next_step="done")],
                ),
                ExperienceStep(
                    name="done",
                    kind=StepKind.SURFACE,
                    surface="contact_form",
                    transitions=[],
                ),
            ],
        )
        appspec = AppSpec(
            name="test_app",
            title="Test",
            domain=DomainSpec(entities=[entity]),
            surfaces=[surface],
            experiences=[experience],
        )
        state = ExperienceState(step="add_contact")

        ctx = compile_experience_context(experience, state, appspec, app_prefix="/app")

        assert ctx.page_context is not None
        assert ctx.page_context.form is not None


# ---------------------------------------------------------------------------
# Field Filtering Tests (issue #335)
# ---------------------------------------------------------------------------


class TestFieldFiltering:
    """Verify fields: attribute restricts entity step forms."""

    def test_fields_parses_comma_separated(self) -> None:
        """fields: name, email parses to step.fields list."""
        dsl = """\
module test_app
app test "Test"

entity Contact "Contact":
  id: uuid pk
  name: str(200) required
  email: email
  phone: str(50)

experience onboarding "Onboarding":
  start at step add_contact

  step add_contact:
    entity: Contact
    fields: name, email
    on success -> step done

  step done:
    entity: Contact
"""
        frag = _parse_fragment(dsl)
        exp = frag.experiences[0]
        step = exp.get_step("add_contact")
        assert step is not None
        assert step.fields == ["name", "email"]

    def test_fields_single_field(self) -> None:
        """fields: name with a single field works."""
        dsl = """\
module test_app
app test "Test"

entity Contact "Contact":
  id: uuid pk
  name: str(200) required

experience onboarding "Onboarding":
  start at step add_contact

  step add_contact:
    entity: Contact
    fields: name
    on success -> step done

  step done:
    entity: Contact
"""
        frag = _parse_fragment(dsl)
        step = frag.experiences[0].get_step("add_contact")
        assert step is not None
        assert step.fields == ["name"]

    def test_fields_with_creates_and_defaults(self) -> None:
        """fields: works alongside creates: and defaults:."""
        dsl = """\
module test_app
app test "Test"

entity Company "Company":
  id: uuid pk
  name: str(200) required

entity Contact "Contact":
  id: uuid pk
  name: str(200) required
  email: email
  phone: str(50)
  company_id: ref Company

experience onboarding "Onboarding":
  start at step add_company

  step add_company:
    entity: Company
    creates: company
    on success -> step add_contact

  step add_contact:
    entity: Contact
    creates: contact
    fields: name, email
    defaults:
      company_id: $company
    on success -> step done

  step done:
    entity: Contact
"""
        frag = _parse_fragment(dsl)
        step = frag.experiences[0].get_step("add_contact")
        assert step is not None
        assert step.fields == ["name", "email"]
        assert step.saves_to == "context.contact"
        assert step.prefills[0].field == "company_id"

    def test_no_fields_returns_none(self) -> None:
        """Step without fields: has fields=None (show all)."""
        dsl = """\
module test_app
app test "Test"

entity Contact "Contact":
  id: uuid pk
  name: str(200) required

experience onboarding "Onboarding":
  start at step add_contact

  step add_contact:
    entity: Contact
    on success -> step done

  step done:
    entity: Contact
"""
        frag = _parse_fragment(dsl)
        step = frag.experiences[0].get_step("add_contact")
        assert step is not None
        assert step.fields is None

    def test_fields_filter_in_compiler(self) -> None:
        """Compiler filters form fields to only those in step.fields."""
        entity = _make_entity(
            "Contact",
            extra_fields=[FieldSpec(name="phone", type=FieldType(kind="str"))],
        )
        experience = ExperienceSpec(
            name="onboarding",
            title="Onboarding",
            start_step="add_contact",
            steps=[
                ExperienceStep(
                    name="add_contact",
                    kind=StepKind.SURFACE,
                    entity_ref="Contact",
                    fields=["name", "email"],
                    transitions=[StepTransition(event="success", next_step="done")],
                ),
                ExperienceStep(
                    name="done",
                    kind=StepKind.SURFACE,
                    entity_ref="Contact",
                    transitions=[],
                ),
            ],
        )
        appspec = AppSpec(
            name="test_app",
            title="Test",
            domain=DomainSpec(entities=[entity]),
            experiences=[experience],
        )
        state = ExperienceState(step="add_contact")

        ctx = compile_experience_context(experience, state, appspec, app_prefix="/app")

        assert ctx.page_context is not None
        assert ctx.page_context.form is not None
        field_names = [f.name for f in ctx.page_context.form.fields]
        assert "name" in field_names
        assert "email" in field_names
        assert "phone" not in field_names

    def test_no_fields_shows_all(self) -> None:
        """Without fields filter, all entity fields are shown."""
        entity = _make_entity(
            "Contact",
            extra_fields=[FieldSpec(name="phone", type=FieldType(kind="str"))],
        )
        experience = ExperienceSpec(
            name="onboarding",
            title="Onboarding",
            start_step="add_contact",
            steps=[
                ExperienceStep(
                    name="add_contact",
                    kind=StepKind.SURFACE,
                    entity_ref="Contact",
                    transitions=[StepTransition(event="success", next_step="done")],
                ),
                ExperienceStep(
                    name="done",
                    kind=StepKind.SURFACE,
                    entity_ref="Contact",
                    transitions=[],
                ),
            ],
        )
        appspec = AppSpec(
            name="test_app",
            title="Test",
            domain=DomainSpec(entities=[entity]),
            experiences=[experience],
        )
        state = ExperienceState(step="add_contact")

        ctx = compile_experience_context(experience, state, appspec, app_prefix="/app")

        assert ctx.page_context is not None
        assert ctx.page_context.form is not None
        field_names = [f.name for f in ctx.page_context.form.fields]
        assert "name" in field_names
        assert "email" in field_names
        assert "phone" in field_names


# ---------------------------------------------------------------------------
# Routes Tests
# ---------------------------------------------------------------------------


def _make_entity_step_appspec() -> AppSpec:
    """Build an AppSpec with entity_ref steps for route testing."""
    company = _make_entity("Company")
    contact = _make_entity(
        "Contact",
        extra_fields=[FieldSpec(name="company_id", type=FieldType(kind="uuid"))],
    )
    experience = ExperienceSpec(
        name="onboarding",
        title="Client Onboarding",
        context=[
            FlowContextVar(name="company", entity_ref="Company"),
            FlowContextVar(name="contact", entity_ref="Contact"),
        ],
        start_step="add_company",
        steps=[
            ExperienceStep(
                name="add_company",
                kind=StepKind.SURFACE,
                entity_ref="Company",
                saves_to="context.company",
                transitions=[StepTransition(event="success", next_step="add_contact")],
            ),
            ExperienceStep(
                name="add_contact",
                kind=StepKind.SURFACE,
                entity_ref="Contact",
                saves_to="context.contact",
                prefills=[StepPrefill(field="company_id", expression="context.company.id")],
                transitions=[StepTransition(event="success", next_step="done")],
            ),
            ExperienceStep(
                name="done",
                kind=StepKind.SURFACE,
                entity_ref="Company",
                transitions=[],
            ),
        ],
    )
    return AppSpec(
        name="test_app",
        title="Test App",
        domain=DomainSpec(entities=[company, contact]),
        experiences=[experience],
    )


@pytest.fixture()
def entity_step_app() -> FastAPI:
    appspec = _make_entity_step_appspec()
    app = FastAPI()
    router = create_experience_routes(appspec, app_prefix="/app")
    app.include_router(router, prefix="/app")
    return app


@pytest.fixture()
def entity_step_client(entity_step_app: FastAPI) -> TestClient:
    return TestClient(entity_step_app, follow_redirects=False)


class TestEntityStepRoutes:
    """Verify entity_ref steps work through the route handler."""

    @patch("dazzle_ui.runtime.experience_routes._proxy_to_backend", new_callable=AsyncMock)
    def test_entity_step_creates_entity(
        self, mock_proxy: AsyncMock, entity_step_client: TestClient
    ) -> None:
        """POST to an entity_ref step proxies to backend."""
        mock_proxy.return_value = (True, {"id": "comp-new-1", "name": "Acme"})

        state = ExperienceState(step="add_company")
        cname = cookie_name("onboarding")
        entity_step_client.cookies.set(cname, sign_state(state))

        resp = entity_step_client.post(
            "/app/experiences/onboarding/add_company?event=success",
            json={"name": "Acme"},
        )
        assert resp.status_code == 302
        assert resp.headers["location"] == "/app/experiences/onboarding/add_contact"
        mock_proxy.assert_called_once()
        # entity_ref should be "Company"
        assert mock_proxy.call_args[0][1] == "Company"

    @patch("dazzle_ui.runtime.experience_routes._proxy_to_backend", new_callable=AsyncMock)
    def test_entity_id_stored_in_state(
        self, mock_proxy: AsyncMock, entity_step_client: TestClient
    ) -> None:
        """Created entity data stored under saves_to key in state."""
        mock_proxy.return_value = (True, {"id": "comp-new-1", "name": "Acme"})

        state = ExperienceState(step="add_company")
        cname = cookie_name("onboarding")
        entity_step_client.cookies.set(cname, sign_state(state))

        resp = entity_step_client.post(
            "/app/experiences/onboarding/add_company?event=success",
            json={"name": "Acme"},
        )
        assert resp.status_code == 302

        raw_cookie = resp.cookies.get(cname)
        assert raw_cookie is not None
        new_state = verify_state(raw_cookie)
        assert new_state is not None
        assert new_state.data.get("company") == {"id": "comp-new-1", "name": "Acme"}

    @patch("dazzle_ui.runtime.experience_routes._proxy_to_backend", new_callable=AsyncMock)
    def test_id_forwarding_across_steps(
        self, mock_proxy: AsyncMock, entity_step_client: TestClient
    ) -> None:
        """Step 2 sees step 1's created entity ID as FK default via prefill."""
        # Simulate state after step 1 completed
        state = ExperienceState(
            step="add_contact",
            completed=["add_company"],
            data={"company": {"id": "comp-123", "name": "Acme"}},
        )
        cname = cookie_name("onboarding")
        entity_step_client.cookies.set(cname, sign_state(state))

        # GET the step — should render with company_id prefilled
        resp = entity_step_client.get("/app/experiences/onboarding/add_contact")
        assert resp.status_code == 200
        # The form should have company_id prefilled with comp-123
        assert "comp-123" in resp.text

    @patch("dazzle_ui.runtime.experience_routes._proxy_to_backend", new_callable=AsyncMock)
    def test_validation_failure_stays_on_step(
        self, mock_proxy: AsyncMock, entity_step_client: TestClient
    ) -> None:
        """Backend rejection returns error, no state change."""
        mock_proxy.return_value = (False, {"detail": "Name is required"})

        state = ExperienceState(step="add_company")
        cname = cookie_name("onboarding")
        entity_step_client.cookies.set(cname, sign_state(state))

        resp = entity_step_client.post(
            "/app/experiences/onboarding/add_company?event=success",
            json={},
        )
        # Non-HTMX: should redirect back to same step
        assert resp.status_code == 302
        assert "add_company" in resp.headers["location"]

    def test_entity_step_renders(self, entity_step_client: TestClient) -> None:
        """GET to entity_ref step renders a form."""
        resp = entity_step_client.get("/app/experiences/onboarding/add_company")
        assert resp.status_code == 200
        assert "Client Onboarding" in resp.text


class TestExistingSurfaceStepsUnchanged:
    """Verify that existing surface-based steps still work through routes."""

    @pytest.fixture()
    def surface_app(self) -> FastAPI:
        entity = _make_entity("Client")
        surfaces = [
            SurfaceSpec(name="client_form", entity_ref="Client", mode=SurfaceMode.CREATE),
            SurfaceSpec(name="client_view", entity_ref="Client", mode=SurfaceMode.VIEW),
        ]
        experience = ExperienceSpec(
            name="onboarding",
            title="Client Onboarding",
            start_step="enter_details",
            steps=[
                ExperienceStep(
                    name="enter_details",
                    kind=StepKind.SURFACE,
                    surface="client_form",
                    transitions=[StepTransition(event="success", next_step="done")],
                ),
                ExperienceStep(
                    name="done",
                    kind=StepKind.SURFACE,
                    surface="client_view",
                    transitions=[],
                ),
            ],
        )
        appspec = AppSpec(
            name="test_app",
            title="Test App",
            domain=DomainSpec(entities=[entity]),
            surfaces=surfaces,
            experiences=[experience],
        )
        app = FastAPI()
        router = create_experience_routes(appspec, app_prefix="/app")
        app.include_router(router, prefix="/app")
        return app

    @pytest.fixture()
    def surface_client(self, surface_app: FastAPI) -> TestClient:
        return TestClient(surface_app, follow_redirects=False)

    @patch("dazzle_ui.runtime.experience_routes._proxy_to_backend", new_callable=AsyncMock)
    def test_surface_step_creates_entity(
        self, mock_proxy: AsyncMock, surface_client: TestClient
    ) -> None:
        mock_proxy.return_value = (True, {"id": "new-id-123"})

        state = ExperienceState(step="enter_details")
        cname = cookie_name("onboarding")
        surface_client.cookies.set(cname, sign_state(state))

        resp = surface_client.post(
            "/app/experiences/onboarding/enter_details?event=success",
            json={"name": "Test Client"},
        )
        assert resp.status_code == 302
        assert resp.headers["location"] == "/app/experiences/onboarding/done"
