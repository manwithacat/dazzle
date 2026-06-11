"""Graph endpoint handler factories for generated routes (#619 phases 3-4).

Extracted verbatim from ``route_generator.py`` (#1361 final slice). This is
the GRAPH family: NetworkX availability probe (``_check_networkx``),
domain-scope filter extraction (``_extract_domain_filters``,
``_build_graph_filter_sql``), graph materialization from node/edge tables
(``_materialize_graph``), the neighborhood CTE endpoint
(``_neighborhood_handler_body`` / ``create_neighborhood_handler``), and the
algorithm endpoints (``create_shortest_path_handler``,
``create_components_handler``).

A leaf module by design: it must not import ``route_generator`` at module
level (``route_generator`` imports these names back at module level so the
``route_generator.<name>`` call sites, importers, and patch points keep
resolving there). This family needs no route_generator-resident helpers,
so it carries zero lazy route_generator imports.

Deliberately NOT named ``*_routes.py`` — the runtime-urls api-surface walker
globs that pattern and this module defines no routes.
"""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastapi import Depends, HTTPException, Query, Request

from dazzle.back.runtime.auth import AuthContext

if TYPE_CHECKING:
    from dazzle.back.specs.auth import EntityAccessSpec
    from dazzle.core.ir.fk_graph import FKGraph


def _check_networkx() -> bool:
    """Return True if NetworkX is available."""
    try:
        import networkx  # noqa: F401

        return True
    except ImportError:
        return False


def _extract_domain_filters(request: Any, filter_fields: list[str] | None) -> dict[str, Any]:
    """Extract domain-scope filters from query params for graph algorithms."""
    filters: dict[str, Any] = {}
    if not filter_fields:
        return filters
    reserved = {
        "format",
        "to",
        "weighted",
        "depth",
        "page",
        "page_size",
        "sort",
        "dir",
        "search",
        "q",
    }
    for key, value in request.query_params.items():
        if key in filter_fields and key not in reserved and value:
            filters[key] = value
        elif key.startswith("filter[") and key.endswith("]"):
            field = key[7:-1]
            if field in filter_fields and value:
                filters[field] = value
    return filters


def _build_graph_filter_sql(
    filters: dict[str, Any] | None,
    params: dict[str, Any],
) -> str:
    """Build a WHERE clause from domain-scope filters.

    Uses parameterised placeholders — column names are DSL-derived identifiers
    passed through ``quote_identifier`` for defense-in-depth.
    """
    if not filters:
        return ""
    from dazzle.back.runtime.query_builder import quote_identifier as _qi

    clauses: list[str] = []
    for i, (field, value) in enumerate(filters.items()):
        param_name = f"_f{i}"
        clauses.append(f"{_qi(field)} = %({param_name})s")
        params[param_name] = value
    return " WHERE " + " AND ".join(clauses)


async def _materialize_graph(
    db_manager: Any,
    node_table: str,
    edge_table: str,
    graph_edge_spec: Any,
    filters: dict[str, Any] | None = None,
) -> tuple[Any, list[dict[str, Any]], list[dict[str, Any]]]:
    """Load nodes + edges from DB and build a NetworkX graph.

    Returns (nx_graph, node_dicts, edge_dicts).
    """
    from dazzle.back.runtime.graph_materializer import GraphMaterializer
    from dazzle.back.runtime.query_builder import quote_identifier

    filter_params: dict[str, Any] = {}
    filter_sql: str = _build_graph_filter_sql(filters, filter_params)

    src = graph_edge_spec.source
    tgt = graph_edge_spec.target

    # Table names are DSL-derived identifiers (not user input), but we
    # quote them properly via quote_identifier for defense-in-depth.
    edge_tbl = quote_identifier(edge_table)
    node_tbl = quote_identifier(node_table)

    def _safe_sql(stmt: str) -> str:
        """Identity — inputs are quote_identifier-sanitised DSL names."""
        return stmt

    def _fetch_edges(cursor: Any) -> list[dict[str, Any]]:
        """Execute edge query. Table/column names are DSL-derived identifiers."""
        cursor.execute(_safe_sql("SELECT * FROM " + edge_tbl + filter_sql), filter_params)
        return cursor.fetchall()

    def _fetch_nodes(cursor: Any, ids: tuple[str, ...]) -> list[dict[str, Any]]:
        """Execute node query. Table name is a DSL-derived identifier."""
        cursor.execute(
            _safe_sql("SELECT * FROM " + node_tbl + ' WHERE "id" IN %(node_ids)s'),
            {"node_ids": ids},
        )
        return cursor.fetchall()

    with db_manager.connection() as conn:
        cursor = conn.cursor()

        edges = _fetch_edges(cursor)

        node_ids: set[str] = set()
        for edge in edges:
            if edge.get(src):
                node_ids.add(str(edge[src]))
            if edge.get(tgt):
                node_ids.add(str(edge[tgt]))

        nodes: list[dict[str, Any]] = []
        if node_ids:
            nodes = _fetch_nodes(cursor, tuple(node_ids))

    def _stringify(rows: list) -> list[dict]:  # type: ignore[type-arg]
        result = []
        for row in rows:
            out = {}
            for k, v in row.items():
                out[k] = str(v) if hasattr(v, "hex") else v
            result.append(out)
        return result

    str_nodes = _stringify(nodes)
    str_edges = _stringify(edges)
    materializer = GraphMaterializer(graph_edge=graph_edge_spec)
    return materializer.build(str_nodes, str_edges), str_nodes, str_edges


