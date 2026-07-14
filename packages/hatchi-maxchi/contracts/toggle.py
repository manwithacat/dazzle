"""HYPERPART: toggle — pressable mode control (toolbar style).

Dual-lock unit is the toggle button root. Label content and size modifiers
are host-owned. Selector ``[data-dz-toggle]`` is the stable substrate root
(gallery CSS; state is ``aria-pressed``). No FragmentRenderer emit yet.
"""

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="toggle",
    root="[data-dz-toggle]",
    nodes=(
        Node(
            "[data-dz-toggle]",
            attrs={"data-dz-toggle": Present()},
        ),
    ),
)

__all__ = ["DOM_CONTRACT"]
