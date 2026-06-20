"""CRUD + graph handler factories for generated routes (#1361 final slice).

The handler-factory families extracted from ``route_generator.py``:

- :mod:`list_handlers` — list family (``create_list_handler`` /
  ``_list_handler_body`` / ``_is_field_condition``)
- :mod:`read_handlers` — read/detail family (``create_read_handler``)
- :mod:`write_handlers` — create/update/delete/custom family + ref
  injection + request-body parsing
- :mod:`graph_handlers` — graph neighborhood + algorithm endpoints
  (#619 phases 3-4)

``route_generator`` re-imports every name below at module level, so the
historical ``dazzle.http.runtime.route_generator.<name>`` import and
patch paths keep working. These submodules are leaf modules: they never
import ``route_generator`` at module level (only lazily inside function
bodies), keeping the import graph acyclic.

Module names deliberately avoid ``*_routes.py`` — the runtime-urls
api-surface walker globs that pattern and these modules define no routes.
"""

from dazzle.http.runtime.handlers.graph_handlers import (
    _VALID_GRAPH_FORMATS,
    _build_graph_filter_sql,
    _check_networkx,
    _extract_domain_filters,
    _materialize_graph,
    _neighborhood_handler_body,
    create_components_handler,
    create_neighborhood_handler,
    create_shortest_path_handler,
)
from dazzle.http.runtime.handlers.list_handlers import (
    _is_field_condition,
    _list_handler_body,
    create_list_handler,
)
from dazzle.http.runtime.handlers.read_handlers import create_read_handler
from dazzle.http.runtime.handlers.write_handlers import (
    _parse_request_body,
    create_create_handler,
    create_custom_handler,
    create_delete_handler,
    create_update_handler,
    inject_current_user_refs,
    resolve_backed_entity_refs,
)

__all__ = [
    "_VALID_GRAPH_FORMATS",
    "_build_graph_filter_sql",
    "_check_networkx",
    "_extract_domain_filters",
    "_is_field_condition",
    "_list_handler_body",
    "_materialize_graph",
    "_neighborhood_handler_body",
    "_parse_request_body",
    "create_components_handler",
    "create_create_handler",
    "create_custom_handler",
    "create_delete_handler",
    "create_list_handler",
    "create_neighborhood_handler",
    "create_read_handler",
    "create_shortest_path_handler",
    "create_update_handler",
    "inject_current_user_refs",
    "resolve_backed_entity_refs",
]
