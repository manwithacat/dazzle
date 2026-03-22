"""Graph algorithm functions (#619 Phase 4). Pure functions on NetworkX graphs."""

from __future__ import annotations

from typing import Any

try:
    import networkx as nx
except ImportError:
    nx = None  # type: ignore[assignment]


def shortest_path(g: Any, source: str, target: str, weighted: bool = False) -> dict[str, Any]:
    """Find shortest path between two nodes. Returns path list and length."""
    if source not in g:
        return {"path": [], "length": None, "error": "source node not found in graph"}
    if target not in g:
        return {"path": [], "length": None, "error": "target node not found in graph"}
    try:
        if weighted:
            path = nx.shortest_path(g, source, target, weight="weight")
            weight = nx.shortest_path_length(g, source, target, weight="weight")
            return {"path": list(path), "length": len(path) - 1, "weight": weight}
        else:
            path = nx.shortest_path(g, source, target)
            return {"path": list(path), "length": len(path) - 1}
    except nx.NetworkXNoPath:
        return {"path": [], "length": None}


def connected_components(g: Any) -> dict[str, Any]:
    """Find connected components. Uses weak connectivity for directed graphs."""
    if len(g) == 0:
        return {"count": 0, "components": []}
    if isinstance(g, nx.DiGraph):
        components = list(nx.weakly_connected_components(g))
    else:
        components = list(nx.connected_components(g))
    components.sort(key=len, reverse=True)
    return {"count": len(components), "components": [sorted(c) for c in components]}
