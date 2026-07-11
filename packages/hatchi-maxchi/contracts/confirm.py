"""HYPERPART: confirm — hx-confirm interceptor (client affordance).

Package-internal dual-lock for CI / validate_dom — not application business
code. To use confirm in an HTMX app: put ``hx-confirm="…"`` on the action
element and load the controller (``controllers/dz-confirm.js``). The dialog
itself is not server-rendered; after the user approves, htmx issues the
element's existing ``hx-*`` request (see the part page Server exchange).

In-contract: any element with ``hx-confirm``. Opt-out: ``data-dz-native-confirm``
(source token; gallery demos may strip the ``dz-`` prefix).
"""

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="confirm",
    root="[hx-confirm]",
    nodes=(Node("[hx-confirm]", attrs={"hx-confirm": Present()}),),
)

__all__ = ["DOM_CONTRACT"]
