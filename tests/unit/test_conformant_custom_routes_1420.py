"""#1420 Slice 3 — conformant custom routes (ADR-0040).

S3.1: the `# dazzle:implements Entity.op via <param>` header (#1126) parses into a
structured binding on the route-override descriptor.
S3.2: a route-override that shadows a generated entity CRUD route but carries no
binding is a conformance violation.
"""

from __future__ import annotations

from pathlib import Path


def _write_route(routes_dir: Path, name: str, header: str, *, via_param: bool = False) -> None:
    sig = "id: str" if via_param else ""
    routes_dir.joinpath(f"{name}.py").write_text(
        f"{header}\n"
        "from fastapi import Request\n"
        "from fastapi.responses import HTMLResponse\n\n"
        f"async def handler(request: Request{', ' + sig if sig else ''}):\n"
        "    return HTMLResponse('ok')\n"
    )


class TestImplementsBindingParses:
    """S3.1 — the binding header parses into implements_entity/op/via."""

    def test_implements_header_populates_descriptor(self, tmp_path: Path) -> None:
        from dazzle.back.runtime.route_overrides import discover_route_overrides

        _write_route(
            tmp_path,
            "task_update",
            "# dazzle:route-override PUT /tasks/{id}\n# dazzle:implements Task.update via id",
            via_param=True,
        )
        descs = discover_route_overrides(tmp_path)
        assert len(descs) == 1
        d = descs[0]
        assert (d.implements_entity, d.implements_op, d.implements_via) == ("Task", "update", "id")

    def test_no_implements_header_leaves_binding_none(self, tmp_path: Path) -> None:
        from dazzle.back.runtime.route_overrides import discover_route_overrides

        _write_route(tmp_path, "task_post", "# dazzle:route-override POST /tasks")
        d = discover_route_overrides(tmp_path)[0]
        assert d.implements_entity is None
        assert d.implements_op is None


def _desc(method: str, path: str, *, entity=None, op=None, via=None):
    from dazzle.back.runtime.route_overrides import RouteOverrideDescriptor

    return RouteOverrideDescriptor(
        method=method,
        path=path,
        source_path=Path("routes/x.py"),
        handler=lambda: None,
        implements_entity=entity,
        implements_op=op,
        implements_via=via,
    )


class TestConformanceCheck:
    """S3.2 — an unbound override that shadows a generated entity route is a violation."""

    _GENERATED = {("PUT", "/tasks/{id}"), ("POST", "/tasks"), ("GET", "/tasks")}

    def test_unbound_shadowing_override_is_violation(self) -> None:
        from dazzle.back.runtime.route_overrides import find_unbound_shadowing_overrides

        v = find_unbound_shadowing_overrides([_desc("PUT", "/tasks/{id}")], self._GENERATED)
        assert len(v) == 1
        assert "PUT /tasks/{id}" in v[0]

    def test_bound_shadowing_override_is_ok(self) -> None:
        from dazzle.back.runtime.route_overrides import find_unbound_shadowing_overrides

        bound = _desc("PUT", "/tasks/{id}", entity="Task", op="update", via="id")
        assert find_unbound_shadowing_overrides([bound], self._GENERATED) == []

    def test_unbound_non_shadowing_override_is_ok(self) -> None:
        from dazzle.back.runtime.route_overrides import find_unbound_shadowing_overrides

        # A custom /reports route that doesn't shadow any generated entity route.
        assert find_unbound_shadowing_overrides([_desc("GET", "/reports")], self._GENERATED) == []


class TestRawDbScanner:
    """S3.3 / ADR-0040 D4 — the residue lint: raw DB access in a custom handler."""

    def test_raw_sql_execute_is_flagged(self) -> None:
        from dazzle.back.runtime.route_overrides import scan_handler_for_raw_db

        src = (
            "async def handler(request, id: str):\n"
            "    async with conn() as c:\n"
            "        await c.execute('DELETE FROM Task WHERE id = %s', (id,))\n"
        )
        assert scan_handler_for_raw_db(src)  # non-empty → flagged

    def test_direct_repository_construction_is_flagged(self) -> None:
        from dazzle.back.runtime.route_overrides import scan_handler_for_raw_db

        src = (
            "async def handler(request):\n    repo = Repository(Task, db)\n    return repo.list()\n"
        )
        assert scan_handler_for_raw_db(src)

    def test_check_entity_op_handler_is_clean(self) -> None:
        from dazzle.back.runtime.route_overrides import scan_handler_for_raw_db

        src = (
            "from dazzle.back.runtime.policy import check_entity_op\n"
            "async def handler(request, id: str):\n"
            "    await check_entity_op(request, 'Task', 'delete', row_id=id)\n"
            "    return {'ok': True}\n"
        )
        assert scan_handler_for_raw_db(src) == []
