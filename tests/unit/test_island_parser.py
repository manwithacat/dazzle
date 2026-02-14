"""Tests for UI island DSL parsing."""

from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir.islands import IslandEventSpec, IslandPropSpec, IslandSpec


class TestIslandParsing:
    """Tests for island DSL parsing."""

    def test_minimal_island(self):
        """Test island with only a name."""
        dsl = """
module test.core
app MyApp "My App"

island chart_widget:
  fallback: "Loading..."
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        assert len(fragment.islands) == 1
        island = fragment.islands[0]
        assert island.name == "chart_widget"
        assert island.title is None
        assert island.entity is None
        assert island.src is None
        assert island.fallback == "Loading..."
        assert island.props == []
        assert island.events == []

    def test_island_with_title(self):
        """Test island with a title string."""
        dsl = """
module test.core
app MyApp "My App"

island task_chart "Task Progress Chart":
  fallback: "Loading chart..."
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        island = fragment.islands[0]
        assert island.name == "task_chart"
        assert island.title == "Task Progress Chart"

    def test_island_with_all_properties(self):
        """Test island with entity, src, fallback, props, and events."""
        dsl = """
module test.core
app MyApp "My App"

entity Task "Task":
  id: uuid pk
  title: str(200) required

island task_chart "Task Progress Chart":
  entity: Task
  src: "islands/task-chart/index.js"
  fallback: "Loading task chart..."
  prop chart_type: str = "bar"
  prop date_range: str = "30d"
  event chart_clicked:
    detail: [task_id, series]
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        assert len(fragment.islands) == 1
        island = fragment.islands[0]
        assert island.name == "task_chart"
        assert island.title == "Task Progress Chart"
        assert island.entity == "Task"
        assert island.src == "islands/task-chart/index.js"
        assert island.fallback == "Loading task chart..."

        # Props
        assert len(island.props) == 2
        assert island.props[0].name == "chart_type"
        assert island.props[0].type == "str"
        assert island.props[0].default == "bar"
        assert island.props[1].name == "date_range"
        assert island.props[1].type == "str"
        assert island.props[1].default == "30d"

        # Events
        assert len(island.events) == 1
        assert island.events[0].name == "chart_clicked"
        assert island.events[0].detail_fields == ["task_id", "series"]

    def test_island_props_with_different_types(self):
        """Test island props with various types and defaults."""
        dsl = """
module test.core
app MyApp "My App"

island settings_panel "Settings":
  prop name: str = "default"
  prop count: int = 10
  prop enabled: bool = true
  prop ratio: float = 3.14
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        island = fragment.islands[0]
        assert len(island.props) == 4

        assert island.props[0].name == "name"
        assert island.props[0].type == "str"
        assert island.props[0].default == "default"

        assert island.props[1].name == "count"
        assert island.props[1].type == "int"
        assert island.props[1].default == 10

        assert island.props[2].name == "enabled"
        assert island.props[2].type == "bool"
        assert island.props[2].default is True

        assert island.props[3].name == "ratio"
        assert island.props[3].type == "float"
        assert island.props[3].default == 3.14

    def test_island_prop_without_default(self):
        """Test island prop with no default value."""
        dsl = """
module test.core
app MyApp "My App"

island widget "Widget":
  prop label: str
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        island = fragment.islands[0]
        assert len(island.props) == 1
        assert island.props[0].name == "label"
        assert island.props[0].type == "str"
        assert island.props[0].default is None

    def test_island_event_with_detail_fields(self):
        """Test event with detail fields."""
        dsl = """
module test.core
app MyApp "My App"

island map_view "Map View":
  event pin_clicked:
    detail: [lat, lng, label]
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        island = fragment.islands[0]
        assert len(island.events) == 1
        event = island.events[0]
        assert event.name == "pin_clicked"
        assert event.detail_fields == ["lat", "lng", "label"]

    def test_multiple_islands(self):
        """Test parsing multiple islands in one module."""
        dsl = """
module test.core
app MyApp "My App"

island chart "Chart":
  fallback: "Loading chart..."

island calendar "Calendar":
  fallback: "Loading calendar..."
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        assert len(fragment.islands) == 2
        assert fragment.islands[0].name == "chart"
        assert fragment.islands[1].name == "calendar"

    def test_island_appears_in_module_fragment(self):
        """Test that islands are correctly stored in ModuleFragment."""
        dsl = """
module test.core
app MyApp "My App"

island dashboard_chart "Dashboard":
  src: "islands/dashboard/index.js"
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        assert hasattr(fragment, "islands")
        assert len(fragment.islands) == 1
        assert isinstance(fragment.islands[0], IslandSpec)

    def test_island_without_entity(self):
        """Test island with no entity binding (standalone JS component)."""
        dsl = """
module test.core
app MyApp "My App"

island confetti "Confetti Effect":
  src: "islands/confetti/index.js"
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        island = fragment.islands[0]
        assert island.entity is None
        assert island.src == "islands/confetti/index.js"


class TestIslandIRModels:
    """Tests for island IR model types."""

    def test_island_spec_defaults(self):
        """Test IslandSpec default values."""
        spec = IslandSpec(name="test")
        assert spec.title is None
        assert spec.entity is None
        assert spec.src is None
        assert spec.fallback is None
        assert spec.props == []
        assert spec.events == []

    def test_island_prop_spec_defaults(self):
        """Test IslandPropSpec default values."""
        prop = IslandPropSpec(name="x", type="str")
        assert prop.default is None

    def test_island_event_spec_defaults(self):
        """Test IslandEventSpec default values."""
        event = IslandEventSpec(name="click")
        assert event.detail_fields == []

    def test_island_spec_frozen(self):
        """Test IslandSpec is immutable (frozen)."""
        spec = IslandSpec(name="test")
        try:
            spec.name = "changed"  # type: ignore[misc]
            assert False, "Should have raised"
        except Exception:
            pass

    def test_island_in_appspec(self):
        """Test that AppSpec has islands field and get_island()."""
        from dazzle.core.ir.appspec import AppSpec
        from dazzle.core.ir.domain import DomainSpec

        app = AppSpec(
            name="test",
            domain=DomainSpec(entities=[]),
            islands=[
                IslandSpec(name="chart", title="Chart"),
                IslandSpec(name="map", title="Map"),
            ],
        )
        assert len(app.islands) == 2
        assert app.get_island("chart") is not None
        assert app.get_island("chart").title == "Chart"
        assert app.get_island("missing") is None
