"""
Built-in component registry for DNR UI.

Contains primitive components, pattern components, and layout types
as defined in DNR-Components-v1.md specification.
"""

from __future__ import annotations

# Built-in component registry (from DNR-Components-v1.md)
PRIMITIVE_COMPONENTS = [
    {"name": "Page", "category": "primitive", "description": "Top-level container for a screen"},
    {
        "name": "LayoutShell",
        "category": "primitive",
        "description": "Generic shell arranging header/sidebar/content",
    },
    {"name": "Card", "category": "primitive", "description": "Groups related content visually"},
    {
        "name": "DataTable",
        "category": "primitive",
        "description": "Feature-rich table for tabular data",
    },
    {
        "name": "SimpleTable",
        "category": "primitive",
        "description": "Minimal table for static layouts",
    },
    {"name": "Form", "category": "primitive", "description": "Container for form fields"},
    {"name": "Button", "category": "primitive", "description": "Primary clickable action control"},
    {"name": "IconButton", "category": "primitive", "description": "Compact icon-only button"},
    {"name": "Tabs", "category": "primitive", "description": "Tabbed navigation for sibling views"},
    {"name": "TabPanel", "category": "primitive", "description": "Content panel for a tab"},
    {"name": "Modal", "category": "primitive", "description": "Centered overlay dialog"},
    {"name": "Drawer", "category": "primitive", "description": "Side panel overlay"},
    {"name": "Toolbar", "category": "primitive", "description": "Row of actions and controls"},
    {
        "name": "FilterBar",
        "category": "primitive",
        "description": "Quick filters above tables/lists",
    },
    {
        "name": "SearchBox",
        "category": "primitive",
        "description": "Single search input with debounce",
    },
    {"name": "MetricTile", "category": "primitive", "description": "Simple KPI metric display"},
    {"name": "MetricRow", "category": "primitive", "description": "Row of KPI metrics"},
    {"name": "SideNav", "category": "primitive", "description": "Sidebar navigation"},
    {"name": "TopNav", "category": "primitive", "description": "Top navigation bar"},
    {
        "name": "Breadcrumbs",
        "category": "primitive",
        "description": "Hierarchical navigation indicator",
    },
]

PATTERN_COMPONENTS = [
    {"name": "FilterableTable", "category": "pattern", "description": "DataTable with FilterBar"},
    {
        "name": "SearchableList",
        "category": "pattern",
        "description": "List with SearchBox and optional FilterBar",
    },
    {
        "name": "MasterDetailLayout",
        "category": "pattern",
        "description": "Master list + detail panel layout",
    },
    {"name": "WizardForm", "category": "pattern", "description": "Multi-step form workflow"},
    {
        "name": "CRUDPage",
        "category": "pattern",
        "description": "Complete CRUD interface for an entity",
    },
    {
        "name": "MetricsDashboard",
        "category": "pattern",
        "description": "Overview page with metrics and charts",
    },
    {
        "name": "SettingsFormPage",
        "category": "pattern",
        "description": "Single-page settings panel",
    },
]

LAYOUT_TYPES = [
    {
        "kind": "singleColumn",
        "description": "Single column layout with main content",
        "regions": ["main"],
    },
    {
        "kind": "twoColumnWithHeader",
        "description": "Two column layout with header",
        "regions": ["header", "main", "secondary"],
    },
    {
        "kind": "appShell",
        "description": "Application shell with sidebar, header, and main content",
        "regions": ["sidebar", "main", "header", "footer"],
    },
    {
        "kind": "custom",
        "description": "Custom layout with arbitrary regions",
        "regions": ["user-defined"],
    },
]


def get_all_component_names() -> set[str]:
    """Get all built-in component names."""
    return {c["name"] for c in PRIMITIVE_COMPONENTS + PATTERN_COMPONENTS}


def get_component_by_name(name: str) -> dict[str, str] | None:
    """Get a built-in component by name."""
    all_builtins = {c["name"]: c for c in PRIMITIVE_COMPONENTS + PATTERN_COMPONENTS}
    return all_builtins.get(name)


def get_valid_layout_kinds() -> set[str]:
    """Get all valid layout kind names."""
    return {str(lt["kind"]) for lt in LAYOUT_TYPES}
