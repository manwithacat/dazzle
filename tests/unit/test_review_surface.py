"""Tests for review surface mode (mode: review)."""

from __future__ import annotations

from dazzle.core.ir import (
    AppSpec,
    DomainSpec,
    EntitySpec,
    FieldSpec,
    FieldType,
    SurfaceSpec,
)
from dazzle.core.ir.state_machine import StateMachineSpec, StateTransition
from dazzle.core.ir.surfaces import SurfaceMode
from dazzle_ui.converters.template_compiler import (
    compile_appspec_to_templates,
    compile_surface_to_context,
)


def _make_entity_with_states() -> EntitySpec:
    """Entity with a state machine for review workflows."""
    return EntitySpec(
        name="VATReturn",
        title="VAT Return",
        fields=[
            FieldSpec(name="id", type=FieldType(kind="uuid"), is_primary_key=True),
            FieldSpec(name="company", type=FieldType(kind="str"), is_required=True),
            FieldSpec(name="period_key", type=FieldType(kind="str")),
            FieldSpec(name="due_date", type=FieldType(kind="date")),
            FieldSpec(
                name="status",
                type=FieldType(kind="enum", enum_values=["draft", "prepared", "reviewed"]),
            ),
            FieldSpec(name="review_notes", type=FieldType(kind="str")),
        ],
        state_machine=StateMachineSpec(
            status_field="status",
            states=["draft", "prepared", "reviewed"],
            transitions=[
                StateTransition(from_state="draft", to_state="prepared"),
                StateTransition(from_state="prepared", to_state="reviewed"),
                StateTransition(from_state="prepared", to_state="draft"),
            ],
        ),
    )


def _make_review_surface() -> SurfaceSpec:
    """Review surface for VAT returns."""
    return SurfaceSpec(
        name="vat_return_review",
        title="VAT Return Review",
        entity_ref="VATReturn",
        mode=SurfaceMode.REVIEW,
    )


class TestReviewSurfaceMode:
    def test_review_mode_enum_exists(self) -> None:
        assert SurfaceMode.REVIEW == "review"

    def test_review_mode_parses(self) -> None:
        mode = SurfaceMode("review")
        assert mode == SurfaceMode.REVIEW


class TestCompileReviewSurface:
    def test_compiles_to_review_context(self) -> None:
        entity = _make_entity_with_states()
        surface = _make_review_surface()
        ctx = compile_surface_to_context(surface, entity)

        assert ctx.review is not None
        assert ctx.detail is None
        assert ctx.table is None
        assert ctx.form is None

    def test_review_template(self) -> None:
        entity = _make_entity_with_states()
        surface = _make_review_surface()
        ctx = compile_surface_to_context(surface, entity)

        assert ctx.template == "components/review_queue.html"

    def test_review_title(self) -> None:
        entity = _make_entity_with_states()
        surface = _make_review_surface()
        ctx = compile_surface_to_context(surface, entity)

        assert ctx.review is not None
        assert ctx.review.title == "VAT Return Review"

    def test_review_entity_name(self) -> None:
        entity = _make_entity_with_states()
        surface = _make_review_surface()
        ctx = compile_surface_to_context(surface, entity)

        assert ctx.review is not None
        assert ctx.review.entity_name == "VATReturn"

    def test_review_fields_populated(self) -> None:
        entity = _make_entity_with_states()
        surface = _make_review_surface()
        ctx = compile_surface_to_context(surface, entity)

        assert ctx.review is not None
        field_names = [f.name for f in ctx.review.fields]
        assert "company" in field_names
        assert "period_key" in field_names
        assert "due_date" in field_names

    def test_review_api_endpoint(self) -> None:
        entity = _make_entity_with_states()
        surface = _make_review_surface()
        ctx = compile_surface_to_context(surface, entity)

        assert ctx.review is not None
        assert ctx.review.api_endpoint == "/vatreturns"


