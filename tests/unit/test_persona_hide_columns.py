"""Cycle 243 — generalised PersonaVariant resolver: ``hide`` field.

Tests the extension of the cycle 240 compile-dict-then-resolve-per-request
pattern to the PersonaVariant ``hide`` field. DSL authors can now write
``for <persona>: hide: col1, col2`` and the template compiler collects
the hide lists into ``TableContext.persona_hide``, which the per-request
resolver in ``page_routes.py`` applies by setting ``hidden=True`` on the
matching columns.

Parser support for ``hide:`` inside ``for <persona>:`` already existed
before cycle 243 (it's been in the DSL since the original PersonaVariant
definition), but was silently dropped at render time.
"""

from pathlib import Path

import pytest

from dazzle.core import ir
from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir import FieldModifier, FieldTypeKind, SurfaceMode

pytest.importorskip("dazzle_ui", reason="dazzle_ui not installed")


# ---------------------------------------------------------------------------
# Parser — existing grammar coverage (regression lock)
# ---------------------------------------------------------------------------


class TestPersonaHideParser:
    """The grammar has always accepted ``for <persona>: hide: ...``.

    These tests lock the parser behaviour in place so the cycle 243
    runtime wiring doesn't silently regress if the parser ever changes.
    """

    def _parse_task_surface(self, dsl_body: str) -> ir.SurfaceSpec:
        dsl = f"""
module testapp
app testapp "Test App"

persona admin "Admin":
  description: "Full system access"

persona member "Team Member":
  description: "Regular user"

entity Task "Task":
  id: uuid pk
  title: str(200) required
  priority: enum[low,medium,high,urgent]=medium
  assigned_to: str(100)

surface task_list "Tasks":
  uses entity Task
  mode: list
  section main:
    field title "Title"
    field priority "Priority"
    field assigned_to "Assignee"
  ux:
{dsl_body}
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        return next(s for s in fragment.surfaces if s.name == "task_list")

    def test_persona_hide_single_field(self) -> None:
        surface = self._parse_task_surface("    for member:\n      hide: assigned_to\n")
        assert surface.ux is not None
        variant = surface.ux.persona_variants[0]
        assert variant.persona == "member"
        assert variant.hide == ["assigned_to"]

    def test_persona_hide_multiple_fields(self) -> None:
        surface = self._parse_task_surface("    for member:\n      hide: assigned_to, priority\n")
        variant = surface.ux.persona_variants[0] if surface.ux else None
        assert variant is not None
        assert variant.hide == ["assigned_to", "priority"]

    def test_persona_hide_coexists_with_empty(self) -> None:
        surface = self._parse_task_surface(
            '    for member:\n      empty: "No tasks assigned yet"\n      hide: assigned_to\n'
        )
        variant = surface.ux.persona_variants[0] if surface.ux else None
        assert variant is not None
        assert variant.empty_message == "No tasks assigned yet"
        assert variant.hide == ["assigned_to"]


# ---------------------------------------------------------------------------
# Compiler — persona_hide dict is populated on TableContext
# ---------------------------------------------------------------------------


class TestPersonaHideCompilation:
    """Template compiler collects persona hide lists into a dict."""

    def _make_entity(self) -> ir.EntitySpec:
        return ir.EntitySpec(
            name="Task",
            title="Task",
            fields=[
                ir.FieldSpec(
                    name="id",
                    type=ir.FieldType(kind=FieldTypeKind.UUID),
                    modifiers=[FieldModifier.PK],
                ),
                ir.FieldSpec(
                    name="title",
                    type=ir.FieldType(kind=FieldTypeKind.STR, max_length=200),
                    is_required=True,
                ),
                ir.FieldSpec(
                    name="priority",
                    type=ir.FieldType(
                        kind=FieldTypeKind.ENUM,
                        enum_values=["low", "medium", "high"],
                    ),
                ),
                ir.FieldSpec(
                    name="assigned_to",
                    type=ir.FieldType(kind=FieldTypeKind.STR, max_length=100),
                ),
            ],
        )

    def _make_list_surface(self, ux: ir.UXSpec | None) -> ir.SurfaceSpec:
        return ir.SurfaceSpec(
            name="task_list",
            title="Tasks",
            entity_ref="Task",
            mode=SurfaceMode.LIST,
            sections=[
                ir.SurfaceSection(
                    name="main",
                    title="",
                    elements=[
                        ir.SurfaceElement(field_name="title", label="Title"),
                        ir.SurfaceElement(field_name="priority", label="Priority"),
                        ir.SurfaceElement(field_name="assigned_to", label="Assignee"),
                    ],
                )
            ],
            actions=[],
            ux=ux,
        )

    def _compile(self, ux: ir.UXSpec | None):
        from dazzle_ui.converters.template_compiler import compile_appspec_to_templates

        appspec = ir.AppSpec(
            name="app",
            title="App",
            module="m",
            domain=ir.DomainSpec(entities=[self._make_entity()]),
            surfaces=[self._make_list_surface(ux)],
            workspaces=[],
        )
        return compile_appspec_to_templates(appspec)["/task"]

    def test_no_variants_produces_empty_dict(self) -> None:
        page = self._compile(ir.UXSpec())
        assert page.table is not None
        assert page.table.persona_hide == {}

    def test_single_persona_hide_populates_dict(self) -> None:
        ux = ir.UXSpec(
            persona_variants=[
                ir.PersonaVariant(persona="member", hide=["assigned_to"]),
            ],
        )
        page = self._compile(ux)
        table = page.table
        assert table is not None
        assert table.persona_hide == {"member": ["assigned_to"]}

    def test_multiple_personas_populate_dict(self) -> None:
        ux = ir.UXSpec(
            persona_variants=[
                ir.PersonaVariant(persona="admin", hide=[]),  # empty — not added
                ir.PersonaVariant(persona="member", hide=["assigned_to", "priority"]),
                ir.PersonaVariant(persona="guest", hide=["assigned_to"]),
            ],
        )
        page = self._compile(ux)
        table = page.table
        assert table is not None
        # admin omitted because its hide list is empty
        assert "admin" not in table.persona_hide
        assert table.persona_hide == {
            "member": ["assigned_to", "priority"],
            "guest": ["assigned_to"],
        }

    def test_empty_hide_list_not_added(self) -> None:
        """A variant with hide=[] should not pollute the dict."""
        ux = ir.UXSpec(
            persona_variants=[
                ir.PersonaVariant(persona="admin", purpose="Admin view"),
            ],
        )
        page = self._compile(ux)
        table = page.table
        assert table is not None
        assert table.persona_hide == {}

    def test_hide_and_empty_coexist_on_same_variant(self) -> None:
        """Cycle 240 empty_message + cycle 243 hide populate both dicts."""
        ux = ir.UXSpec(
            empty_message="No tasks yet",
            persona_variants=[
                ir.PersonaVariant(
                    persona="member",
                    hide=["assigned_to"],
                    empty_message="You have no assigned tasks",
                ),
            ],
        )
        page = self._compile(ux)
        table = page.table
        assert table is not None
        assert table.persona_hide == {"member": ["assigned_to"]}
        assert table.persona_empty_messages == {"member": "You have no assigned tasks"}

    def test_read_only_populates_set(self) -> None:
        """Cycle 244 — read_only variant populates persona_read_only."""
        ux = ir.UXSpec(
            persona_variants=[
                ir.PersonaVariant(persona="member", read_only=True),
                ir.PersonaVariant(persona="admin", read_only=False),
            ],
        )
        page = self._compile(ux)
        table = page.table
        assert table is not None
        assert table.persona_read_only == {"member"}


# ---------------------------------------------------------------------------
# Resolver — the per-request helper that applies the overrides
# ---------------------------------------------------------------------------


class TestApplyPersonaOverrides:
    """``_apply_persona_overrides`` walks user_roles and applies overrides.

    Extracted from the inline page_routes.py block in cycle 243 so the
    resolver logic can be tested in isolation without a request context.
    """

    def _make_table(
        self,
        columns: list[tuple[str, bool]] | None = None,
        persona_empty: dict[str, str] | None = None,
        persona_hide: dict[str, list[str]] | None = None,
        base_empty: str = "No items found.",
    ):
        from dazzle_ui.runtime.template_context import ColumnContext, TableContext

        col_pairs = columns or [("title", False), ("assigned_to", False), ("priority", False)]
        return TableContext(
            entity_name="Task",
            title="Tasks",
            api_endpoint="/tasks",
            columns=[
                ColumnContext(key=key, label=key.title(), type="text", hidden=hidden)
                for key, hidden in col_pairs
            ],
            empty_message=base_empty,
            persona_empty_messages=persona_empty or {},
            persona_hide=persona_hide or {},
        )

    def test_no_roles_is_noop(self) -> None:
        from dazzle_ui.runtime.page_routes import _apply_persona_overrides

        table = self._make_table(persona_hide={"member": ["assigned_to"]})
        _apply_persona_overrides(table, [])
        # No column hidden, base empty preserved
        assert all(not c.hidden for c in table.columns)
        assert table.empty_message == "No items found."

    def test_no_overrides_is_noop(self) -> None:
        from dazzle_ui.runtime.page_routes import _apply_persona_overrides

        table = self._make_table()
        _apply_persona_overrides(table, ["member"])
        assert all(not c.hidden for c in table.columns)

    def test_hide_applies_for_matching_role(self) -> None:
        from dazzle_ui.runtime.page_routes import _apply_persona_overrides

        table = self._make_table(persona_hide={"member": ["assigned_to", "priority"]})
        _apply_persona_overrides(table, ["member"])
        hidden_keys = [c.key for c in table.columns if c.hidden]
        assert sorted(hidden_keys) == ["assigned_to", "priority"]

    def test_hide_does_not_touch_non_matching_columns(self) -> None:
        from dazzle_ui.runtime.page_routes import _apply_persona_overrides

        table = self._make_table(persona_hide={"member": ["assigned_to"]})
        _apply_persona_overrides(table, ["member"])
        title_col = next(c for c in table.columns if c.key == "title")
        assert title_col.hidden is False

    def test_role_prefix_stripped(self) -> None:
        """User roles arrive with ``role_`` prefix from the auth layer."""
        from dazzle_ui.runtime.page_routes import _apply_persona_overrides

        table = self._make_table(persona_hide={"member": ["assigned_to"]})
        _apply_persona_overrides(table, ["role_member"])
        assert next(c for c in table.columns if c.key == "assigned_to").hidden is True

    def test_non_matching_role_is_noop(self) -> None:
        from dazzle_ui.runtime.page_routes import _apply_persona_overrides

        table = self._make_table(persona_hide={"member": ["assigned_to"]})
        _apply_persona_overrides(table, ["admin"])
        assert all(not c.hidden for c in table.columns)

    def test_first_matching_role_wins(self) -> None:
        """Primary persona (first role) wins when multiple match."""
        from dazzle_ui.runtime.page_routes import _apply_persona_overrides

        table = self._make_table(
            persona_hide={
                "member": ["assigned_to"],
                "guest": ["priority"],
            }
        )
        _apply_persona_overrides(table, ["member", "guest"])
        # Only member's overrides applied; guest is ignored because
        # member matched first
        assert next(c for c in table.columns if c.key == "assigned_to").hidden is True
        assert next(c for c in table.columns if c.key == "priority").hidden is False

    def test_empty_message_override_applies(self) -> None:
        """Cycle 240 regression — the pilot still works after refactor."""
        from dazzle_ui.runtime.page_routes import _apply_persona_overrides

        table = self._make_table(persona_empty={"member": "You have no assigned tasks"})
        _apply_persona_overrides(table, ["member"])
        assert table.empty_message == "You have no assigned tasks"

    def test_hide_and_empty_apply_together(self) -> None:
        """Both overrides from a single variant apply atomically."""
        from dazzle_ui.runtime.page_routes import _apply_persona_overrides

        table = self._make_table(
            persona_empty={"member": "You have no assigned tasks"},
            persona_hide={"member": ["assigned_to"]},
        )
        _apply_persona_overrides(table, ["member"])
        assert table.empty_message == "You have no assigned tasks"
        assert next(c for c in table.columns if c.key == "assigned_to").hidden is True

    def test_empty_hide_list_not_processed(self) -> None:
        """Empty list in the dict doesn't accidentally hide all columns."""
        from dazzle_ui.runtime.page_routes import _apply_persona_overrides

        table = self._make_table(persona_hide={"member": []})
        _apply_persona_overrides(table, ["member"])
        assert all(not c.hidden for c in table.columns)

    # --- Cycle 244 — read_only PersonaVariant extension ---

    def _make_mutable_table(
        self,
        persona_read_only: set[str] | None = None,
    ):
        from dazzle_ui.runtime.template_context import ColumnContext, TableContext

        return TableContext(
            entity_name="Task",
            title="Tasks",
            api_endpoint="/tasks",
            columns=[
                ColumnContext(key="title", label="Title", type="text"),
                ColumnContext(key="status", label="Status", type="badge"),
            ],
            create_url="/app/task/create",
            bulk_actions=True,
            inline_editable=["title", "status"],
            persona_read_only=persona_read_only or set(),
        )

    def test_read_only_suppresses_mutations(self) -> None:
        from dazzle_ui.runtime.page_routes import _apply_persona_overrides

        table = self._make_mutable_table(persona_read_only={"member"})
        _apply_persona_overrides(table, ["member"])
        assert table.create_url is None
        assert table.bulk_actions is False
        assert table.inline_editable == []

    def test_read_only_non_matching_persona_preserves_mutations(self) -> None:
        from dazzle_ui.runtime.page_routes import _apply_persona_overrides

        table = self._make_mutable_table(persona_read_only={"member"})
        _apply_persona_overrides(table, ["admin"])
        assert table.create_url == "/app/task/create"
        assert table.bulk_actions is True
        assert table.inline_editable == ["title", "status"]

    def test_read_only_stacks_with_hide(self) -> None:
        """A persona can be both read-only AND have hide overrides."""
        from dazzle_ui.runtime.page_routes import _apply_persona_overrides
        from dazzle_ui.runtime.template_context import ColumnContext, TableContext

        table = TableContext(
            entity_name="Task",
            title="Tasks",
            api_endpoint="/tasks",
            columns=[
                ColumnContext(key="title", label="Title", type="text"),
                ColumnContext(key="assigned_to", label="Assignee", type="text"),
            ],
            create_url="/app/task/create",
            bulk_actions=True,
            inline_editable=["title"],
            persona_hide={"member": ["assigned_to"]},
            persona_read_only={"member"},
        )
        _apply_persona_overrides(table, ["member"])
        # hide applied
        assert next(c for c in table.columns if c.key == "assigned_to").hidden is True
        # read_only applied
        assert table.create_url is None
        assert table.bulk_actions is False
        assert table.inline_editable == []

    def test_read_only_respects_role_prefix(self) -> None:
        from dazzle_ui.runtime.page_routes import _apply_persona_overrides

        table = self._make_mutable_table(persona_read_only={"member"})
        _apply_persona_overrides(table, ["role_member"])
        assert table.create_url is None

    def test_read_only_empty_set_is_noop(self) -> None:
        from dazzle_ui.runtime.page_routes import _apply_persona_overrides

        table = self._make_mutable_table(persona_read_only=set())
        _apply_persona_overrides(table, ["member"])
        assert table.create_url == "/app/task/create"
        assert table.bulk_actions is True
