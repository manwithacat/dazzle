"""#1420 Slice 2 / S2.4 — a surface whose op is not in the entity's `expose:` is a
validate error (no silent contradiction: the surface would render but its route
would be suppressed)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir import ModuleIR
from dazzle.core.linker import build_appspec
from dazzle.core.validation.entities import validate_expose_surface_consistency

_DSL = """module t
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


def _errors(expose_line: str) -> list[str]:
    dsl = _DSL.format(expose=expose_line)
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
    errors, _warnings = validate_expose_surface_consistency(app)
    return errors


class TestExposeSurfaceConsistency:
    def test_create_surface_excluded_op_is_error(self) -> None:
        # expose: list omits create, but job_new is a create surface → error.
        errors = _errors("  expose: list")
        assert any("job_new" in e and "create" in e for e in errors)

    def test_surface_op_in_expose_is_ok(self) -> None:
        # expose includes both list and create → no contradiction.
        assert _errors("  expose: list, create") == []

    def test_absent_expose_is_ok(self) -> None:
        assert _errors("") == []
