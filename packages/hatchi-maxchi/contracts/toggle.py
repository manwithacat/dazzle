"""HYPERPART: toggle — pressable mode control (toolbar style).

Dual-lock unit is the toggle button root. Label content and size modifiers
are host-owned. Selector ``[data-dz-toggle]`` is the stable substrate root
(gallery CSS; state is ``aria-pressed``).

Emitter: ``widget=toggle`` → ToggleField / free Toggle fragment
(``button.dz-toggle[data-dz-toggle]`` + aria-pressed; ``dz-toggle.js``).
Form hosts may wrap a named hidden carrier in ``[data-dz-field-widget=toggle]``;
the controller syncs that carrier to ``aria-pressed`` on click.
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
