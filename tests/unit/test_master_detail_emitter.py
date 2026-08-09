"""master-detail hyperpart emitter — unit pins (cycle 1768).

``stage: dual_pane_flow`` + LIST/DETAIL region pair → HM master-detail shell
(``.dz-master-detail`` / ``data-dz-master-detail``).
"""

from __future__ import annotations

from pathlib import Path

from dazzle.core.appspec_loader import load_project_appspec
from dazzle.page.runtime.dual_pane_master_detail import (
    detect_dual_pane_master_detail_pair,
    render_master_detail_shell,
)
from dazzle.qa.hyperpart_dsl_shapes import shapes_snapshot

ROOT = Path(__file__).resolve().parents[2]
CONTACT = ROOT / "examples" / "contact_manager"


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


def test_contact_manager_declares_dual_pane_flow() -> None:
    text = (CONTACT / "dsl" / "app.dsl").read_text(encoding="utf-8")
    assert "dual_pane_flow" in text
    assert "contact_list:" in text
    assert "contact_detail:" in text
    assert "display: list" in text
    assert "display: detail" in text


def test_contact_manager_appspec_list_detail_pair() -> None:
    appspec = load_project_appspec(CONTACT)
    workspaces = list(getattr(appspec, "workspaces", None) or [])
    contacts = next((w for w in workspaces if getattr(w, "name", None) == "contacts"), None)
    assert contacts is not None, (
        f"contacts workspace missing; {[getattr(w, 'name', None) for w in workspaces]}"
    )
    stage = getattr(contacts, "stage", None)
    stage_v = getattr(stage, "value", stage)
    assert str(stage_v) == "dual_pane_flow"
    regions = list(getattr(contacts, "regions", None) or [])
    pair = detect_dual_pane_master_detail_pair("dual_pane_flow", regions)
    assert pair is not None
    assert pair.list_region == "contact_list"
    assert pair.detail_region == "contact_detail"


def test_master_detail_shape_live() -> None:
    snap = shapes_snapshot()
    assert "master-detail" not in snap["planned_ids"]
    assert snap["next_planned"] != "master-detail"
