"""Tests for param declaration and param() reference parsing."""

from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir.params import ParamRef


def _parse(dsl_text: str):
    """Helper to parse DSL text and return the fragment."""
    _, _, _, _, _, fragment = parse_dsl(dsl_text, Path("test.dsl"))
    return fragment


class TestParamDeclaration:
    """Tests for parsing param declarations."""

    def test_basic_param(self):
        dsl = """\
module test_mod
app test "Test"

param ui.page_size "Items per page":
  type: int
  default: 25
  scope: tenant
"""
        fragment = _parse(dsl)
        assert len(fragment.params) == 1
        p = fragment.params[0]
        assert p.key == "ui.page_size"
        assert p.param_type == "int"
        assert p.default == 25
        assert p.scope == "tenant"
        assert p.description == "Items per page"

    def test_param_with_constraints(self):
        dsl = """\
module test_mod
app test "Test"

param heatmap.rag.thresholds "RAG boundary percentages":
  type: list[float]
  default: [40, 60]
  scope: tenant
  category: "Assessment Display"
  constraints:
    min_length: 2
    max_length: 5
    ordered: ascending
    range: [0, 100]
"""
        fragment = _parse(dsl)
        assert len(fragment.params) == 1
        p = fragment.params[0]
        assert p.key == "heatmap.rag.thresholds"
        assert p.param_type == "list[float]"
        assert p.default == [40.0, 60.0]
        assert p.scope == "tenant"
        assert p.category == "Assessment Display"
        assert p.constraints is not None
        assert p.constraints.min_length == 2
        assert p.constraints.max_length == 5
        assert p.constraints.ordered == "ascending"
        assert p.constraints.range == [0.0, 100.0]

    def test_param_dotted_key_three_segments(self):
        dsl = """\
module test_mod
app test "Test"

param display.grid.columns "Grid columns":
  type: int
  default: 4
  scope: user
"""
        fragment = _parse(dsl)
        p = fragment.params[0]
        assert p.key == "display.grid.columns"

    def test_param_with_category(self):
        dsl = """\
module test_mod
app test "Test"

param notifications.email_enabled "Enable email":
  type: bool
  default: true
  scope: user
  category: "Notification Settings"
"""
        fragment = _parse(dsl)
        p = fragment.params[0]
        assert p.category == "Notification Settings"
        assert p.param_type == "bool"
        assert p.default is True

    def test_param_with_sensitive_flag(self):
        dsl = """\
module test_mod
app test "Test"

param integrations.api_key "External API key":
  type: str
  default: ""
  scope: tenant
  sensitive: true
"""
        fragment = _parse(dsl)
        p = fragment.params[0]
        assert p.sensitive is True
        assert p.param_type == "str"

    def test_param_string_default(self):
        dsl = """\
module test_mod
app test "Test"

param ui.theme "Theme":
  type: str
  default: "light"
  scope: user
"""
        fragment = _parse(dsl)
        p = fragment.params[0]
        assert p.default == "light"

    def test_param_float_default(self):
        dsl = """\
module test_mod
app test "Test"

param scoring.threshold "Score threshold":
  type: float
  default: 0.75
  scope: system
"""
        fragment = _parse(dsl)
        p = fragment.params[0]
        assert p.default == 0.75
        assert p.scope == "system"

    def test_multiple_params_in_one_module(self):
        dsl = """\
module test_mod
app test "Test"

param ui.page_size "Items per page":
  type: int
  default: 25
  scope: tenant

param ui.theme "Theme":
  type: str
  default: "dark"
  scope: user
"""
        fragment = _parse(dsl)
        assert len(fragment.params) == 2
        assert fragment.params[0].key == "ui.page_size"
        assert fragment.params[1].key == "ui.theme"

    def test_param_with_min_max_constraints(self):
        dsl = """\
module test_mod
app test "Test"

param scoring.weight "Weight":
  type: float
  default: 1.0
  scope: system
  constraints:
    min_value: 0.0
    max_value: 10.0
"""
        fragment = _parse(dsl)
        p = fragment.params[0]
        assert p.constraints is not None
        assert p.constraints.min_value == 0.0
        assert p.constraints.max_value == 10.0

    def test_param_list_string_default(self):
        dsl = """\
module test_mod
app test "Test"

param tags.defaults "Default tags":
  type: list[str]
  default: ["urgent", "review"]
  scope: tenant
"""
        fragment = _parse(dsl)
        p = fragment.params[0]
        assert p.param_type == "list[str]"
        assert p.default == ["urgent", "review"]


class TestParamRefInWorkspace:
    """Tests for param() references in workspace heatmap thresholds."""

    def test_param_ref_in_heatmap_thresholds(self):
        dsl = """\
module test_mod
app test "Test"

entity Score "Score":
  id: uuid pk
  value: int

workspace dashboard "Dashboard":
  scores:
    source: Score
    display: heatmap
    rows: category
    columns: period
    value: avg(value)
    thresholds: param("heatmap.rag.thresholds")
"""
        fragment = _parse(dsl)
        assert len(fragment.workspaces) == 1
        region = fragment.workspaces[0].regions[0]
        assert isinstance(region.heatmap_thresholds, ParamRef)
        assert region.heatmap_thresholds.key == "heatmap.rag.thresholds"
