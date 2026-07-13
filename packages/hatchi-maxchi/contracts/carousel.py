"""HYPERPART: carousel — slide strip with prev/next/dots (DOM-local state).

See docs/decisions/0009-carousel-stage-and-motion.md for wrap / autoplay / stage.
"""

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="carousel",
    root="[data-dz-carousel]",
    nodes=(
        Node("[data-dz-carousel]", attrs={}),
        Node("[data-dz-carousel-index]", attrs={"data-dz-carousel-index": Present()}),
        Node("[data-dz-carousel-prev]", attrs={}),
        Node("[data-dz-carousel-next]", attrs={}),
        Node("[data-dz-active]", attrs={}),
        # Optional chrome / policy (present when authored)
        Node("[data-dz-carousel-wrap]", attrs={"data-dz-carousel-wrap": Present()}),
        Node("[data-dz-carousel-interval]", attrs={"data-dz-carousel-interval": Present()}),
        Node("[data-dz-carousel-status]", attrs={}),
    ),
)

__all__ = ["DOM_CONTRACT"]
