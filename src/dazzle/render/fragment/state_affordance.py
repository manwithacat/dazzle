"""#1558 (3c → L4): the single builder and gating rule for state-machine
transition affordances — what each control says and asks (#1813), and which
transitions are valid from a record's current state. Shared by the detail
view, the list-row render and the queue. Pure, no I/O."""

from typing import Any

from dazzle.core.ir.state_machine import transition_action_label
from dazzle.render.context import TransitionContext


def transition_affordances(state_machine: Any, api_url: str) -> tuple[TransitionContext, ...]:
    """#1813: the ONE builder of transition controls — list rows, detail and
    queue all read it, so an authored label / confirm reaches every control.

    ``state_machine`` is the IR ``StateMachineSpec`` or its runtime twin; empty
    when there is none. One affordance per distinct ``(from_state, to_state)``
    edge (two edges into one target from different sources are distinct), with
    ``from_state`` kept for current-state gating (:func:`gated_row_transitions`).
    The label is the authored one or ``Set to <State>``; ``confirm`` is the
    authored question or ``""``.
    """
    if not state_machine:
        return ()
    seen: set[tuple[str, str]] = set()
    out: list[TransitionContext] = []
    for t in state_machine.transitions:
        key = (t.from_state, t.to_state)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            TransitionContext(
                from_state=t.from_state,
                to_state=t.to_state,
                label=t.label or transition_action_label(t.to_state),
                confirm=t.confirm or "",
                api_url=api_url,
            )
        )
    return tuple(out)


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
