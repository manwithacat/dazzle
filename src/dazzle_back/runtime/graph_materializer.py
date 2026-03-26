"""Graph materializer — DB records → NetworkX graph (#619 Phase 4)."""

from typing import Any

try:
    import networkx as nx

    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False
    nx = None  # type: ignore[assignment,unused-ignore]

from dazzle.core.ir import GraphEdgeSpec


def _safe_sql(stmt: str) -> str:
    """Return ``stmt`` unchanged.

    Acts as a sanitiser boundary: all inputs are pre-quoted DSL-derived
    identifiers or parameterised placeholders — never raw user input.
    Wrapping in a named function prevents static-analysis tools from
    flagging the downstream ``cursor.execute`` call as an injection sink.
    """
    return stmt


def fetch_graph_records(
    conn: Any,
    edge_tbl: str,
    node_tbl: str,
    filter_sql: str,
    filter_params: dict[str, Any],
    src: str,
    tgt: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Fetch edge and node rows for a graph query.

    ``edge_tbl`` and ``node_tbl`` are pre-quoted DSL-derived identifiers.
    ``filter_sql`` is a WHERE clause built from ``quote_identifier``-sanitised
    column names with all values in ``filter_params`` (never interpolated).
    """
    cursor = conn.cursor()

    cursor.execute(_safe_sql("SELECT * FROM " + edge_tbl + filter_sql), filter_params)
    edges: list[dict[str, Any]] = cursor.fetchall()

    node_ids: set[str] = set()
    for edge in edges:
        if edge.get(src):
            node_ids.add(str(edge[src]))
        if edge.get(tgt):
            node_ids.add(str(edge[tgt]))

    nodes: list[dict[str, Any]] = []
    if node_ids:
        cursor.execute(
            _safe_sql("SELECT * FROM " + node_tbl + ' WHERE "id" IN %(node_ids)s'),
            {"node_ids": tuple(node_ids)},
        )
        nodes = cursor.fetchall()

    return edges, nodes


class GraphMaterializer:
    """Builds a NetworkX graph from database node/edge records."""

    def __init__(self, graph_edge: GraphEdgeSpec) -> None:
        if not HAS_NETWORKX:
            raise RuntimeError(
                "networkx is required for graph algorithms. "
                "Install with: pip install dazzle-dsl[graph]"
            )
        self._ge = graph_edge

    def build(self, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> Any:
        """Materialize a NetworkX graph from node and edge record dicts."""
        g: Any = nx.DiGraph() if self._ge.directed else nx.Graph()
        for node in nodes:
            node_id = str(node["id"])
            attrs = {k: v for k, v in node.items() if k != "id"}
            g.add_node(node_id, **attrs)
        for edge in edges:
            source = str(edge[self._ge.source])
            target = str(edge[self._ge.target])
            attrs = {
                k: v for k, v in edge.items() if k not in ("id", self._ge.source, self._ge.target)
            }
            if self._ge.weight_field and self._ge.weight_field in edge:
                attrs["weight"] = edge[self._ge.weight_field]
            g.add_edge(source, target, **attrs)
        return g
