"""Tests for UI island DSL parsing."""

from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir.islands import IslandSpec


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
        """Test island with entity, src and fallback."""
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
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        assert len(fragment.islands) == 1
        island = fragment.islands[0]
        assert island.name == "task_chart"
        assert island.title == "Task Progress Chart"
        assert island.entity == "Task"
        assert island.src == "islands/task-chart/index.js"
        assert island.fallback == "Loading task chart..."

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
