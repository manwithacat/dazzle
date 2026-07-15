"""HYPERPART: toolbar — action bar composition host.

Dual-lock unit is the bar root. Nested buttons/menus/toggles are host-owned
composition. Gallery uses ``role="toolbar"``; substrate ``Toolbar`` emits
``aria-label`` from the label field. Class ``.dz-toolbar`` is the stable root.
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="toolbar",
    root=".dz-toolbar",
    nodes=(Node(".dz-toolbar", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
