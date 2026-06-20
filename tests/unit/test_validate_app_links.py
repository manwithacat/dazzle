"""#1426: the link↔route boot check. A list/region that advertises a
/app/<slug>/{id} drill-down link must have a mounted detail route — else warn
(default) or raise (strict). Catches the silent list-only dead-link footgun.
"""

from types import SimpleNamespace

import pytest

from dazzle.http.runtime.route_validator import validate_app_links


def _route(path: str, methods=("GET",)):
    return SimpleNamespace(path=path, methods=set(methods))


def _app(route_paths):
    return SimpleNamespace(
        state=SimpleNamespace(),
        routes=[_route(p) for p in route_paths],
    )


def _list_surface(entity_ref: str):
    return SimpleNamespace(mode=SimpleNamespace(value="list"), entity_ref=entity_ref)


def _appspec(*, surfaces, entities, workspaces=()):
    domain = SimpleNamespace(get_entity=lambda name: entities.get(name))
    return SimpleNamespace(surfaces=list(surfaces), workspaces=list(workspaces), domain=domain)


def test_clean_app_has_no_problems():
    entities = {"Task": SimpleNamespace(name="Task")}
    appspec = _appspec(surfaces=[_list_surface("Task")], entities=entities)
    app = _app(["/app/task", "/app/task/{id}"])  # detail route IS mounted
    assert validate_app_links(app, appspec) == []


def test_list_without_detail_route_is_flagged():
    entities = {"Task": SimpleNamespace(name="Task")}
    appspec = _appspec(surfaces=[_list_surface("Task")], entities=entities)
    app = _app(["/app/task"])  # list mounted, NO /app/task/{id}
    problems = validate_app_links(app, appspec)
    assert len(problems) == 1
    assert "Task" in problems[0]
    assert "/app/task/{id}" in problems[0]


def test_strict_raises_on_mismatch():
    entities = {"Task": SimpleNamespace(name="Task")}
    appspec = _appspec(surfaces=[_list_surface("Task")], entities=entities)
    app = _app(["/app/task"])
    with pytest.raises(RuntimeError, match="Link↔route mismatches"):
        validate_app_links(app, appspec, strict=True)


def test_strict_env_opt_in(monkeypatch):
    monkeypatch.setenv("DAZZLE_STRICT_LINKS", "1")
    entities = {"Task": SimpleNamespace(name="Task")}
    appspec = _appspec(surfaces=[_list_surface("Task")], entities=entities)
    app = _app(["/app/task"])
    with pytest.raises(RuntimeError):
        validate_app_links(app, appspec)


def test_workspace_region_source_also_requires_detail_route():
    entities = {"Order": SimpleNamespace(name="Order")}
    region = SimpleNamespace(source="Order")
    ws = SimpleNamespace(regions=[region])
    appspec = _appspec(surfaces=[], entities=entities, workspaces=[ws])
    app = _app(["/app/order"])  # region drill-down target /app/order/{id} missing
    problems = validate_app_links(app, appspec)
    assert len(problems) == 1
    assert "Order" in problems[0]


def test_dashed_slug_entity_name():
    entities = {"invoice_line": SimpleNamespace(name="invoice_line")}
    appspec = _appspec(surfaces=[_list_surface("invoice_line")], entities=entities)
    app = _app(["/app/invoice-line", "/app/invoice-line/{id}"])
    assert validate_app_links(app, appspec) == []


def test_idempotent_second_call_returns_cached():
    entities = {"Task": SimpleNamespace(name="Task")}
    appspec = _appspec(surfaces=[_list_surface("Task")], entities=entities)
    app = _app(["/app/task"])
    first = validate_app_links(app, appspec)
    # Second call short-circuits on the state flag even if routes changed.
    app.routes = []
    second = validate_app_links(app, appspec)
    assert first == second
