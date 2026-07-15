"""HYPERPART: drawer — edge-anchored panel (native dialog or aside).

Dual-lock unit is the drawer surface root. Gallery demos use
``<dialog class="dz-drawer">`` opened via ``data-dz-dialog-open``; the
substrate ``Drawer`` primitive emits ``<aside class="dz-drawer …">``.
Slide-over peek also uses ``dialog.dz-drawer``. Class ``.dz-drawer`` is the
stable cross-path selector.
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="drawer",
    root=".dz-drawer",
    nodes=(Node(".dz-drawer", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
