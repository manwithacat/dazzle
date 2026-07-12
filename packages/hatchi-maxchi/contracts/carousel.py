"""HYPERPART: carousel — slide strip with prev/next/dots (DOM-local state)."""

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="carousel",
    root="[data-dz-carousel]",
    nodes=(
        Node("[data-dz-carousel]", attrs={}),
        # Optional index stamp on the root (controller keeps it in sync).
        Node("[data-dz-carousel-index]", attrs={"data-dz-carousel-index": Present()}),
        Node("[data-dz-carousel-prev]", attrs={}),
        Node("[data-dz-carousel-next]", attrs={}),
        # Active slide marker (also mirrored as data-active after prefix strip).
        Node("[data-dz-active]", attrs={}),
    ),
)

__all__ = ["DOM_CONTRACT"]
