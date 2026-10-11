"""master-detail hyperpart emitter — unit pins (cycle 1768).

``stage: dual_pane_flow`` + LIST/DETAIL region pair → HM master-detail shell
(``.dz-master-detail`` / ``data-dz-master-detail``).
"""

from __future__ import annotations

from dazzle.page.runtime.dual_pane_master_detail import (
    render_master_detail_shell,
)
from dazzle.qa.hyperpart_dsl_shapes import shapes_snapshot


def test_master_detail_shell_mounts_dz_spine() -> None:
    html = render_master_detail_shell(
        list_region="contact_list",
        list_title="Contacts",
        list_endpoint="/api/workspaces/contacts/regions/contact_list",
        detail_region="contact_detail",
        detail_title="Detail",
        detail_endpoint_base="/api/workspaces/contacts/regions/contact_detail",
    )
    assert 'class="dz-master-detail"' in html or "dz-master-detail" in html
    assert "data-dz-master-detail" in html
    assert "data-dz-master-detail-list-body" in html
    assert "data-dz-master-detail-detail-body" in html
    assert "dz-master-detail__list" in html
    assert "dz-master-detail__detail" in html
    assert "Select an item" in html


def test_master_detail_shape_live() -> None:
    snap = shapes_snapshot()
    assert "master-detail" not in snap["planned_ids"]
    assert snap["next_planned"] != "master-detail"
