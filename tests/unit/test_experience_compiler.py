"""Tests for experience compiler — ExperienceSpec + state → ExperienceContext."""

from __future__ import annotations

from dazzle.core.ir import AppSpec, DomainSpec, EntitySpec, FieldSpec, FieldType, SurfaceSpec
from dazzle.core.ir.experiences import (
    ExperienceSpec,
    ExperienceStep,
    StepKind,
    StepTransition,
)
from dazzle.core.ir.surfaces import SurfaceMode
from dazzle_ui.converters.experience_compiler import compile_experience_context
from dazzle_ui.runtime.experience_state import ExperienceState


def _make_entity(name: str = "Client") -> EntitySpec:
    return EntitySpec(
        name=name,
        fields=[
            FieldSpec(name="id", type=FieldType(kind="uuid"), is_primary_key=True),
            FieldSpec(name="name", type=FieldType(kind="str"), is_required=True),
            FieldSpec(name="email", type=FieldType(kind="email")),
        ],
    )


def _make_surface(
    name: str = "client_form", entity_ref: str = "Client", mode: str = "create"
) -> SurfaceSpec:
    return SurfaceSpec(name=name, entity_ref=entity_ref, mode=SurfaceMode(mode))


def _make_experience(
    name: str = "onboarding",
    steps: list[ExperienceStep] | None = None,
) -> ExperienceSpec:
    if steps is None:
        steps = [
            ExperienceStep(
                name="enter_details",
                kind=StepKind.SURFACE,
                surface="client_form",
                transitions=[
                    StepTransition(event="success", next_step="review"),
                    StepTransition(event="cancel", next_step="enter_details"),
                ],
            ),
            ExperienceStep(
                name="review",
                kind=StepKind.SURFACE,
                surface="client_view",
                transitions=[
                    StepTransition(event="approve", next_step="done"),
                    StepTransition(event="back", next_step="enter_details"),
                ],
            ),
            ExperienceStep(
                name="done",
                kind=StepKind.SURFACE,
                surface="client_view",
                transitions=[],
            ),
        ]
    return ExperienceSpec(
        name=name,
        title="Client Onboarding",
        start_step="enter_details",
        steps=steps,
    )


def _make_appspec(
    experience: ExperienceSpec | None = None,
    surfaces: list[SurfaceSpec] | None = None,
    entities: list[EntitySpec] | None = None,
) -> AppSpec:
    if entities is None:
        entities = [_make_entity()]
    if surfaces is None:
        surfaces = [
            _make_surface("client_form", "Client", "create"),
            _make_surface("client_view", "Client", "view"),
        ]
    if experience is None:
        experience = _make_experience()
    return AppSpec(
        name="test_app",
        title="Test App",
        domain=DomainSpec(entities=entities),
        surfaces=surfaces,
        experiences=[experience],
    )


class TestCompileExperienceContext:
    def test_basic_compilation(self) -> None:
        experience = _make_experience()
        state = ExperienceState(step="enter_details")
        appspec = _make_appspec(experience)

        ctx = compile_experience_context(experience, state, appspec, "/app")

        assert ctx.name == "onboarding"
        assert ctx.title == "Client Onboarding"
        assert ctx.current_step == "enter_details"

    def test_step_progress_indicators(self) -> None:
        experience = _make_experience()
        state = ExperienceState(step="review", completed=["enter_details"])
        appspec = _make_appspec(experience)

        ctx = compile_experience_context(experience, state, appspec, "/app")

        assert len(ctx.steps) == 3
        assert ctx.steps[0].name == "enter_details"
        assert ctx.steps[0].is_completed is True
        assert ctx.steps[0].is_current is False
        assert ctx.steps[1].name == "review"
        assert ctx.steps[1].is_current is True
        assert ctx.steps[1].is_completed is False
        assert ctx.steps[2].name == "done"
        assert ctx.steps[2].is_current is False
        assert ctx.steps[2].is_completed is False

    def test_step_urls(self) -> None:
        experience = _make_experience()
        state = ExperienceState(step="enter_details")
        appspec = _make_appspec(experience)

        ctx = compile_experience_context(experience, state, appspec, "/app")

        for step_ctx in ctx.steps:
            assert step_ctx.url == f"/app/experiences/onboarding/{step_ctx.name}"


