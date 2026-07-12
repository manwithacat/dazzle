"""HYPERPART: popover — details free-content panel (light-dismiss enhanced).

Optional instance attrs (controller reads; not required by DomContract):
  data-dz-dismiss, data-dz-dismiss-ms — see stems/overlay-light-dismiss.md
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="popover",
    root="details.dz-popover, .dz-popover",
    nodes=(Node("details.dz-popover, .dz-popover", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
