"""HYPERPART: slider — native range group + editable value companion.

Leftover honesty (cycle 2134): the readout is an editable text input
(no ``name`` — the native ``type=range`` is the submitted value).
Typed leftover junk (``70abc``, ``zzz``) must not invent a range
position — the range stays put and both controls fail custom validity
so submit cannot post the previous value as if the leftover were
accepted. Empty companion on blur restores from the range.
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="slider",
    root="[data-dz-slider]",
    nodes=(
        Node("[data-dz-slider]", attrs={}),
        Node("[data-dz-range-value]", attrs={}),
    ),
)

__all__ = ["DOM_CONTRACT"]
