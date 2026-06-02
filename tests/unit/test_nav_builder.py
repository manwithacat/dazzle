from pathlib import Path

from dazzle.core.linker import build_appspec
from dazzle.core.parser import parse_modules
from dazzle.rbac.matrix import PolicyDecision
from dazzle.ui.converters.nav_builder import (
    NavGroup,
    NavLink,
    NavModel,
    build_all_persona_navs,
    build_anon_nav,
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


# ---------------------------------------------------------------------------
# build_persona_nav — auto-discover fallback (#1324 Task 2.4)
# ---------------------------------------------------------------------------

# DSL with a workspace whose regions source two entities (each with a list
# surface) and a persona with NO `uses nav` → auto-discover fallback path.
_AUTO_DSL = """module test
app TestApp "Test Application"

entity Assignment "Assignment":
  id: uuid pk
  title: str(200) required

entity Submission "Submission":
  id: uuid pk
  name: str(200) required

surface assignment_list "Assignments":
  uses entity Assignment
  mode: list
  section main "Assignments":
    field title "Title"

surface submission_list "Submissions":
  uses entity Submission
  mode: list
  section main "Submissions":
    field name "Name"

workspace classroom "Classroom":
  purpose: "Teaching workspace"

  assignment_list:
    source: Assignment
    display: list

  submission_list:
    source: Submission
    display: list

persona teacher "Teacher":
  role: teacher
"""


def test_auto_discover_when_no_nav_ref(tmp_path: Path):
    appspec = _appspec(_AUTO_DSL, tmp_path)
    persona = _teacher(appspec)

    model = build_persona_nav(appspec, persona, _StubMatrix())

    assert model.auto_discovered is True
    entities = {link.entity for group in model.groups for link in group.links}
    assert "Assignment" in entities
    assert "Submission" in entities


# DSL with a curated nav (teacher) AND a second persona (admin) with no nav.
_ALL_PERSONAS_DSL = """module test
app TestApp "Test Application"

entity Assignment "Assignment":
  id: uuid pk
  title: str(200) required

surface assignment_list "Assignments":
  uses entity Assignment
  mode: list
  section main "Assignments":
    field title "Title"

workspace classroom "Classroom":
  purpose: "Teaching workspace"

  assignment_list:
    source: Assignment
    display: list

nav teaching:
  group "Marking":
    item Assignment

persona teacher "Teacher":
  uses nav teaching

persona admin "Admin":
  role: admin
"""


def test_build_all_persona_navs_keys_by_persona_id(tmp_path: Path):
    appspec = _appspec(_ALL_PERSONAS_DSL, tmp_path)

    navs = build_all_persona_navs(appspec, _StubMatrix())

    assert set(navs.keys()) == {"teacher", "admin"}
    assert navs["teacher"].auto_discovered is False
    assert navs["admin"].auto_discovered is True


# ---------------------------------------------------------------------------
# Workspace-target access filtering (#1324 slice 3a, correctness fix)
# ---------------------------------------------------------------------------

# A curated nav item can target a WORKSPACE name (not an entity). Such items
# must be filtered by WORKSPACE access, not the entity matrix. Here the curated
# nav points at the `classroom` workspace which `teacher` is allowed into.
_WORKSPACE_TARGET_DSL = """module test
app TestApp "Test Application"

entity Assignment "Assignment":
  id: uuid pk
  title: str(200) required

surface assignment_list "Assignments":
  uses entity Assignment
  mode: list
  section main "Assignments":
    field title "Title"

workspace classroom "Classroom":
  purpose: "Teaching workspace"
  access: persona(teacher)

  assignment_list:
    source: Assignment
    display: list

nav teaching:
  group "Spaces":
    item classroom

persona teacher "Teacher":
  uses nav teaching

persona stranger "Stranger":
  uses nav teaching
"""


def test_curated_workspace_target_not_dropped_by_entity_matrix(tmp_path: Path):
    appspec = _appspec(_WORKSPACE_TARGET_DSL, tmp_path)
    persona = _teacher(appspec)

    # The entity matrix would DENY `classroom` as an entity (it isn't one).
    # The old code called matrix.get(role, "classroom", "list") → DENY and
    # dropped the link. Workspace targets must instead be filtered by
    # workspace access, which permits `teacher`.
    matrix = _StubMatrix(deny={("teacher", "classroom")})
    model = build_persona_nav(appspec, persona, matrix)

    all_links = [link for group in model.groups for link in group.links]
    ws_link = next(link for link in all_links if link.entity == "classroom")
    assert ws_link.route == "/workspaces/classroom"


def test_curated_workspace_target_dropped_when_workspace_denied(tmp_path: Path):
    appspec = _appspec(_WORKSPACE_TARGET_DSL, tmp_path)
    persona = next(p for p in appspec.personas if p.id == "stranger")

    # `stranger` is NOT in classroom's `access: persona(teacher)` → the
    # workspace link must be dropped even though the (entity) matrix permits.
    model = build_persona_nav(appspec, persona, _StubMatrix())

    entities = {link.entity for group in model.groups for link in group.links}
    assert "classroom" not in entities


# ---------------------------------------------------------------------------
# build_anon_nav — only anon-safe items (#1324 slice 3a, mirrors #1127)
# ---------------------------------------------------------------------------

# #1127 anon-safety: a workspace is anon-safe iff `workspace_allowed_personas`
# returns None (no persona gate). `open_space` declares no access → anon-safe;
# `gated_space` declares `access: persona(...)` → never anon-safe.
_ANON_DSL = """module test
app TestApp "Test Application"

entity Public "Public":
  id: uuid pk
  title: str(200) required

entity Private "Private":
  id: uuid pk
  name: str(200) required

surface public_list "Public":
  uses entity Public
  mode: list
  section main "Public":
    field title "Title"

surface private_list "Private":
  uses entity Private
  mode: list
  section main "Private":
    field name "Name"

workspace open_space "Open Space":
  purpose: "Open to everyone"

  public_list:
    source: Public
    display: list

workspace gated_space "Gated Space":
  purpose: "Members only"
  access: persona(member)

  private_list:
    source: Private
    display: list

persona member "Member":
  default_workspace: gated_space
"""


def test_build_anon_nav_only_anon_safe(tmp_path: Path):
    appspec = _appspec(_ANON_DSL, tmp_path)

    model = build_anon_nav(appspec, _StubMatrix())

    assert isinstance(model, NavModel)
    assert model.auto_discovered is True
    entities = {link.entity for group in model.groups for link in group.links}
    # `Public` is surfaced by the open (anon-safe) workspace → present.
    assert "Public" in entities
    # `Private` is only behind the gated workspace → never anon-safe.
    assert "Private" not in entities