class TestTransitionButtons:
    def test_transition_generation(self) -> None:
        experience = _make_experience()
        state = ExperienceState(step="enter_details")
        appspec = _make_appspec(experience)

        ctx = compile_experience_context(experience, state, appspec, "/app")

        assert len(ctx.transitions) == 2
        assert ctx.transitions[0].event == "success"
        assert ctx.transitions[0].label == "Continue"
        assert ctx.transitions[0].style == "primary"
        assert ctx.transitions[1].event == "cancel"
        assert ctx.transitions[1].label == "Cancel"
        assert ctx.transitions[1].style == "ghost"

    def test_transition_urls(self) -> None:
        experience = _make_experience()
        state = ExperienceState(step="enter_details")
        appspec = _make_appspec(experience)

        ctx = compile_experience_context(experience, state, appspec, "/app")

        assert ctx.transitions[0].url == "/app/experiences/onboarding/enter_details?event=success"
        assert ctx.transitions[1].url == "/app/experiences/onboarding/enter_details?event=cancel"

    def test_known_event_styles(self) -> None:
        """Test that well-known events map to expected styles."""
        steps = [
            ExperienceStep(
                name="step_1",
                kind=StepKind.SURFACE,
                surface="client_form",
                transitions=[
                    StepTransition(event="approve", next_step="step_2"),
                    StepTransition(event="reject", next_step="step_1"),
                    StepTransition(event="skip", next_step="step_2"),
                ],
            ),
            ExperienceStep(name="step_2", kind=StepKind.SURFACE, surface="client_view"),
        ]
        experience = ExperienceSpec(name="test", start_step="step_1", steps=steps)
        state = ExperienceState(step="step_1")
        appspec = _make_appspec(experience)

        ctx = compile_experience_context(experience, state, appspec, "/app")

        styles = {t.event: t.style for t in ctx.transitions}
        assert styles["approve"] == "primary"
        assert styles["reject"] == "error"
        assert styles["skip"] == "ghost"

    def test_terminal_step_no_transitions(self) -> None:
        experience = _make_experience()
        state = ExperienceState(step="done", completed=["enter_details", "review"])
        appspec = _make_appspec(experience)

        ctx = compile_experience_context(experience, state, appspec, "/app")

        assert ctx.transitions == []


class TestPageContext:
    def test_form_step_has_page_context(self) -> None:
        experience = _make_experience()
        state = ExperienceState(step="enter_details")
        appspec = _make_appspec(experience)

        ctx = compile_experience_context(experience, state, appspec, "/app")

        assert ctx.page_context is not None
        assert ctx.page_context.form is not None
        assert ctx.page_context.form.entity_name == "Client"

    def test_form_action_rewritten(self) -> None:
        experience = _make_experience()
        state = ExperienceState(step="enter_details")
        appspec = _make_appspec(experience)

        ctx = compile_experience_context(experience, state, appspec, "/app")

        assert ctx.page_context is not None
        assert ctx.page_context.form is not None
        assert (
            ctx.page_context.form.action_url
            == "/app/experiences/onboarding/enter_details?event=success"
        )

    def test_cancel_url_set_when_cancel_transition_exists(self) -> None:
        experience = _make_experience()
        state = ExperienceState(step="enter_details")
        appspec = _make_appspec(experience)

        ctx = compile_experience_context(experience, state, appspec, "/app")

        assert ctx.page_context is not None
        assert ctx.page_context.form is not None
        assert "event=cancel" in ctx.page_context.form.cancel_url

    def test_process_step_no_page_context(self) -> None:
        steps = [
            ExperienceStep(
                name="verify",
                kind=StepKind.PROCESS,
                transitions=[StepTransition(event="success", next_step="done")],
            ),
            ExperienceStep(name="done", kind=StepKind.SURFACE, surface="client_view"),
        ]
        experience = ExperienceSpec(name="proc_test", start_step="verify", steps=steps)
        state = ExperienceState(step="verify")
        appspec = _make_appspec(experience)

        ctx = compile_experience_context(experience, state, appspec, "/app")

        assert ctx.page_context is None

    def test_missing_surface_no_page_context(self) -> None:
        steps = [
            ExperienceStep(
                name="step_1",
                kind=StepKind.SURFACE,
                surface="nonexistent_surface",
            ),
        ]
        experience = ExperienceSpec(name="missing", start_step="step_1", steps=steps)
        state = ExperienceState(step="step_1")
        appspec = _make_appspec(experience)

        ctx = compile_experience_context(experience, state, appspec, "/app")

        assert ctx.page_context is None
