"""HYPERPART: switch — on/off control over a native checkbox.

Dual-lock unit is the switch input root. Label chrome and track styling are
host-owned. Selector ``[data-dz-switch]`` is the stable substrate root.

Dazzle form path (2026-08-07): ``widget=switch`` → ``SwitchField`` →
``FragmentRenderer._emit_switch_field`` mounts this anatomy on create/edit forms.
"""

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="switch",
    root="[data-dz-switch]",
    nodes=(
        Node(
            "[data-dz-switch]",
            attrs={"data-dz-switch": Present()},
        ),
    ),
)

__all__ = ["DOM_CONTRACT"]
