"""FKGraph.deletion_order — children-before-parents (RLS Phase E.1)."""

from dazzle.core.ir.fk_graph import FKGraph


def _graph(edges: dict[str, dict[str, str]]) -> FKGraph:
    g = FKGraph()
    g._edges = {k: dict(v) for k, v in edges.items()}
    return g


def test_deletion_order_is_children_before_parents() -> None:
    # Task -> Project -> Workspace (FK source deleted first).
    g = _graph(
        {
            "Workspace": {},
            "Project": {"workspace": "Workspace"},
            "Task": {"project": "Project"},
        }
    )
    order = g.deletion_order(["Workspace", "Project", "Task"])
    assert order is not None
    assert order.index("Task") < order.index("Project") < order.index("Workspace")


def test_deletion_order_is_exact_reverse_of_creation_order() -> None:
    g = _graph({"A": {}, "B": {"a": "A"}, "C": {"b": "B"}})
    creation = g.creation_order(["A", "B", "C"])
    deletion = g.deletion_order(["A", "B", "C"])
    assert creation is not None and deletion is not None
    assert deletion == list(reversed(creation))


def test_deletion_order_none_on_cycle() -> None:
    # Self-referential FK -> cycle -> no safe order.
    g = _graph({"Employee": {"manager": "Employee"}})
    assert g.deletion_order(["Employee"]) is None
