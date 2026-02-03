"""Tests for process coverage matching logic."""

from __future__ import annotations

from dazzle.core.ir.process import (
    CompensationSpec,
    ProcessOutputField,
    ProcessSpec,
    ProcessStepSpec,
    ProcessTriggerKind,
    ProcessTriggerSpec,
    SatisfiesRef,
    StepKind,
)
from dazzle.mcp.server.handlers.process import (
    _collect_process_match_pool,
    _find_missing_aspects,
    _find_missing_aspects_from_index,
    _infer_structural_satisfaction,
    _outcome_matches_pool,
)


def _make_process(
    name: str = "test_proc",
    steps: list[ProcessStepSpec] | None = None,
    outputs: list[ProcessOutputField] | None = None,
    trigger: ProcessTriggerSpec | None = None,
    compensations: list[CompensationSpec] | None = None,
    implements: list[str] | None = None,
) -> ProcessSpec:
    return ProcessSpec(
        name=name,
        title=name,
        implements=implements or [],
        steps=steps or [],
        outputs=outputs or [],
        trigger=trigger,
        compensations=compensations or [],
    )


def _make_step(
    name: str,
    kind: StepKind = StepKind.SERVICE,
    service: str | None = None,
    satisfies: list[SatisfiesRef] | None = None,
) -> ProcessStepSpec:
    return ProcessStepSpec(
        name=name,
        kind=kind,
        service=service,
        satisfies=satisfies or [],
    )


class TestCollectMatchPool:
    def test_includes_step_names(self) -> None:
        proc = _make_process(
            steps=[_make_step("validate_order"), _make_step("send_confirmation")],
        )
        pool, _, _ = _collect_process_match_pool([proc], [proc.name])
        assert "validate_order" in pool
        assert "send_confirmation" in pool

    def test_includes_service_bindings(self) -> None:
        proc = _make_process(
            steps=[_make_step("charge", service="Payment.charge")],
        )
        pool, _, _ = _collect_process_match_pool([proc], [proc.name])
        assert "payment.charge" in pool

    def test_includes_output_names_and_descriptions(self) -> None:
        proc = _make_process(
            outputs=[
                ProcessOutputField(
                    name="invoice_url",
                    description="URL of the generated invoice PDF",
                )
            ],
        )
        pool, _, _ = _collect_process_match_pool([proc], [proc.name])
        assert "invoice_url" in pool
        assert "url of the generated invoice pdf" in pool

    def test_includes_compensation_names(self) -> None:
        proc = _make_process(
            compensations=[CompensationSpec(name="refund_payment")],
        )
        pool, _, _ = _collect_process_match_pool([proc], [proc.name])
        assert "refund_payment" in pool

    def test_collects_satisfies_refs(self) -> None:
        proc = _make_process(
            steps=[
                _make_step(
                    "save_record",
                    satisfies=[SatisfiesRef(story="ST-001", outcome="the task is saved")],
                )
            ],
        )
        _, satisfies, _ = _collect_process_match_pool([proc], [proc.name])
        assert "the task is saved" in satisfies


class TestOutcomeMatchesPool:
    def test_explicit_satisfies_match(self) -> None:
        assert _outcome_matches_pool(
            "the task is saved",
            match_pool=[],
            satisfies_outcomes={"the task is saved"},
            impl_procs=[],
        )

    def test_word_overlap_match(self) -> None:
        assert _outcome_matches_pool(
            "the order is validated",
            match_pool=["validate_order"],
            satisfies_outcomes=set(),
            impl_procs=[],
        )

    def test_no_match(self) -> None:
        assert not _outcome_matches_pool(
            "an email is sent to the manager",
            match_pool=["validate_order"],
            satisfies_outcomes=set(),
            impl_procs=[],
        )


class TestStructuralInference:
    def test_crud_create_inference(self) -> None:
        proc = _make_process(
            steps=[_make_step("save", service="Task.create")],
        )
        assert _infer_structural_satisfaction("the task is created", [proc])

    def test_crud_delete_inference(self) -> None:
        proc = _make_process(
            steps=[_make_step("remove", service="Task.delete")],
        )
        assert _infer_structural_satisfaction("the task is deleted", [proc])

    def test_status_transition_inference(self) -> None:
        proc = _make_process(
            trigger=ProcessTriggerSpec(
                kind=ProcessTriggerKind.ENTITY_STATUS_TRANSITION,
                entity_name="Order",
                from_status="pending",
                to_status="confirmed",
            ),
        )
        assert _infer_structural_satisfaction("the order status is changed", [proc])
        assert _infer_structural_satisfaction("a timestamp is recorded", [proc])

    def test_no_inference_for_unrelated(self) -> None:
        proc = _make_process(
            steps=[_make_step("save", service="Task.create")],
        )
        assert not _infer_structural_satisfaction("an email is sent", [proc])


class TestFindMissingAspects:
    """Integration tests using mock StorySpec-like objects."""

    def test_fully_covered_via_satisfies(self) -> None:
        """A process with explicit satisfies should cover the outcome."""

        class FakeCondition:
            expression = "the invoice is generated"

        class FakeStory:
            story_id = "ST-001"
            title = "Generate Invoice"
            then = [FakeCondition()]
            happy_path_outcome: list[str] = []
            unless: list[object] = []

        proc = _make_process(
            name="invoice_proc",
            implements=["ST-001"],
            steps=[
                _make_step(
                    "generate",
                    satisfies=[SatisfiesRef(story="ST-001", outcome="the invoice is generated")],
                ),
            ],
        )

        missing = _find_missing_aspects(FakeStory(), [proc], ["invoice_proc"])
        assert missing == []

    def test_partially_covered(self) -> None:
        class FakeCond1:
            expression = "the order is validated"

        class FakeCond2:
            expression = "a notification email is sent to the admin"

        class FakeStory:
            story_id = "ST-002"
            title = "Process Order"
            then = [FakeCond1(), FakeCond2()]
            happy_path_outcome: list[str] = []
            unless: list[object] = []

        proc = _make_process(
            name="order_proc",
            implements=["ST-002"],
            steps=[_make_step("validate_order")],
        )

        missing = _find_missing_aspects(FakeStory(), [proc], ["order_proc"])
        assert len(missing) == 1
        assert "notification email" in missing[0]


class TestFindMissingAspectsFromIndex:
    def test_covered_via_output_description(self) -> None:
        story_dict = {
            "story_id": "ST-010",
            "title": "Generate Report",
            "then": [{"expression": "a PDF report is generated"}],
            "unless": [],
        }
        proc = _make_process(
            name="report_proc",
            implements=["ST-010"],
            outputs=[ProcessOutputField(name="report_pdf", description="The generated PDF report")],
        )

        missing = _find_missing_aspects_from_index(story_dict, [proc], ["report_proc"])
        assert missing == []
