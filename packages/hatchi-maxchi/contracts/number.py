"""HYPERPART: field (extension: dz-number) — standalone number group.

Leftover honesty (cycle 2149): the companion is an editable text
input (no ``name`` — the native ``type=number`` is the submitted
value). Typed leftover junk (``12abc``, ``zzz``, ``1e2``) must not
invent a number — the native stays put and both controls fail custom
validity so submit cannot post the previous number as if the leftover
were accepted. Empty companion on blur restores from the native.
Out-of-[min,max] is invalid (do not invent by clamping).
"""

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="number",
    root="[data-dz-number-group]",
    nodes=(
        Node("[data-dz-number-group]", attrs={"data-dz-number-group": Present()}),
        Node("[data-dz-number-value]", attrs={"data-dz-number-value": Present()}),
    ),
)

__all__ = ["DOM_CONTRACT"]
