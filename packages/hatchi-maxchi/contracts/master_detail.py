"""HYPERPART: master-detail — selection marker + detail pane root.

Dazzle emission site (workspace dual_pane_flow LIST+DETAIL pair):
``dazzle.page.runtime.dual_pane_master_detail.render_master_detail_shell``.
List rows carry ``.dz-master-detail__item`` and hx-get a detail fragment into
``.dz-master-detail__detail``; ``dz-master-detail.js`` owns aria-current.

Leftover honesty (cycle 2183 class-close): list-pane ``hx-get``
must echo leftover-honest ``include_closed`` / ``as_of``. Bare
``hx-get="{list_endpoint}"`` dropped them and invented open-only /
current on pane load. Leftover junk must not invent. Valid
``true`` / YYYY-MM-DD still ride. Do not walk another ``hx-get``
sibling (oral #67).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="master-detail",
    root="[data-dz-master-detail]",
    nodes=(
        Node("[data-dz-master-detail]", attrs={}),
        # Pane markers (kit selectors are [attr] only — no class engine).
        Node("[data-dz-master-detail-list-body]", attrs={}),
        Node("[data-dz-master-detail-detail-body]", attrs={}),
    ),
)

__all__ = ["DOM_CONTRACT"]
