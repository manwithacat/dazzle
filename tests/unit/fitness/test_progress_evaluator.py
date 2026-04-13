from dazzle.core.ir.lifecycle import (
    LifecycleSpec,
    LifecycleStateSpec,
    LifecycleTransitionSpec,
)
from dazzle.fitness.models import FitnessDiff, RowChange
from dazzle.fitness.progress_evaluator import evaluate_progress


def _lifecycle() -> LifecycleSpec:
    return LifecycleSpec(
        status_field="status",
        states=[
            LifecycleStateSpec(name="new", order=0),
            LifecycleStateSpec(name="in_progress", order=1),
            LifecycleStateSpec(name="resolved", order=2),
        ],
        transitions=[
            LifecycleTransitionSpec(from_state="new", to_state="in_progress", evidence="true"),
            LifecycleTransitionSpec(
                from_state="in_progress",
                to_state="resolved",
                evidence="resolution_notes != null",
            ),
        ],
    )


def test_valid_transition_counts_as_progress() -> None:
    row_changes = [
        RowChange(
            table="ticket",
            row_id="t1",
            kind="update",
            semantic_repr="",
            field_deltas={"status": ("new", "in_progress")},
        )
    ]
    diff = FitnessDiff(
        run_id="r",
        steps=[],
        created=[],
        updated=row_changes,
        deleted=[],
        progress=[],
        semantic_repr_config={},
    )
    entity_state = {"t1": {"status": "in_progress", "resolution_notes": None}}
    records = evaluate_progress(_lifecycle(), diff, entity_state=entity_state, entity_name="Ticket")
    assert len(records) == 1
    assert records[0].was_progress is True


def test_unsatisfied_evidence_is_not_progress() -> None:
    row_changes = [
        RowChange(
            table="ticket",
            row_id="t2",
            kind="update",
            semantic_repr="",
            field_deltas={"status": ("in_progress", "resolved")},
        )
    ]
    diff = FitnessDiff(
        run_id="r",
        steps=[],
        created=[],
        updated=row_changes,
        deleted=[],
        progress=[],
        semantic_repr_config={},
    )
    entity_state = {"t2": {"status": "resolved", "resolution_notes": None}}
    records = evaluate_progress(_lifecycle(), diff, entity_state=entity_state, entity_name="Ticket")
    assert records[0].was_progress is False


def test_backward_transition_is_not_progress() -> None:
    row_changes = [
        RowChange(
            table="ticket",
            row_id="t3",
            kind="update",
            semantic_repr="",
            field_deltas={"status": ("in_progress", "new")},
        )
    ]
    diff = FitnessDiff(
        run_id="r",
        steps=[],
        created=[],
        updated=row_changes,
        deleted=[],
        progress=[],
        semantic_repr_config={},
    )
    entity_state = {"t3": {"status": "new", "resolution_notes": None}}
    records = evaluate_progress(_lifecycle(), diff, entity_state=entity_state, entity_name="Ticket")
    assert records[0].was_progress is False
