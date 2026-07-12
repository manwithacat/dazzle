"""HYPERPART: menu — details disclosure root (light-dismiss enhanced).

Optional instance attrs (controller reads; not required by DomContract):
  data-dz-dismiss, data-dz-dismiss-ms — see stems/overlay-light-dismiss.md
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="menu",
    root="details.dz-menu, .dz-menu",
    nodes=(Node("details.dz-menu, .dz-menu", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