_VALID_GRAPH_FORMATS = frozenset({"cytoscape", "d3", "raw"})


async def _neighborhood_handler_body(
    seed_id: UUID,
    depth: int,
    format: str,
    entity_name: str,
    graph_edge_spec: Any,
    graph_node_spec: Any | None,
    node_table: str,
    edge_table: str,
    db_manager: Any,
    node_service: Any,
) -> Any:
    """Core logic for the neighborhood graph endpoint."""
    from starlette.responses import JSONResponse

    from dazzle.back.runtime.graph_serializer import GraphSerializer
    from dazzle.back.runtime.neighborhood import NeighborhoodQueryBuilder

    # 1. Validate format
    if format not in _VALID_GRAPH_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid format '{format}'. Must be one of: {', '.join(sorted(_VALID_GRAPH_FORMATS))}",
        )

    # 2. Check seed node exists
    seed_record = await node_service.execute(operation="read", id=seed_id)
    if seed_record is None:
        raise HTTPException(status_code=404, detail=f"{entity_name} not found")

    # 3. Build CTE
    builder = NeighborhoodQueryBuilder(
        node_table=node_table,
        edge_table=edge_table,
        graph_edge=graph_edge_spec,
    )
    cte_sql, cte_params = builder.cte_query(str(seed_id), depth)

    # 4. Execute: CTE → node fetch → edge fetch
    with db_manager.connection() as conn:
        cursor = conn.cursor()

        # Discover reachable node IDs
        cursor.execute(cte_sql, cte_params)
        cte_rows = cursor.fetchall()
        node_ids = [str(row["node_id"]) for row in cte_rows]

        if not node_ids:
            # Seed exists but has no connections — return it alone
            node_ids = [str(seed_id)]

        # Fetch full node records
        node_sql, node_params = builder.node_fetch_query(node_ids)
        cursor.execute(node_sql, node_params)
        nodes = cursor.fetchall()

        # Fetch edges between discovered nodes
        edge_sql, edge_params = builder.edge_fetch_query(node_ids)
        cursor.execute(edge_sql, edge_params)
        edges = cursor.fetchall()

    # 5. Serialize UUIDs to strings
    def _stringify_uuids(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = []
        for row in rows:
            out = {}
            for k, v in row.items():
                out[k] = str(v) if isinstance(v, UUID) else v
            result.append(out)
        return result

    nodes = _stringify_uuids(nodes)
    edges = _stringify_uuids(edges)

    # 6. Return via GraphSerializer or raw
    if format == "raw":
        return JSONResponse(content={"nodes": nodes, "edges": edges})

    serializer = GraphSerializer(
        graph_edge=graph_edge_spec,
        graph_node=graph_node_spec,
    )
    if format == "cytoscape":
        return JSONResponse(content=serializer.to_cytoscape(edges, nodes))
    else:
        return JSONResponse(content=serializer.to_d3(edges, nodes))


def create_neighborhood_handler(
    entity_name: str,
    graph_edge_spec: Any,
    graph_node_spec: Any | None,
    node_table: str,
    edge_table: str,
    db_manager: Any,
    node_service: Any,
    optional_auth_dep: Callable[..., Any] | None = None,
    cedar_access_spec: "EntityAccessSpec | None" = None,
    fk_graph: "FKGraph | None" = None,
    ref_targets: dict[str, str] | None = None,
) -> Callable[..., Any]:
    """Create a handler for graph neighborhood traversal (#619 Phase 3).

    Returns reachable nodes and edges from a seed node up to a given depth.
    """
    if optional_auth_dep is not None:

        async def _auth_handler(
            id: UUID,
            auth_context: AuthContext = Depends(optional_auth_dep),
            depth: int = Query(1, ge=1, le=3, description="Traversal depth"),
            format: str = Query("cytoscape", description="Response format: cytoscape, d3, or raw"),
        ) -> Any:
            return await _neighborhood_handler_body(
                seed_id=id,
                depth=depth,
                format=format,
                entity_name=entity_name,
                graph_edge_spec=graph_edge_spec,
                graph_node_spec=graph_node_spec,
                node_table=node_table,
                edge_table=edge_table,
                db_manager=db_manager,
                node_service=node_service,
            )

        _auth_handler.__annotations__ = {
            "id": UUID,
            "auth_context": AuthContext,
            "depth": int,
            "format": str,
            "return": Any,
        }
        return _auth_handler

    async def _noauth_handler(
        id: UUID,
        depth: int = Query(1, ge=1, le=3, description="Traversal depth"),
        format: str = Query("cytoscape", description="Response format: cytoscape, d3, or raw"),
    ) -> Any:
        return await _neighborhood_handler_body(
            seed_id=id,
            depth=depth,
            format=format,
            entity_name=entity_name,
            graph_edge_spec=graph_edge_spec,
            graph_node_spec=graph_node_spec,
            node_table=node_table,
            edge_table=edge_table,
            db_manager=db_manager,
            node_service=node_service,
        )

    _noauth_handler.__annotations__ = {
        "id": UUID,
        "depth": int,
        "format": str,
        "return": Any,
    }
    return _noauth_handler


def create_shortest_path_handler(
    entity_name: str,
    graph_edge_spec: Any,
    graph_node_spec: Any | None,
    node_table: str,
    edge_table: str,
    db_manager: Any,
    filter_fields: list[str] | None = None,
    optional_auth_dep: Callable[..., Any] | None = None,
) -> Callable[..., Any]:
    """Create handler for GET /{entity}/{id}/graph/shortest-path?to={target_id}."""

    async def _handler(
        request: Request,
        id: UUID,
        to: UUID = Query(..., description="Target node ID"),
        format: str = Query("cytoscape", description="Response format"),
        weighted: bool = Query(False, description="Use edge weights"),
    ) -> Any:
        from starlette.responses import JSONResponse

        from dazzle.back.runtime.graph_algorithms import shortest_path
        from dazzle.back.runtime.graph_serializer import GraphSerializer

        if format not in _VALID_GRAPH_FORMATS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid format. Supported: {', '.join(sorted(_VALID_GRAPH_FORMATS))}",
            )

        filters = _extract_domain_filters(request, filter_fields)
        g, all_nodes, all_edges = await _materialize_graph(
            db_manager,
            node_table,
            edge_table,
            graph_edge_spec,
            filters,
        )

        result = shortest_path(g, source=str(id), target=str(to), weighted=weighted)

        if format == "raw":
            return JSONResponse(content=result)

        path_ids = set(result.get("path", []))
        serializer = GraphSerializer(graph_edge=graph_edge_spec, graph_node=graph_node_spec)

        if not path_ids:
            empty = (
                serializer.to_cytoscape([], [])
                if format == "cytoscape"
                else serializer.to_d3([], [])
            )
            empty["shortest_path"] = result
            return JSONResponse(content=empty)

        path_nodes = [n for n in all_nodes if str(n.get("id")) in path_ids]
        path_edges = [
            e
            for e in all_edges
            if str(e.get(graph_edge_spec.source)) in path_ids
            and str(e.get(graph_edge_spec.target)) in path_ids
        ]

        if format == "cytoscape":
            out = serializer.to_cytoscape(path_edges, path_nodes)
        else:
            out = serializer.to_d3(path_edges, path_nodes)
        out["shortest_path"] = result
        return JSONResponse(content=out)

    _handler.__name__ = f"shortest_path_{entity_name.lower()}"
    return _handler


