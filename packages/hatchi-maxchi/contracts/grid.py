"""HYPERPART: grid — root contract (thin). The base grid's structural
root attributes; the data-bearing seams live in extension contracts
(grid_edit). Root-only: no ingestion model, no exemplars.

Leftover honesty (cycle 2157): URL ``?page=2abc`` / ``?page_size=2abc``
must not invent a window. ``parseInt("2abc", 10) === 2`` is leftover
junk — same class as PDF leftover page (2151). Empty / invalid
restores the server default. Valid whole numbers still window.
Rest-state gallery is unchanged (oral #33).
"""

from contracts._kit import DomContract

DOM_CONTRACT = DomContract(
    part="grid",
    root="[data-dz-grid]",
    nodes=(),
)

__all__ = ["DOM_CONTRACT"]
