"""HYPERPART: layout-grid — N-column layout grid (substrate Grid primitive).

Distinct from the data table grid (``[data-dz-grid]`` / contracts/grid.py).
Dual-lock unit is the layout root. Column count rides BEM modifiers
(``dz-grid--columns-N``). Class ``.dz-grid`` is the stable substrate root
(``_emit_grid``).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="layout-grid",
    root=".dz-grid",
    nodes=(Node(".dz-grid", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
