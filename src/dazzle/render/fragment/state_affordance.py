"""#1558 (3c → L4): the single gating rule for state-machine transition
affordances — which transitions are valid from a record's current state.
Shared by the detail-view filter and the list-row render. Pure, no I/O."""

from dazzle.render.context import TransitionContext


def gated_row_transitions(
    transitions: list[TransitionContext], current_state: str
) -> list[TransitionContext]:
    """Transitions valid FROM ``current_state`` — ``from_state == current_state``
    or the ``"*"`` wildcard (mirrors ``StateMachineSpec.get_transitions_from``).
    An empty ``current_state`` yields no affordances."""
    if not current_state:
        return []
    return [t for t in transitions if t.from_state == current_state or t.from_state == "*"]
