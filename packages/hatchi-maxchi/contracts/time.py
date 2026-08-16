"""HYPERPART: field (extension: dz-time) — time / datetime-local group.

Leftover honesty (cycle 2144): the ISO companion is an editable text
input (no ``name`` — the native ``type=time`` / ``datetime-local`` is
the submitted value). Typed leftover junk (``14:30zzz``, ``2pm``,
``2026-06-01T14:30zzz``) must not invent a clock — the native stays
put and both controls fail custom validity so submit cannot post the
previous time as if the leftover were accepted. Empty ISO on blur
restores from the native.
"""

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="time",
    root="[data-dz-time-group]",
    nodes=(
        Node("[data-dz-time-group]", attrs={"data-dz-time-group": Present()}),
        Node("[data-dz-time-iso]", attrs={"data-dz-time-iso": Present()}),
    ),
)

__all__ = ["DOM_CONTRACT"]
