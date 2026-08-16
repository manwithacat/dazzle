"""HYPERPART: grid — root contract (thin). The base grid's structural
root attributes; the data-bearing seams live in extension contracts
(grid_edit). Root-only: no ingestion model, no exemplars.

Leftover honesty (cycle 2157): URL ``?page=2abc`` / ``?page_size=2abc``
must not invent a window. ``parseInt("2abc", 10) === 2`` is leftover
junk — same class as PDF leftover page (2151). Empty / invalid
restores the server default. Valid whole numbers still window.
Rest-state gallery is unchanged (oral #33).

Leftover honesty (cycle 2170): ``ownedKeys`` / ``buildQuery`` must
echo leftover-honest ``include_closed`` / ``as_of``. Dropping them
from hx-get invented open-only / current after a refresh (page URL
foreign params survived; all-matching echo then invented). Leftover
junk (``zzz``, ``2abc``, ``maybe``, ``not-a-date``) must not invent.
Valid ``true`` / YYYY-MM-DD still ride hx-get. Not leftover list
include_closed / related-tab as_of / DETAIL as_of onto the edit form.
"""

from contracts._kit import DomContract

DOM_CONTRACT = DomContract(
    part="grid",
    root="[data-dz-grid]",
    nodes=(),
)

__all__ = ["DOM_CONTRACT"]
