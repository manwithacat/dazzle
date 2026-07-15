"""HYPERPART: controls — selection controls (checkbox / radio / switch).

Dual-lock unit is the designed native-input family. Label chrome is host-owned.
Classes ``.dz-checkbox``, ``.dz-radio``, and ``.dz-switch`` are the stable
substrate roots (gallery partial; no FragmentRenderer emit yet). Switch also
has a dedicated contracts/switch.py for data-dz-switch progressive enhancement.
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="controls",
    root=".dz-checkbox, .dz-radio, .dz-switch",
    nodes=(Node(".dz-checkbox, .dz-radio, .dz-switch", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
