"""HYPERPART: confirm — hx-confirm interceptor (no server root; trigger attrs).

Any element with hx-confirm is in-contract; opt-out is data-dz-native-confirm.
"""

from __future__ import annotations

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="confirm",
    root="[hx-confirm]",
    nodes=(Node("[hx-confirm]", attrs={"hx-confirm": Present()}),),
)

__all__ = ["DOM_CONTRACT"]
