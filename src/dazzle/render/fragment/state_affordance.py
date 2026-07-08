"""#1558 (3c → L4): the single gating rule for state-machine transition
affordances — which transitions are valid from a record's current state.
Shared by the detail-view filter and the list-row render. Pure, no I/O."""

from dazzle.render.context import TransitionContext


def gated_row_transitions(
    transitions: list[TransitionContext], current_state: str
) -> list[TransitionContext]:
    """Transition affordances valid FROM ``current_state`` — ``from_state ==
    current_state`` or the ``"*"`` wildcard (mirrors
    ``StateMachineSpec.get_transitions_from``).

    Two negative-space rules keep this an honest affordance set (queue parity):
    - a transition into the CURRENT state is excluded (no no-op self-loop button);
    - the result is deduped by ``to_state`` (an explicit edge and a ``"*"``
      wildcard to the same target render as ONE button — first match wins).

    An empty ``current_state`` yields no affordances."""
    if not current_state:
        return []
    out: list[TransitionContext] = []
    seen_targets: set[str] = set()
    for t in transitions:
        if t.from_state != current_state and t.from_state != "*":
            continue
        if t.to_state == current_state:
            continue  # no self-loop affordance
        if t.to_state in seen_targets:
            continue  # dedup by target (explicit or wildcard — one button)
        seen_targets.add(t.to_state)
        out.append(t)
    return out
