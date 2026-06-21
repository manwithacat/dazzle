"""#1428: the page in-process read/list must be fed an *entity-name-keyed* service map.

Page handlers (`_read_entity_in_process` / `_list_entity_in_process`) look services up by
ENTITY name (`MarkingResult`), but `DazzleBackendApp.services` is keyed by *service* name
(`get_markingresult`, `list_markingresults`, …). Feeding the op-keyed map to
`create_page_routes` made every entity-name lookup silently miss — so every in-process
detail read 404'd and every in-process list went silently empty (the same #1181 footgun,
one layer up). The fix hands page routes `builder.services_by_entity()`.

This locks three things:
1. `DazzleBackendApp.services_by_entity()` is public (the page wiring depends on it) and the
   old private `_services_by_entity` name is gone (clean rename, no shim).
2. `app_factory` passes the *entity-keyed* view (`services_by_entity()`) to
   `create_page_routes`, never the op-keyed `builder.services`.
3. The consumer side still looks up by entity name — so producer and consumer agree.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from dazzle.http.runtime.server import DazzleBackendApp

_SRC = Path(__file__).resolve().parents[2] / "src" / "dazzle"
_APP_FACTORY = _SRC / "http" / "runtime" / "app_factory.py"
_PAGE_ROUTES = _SRC / "http" / "runtime" / "page_routes.py"


def test_services_by_entity_is_public_and_old_private_name_is_gone() -> None:
    # The page wiring (and #1181 callers) depend on the public accessor.
    assert callable(getattr(DazzleBackendApp, "services_by_entity", None))
    # Clean rename — the private alias must not linger.
    assert not hasattr(DazzleBackendApp, "_services_by_entity")


def _create_page_routes_entity_services_arg() -> str:
    """Return the source text of the `entity_services=` kwarg in the
    `create_page_routes(...)` call inside app_factory."""
    tree = ast.parse(_APP_FACTORY.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "create_page_routes"
        ):
            for kw in node.keywords:
                if kw.arg == "entity_services":
                    return ast.unparse(kw.value)
    raise AssertionError("create_page_routes(entity_services=...) call not found in app_factory")


def test_app_factory_feeds_page_routes_the_entity_keyed_map() -> None:
    arg = _create_page_routes_entity_services_arg()
    # Must be the entity-keyed view, not the op-keyed `builder.services`.
    assert "services_by_entity" in arg, (
        f"create_page_routes must receive the entity-name-keyed service map, got: {arg!r}"
    )
    assert arg.strip() != "builder.services", (
        "page routes were handed the *service*-name-keyed map — entity-name lookups silently miss (#1428)"
    )


def test_page_in_process_read_looks_up_by_entity_name() -> None:
    """The consumer side keys by entity name — confirming the producer must too."""
    src = _PAGE_ROUTES.read_text(encoding="utf-8")
    assert "prc.deps.entity_services.get(entity_name)" in src


def test_services_by_entity_delegates_to_factory_keying() -> None:
    """The accessor returns `{}` when no factory is wired, else the factory's
    entity-keyed view — so it can never silently hand back the op-keyed dict."""
    body = inspect.getsource(DazzleBackendApp.services_by_entity)
    assert "services_by_entity" in body  # delegates to ServiceFactory.services_by_entity()
    assert "_service_factory" in body
