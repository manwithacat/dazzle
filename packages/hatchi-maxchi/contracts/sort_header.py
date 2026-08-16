"""HYPERPART: sort-header — list column sort control link.

Dual-lock unit is the sort link root. Column key, endpoint, region target,
and active-direction indicator are host-owned. Class ``.dz-list-sort-link``
is the stable substrate root (``_emit_sort_header``).

Leftover honesty (cycle 2172): ``hx-get`` must echo leftover-honest
``include_closed`` / ``as_of``. ``?sort=&dir=`` only dropped them and
invented open-only / current after a sort click. Leftover junk
(``zzz``, ``2abc``, ``maybe``, ``not-a-date``) must not invent.
Valid ``true`` / YYYY-MM-DD still ride hx-get. Rest-state gallery
is unchanged (oral #33). Not leftover list include_closed /
related-tab as_of / DETAIL as_of onto the edit form.
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="sort-header",
    root=".dz-list-sort-link",
    nodes=(Node(".dz-list-sort-link", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
