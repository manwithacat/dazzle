"""dual_pane_flow → master-detail Hyperpart pairing.

When a workspace declares ``stage: dual_pane_flow`` and has a LIST + DETAIL
region pair (same source entity preferred), the page shell emits the HM
``data-dz-master-detail`` composite and list rows swap detail fragments into
the pane instead of full-page drill.

This is the product emission site that dual-locks ``contracts/master_detail.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class DualPaneMasterDetailPair:
    """A list region that drives a sibling detail region inside master-detail."""

    list_region: str
    detail_region: str
    source: str  # shared entity when both match; else list's source


def _display_upper(region: Any) -> str:
    return str(getattr(region, "display", "") or "").upper()


def _source_of(region: Any) -> str:
    return str(getattr(region, "source", "") or "")


def _name_of(region: Any) -> str:
    return str(getattr(region, "name", "") or "")


def detect_dual_pane_master_detail_pair(
    stage: str,
    regions: list[Any],
) -> DualPaneMasterDetailPair | None:
    """Return the first LIST+DETAIL pair for a dual_pane_flow workspace.

    Heuristic (contact_manager shape):
    1. stage is dual_pane_flow
    2. pick first LIST region and first DETAIL region with the same source
    3. if no same-source pair, first LIST + first DETAIL (still dual-pane intent)
    4. otherwise None — multi-list dual_pane stays independent half-width cards
    """
    if str(stage or "").lower() != "dual_pane_flow":
        return None

    lists = [r for r in regions if _display_upper(r) == "LIST" and _name_of(r)]
    details = [r for r in regions if _display_upper(r) == "DETAIL" and _name_of(r)]
    if not lists or not details:
        return None

    for lst in lists:
        src = _source_of(lst)
        if not src:
            continue
        for det in details:
            if _source_of(det) == src:
                return DualPaneMasterDetailPair(
                    list_region=_name_of(lst),
                    detail_region=_name_of(det),
                    source=src,
                )

    # Fallback: first list + first detail even if sources differ (author intent).
    return DualPaneMasterDetailPair(
        list_region=_name_of(lists[0]),
        detail_region=_name_of(details[0]),
        source=_source_of(lists[0]),
    )


def master_detail_item_endpoint(workspace_name: str, detail_region: str) -> str:
    """URL template for list-row hx-get into the detail pane (``{id}`` placeholder)."""
    return f"/api/workspaces/{workspace_name}/regions/{detail_region}?id={{id}}"


def master_detail_pane_id(detail_region: str) -> str:
    """Stable DOM id for the detail pane (list rows hx-target this).

    Must not use htmx ``closest A B`` — Element.closest cannot reach a cousin
    pane under the master-detail root. Id targeting is multi-instance-safe
    because region names are unique within a workspace page.
    """
    return f"dz-md-detail-{detail_region}"


def render_master_detail_shell(
    *,
    list_region: str,
    list_title: str,
    list_endpoint: str,
    detail_region: str,
    detail_title: str,
    detail_endpoint_base: str,
    card_id: str = "md-pair",
    eager: bool = True,
    list_card_id: str = "card-list",
    detail_card_id: str = "card-detail",
) -> str:
    """Emit the dual-pane master-detail Hyperpart shell for a workspace pair.

    List body lazy-loads via the normal region endpoint. Detail pane starts with
    an empty prompt; the first list row uses ``hx-trigger="click, load once"`` so
    it auto-fills the pane when the list fragment settles. Further rows hx-get
    ``detail_endpoint_base?id=…`` into ``.dz-master-detail__detail`` on click.
    """
    import html as _html

    def esc(s: str) -> str:
        return _html.escape(s, quote=True)

    trigger = "load" if eager else "intersect once"
    list_body_id = f"region-{list_region}-{list_card_id}"
    detail_pane_id = master_detail_pane_id(detail_region)

    return (
        f'<div id="card-master-detail-{esc(card_id)}" '
        f'data-card-id="{esc(card_id)}" '
        f'data-card-region="{esc(list_region)}+{esc(detail_region)}" '
        f'data-card-col-span="12" '
        f'data-card-row-order="0" '
        f'class="dz-card-wrapper dz-master-detail-pair is-animating" '
        f'style="grid-column: span 12 / span 12;" '
        f'tabindex="0">'
        f'<div class="dz-master-detail" data-dz-master-detail '
        f'data-dz-master-detail-list="{esc(list_region)}" '
        f'data-dz-master-detail-detail="{esc(detail_region)}">'
        f'<div class="dz-master-detail__list" aria-label="{esc(list_title)}">'
        f'<article class="dz-card" aria-labelledby="card-title-{esc(list_card_id)}">'
        f'<div class="dz-card-header">'
        f'<div class="dz-card-titles">'
        f'<h3 id="card-title-{esc(list_card_id)}" class="dz-card-title">'
        f"{_html.escape(list_title)}</h3>"
        f"</div></div>"
        f'<div class="dz-card-body" id="{esc(list_body_id)}" '
        f'data-display="list" '
        f'data-dz-master-detail-list-body="true" '
        f'hx-get="{esc(list_endpoint)}" '
        f'hx-trigger="{esc(trigger)}" '
        f'hx-swap="innerHTML">'
        f'<div class="dz-card-skeleton">'
        f'<div class="dz-card-skeleton-line w-3-4"></div>'
        f'<div class="dz-card-skeleton-line is-thin"></div>'
        f"</div></div></article></div>"
        f'<div class="dz-master-detail__detail" id="{esc(detail_pane_id)}" '
        f'data-display="detail" '
        f'data-dz-master-detail-detail-body="true" '
        f'data-dz-master-detail-endpoint="{esc(detail_endpoint_base)}">'
        f'<div class="dz-master-detail__empty" role="status">'
        f'<p class="dz-empty-state-title">Select an item</p>'
        f'<p class="dz-empty-state-description">'
        f"Choose a row from the list to view details here."
        f"</p></div></div>"
        f"</div></div>"
    )
