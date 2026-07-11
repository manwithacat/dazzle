"""HYPERPART: wizard — multi-stage form with data-dz-step state."""

from contracts._kit import DomContract, Node, OneOf, Present

DOM_CONTRACT = DomContract(
    part="wizard",
    root="[data-dz-wizard]",
    nodes=(
        Node("[data-dz-wizard]", attrs={"data-dz-step": Present()}),
        Node("[data-dz-stage]", attrs={"data-dz-stage": Present()}),
        Node(
            "[data-dz-state]",
            attrs={"data-dz-state": OneOf("complete", "current", "pending")},
        ),
    ),
)

__all__ = ["DOM_CONTRACT"]
