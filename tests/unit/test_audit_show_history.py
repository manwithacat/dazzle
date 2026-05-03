"""Tests for #956 cycle 8 — `show_history:` DSL flag + region template.

Cycle 7 wired the runtime layer (visibility gate + load_history
loader). Cycle 8 adds the user-facing surface:

  * `SurfaceSpec.show_history: bool` field — default False
  * Parser support for `show_history: true|false` inside surface
    blocks
  * Jinja template `audit_history.html` that renders
    HistoryChange list

These tests verify the IR field round-trip, the parser, and a
basic Jinja template smoke pass (no real loader call — that's
covered by cycle-7 tests).
"""

from __future__ import annotations

import pathlib
import textwrap
from dataclasses import dataclass

import pytest


@pytest.fixture()
def parse_dsl():
    from dazzle.core.linker import build_appspec
    from dazzle.core.parser import parse_modules

    def _parse(source: str, tmp_path: pathlib.Path):
        dsl_path = tmp_path / "test.dsl"
        dsl_path.write_text(textwrap.dedent(source).lstrip())
        modules = parse_modules([dsl_path])
        return build_appspec(modules, "test")

    return _parse


# ---------------------------------------------------------------------------
# IR field
# ---------------------------------------------------------------------------


class TestSurfaceSpecField:
    def test_default_false(self):
        from dazzle.core.ir import SurfaceMode, SurfaceSpec

        s = SurfaceSpec(name="x", mode=SurfaceMode.VIEW)
        assert s.show_history is False

    def test_explicit_true(self):
        from dazzle.core.ir import SurfaceMode, SurfaceSpec

        s = SurfaceSpec(name="x", mode=SurfaceMode.VIEW, show_history=True)
        assert s.show_history is True


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


class TestParser:
    def test_show_history_true_parses(self, parse_dsl, tmp_path):
        appspec = parse_dsl(
            """
            module test
            app a "A"

            entity Manuscript "M":
              id: uuid pk
              status: str(50) required

            surface manuscript_detail "Detail":
              uses entity Manuscript
              mode: view
              show_history: true
              section main:
                field status "Status"
            """,
            tmp_path,
        )
        s = next(s for s in appspec.surfaces if s.name == "manuscript_detail")
        assert s.show_history is True

    def test_show_history_false_parses(self, parse_dsl, tmp_path):
        appspec = parse_dsl(
            """
            module test
            app a "A"

            entity Manuscript "M":
              id: uuid pk
              status: str(50) required

            surface manuscript_detail "Detail":
              uses entity Manuscript
              mode: view
              show_history: false
              section main:
                field status "Status"
            """,
            tmp_path,
        )
        s = next(s for s in appspec.surfaces if s.name == "manuscript_detail")
        assert s.show_history is False

    def test_show_history_omitted_defaults_false(self, parse_dsl, tmp_path):
        appspec = parse_dsl(
            """
            module test
            app a "A"

            entity Manuscript "M":
              id: uuid pk
              status: str(50) required

            surface manuscript_detail "Detail":
              uses entity Manuscript
              mode: view
              section main:
                field status "Status"
            """,
            tmp_path,
        )
        s = next(s for s in appspec.surfaces if s.name == "manuscript_detail")
        assert s.show_history is False


# ---------------------------------------------------------------------------
# Template smoke
# ---------------------------------------------------------------------------


@dataclass
class _Field:
    field_name: str
    operation: str = "update"
    decoded_before: object = None
    decoded_after: object = None


@dataclass
class _Change:
    at: str
    by_user_id: str | None
    operation: str
    entity_type: str = "Manuscript"
    entity_id: str = "abc"
    fields: list[_Field] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.fields is None:
            self.fields = []


@pytest.fixture()
def template_env():
    from jinja2 import Environment, FileSystemLoader

    template_dir = (
        pathlib.Path(__file__).parent.parent.parent
        / "src"
        / "dazzle_ui"
        / "templates"
        / "workspace"
        / "regions"
    )
    return Environment(  # nosemgrep: direct-use-of-jinja2
        loader=FileSystemLoader(template_dir),
        autoescape=True,
    )


class TestAuditHistoryTemplate:
    def test_renders_change_list(self, template_env):
        change = _Change(
            at="2026-05-03T12:00:00",
            by_user_id="user-1",
            operation="update",
            fields=[_Field(field_name="status", decoded_before="draft", decoded_after="submitted")],
        )
        tmpl = template_env.get_template("audit_history.html")
        html = tmpl.render(audit_history=[change])  # nosemgrep: direct-use-of-jinja2
        assert "user-1" in html
        assert "status" in html
        assert "draft" in html
        assert "submitted" in html
        assert "→" in html  # update arrow

    def test_renders_empty_state(self, template_env):
        tmpl = template_env.get_template("audit_history.html")
        html = tmpl.render(audit_history=[])  # nosemgrep: direct-use-of-jinja2
        assert "No history yet" in html

    def test_create_omits_arrow(self, template_env):
        change = _Change(
            at="2026-05-03T12:00:00",
            by_user_id="user-1",
            operation="create",
            fields=[_Field(field_name="status", operation="create", decoded_after="draft")],
        )
        tmpl = template_env.get_template("audit_history.html")
        html = tmpl.render(audit_history=[change])  # nosemgrep: direct-use-of-jinja2
        # Create only shows the "after" value — no before/arrow.
        assert "draft" in html
        assert "→" not in html

    def test_delete_omits_arrow_shows_before(self, template_env):
        change = _Change(
            at="2026-05-03T12:00:00",
            by_user_id="user-1",
            operation="delete",
            fields=[_Field(field_name="status", operation="delete", decoded_before="draft")],
        )
        tmpl = template_env.get_template("audit_history.html")
        html = tmpl.render(audit_history=[change])  # nosemgrep: direct-use-of-jinja2
        assert "draft" in html
        assert "→" not in html

    def test_system_write_renders(self, template_env):
        change = _Change(
            at="2026-05-03T12:00:00",
            by_user_id=None,
            operation="update",
            fields=[_Field(field_name="status", decoded_before="d", decoded_after="s")],
        )
        tmpl = template_env.get_template("audit_history.html")
        html = tmpl.render(audit_history=[change])  # nosemgrep: direct-use-of-jinja2
        # Falls back to "system" label rather than blank.
        assert "system" in html
