from dataclasses import dataclass

import pytest

from dazzle.render.ids import id_for


@dataclass(frozen=True)
class _FakeIRNode:
    kind: str
    name: str
    parent: "_FakeIRNode | None" = None


def test_id_for_surface() -> None:
    node = _FakeIRNode(kind="surface", name="task_list")
    assert id_for(node) == "surface-task_list"


def test_id_for_region() -> None:
    parent = _FakeIRNode(kind="surface", name="ops_dashboard")
    region = _FakeIRNode(kind="region", name="citation_graph", parent=parent)
    assert id_for(region) == "region-ops_dashboard-citation_graph"


def test_id_for_rejects_unknown_kind() -> None:
    node = _FakeIRNode(kind="moonbeam", name="foo")
    with pytest.raises(ValueError, match="unknown ir kind"):
        id_for(node)


def test_id_for_rejects_non_identifier_name() -> None:
    node = _FakeIRNode(kind="surface", name="task list with spaces")
    with pytest.raises(ValueError, match="invalid name"):
        id_for(node)


def test_id_for_three_level_chain() -> None:
    surface = _FakeIRNode(kind="surface", name="dashboard")
    region = _FakeIRNode(kind="region", name="alerts", parent=surface)
    fragment = _FakeIRNode(kind="fragment", name="badge", parent=region)
    assert id_for(fragment) == "fragment-dashboard-alerts-badge"
