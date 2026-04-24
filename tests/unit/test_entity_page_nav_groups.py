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
from dazzle_ui.converters.template_compiler import compile_appspec_to_templates


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


class TestEntityPageNavGroups:
    def test_entity_list_ctx_inherits_nav_groups(self, tmp_path: Path) -> None:
        """Entity-list surface contexts should have nav_groups populated
        from workspace nav_group declarations."""
        spec = _appspec(_DSL, tmp_path)
        contexts = compile_appspec_to_templates(spec, app_prefix="/app")
        user_list_route = "/app/user"
        assert user_list_route in contexts, list(contexts.keys())
        ctx = contexts[user_list_route]
        # Before the fix this was []. After: one group from the workspace.
        assert ctx.nav_groups, f"expected nav_groups populated; got {ctx.nav_groups!r}"
        labels = [g["label"] for g in ctx.nav_groups]
        assert "Operations" in labels

    def test_nav_group_children_have_entity_routes(self, tmp_path: Path) -> None:
        spec = _appspec(_DSL, tmp_path)
        contexts = compile_appspec_to_templates(spec, app_prefix="/app")
        ctx = contexts["/app/user"]
        ops = next(g for g in ctx.nav_groups if g["label"] == "Operations")
        routes = {c["route"] for c in ops["children"]}
        assert "/app/user" in routes
        assert "/app/task" in routes

    def test_workspace_and_entity_pages_share_group_structure(self, tmp_path: Path) -> None:
        """Both surface contexts (user_list, task_list) pick up the same
        nav_groups — the sidebar is continuous across the two page types."""
        spec = _appspec(_DSL, tmp_path)
        contexts = compile_appspec_to_templates(spec, app_prefix="/app")
        user_ctx = contexts["/app/user"]
        task_ctx = contexts["/app/task"]
        assert user_ctx.nav_groups == task_ctx.nav_groups

    def test_deduplicates_across_workspaces(self, tmp_path: Path) -> None:
        """Two workspaces declaring the same nav_group label should not
        produce duplicates on entity-list pages."""
        dsl = (
            _DSL
            + """
workspace second_dashboard "Second":
  nav_group "Operations":
    Task
  tasks:
    source: Task
"""
        )
        spec = _appspec(dsl, tmp_path)
        contexts = compile_appspec_to_templates(spec, app_prefix="/app")
        ctx = contexts["/app/user"]
        labels = [g["label"] for g in ctx.nav_groups]
        # Operations should appear once despite being declared twice.
        assert labels.count("Operations") == 1

    def test_ctx_nav_groups_field_always_exists(self, tmp_path: Path) -> None:
        """Every PageContext has nav_groups (possibly empty) so templates
        don't explode when a workspace doesn't declare any."""
        dsl = """module t
app T "T"
entity Task "Task":
  id: uuid pk
surface task_list "Tasks":
  uses entity Task
  mode: list
"""
        spec = _appspec(dsl, tmp_path)
        contexts = compile_appspec_to_templates(spec, app_prefix="/app")
        for ctx in contexts.values():
            # Field exists — framework may auto-inject admin workspaces
            # with their own nav_groups, so we only assert the attribute
            # is present and is a list.
            assert isinstance(ctx.nav_groups, list)
