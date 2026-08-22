"""Tree group_by scalar must not dump a flat device list (oral #163)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.project import load_project
from dazzle.http.runtime.workspace_region_computes import compute_tree
from dazzle.render.fragment.region import WorkspaceRegionAdapter
from dazzle.render.fragment.renderer import FragmentRenderer


class _FakeTree:
    name = "device_tree"
    title = "Device tree"
    display = "tree"
    empty_message = "No devices registered"


def _fieldtest_device_tree():
    spec = load_project(Path("examples/fieldtest_hub"))
    for ws in spec.workspaces:
        for region in ws.regions:
            if region.name == "device_tree":
                return region
    raise AssertionError("fieldtest_hub device_tree missing")


def test_fieldtest_device_tree_groups_by_batch_number() -> None:
    region = _fieldtest_device_tree()
    assert str(getattr(region.display, "value", region.display)) == "tree"
    assert region.group_by == "batch_number"


def test_scalar_group_by_nests_devices_under_batch() -> None:
    items = [
        {
            "id": "d1000000-0000-4000-8000-000000000001",
            "name": "FT-PROBE-A12",
            "batch_number": "B-2026-01",
        },
        {
            "id": "d1000000-0000-4000-8000-000000000002",
            "name": "FT-PROBE-B07",
            "batch_number": "B-2026-01",
        },
        {
            "id": "d1000000-0000-4000-8000-000000000003",
            "name": "FT-GATEWAY-01",
            "batch_number": "B-2026-02",
        },
        {
            "id": "d1000000-0000-4000-8000-000000000099",
            "name": "Leftover probe",
            "batch_number": "zzz",
        },
    ]
    tree = compute_tree(items, "batch_number")
    assert [n["name"] for n in tree] == ["B-2026-01", "B-2026-02", "zzz"]
    assert all(n.get("_group") for n in tree)
    first = {c["name"] for c in tree[0]["_children"]}
    assert first == {"FT-PROBE-A12", "FT-PROBE-B07"}
    assert tree[2]["_children"][0]["name"] == "Leftover probe"


def test_parent_ref_tree_still_nests() -> None:
    items = [
        {"id": "eng", "name": "Engineering", "parent_department": None},
        {"id": "fe", "name": "Frontend", "parent_department": "eng"},
        {"id": "be", "name": "Backend", "parent_department": {"id": "eng"}},
    ]
    tree = compute_tree(items, "parent_department")
    assert len(tree) == 1
    assert tree[0]["name"] == "Engineering"
    assert not tree[0].get("_group")
    kids = {c["name"] for c in tree[0]["_children"]}
    assert kids == {"Frontend", "Backend"}


def test_tree_html_renders_batch_folders_not_flat_list() -> None:
    items = [
        {
            "id": "d1",
            "name": "FT-PROBE-A12",
            "batch_number": "B-2026-01",
        },
        {
            "id": "d2",
            "name": "FT-PROBE-B07",
            "batch_number": "B-2026-01",
        },
        {
            "id": "d3",
            "name": "Leftover probe",
            "batch_number": "zzz",
        },
    ]
    html = FragmentRenderer().render(
        WorkspaceRegionAdapter().build(  # type: ignore[arg-type]
            _FakeTree(),
            {
                "tree_items": compute_tree(items, "batch_number"),
                "detail_url_template": "/app/device/{id}",
            },
        )
    )
    assert "B-2026-01" in html
    assert "FT-PROBE-A12" in html
    assert "FT-PROBE-B07" in html
    assert "zzz" in html
    assert "Leftover probe" in html
    assert 'href="/app/device/d1"' in html
    assert 'href="/app/device/d2"' in html
    # Group folders are not device hubs.
    assert html.count("data-dz-tree-drill") == 3
    assert 'href="/app/device/B-2026-01"' not in html
    assert "dz-tree-count" in html
