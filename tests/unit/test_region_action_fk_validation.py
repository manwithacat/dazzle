"""Cross-entity region `action:` FK validation (#861).

When a workspace region sourced from entity A declares ``action: <surface>``
and that surface is bound to a different entity B, the runtime needs a
single FK field on A referencing B to thread the row ID into the action
URL. If zero or multiple candidates exist, the action silently misfires.
The validator now flags both cases as errors at ``dazzle validate`` time.
"""

from __future__ import annotations

from pathlib import Path

from dazzle.core.linker import build_appspec
from dazzle.core.lint import lint_appspec
from dazzle.core.parser import parse_modules
from dazzle.core.validator import validate_workspace_region_actions


def _appspec(dsl: str, tmp_path: Path):
    dsl_dir = tmp_path / "dsl"
    dsl_dir.mkdir()
    (dsl_dir / "app.dsl").write_text(dsl)
    (tmp_path / "dazzle.toml").write_text(
        '[project]\nname = "t"\nversion = "0.1.0"\nroot = "t"\n[modules]\npaths = ["./dsl"]\n'
    )
    modules = parse_modules([dsl_dir / "app.dsl"])
    return build_appspec(modules, "t")


class TestRegionActionFKValidation:
    def test_same_entity_action_is_ok(self, tmp_path: Path) -> None:
        """Action on a surface bound to the same entity needs no FK."""
        dsl = """module t
app T "T"

entity Task "Task":
  id: uuid pk
  title: str(200)

surface task_list "Tasks":
  uses entity Task
  mode: list

surface task_edit "Edit Task":
  uses entity Task
  mode: edit

workspace w "W":
  tasks:
    source: Task
    action: task_edit
"""
        spec = _appspec(dsl, tmp_path)
        errors, _ = validate_workspace_region_actions(spec)
        assert errors == []

    def test_cross_entity_action_with_single_fk_is_ok(self, tmp_path: Path) -> None:
        """A single FK from source → target resolves unambiguously."""
        dsl = """module t
app T "T"

entity Customer "Customer":
  id: uuid pk
  name: str(200)

entity Order "Order":
  id: uuid pk
  customer: ref Customer
  total: int

surface order_list "Orders":
  uses entity Order
  mode: list

surface customer_edit "Edit Customer":
  uses entity Customer
  mode: edit

workspace w "W":
  orders:
    source: Order
    action: customer_edit
"""
        spec = _appspec(dsl, tmp_path)
        errors, _ = validate_workspace_region_actions(spec)
        assert errors == [], errors

    def test_cross_entity_action_with_no_fk_errors(self, tmp_path: Path) -> None:
        """Zero FK candidates is an error."""
        dsl = """module t
app T "T"

entity Customer "Customer":
  id: uuid pk
  name: str(200)

entity Order "Order":
  id: uuid pk
  total: int

surface order_list "Orders":
  uses entity Order
  mode: list

surface customer_edit "Edit Customer":
  uses entity Customer
  mode: edit

workspace w "W":
  orders:
    source: Order
    action: customer_edit
"""
        spec = _appspec(dsl, tmp_path)
        errors, _ = validate_workspace_region_actions(spec)
        assert any("no FK field referencing 'Customer'" in e for e in errors), errors

    def test_cross_entity_action_with_ambiguous_fk_errors(self, tmp_path: Path) -> None:
        """Two FK candidates is an error — runtime can't pick automatically."""
        dsl = """module t
app T "T"

entity Person "Person":
  id: uuid pk
  name: str(200)

entity Message "Message":
  id: uuid pk
  sender: ref Person
  recipient: ref Person
  body: str(500)

surface msg_list "Messages":
  uses entity Message
  mode: list

surface person_edit "Edit Person":
  uses entity Person
  mode: edit

workspace w "W":
  inbox:
    source: Message
    action: person_edit
"""
        spec = _appspec(dsl, tmp_path)
        errors, _ = validate_workspace_region_actions(spec)
        assert any("multiple FK fields" in e for e in errors), errors
        assert any("sender" in e and "recipient" in e for e in errors), errors

    def test_error_surfaces_via_lint_appspec(self, tmp_path: Path) -> None:
        """The new check runs in the main lint pass (not only extended mode)."""
        dsl = """module t
app T "T"

entity Customer "Customer":
  id: uuid pk
  name: str(200)

entity Order "Order":
  id: uuid pk
  total: int

surface order_list "Orders":
  uses entity Order
  mode: list

surface customer_edit "Edit Customer":
  uses entity Customer
  mode: edit

workspace w "W":
  orders:
    source: Order
    action: customer_edit
"""
        spec = _appspec(dsl, tmp_path)
        errors, _warnings, _rel = lint_appspec(spec, extended=False)
        assert any("no FK field referencing 'Customer'" in e for e in errors), errors
