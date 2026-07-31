"""#1626 R2 — runtime StateMachineSpec must expose terminal_states for HTMX poll-stop."""

from dazzle.http.specs.entity import StateMachineSpec, StateTransitionSpec


def test_runtime_sm_terminal_states_matches_ir_contract() -> None:
    sm = StateMachineSpec(
        status_field="status",
        states=["active", "acknowledged", "resolved"],
        transitions=[
            StateTransitionSpec(from_state="active", to_state="acknowledged"),
            StateTransitionSpec(from_state="acknowledged", to_state="resolved"),
        ],
    )
    assert sm.terminal_states() == {"resolved"}


def test_runtime_sm_self_loop_still_terminal() -> None:
    sm = StateMachineSpec(
        status_field="status",
        states=["done"],
        transitions=[StateTransitionSpec(from_state="done", to_state="done")],
    )
    assert sm.terminal_states() == {"done"}
