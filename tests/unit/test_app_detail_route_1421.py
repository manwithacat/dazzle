"""#1421 — the app-shell detail route `/app/<slug>/{id}` must exist for every
entity whose list emits a `detail_url` row link.

Regression: a list surface (and the workspace list-region) emits row links to
`/app/<slug>/{id}`, but that page route was only mounted when the entity had an
explicit `mode: view` surface — so list-only entities 404'd on drill-to-detail.
The fix synthesizes a default detail page-context for list entities lacking a
VIEW surface (mirroring the converter's auto-READ at `/<plural>/{id}`).
"""

from __future__ import annotations

from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir import ModuleIR
from dazzle.core.linker import build_appspec
from dazzle.http.runtime.page_routes import create_page_routes


def _appspec(dsl: str):
    n, a, t, c, u, frag = parse_dsl(dsl, Path("t.dsl"))
    return build_appspec(
        [
            ModuleIR(
                name=n or "t",
                file=Path("t.dsl"),
                app_name=a,
                app_title=t,
                app_config=c,
                uses=u,
                fragment=frag,
            )
        ],
        "t",
    )


def _reg_paths(appspec) -> set[str]:
    router = create_page_routes(appspec, app_prefix="/app")
    return {getattr(rt, "path", "") for rt in router.routes}


_LIST_ONLY = """module t
app t "T"
entity Job "Job":
  id: uuid pk
  title: str(80)
surface job_list "Jobs":
  uses entity Job
  mode: list
  section main:
    field title "Title"
"""


class TestAppDetailRoute:
    def test_list_only_entity_has_app_detail_route(self) -> None:
        # Reg paths are app_prefix-stripped; mounted at /app → /app/job/{id}.
        assert "/job/{id}" in _reg_paths(_appspec(_LIST_ONLY))

    def test_every_emitted_detail_url_has_a_route(self) -> None:
        """Link↔route gate: for every entity with a list surface, the
        `/app/<slug>/{id}` detail link the framework emits must resolve."""
        dsl = (
            _LIST_ONLY
            + """
entity Note "Note":
  id: uuid pk
  body: str(200)
surface note_list "Notes":
  uses entity Note
  mode: list
  section main:
    field body "Body"
"""
        )
        appspec = _appspec(dsl)
        reg = _reg_paths(appspec)
        for entity in appspec.domain.entities:
            slug = entity.name.lower().replace("_", "-")
            # Only entities that have a list surface advertise a detail_url.
            has_list = any(
                s.entity_ref == entity.name
                and str(s.mode) == "SurfaceMode.LIST"
                or (s.entity_ref == entity.name and getattr(s.mode, "value", "") == "list")
                for s in appspec.surfaces
            )
            if has_list:
                assert f"/{slug}/{{id}}" in reg, f"{entity.name}: detail route missing"
