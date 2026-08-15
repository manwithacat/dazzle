"""HYPERPART: field (extension: dz-color) — colour input group.

Leftover honesty (cycle 2133): the hex companion is an editable text
input (no ``name`` — the native ``type=color`` swatch is the submitted
value). Typed leftover junk (``#3b82f6zzz``, ``red``, ``rgb(…)``) must
not invent a colour — the swatch stays put and both controls fail
custom validity so submit cannot post the previous swatch as if the
leftover were accepted. Empty hex on blur restores from the swatch.
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="color",
    root="[data-dz-color-group]",
    nodes=(Node("[data-dz-color-group]", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
