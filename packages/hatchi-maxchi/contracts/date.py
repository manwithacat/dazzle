"""HYPERPART: field (extension: dz-date) — standalone date group.

Leftover honesty (cycle 2145): the ISO companion is an editable text
input (no ``name`` — the native ``type=date`` is the submitted value).
Typed leftover junk (``2026-06-01zzz``, ``zzz``, ``June 1``) must not
invent a date — the native stays put and both controls fail custom
validity so submit cannot post the previous date as if the leftover
were accepted. Empty ISO on blur restores from the native.
"""

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="date",
    root="[data-dz-date-group]",
    nodes=(
        Node("[data-dz-date-group]", attrs={"data-dz-date-group": Present()}),
        Node("[data-dz-date-iso]", attrs={"data-dz-date-iso": Present()}),
    ),
)

__all__ = ["DOM_CONTRACT"]
