"""HYPERPART: switch — on/off control over a native checkbox.

Dual-lock unit is the switch input root. Label chrome and track styling are
host-owned. Selector ``[data-dz-switch]`` is the stable substrate root
(gallery CSS progressive enhancement; no FragmentRenderer emit yet).
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
