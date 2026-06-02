from pathlib import Path

from dazzle.core.linker import build_appspec
from dazzle.core.parser import parse_modules
from dazzle.rbac.matrix import PolicyDecision
from dazzle.ui.converters.nav_builder import (
    NavGroup,
    NavLink,
    NavModel,
    build_persona_nav,
)


def test_nav_model_is_frozen_and_holds_groups():
    link = NavLink(
        label="Assignments", route="/a/list/Assignment", icon="file", entity="Assignment"
    )
    group = NavGroup(label="Marking", icon=None, collapsed=False, links=(link,))
    model = NavModel(groups=(group,), auto_discovered=False)
    assert model.groups[0].links[0].entity == "Assignment"
    assert model.auto_discovered is False


# ---------------------------------------------------------------------------
# build_persona_nav — curated path + FR-3 access filter (#1324 Task 2.2/2.3)
# ---------------------------------------------------------------------------


class _StubMatrix:
    """Minimal AccessMatrix stand-in: every (role, entity) PERMITs unless denied."""

    def __init__(self, deny: set[tuple[str, str]] | None = None):
        self._deny = deny or set()

    def get(self, role: str, entity: str, op: str) -> PolicyDecision:
        return PolicyDecision.DENY if (role, entity) in self._deny else PolicyDecision.PERMIT


# DSL with two entities, a list surface each, a curated nav grouping both
# items, and a persona bound to that nav via `uses nav`.
_CURATED_DSL = """module test
app TestApp "Test Application"

entity Assignment "Assignment":
  id: uuid pk
  title: str(200) required

entity Secret "Secret":
  id: uuid pk
  name: str(200) required

surface assignment_list "Assignments":
  uses entity Assignment
  mode: list
  section main "Assignments":
    field title "Title"

surface secret_list "Secrets":
  uses entity Secret
  mode: list
  section main "Secrets":
    field name "Name"

nav teaching:
  group "Marking":
    item Assignment
    item Secret

persona teacher "Teacher":
  uses nav teaching
"""


def _appspec(dsl: str, tmp_path: Path):
    dsl_dir = tmp_path / "dsl"
    dsl_dir.mkdir()
    (dsl_dir / "app.dsl").write_text(dsl)
    (tmp_path / "dazzle.toml").write_text(
        '[project]\nname = "test"\nversion = "0.1.0"\nroot = "test"\n[modules]\npaths = ["./dsl"]\n'
    )
    modules = parse_modules([dsl_dir / "app.dsl"])
    return build_appspec(modules, "test")


def _teacher(appspec):
    return next(p for p in appspec.personas if p.id == "teacher")


def test_curated_nav_resolves_navspec_groups(tmp_path: Path):
    appspec = _appspec(_CURATED_DSL, tmp_path)
    persona = _teacher(appspec)

    model = build_persona_nav(appspec, persona, _StubMatrix())

    assert model.auto_discovered is False
    assert len(model.groups) == 1
    group = model.groups[0]
    assert group.label == "Marking"
    # Both entities are permitted, both have list surfaces → both link.
    assignment_link = next(link for link in group.links if link.entity == "Assignment")
    assert assignment_link.entity == "Assignment"
    assert assignment_link.route is not None


def test_access_filter_drops_denied_entity(tmp_path: Path):
    appspec = _appspec(_CURATED_DSL, tmp_path)
    persona = _teacher(appspec)

    # FR-3: deny `teacher` list access on Secret → its link must vanish.
    matrix = _StubMatrix(deny={("teacher", "Secret")})
    model = build_persona_nav(appspec, persona, matrix)

    entities = {link.entity for group in model.groups for link in group.links}
    assert "Assignment" in entities
    assert "Secret" not in entities
