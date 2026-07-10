"""HYPERPART: pdf — progressive PDF shell (access + lazy PDF.js)."""

from __future__ import annotations

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="pdf",
    root="[data-dz-pdf]",
    nodes=(
        Node(
            "[data-dz-pdf]",
            attrs={
                "data-dz-pdf-src": Present(),
                "data-dz-pdf-lib": Present(),
            },
        ),
        Node("[data-dz-pdf-viewer]", attrs={}),
    ),
)

__all__ = ["DOM_CONTRACT"]
