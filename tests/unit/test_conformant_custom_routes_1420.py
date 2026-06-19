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
