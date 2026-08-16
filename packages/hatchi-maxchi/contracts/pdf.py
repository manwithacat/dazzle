"""HYPERPART: pdf — progressive PDF shell (access + lazy PDF.js).

Leftover honesty (cycle 2151): leftover page junk (``2abc``, ``zzz``,
out-of-range) must not invent a page jump. ``parseInt("2abc")`` is not
a committed page. Empty input on blur restores from the current page.
Rest-state toolbar markup is unchanged.
"""

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="pdf",
    root="[data-dz-pdf]",
    nodes=(
        Node(
            "[data-dz-pdf]",
            attrs={
                "data-dz-pdf-src": Present(),
                "data-dz-pdf-lib": Present(),
            },
        ),
        Node("[data-dz-pdf-viewer]", attrs={}),
    ),
)

__all__ = ["DOM_CONTRACT"]
