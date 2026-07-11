"""HYPERPART: grid — root contract (thin). The base grid's structural
root attributes; the data-bearing seams live in extension contracts
(grid_edit). Root-only: no ingestion model, no exemplars."""

from contracts._kit import DomContract

DOM_CONTRACT = DomContract(
    part="grid",
    root="[data-dz-grid]",
    nodes=(),
)

__all__ = ["DOM_CONTRACT"]
