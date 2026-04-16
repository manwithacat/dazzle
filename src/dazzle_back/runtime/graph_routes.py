"""Parent-scoped graph visualization endpoints (#781).

When a ``graph_node:`` block declares ``parent: <ref_field>``, the runtime
generates ``GET /api/{parent_plural}/{id}/graph`` returning every node
whose parent_field equals ``{id}`` together with the edges connecting
them, serialized via ``GraphSerializer``.

Complements the existing seed-based neighborhood endpoint
(``/api/{node}/{id}/graph``) which starts from a node; this one starts
from the parent / container entity.
"""

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from dazzle.core.ir import GraphEdgeSpec, GraphNodeSpec
from dazzle.core.strings import to_api_plural
from dazzle_back.runtime.graph_serializer import GraphSerializer

logger = logging.getLogger(__name__)

_VALID_FORMATS = ("cytoscape", "d3", "raw")


def _stringify_uuids(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert UUID columns to strings for JSON serialisation."""
    result: list[dict[str, Any]] = []
    for row in rows:
        out: dict[str, Any] = {}
        for k, v in row.items():
            out[k] = str(v) if isinstance(v, UUID) else v
        result.append(out)
    return result


def build_parent_graph_routes(
    node_graph_specs: dict[str, dict[str, Any]],
    entities: list[Any],
    repositories: dict[str, Any],
) -> APIRouter | None:
    """Return an APIRouter registering parent-scoped graph endpoints.

    ``node_graph_specs`` maps node entity name to ``{"graph_edge", "graph_node",
    "node_table", "edge_table"}`` — the same shape computed in ``server.py``.

    Returns ``None`` when no node has a ``parent_field`` set so no route is
    mounted for apps that don't need it.
    """
    # Only consider node entities with a parent_field declaration
    parent_graphs: list[dict[str, Any]] = []
    for node_name, spec in node_graph_specs.items():
        gn: GraphNodeSpec | None = spec.get("graph_node")
        ge: GraphEdgeSpec | None = spec.get("graph_edge")
        if gn is None or ge is None or not gn.parent_field:
            continue
        node_entity = next((e for e in entities if e.name == node_name), None)
        if node_entity is None:
            continue
        # Resolve parent entity via the named ref field
        parent_field_spec = next((f for f in node_entity.fields if f.name == gn.parent_field), None)
        if parent_field_spec is None or not parent_field_spec.type.ref_entity:
            continue
        parent_entity_name = parent_field_spec.type.ref_entity
        parent_repo = repositories.get(parent_entity_name)
        node_repo = repositories.get(node_name)
        edge_repo = repositories.get(spec["edge_table"])
        if parent_repo is None or node_repo is None or edge_repo is None:
            continue

        parent_graphs.append(
            {
                "node_name": node_name,
                "parent_name": parent_entity_name,
                "parent_plural": to_api_plural(parent_entity_name),
                "parent_field": gn.parent_field,
                "graph_node": gn,
                "graph_edge": ge,
                "parent_repo": parent_repo,
                "node_repo": node_repo,
                "edge_repo": edge_repo,
            }
        )

    if not parent_graphs:
        return None

    router = APIRouter(tags=["Graph"])

    for cfg in parent_graphs:
        _register_parent_graph_route(router, cfg)

    return router


def _register_parent_graph_route(router: APIRouter, cfg: dict[str, Any]) -> None:
    """Register one parent-scoped graph route bound to the config via closure."""
    parent_name = cfg["parent_name"]
    node_name = cfg["node_name"]
    parent_field = cfg["parent_field"]
    parent_repo = cfg["parent_repo"]
    node_repo = cfg["node_repo"]
    edge_repo = cfg["edge_repo"]
    graph_edge: GraphEdgeSpec = cfg["graph_edge"]
    graph_node: GraphNodeSpec = cfg["graph_node"]
    path = f"/api/{cfg['parent_plural']}/{{parent_id}}/graph"

    async def parent_graph(
        parent_id: str,
        format: str = Query("cytoscape", description="cytoscape | d3 | raw"),
    ) -> JSONResponse:
        if format not in _VALID_FORMATS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid format '{format}'. Must be one of: {', '.join(_VALID_FORMATS)}",
            )

        # Validate parent exists so callers get 404 instead of an empty graph
        parent_record = await parent_repo.read(parent_id)
        if parent_record is None:
            raise HTTPException(status_code=404, detail=f"{parent_name} not found")

        nodes_page = await node_repo.list(
            page=1,
            page_size=10_000,
            filters={parent_field: parent_id},
        )
        node_rows = nodes_page.get("items", []) if isinstance(nodes_page, dict) else []
        nodes: list[dict[str, Any]] = [
            row if isinstance(row, dict) else row.model_dump(mode="json") for row in node_rows
        ]

        edges: list[dict[str, Any]] = []
        if nodes:
            node_ids = [str(n["id"]) for n in nodes if n.get("id") is not None]
            source = graph_edge.source
            target = graph_edge.target
            try:
                source_hits = await edge_repo.list(
                    page=1,
                    page_size=10_000,
                    filters={f"{source}__in": node_ids},
                )
                target_hits = await edge_repo.list(
                    page=1,
                    page_size=10_000,
                    filters={f"{target}__in": node_ids},
                )
            except Exception:
                logger.warning(
                    "Parent graph edge fetch failed for %s:%s",
                    parent_name,
                    parent_id,
                    exc_info=True,
                )
                source_hits = {"items": []}
                target_hits = {"items": []}

            node_id_set = set(node_ids)
            raw_edges: dict[str, dict[str, Any]] = {}
            for page in (source_hits, target_hits):
                for row in page.get("items", []):
                    r = row if isinstance(row, dict) else row.model_dump(mode="json")
                    src = str(r.get(source, ""))
                    tgt = str(r.get(target, ""))
                    if src in node_id_set and tgt in node_id_set:
                        eid = str(r.get("id", f"{src}:{tgt}"))
                        raw_edges[eid] = r
            edges = list(raw_edges.values())

        nodes = _stringify_uuids(nodes)
        edges = _stringify_uuids(edges)

        if format == "raw":
            return JSONResponse(
                content={
                    "parent": {"entity": parent_name, "id": str(parent_id)},
                    "nodes": nodes,
                    "edges": edges,
                }
            )

        serializer = GraphSerializer(graph_edge=graph_edge, graph_node=graph_node)
        if format == "cytoscape":
            payload = serializer.to_cytoscape(edges, nodes)
        else:
            payload = serializer.to_d3(edges, nodes)
        payload["parent"] = {"entity": parent_name, "id": str(parent_id)}
        payload["node_entity"] = node_name
        return JSONResponse(content=payload)

    router.get(path, summary=f"Graph of {node_name} nodes for a {parent_name}")(parent_graph)
