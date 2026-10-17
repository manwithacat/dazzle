"""HYPERPART: badge — status chip (tone/variant + optional icon).

Dual-lock unit is the chip root. Icon markup and tone attrs are host-owned;
every path — gallery, status cells, the Dazzle ``Badge`` primitive (#1799) —
tones it with ``data-dz-tone``. Class ``.dz-badge`` is the stable cross-path
selector.
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="badge",
    root=".dz-badge",
    nodes=(Node(".dz-badge", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
