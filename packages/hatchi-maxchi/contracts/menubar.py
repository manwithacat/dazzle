"""HYPERPART: menubar — app chrome exclusive-open root contract."""

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="menubar",
    root="[data-dz-menubar]",
    nodes=(Node("[data-dz-menubar]", attrs={"data-dz-menubar": Present()}),),
)

__all__ = ["DOM_CONTRACT"]
