"""HYPERPART: tooltip — CSS-only visual hint (data-dz-tooltip).

Dual-lock unit is the tooltip host. Hint text and host chrome are host-owned.
Selector ``[data-dz-tooltip]`` is the stable substrate root (zero-JS gallery
hint; not an accessible tooltip — non-critical content only; no
FragmentRenderer emit yet).
"""

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="tooltip",
    root="[data-dz-tooltip]",
    nodes=(
        Node(
            "[data-dz-tooltip]",
            attrs={"data-dz-tooltip": Present()},
        ),
    ),
)

__all__ = ["DOM_CONTRACT"]
