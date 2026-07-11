"""HYPERPART: app-shell — DOM contract for the sidebar shell controller."""

from contracts._kit import DomContract, Node, OneOf

DOM_CONTRACT = DomContract(
    part="app-shell",
    root="[data-dz-sidebar]",
    nodes=(
        Node("[data-dz-sidebar]", attrs={"data-dz-sidebar": OneOf("open", "closed")}),
        Node("[data-dz-sidebar-toggle]", attrs={}),
    ),
)

__all__ = ["DOM_CONTRACT"]
