"""HYPERPART: badge — status chip (tone/variant + optional icon).

Dual-lock unit is the chip root. Icon markup and tone attrs are host-owned;
gallery uses ``data-dz-tone``; Dazzle ``Badge`` primitive uses variant BEM
modifiers. Class ``.dz-badge`` is the stable cross-path selector.
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="badge",
    root=".dz-badge",
    nodes=(Node(".dz-badge", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
