"""HYPERPART: code — fenced code surface (root + optional copy control)."""

from __future__ import annotations

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="code",
    root="[data-dz-code]",
    nodes=(
        Node("[data-dz-code]", attrs={"data-dz-code": Present()}),
        # Copy is optional chrome; when present the attr marks the control.
        Node("[data-dz-code-copy]", attrs={"data-dz-code-copy": Present()}),
    ),
)

__all__ = ["DOM_CONTRACT"]
