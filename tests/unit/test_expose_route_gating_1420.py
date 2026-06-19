"""#1420 Slice 2 / S2.2 — `expose:` suppresses generated REST routes.

An entity declaring `expose: list` should emit only the list GET route — no
create (POST), read (GET /{id}), update (PUT), or delete. Absent `expose:`
keeps all routes (backward compatible).
"""

from __future__ import annotations

from pathlib import Path

from dazzle.back.converters.surface_converter import convert_surfaces_to_services
from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir import ModuleIR
from dazzle.core.linker import build_appspec

_BASE = """module t
app t "Test"
entity Job "Job":
  id: uuid pk
  title: str(80)
{expose}

surface job_list "Jobs":
  uses entity Job
  mode: list
  section main:
    field title "Title"

surface job_new "New Job":
  uses entity Job
  mode: create
  section main:
    field title "Title"
"""


def _endpoints(expose_line: str):
    dsl = _BASE.format(expose=expose_line)
    mod_name, app_name, app_title, app_config, uses, fragment = parse_dsl(dsl, Path("test.dsl"))
    module = ModuleIR(
        name=mod_name or "t",
        file=Path("test.dsl"),
        app_name=app_name,
        app_title=app_title,
        app_config=app_config,
        uses=uses,
        fragment=fragment,
    )
    app = build_appspec([module], module.name)
    _services, endpoints = convert_surfaces_to_services(app.surfaces, app.domain)
    # (method, has-{id}) pairs for Job paths
    return {(ep.method.value, "{id}" in ep.path) for ep in endpoints if "/jobs" in ep.path.lower()}


class TestExposeRouteGating:
    def test_expose_list_only_emits_list_get(self) -> None:
        eps = _endpoints("  expose: list")
        assert ("GET", False) in eps  # list
        assert ("POST", False) not in eps  # create suppressed
        assert ("GET", True) not in eps  # read suppressed
        assert ("DELETE", True) not in eps  # delete suppressed

    def test_absent_expose_keeps_all_ops(self) -> None:
        eps = _endpoints("")
        assert ("GET", False) in eps  # list
        assert ("POST", False) in eps  # create (from job_new surface)
        assert ("DELETE", True) in eps  # delete (auto from list surface)

    def test_expose_none_suppresses_all_generated_rest(self) -> None:
        eps = _endpoints("  expose: none")
        assert eps == set()
