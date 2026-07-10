"""HYPERPART: confirm-panel — irreversible-action consent gate."""

from __future__ import annotations

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="confirm-panel",
    root="[data-dz-confirm-gate]",
    nodes=(
        Node(
            "[data-dz-confirm-gate]",
            attrs={"data-dz-required-count": Present()},
        ),
        Node('[data-dz-required="true"]', attrs={"data-dz-required": Present()}),
    ),
)

__all__ = ["DOM_CONTRACT"]
