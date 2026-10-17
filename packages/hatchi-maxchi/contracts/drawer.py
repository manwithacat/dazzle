"""HYPERPART: drawer — edge-anchored panel (native dialog).

Dual-lock unit is the drawer surface root: ``<dialog class="dz-drawer">``
opened via ``data-dz-dialog-open``, edge by ``data-dz-side``. The gallery,
the slide-over peek and the substrate ``Drawer`` primitive (#1799) all emit
this shape. Class ``.dz-drawer`` is the stable cross-path selector.
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="drawer",
    root=".dz-drawer",
    nodes=(Node(".dz-drawer", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
