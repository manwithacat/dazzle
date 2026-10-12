"""
UI semantic layout types for DAZZLE IR.

Attention-signal kinds and the named workspace layout stages.
"""

from enum import StrEnum


class AttentionSignalKind(StrEnum):
    """
    Semantic kinds of UI attention signals.

    Each kind represents a distinct UI interaction pattern that requires
    specific layout treatment.
    """

    KPI = "kpi"  # Key metric/number requiring visual prominence
    ALERT_FEED = "alert_feed"  # Stream of notifications/alerts
    TABLE = "table"  # Tabular data grid
    ITEM_LIST = "item_list"  # Vertical list of items
    DETAIL_VIEW = "detail_view"  # Full details of single item
    TASK_LIST = "task_list"  # Actionable task items
    FORM = "form"  # Input form for data entry
    CHART = "chart"  # Data visualization
    SEARCH = "search"  # Search interface
    FILTER = "filter"  # Filter controls


class Stage(StrEnum):
    """
    Named layout stages with specific compositional rules.

    Each stage defines a specific way to organize attention signals
    into a coherent UI structure. Stages are like theater stages -
    they provide a layout where your UI components perform.

    Available stages:
    - FOCUS_METRIC: Spotlight stage - one hero KPI with supporting context
    - SCANNER_TABLE: Open stage - data-heavy table with filters
    - DUAL_PANE_FLOW: Split stage - list on one side, detail on the other
    - MONITOR_WALL: Gallery stage - multiple displays arranged in grid
    - COMMAND_CENTER: Control room stage - dense expert interface
    """

    FOCUS_METRIC = "focus_metric"  # Single dominant KPI/metric
    SCANNER_TABLE = "scanner_table"  # Table-centric with filters
    DUAL_PANE_FLOW = "dual_pane_flow"  # List + detail master-detail
    MONITOR_WALL = "monitor_wall"  # Multiple moderate-importance signals
    COMMAND_CENTER = "command_center"  # Dense, expert-focused dashboard
