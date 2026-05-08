"""Verify the Fragment alias names every primitive type. Adding a new
primitive without adding it here is what we want this test to catch."""

import typing

from dazzle.render.fragment import Fragment


def test_fragment_alias_includes_all_primitives() -> None:
    args = typing.get_args(Fragment)
    names = {t.__name__ for t in args}
    expected = {
        # layout
        "Stack",
        "Row",
        "Split",
        "Grid",
        # containers
        "Page",
        "AppShell",
        "Sidebar",
        "Topbar",
        "NavGroup",
        "NavItem",
        "SkipLink",
        "Surface",
        "Card",
        "Region",
        "Toolbar",
        "Drawer",
        "Modal",
        "Tabs",
        "ErrorPage",
        # content
        "Text",
        "Heading",
        "Icon",
        "Badge",
        "EmptyState",
        "Skeleton",
        # interactive
        "Button",
        "Link",
        "InlineEdit",
        "Interactive",
        # data
        "Table",
        "KanbanBoard",
        "CalendarGrid",
        "Timeline",
        "KPI",
        "BarChart",
        "PivotTable",
        "Diagram",
        "TimeSeries",
        "Radar",
        "BoxPlot",
        "Bullet",
        "PipelineSteps",
        "Sparkline",
        "Tree",
        "ActionCard",
        "ProfileCard",
        "MetricTile",
        "MetricsGrid",
        "DetailGrid",
        "ActivityFeed",
        "StatusList",
        "BarTrack",
        "StageBar",
        "LazyTabPanel",
        "SearchBox",
        "ConfirmGate",
        "FilterBar",
        "SortHeader",
        "CsvExportButton",
        "DateRangePicker",
        # forms
        "FormStack",
        "Field",
        "Combobox",
        "RefPicker",
        "Submit",
        # escape
        "RawHTML",
        "Slot",
    }
    assert names == expected, f"missing: {expected - names}; extra: {names - expected}"