class TestReviewActions:
    def test_actions_from_state_machine(self) -> None:
        entity = _make_entity_with_states()
        surface = _make_review_surface()
        ctx = compile_surface_to_context(surface, entity)

        assert ctx.review is not None
        assert len(ctx.review.actions) > 0

    def test_approve_action_style(self) -> None:
        entity = _make_entity_with_states()
        surface = _make_review_surface()
        ctx = compile_surface_to_context(surface, entity)

        assert ctx.review is not None
        reviewed_action = next((a for a in ctx.review.actions if a.to_state == "reviewed"), None)
        assert reviewed_action is not None
        assert reviewed_action.style == "primary"
        assert reviewed_action.label == "Approve"

    def test_return_action_style(self) -> None:
        entity = _make_entity_with_states()
        surface = _make_review_surface()
        ctx = compile_surface_to_context(surface, entity)

        assert ctx.review is not None
        draft_action = next((a for a in ctx.review.actions if a.to_state == "draft"), None)
        assert draft_action is not None
        assert draft_action.style == "error"
        assert draft_action.label == "Return"
        assert draft_action.require_notes is True

    def test_transition_url_has_id_template(self) -> None:
        entity = _make_entity_with_states()
        surface = _make_review_surface()
        ctx = compile_surface_to_context(surface, entity)

        assert ctx.review is not None
        for action in ctx.review.actions:
            assert "{id}" in action.transition_url

    def test_status_field_from_state_machine(self) -> None:
        entity = _make_entity_with_states()
        surface = _make_review_surface()
        ctx = compile_surface_to_context(surface, entity)

        assert ctx.review is not None
        assert ctx.review.status_field == "status"


class TestReviewRouteMap:
    def test_review_route_pattern(self) -> None:
        entity = _make_entity_with_states()
        surface = _make_review_surface()
        appspec = AppSpec(
            name="test_app",
            domain=DomainSpec(entities=[entity]),
            surfaces=[surface],
        )
        contexts = compile_appspec_to_templates(appspec, app_prefix="/app")

        # Review route should be /app/{entity_slug}/review/{id}
        assert "/app/vatreturn/review/{id}" in contexts

    def test_review_context_in_route_map(self) -> None:
        entity = _make_entity_with_states()
        surface = _make_review_surface()
        appspec = AppSpec(
            name="test_app",
            domain=DomainSpec(entities=[entity]),
            surfaces=[surface],
        )
        contexts = compile_appspec_to_templates(appspec, app_prefix="/app")
        ctx = contexts.get("/app/vatreturn/review/{id}")

        assert ctx is not None
        assert ctx.review is not None
        assert ctx.review.entity_name == "VATReturn"


class TestReviewQueueNavigation:
    def test_default_queue_values(self) -> None:
        entity = _make_entity_with_states()
        surface = _make_review_surface()
        ctx = compile_surface_to_context(surface, entity)

        assert ctx.review is not None
        assert ctx.review.queue_position == 0
        assert ctx.review.queue_total == 0
        assert ctx.review.next_url is None
        assert ctx.review.prev_url is None

    def test_queue_url_set(self) -> None:
        entity = _make_entity_with_states()
        surface = _make_review_surface()
        ctx = compile_surface_to_context(surface, entity, app_prefix="/app")

        assert ctx.review is not None
        assert ctx.review.queue_url == "/app/vatreturn/review"

    def test_back_url_points_to_list(self) -> None:
        entity = _make_entity_with_states()
        surface = _make_review_surface()
        ctx = compile_surface_to_context(surface, entity, app_prefix="/app")

        assert ctx.review is not None
        assert ctx.review.back_url == "/app/vatreturn"


class TestReviewWithoutStateMachine:
    def test_no_actions_without_state_machine(self) -> None:
        """Review surface without state machine should have no actions."""
        entity = EntitySpec(
            name="Document",
            fields=[
                FieldSpec(name="id", type=FieldType(kind="uuid"), is_primary_key=True),
                FieldSpec(name="title", type=FieldType(kind="str")),
            ],
        )
        surface = SurfaceSpec(
            name="doc_review",
            title="Document Review",
            entity_ref="Document",
            mode=SurfaceMode.REVIEW,
        )
        ctx = compile_surface_to_context(surface, entity)

        assert ctx.review is not None
        assert len(ctx.review.actions) == 0
