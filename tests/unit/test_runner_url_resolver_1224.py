"""#1224: TestRunner URL resolver uses route-generator templates per SurfaceKind.

Pre-fix, the test runner hardcoded `/app/workspaces/{name}` for every
surface — 17 TD-* tests failed on v0.71.161 because list/create
surfaces have different URL templates. The fix:

1. ``_build_surface_url_map`` walks the project's appspec and emits one
   URL per workspace + per surface (LIST → /<plural>, CREATE →
   /<plural>/create, workspaces → /app/workspaces/<name>).
2. ``_resolve_surface_url(name)`` returns the URL or None.
3. ``_execute_navigate_to_step`` falls back to the map when
   ``data.route`` is missing.

This test fixture-builds a tiny project on disk, points TestRunner at
it, and asserts the map shape. We don't boot the FastAPI app — just
exercise the resolver.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.testing.test_runner import TestRunner


@pytest.fixture
def tiny_project(tmp_path: Path) -> Path:
    """Minimal project with one workspace, one list surface, one create surface."""
    (tmp_path / "dazzle.toml").write_text("""\
[project]
name = "tinyapp"
version = "0.1.0"
root = "tinyapp.core"

[modules]
paths = ["./dsl"]

[stack]
name = "dnr"
""")
    dsl = tmp_path / "dsl"
    dsl.mkdir()
    (dsl / "app.dsl").write_text("""\
module tinyapp.core
app tinyapp "Tiny App"

persona admin "Admin":
  description: "test admin"

entity Contact "Contact":
  id: uuid pk
  name: str(100) required

  permit:
    create: role(admin)
    read: role(admin)
    list: role(admin)
    update: role(admin)
    delete: role(admin)

  scope:
    create: all
      as: admin
    read: all
      as: admin
    update: all
      as: admin
    delete: all
      as: admin
    list: all
      as: admin

surface contact_list "Contacts":
  uses entity Contact
  mode: list
  section main:
    field name "Name"

surface contact_create "New Contact":
  uses entity Contact
  mode: create
  section main:
    field name "Name"

workspace home_dashboard "Home":
  access: persona(admin)
  purpose: "Test"

  recent_contacts:
    source: Contact
    display: list
""")
    return tmp_path


class TestSurfaceURLMap:
    def test_workspace_resolves_to_app_workspaces_template(self, tiny_project: Path) -> None:
        runner = TestRunner(project_path=tiny_project)
        assert (
            runner.steps._resolve_surface_url("home_dashboard") == "/app/workspaces/home_dashboard"
        )

    def test_list_surface_resolves_to_app_entity_slug_path(self, tiny_project: Path) -> None:
        # #1230: must mirror template_compiler.py's `/app/{entity_slug}` —
        # the JSON API mounts `/contacts` but the UI surface (which the
        # test-runner navigates) is at `/app/contact`.
        runner = TestRunner(project_path=tiny_project)
        assert runner.steps._resolve_surface_url("contact_list") == "/app/contact"

    def test_create_surface_resolves_to_create_path(self, tiny_project: Path) -> None:
        # #1230: matches `/app/{entity_slug}/create` from template_compiler.py.
        runner = TestRunner(project_path=tiny_project)
        assert runner.steps._resolve_surface_url("contact_create") == "/app/contact/create"

    def test_unknown_name_returns_none(self, tiny_project: Path) -> None:
        runner = TestRunner(project_path=tiny_project)
        assert runner.steps._resolve_surface_url("nonexistent_surface") is None

    def test_no_dsl_dir_returns_empty_map_silently(self, tmp_path: Path) -> None:
        """Robustness: if the project has no DSL, resolver returns None
        rather than raising — the runner has API-only test paths that
        don't need URL resolution at all."""
        runner = TestRunner(project_path=tmp_path)
        assert runner.steps._resolve_surface_url("anything") is None

    def test_map_caches_between_calls(self, tiny_project: Path) -> None:
        """Lazy build — second call doesn't re-parse the DSL."""
        runner = TestRunner(project_path=tiny_project)
        runner.steps._resolve_surface_url("home_dashboard")
        assert runner.steps._surface_url_map is not None
        snapshot = runner.steps._surface_url_map
        # Second call should reuse the same map object
        runner.steps._resolve_surface_url("contact_list")
        assert runner.steps._surface_url_map is snapshot
