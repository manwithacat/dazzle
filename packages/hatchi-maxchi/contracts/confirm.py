"""HYPERPART: confirm — hx-confirm interceptor (client affordance).

Package-internal dual-lock for CI / validate_dom — not application business
code. To use confirm in an HTMX app: put ``hx-confirm="…"`` on the action
element and load the controller (``controllers/dz-confirm.js``). The dialog
itself is not server-rendered; after the user approves, htmx issues the
element's existing ``hx-*`` request (see the part page Server exchange).

In-contract: any element with ``hx-confirm``. Opt-out: ``data-dz-native-confirm``
(source token; gallery demos may strip the ``dz-`` prefix).

Accept button (#1795): optional ``data-dz-confirm-variant``
(``primary|destructive|outline|ghost``) and ``data-dz-confirm-label`` on the
triggering element set the accept button's variant and text per open.
Defaults: ``destructive`` for ``hx-delete``, ``primary`` otherwise; label
``Confirm``. Hosts emitting a destructive ``hx-post`` say so explicitly.
"""

from contracts._kit import DomContract, Node, OneOf, Present

VARIANTS = ("primary", "destructive", "outline", "ghost")

DOM_CONTRACT = DomContract(
    part="confirm",
    root="[hx-confirm]",
    nodes=(
        Node("[hx-confirm]", attrs={"hx-confirm": Present()}),
        # Optional: the node selector matches only when the attr is present.
        Node(
            "[hx-confirm][data-dz-confirm-variant]",
            attrs={"data-dz-confirm-variant": OneOf(*VARIANTS)},
        ),
        Node(
            "[hx-confirm][data-dz-confirm-label]",
            attrs={"data-dz-confirm-label": Present()},
        ),
    ),
)

__all__ = ["DOM_CONTRACT"]
