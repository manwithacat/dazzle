"""Entity-list pages inherit workspace nav_groups (#863).

Before this fix, only workspace pages (`/app/workspaces/<ws>`) had
collapsible `nav_group` sections in the sidebar. Entity-list pages
(`/app/<entity>`) used a different code path (`template_compiler.py`)
that never populated `nav_groups` on the PageContext — so clicking
into an entity collapsed the sidebar's group structure.

The fix threads the workspace `nav_group` declarations through
`template_compiler.build_page_contexts` so entity-list and workspace
pages render the same sidebar shape.
"""

from __future__ import annotations

from pathlib import Path

from dazzle.core.linker import build_appspec
from dazzle.core.parser import parse_modules


def _appspec(dsl: str, tmp_path: Path):
    dsl_dir = tmp_path / "dsl"
    dsl_dir.mkdir()
    (dsl_dir / "app.dsl").write_text(dsl)
    (tmp_path / "dazzle.toml").write_text(
        '[project]\nname = "t"\nversion = "0.1.0"\nroot = "t"\n[modules]\npaths = ["./dsl"]\n'
    )
    modules = parse_modules([dsl_dir / "app.dsl"])
    return build_appspec(modules, "t")


_DSL = """module t
app T "T"

entity User "User":
  id: uuid pk
  email: str(200)

entity Task "Task":
  id: uuid pk
  title: str(200)

surface user_list "Users":
  uses entity User
  mode: list

surface task_list "Tasks":
  uses entity Task
  mode: list

workspace admin_dashboard "Admin Dashboard":
  nav_group "Operations" icon=settings:
    User
    Task
  users:
    source: User
  tasks:
    source: Task
"""


def test_curated_group_is_in_single_unrestricted_model(tmp_path: Path) -> None:
    from dazzle.page.converters.nav_builder import build_unrestricted_nav

    spec = _appspec(_DSL, tmp_path)
    model = build_unrestricted_nav(spec)
    ops = next(group for group in model.groups if group.label == "Operations")
    assert {link.route for link in ops.links} == {"/list/User", "/list/Task"}
    assert all(not link.route.endswith("/missing") for link in ops.links)


_DSL_AUTO_DISCOVERY_873 = """module t
app T "T"

entity User "User":
  id: uuid pk
  email: str(200)

entity Task "Task":
  id: uuid pk
  title: str(200)

entity ClassEnrolment "Class Enrolment":
  id: uuid pk
  student: ref User required

surface user_list "Users":
  uses entity User
  mode: list

surface task_list "Tasks":
  uses entity Task
  mode: list

surface class_enrolment_list "Class Enrolments":
  uses entity ClassEnrolment
  mode: list

workspace teacher_workspace "Teacher":
  nav_group "My Classes" icon=users:
    Task
  my_class_pupils:
    source: ClassEnrolment
"""


def test_curated_group_suppresses_region_auto_discovery(tmp_path: Path) -> None:
    from dazzle.page.converters.nav_builder import build_unrestricted_nav

    spec = _appspec(_DSL_AUTO_DISCOVERY_873, tmp_path)
    routes = {link.route for group in build_unrestricted_nav(spec).groups for link in group.links}
    assert "/list/ClassEnrolment" not in routes


def test_zero_config_workspace_discovers_region_source(tmp_path: Path) -> None:
    from dazzle.page.converters.nav_builder import build_unrestricted_nav

    dsl = 'module t\napp T "T"\nentity Task "Task":\n  id: uuid pk\nsurface task_list "Tasks":\n  uses entity Task\n  mode: list\nworkspace dashboard "Dashboard":\n  tasks:\n    source: Task\n'
    spec = _appspec(dsl, tmp_path)
    routes = {link.route for group in build_unrestricted_nav(spec).groups for link in group.links}
    assert "/list/Task" in routes