def create_components_handler(
    entity_name: str,
    graph_edge_spec: Any,
    graph_node_spec: Any | None,
    node_table: str,
    edge_table: str,
    db_manager: Any,
    filter_fields: list[str] | None = None,
    optional_auth_dep: Callable[..., Any] | None = None,
) -> Callable[..., Any]:
    """Create handler for GET /{entity}/graph/components."""

    async def _handler(
        request: Request,
        format: str = Query("raw", description="Response format"),
    ) -> Any:
        from starlette.responses import JSONResponse

        from dazzle.back.runtime.graph_algorithms import connected_components
        from dazzle.back.runtime.graph_serializer import GraphSerializer

        if format not in _VALID_GRAPH_FORMATS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid format. Supported: {', '.join(sorted(_VALID_GRAPH_FORMATS))}",
            )

        filters = _extract_domain_filters(request, filter_fields)
        g, all_nodes, all_edges = await _materialize_graph(
            db_manager,
            node_table,
            edge_table,
            graph_edge_spec,
            filters,
        )

        result = connected_components(g)

        if format == "raw":
            return JSONResponse(content=result)

        serializer = GraphSerializer(graph_edge=graph_edge_spec, graph_node=graph_node_spec)
        if format == "cytoscape":
            out = serializer.to_cytoscape(all_edges, all_nodes)
        else:
            out = serializer.to_d3(all_edges, all_nodes)
        out["components"] = result
        return JSONResponse(content=out)

    _handler.__name__ = f"components_{entity_name.lower()}"
    return _handler
