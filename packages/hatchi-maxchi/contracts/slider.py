"""HYPERPART: slider — native range group + live value readout."""

from __future__ import annotations

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="slider",
    root="[data-dz-slider]",
    nodes=(
        Node("[data-dz-slider]", attrs={}),
        Node("[data-dz-range-value]", attrs={}),
    ),
)

__all__ = ["DOM_CONTRACT"]
