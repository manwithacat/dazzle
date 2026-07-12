"""HYPERPART: navigation-menu — product nav exclusive-open root contract."""

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="navigation-menu",
    root="[data-dz-navigation-menu]",
    nodes=(
        Node(
            "[data-dz-navigation-menu]",
            attrs={"data-dz-navigation-menu": Present()},
        ),
    ),
)

__all__ = ["DOM_CONTRACT"]
