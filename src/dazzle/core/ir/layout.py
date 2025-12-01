"""
UI semantic layout types for DAZZLE IR.

This module contains layout engine specifications including
layout signals, workspace layouts, persona layouts, archetypes,
surfaces, and layout plans.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class AttentionSignalKind(str, Enum):
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


class LayoutSignal(BaseModel):
    """
    Semantic UI element requiring user attention in the layout engine.

    A layout signal represents a logical UI element that the user needs to
    be aware of and potentially interact with. Signals are allocated to surfaces
    by the layout engine based on their characteristics.

    Note: This is distinct from AttentionSignal (in ux.py) which is for DSL-based
    data-driven attention signals with conditions and messages.

    Attributes:
        id: Unique signal identifier
        kind: Semantic kind of signal
        label: Human-readable label
        source: Entity/surface reference that provides data
        attention_weight: Relative importance (0.0-1.0, higher = more important)
        urgency: How quickly user needs to respond
        interaction_frequency: How often user interacts with this signal
        density_preference: Preferred information density
        mode: Primary interaction mode
        constraints: Additional constraints (e.g., min_width, max_items)
    """

    model_config = {"frozen": True}

    id: str
    kind: AttentionSignalKind
    label: str
    source: str  # Entity or surface name
    attention_weight: float = Field(default=0.5, ge=0.0, le=1.0)
    urgency: str = "medium"  # low, medium, high
    interaction_frequency: str = "occasional"  # rare, occasional, frequent
    density_preference: str = "comfortable"  # compact, comfortable, spacious
    mode: str = "read"  # read, act, configure
    constraints: dict[str, Any] = Field(default_factory=dict)

    @field_validator("urgency")
    @classmethod
    def validate_urgency(cls, v: str) -> str:
        """Validate urgency is one of allowed values."""
        if v not in ("low", "medium", "high"):
            raise ValueError(f"urgency must be low/medium/high, got: {v}")
        return v

    @field_validator("interaction_frequency")
    @classmethod
    def validate_interaction_frequency(cls, v: str) -> str:
        """Validate interaction frequency is one of allowed values."""
        if v not in ("rare", "occasional", "frequent"):
            raise ValueError(f"interaction_frequency must be rare/occasional/frequent, got: {v}")
        return v

    @field_validator("density_preference")
    @classmethod
    def validate_density_preference(cls, v: str) -> str:
        """Validate density preference is one of allowed values."""
        if v not in ("compact", "comfortable", "spacious"):
            raise ValueError(f"density_preference must be compact/comfortable/spacious, got: {v}")
        return v

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        """Validate mode is one of allowed values."""
        if v not in ("read", "act", "configure"):
            raise ValueError(f"mode must be read/act/configure, got: {v}")
        return v


class WorkspaceLayout(BaseModel):
    """
    Layout-enriched workspace definition.

    Extends the basic workspace concept with layout-specific metadata used
    by the layout engine to determine optimal UI structure.

    Attributes:
        id: Workspace identifier
        label: Human-readable label
        persona_targets: List of persona IDs this workspace is optimized for
        attention_budget: Total attention capacity (1.0 = normal, >1.0 = dense)
        time_horizon: Temporal focus of workspace
        engine_hint: Optional archetype hint (e.g., "scanner_table")
        engine_options: Archetype-specific customization options
            - hero_height: "tall" | "medium" | "compact" (for FOCUS_METRIC)
            - context_columns: int (for FOCUS_METRIC)
            - show_empty_slots: bool
            - table_density: "comfortable" | "compact" (for SCANNER_TABLE)
        attention_signals: List of signals to display in this workspace
    """

    model_config = {"frozen": True}

    id: str
    label: str
    persona_targets: list[str] = Field(default_factory=list)
    attention_budget: float = Field(default=1.0, ge=0.0, le=1.5)
    time_horizon: str = "daily"  # realtime, daily, archival
    engine_hint: str | None = None
    engine_options: dict[str, Any] = Field(default_factory=dict)
    attention_signals: list[LayoutSignal] = Field(default_factory=list)

    @field_validator("time_horizon")
    @classmethod
    def validate_time_horizon(cls, v: str) -> str:
        """Validate time horizon is one of allowed values."""
        if v not in ("realtime", "daily", "archival"):
            raise ValueError(f"time_horizon must be realtime/daily/archival, got: {v}")
        return v


class PersonaLayout(BaseModel):
    """
    Layout-enriched persona definition.

    Extends the basic persona concept with UI preference biases used by
    the layout engine to optimize interfaces for specific user roles.

    Attributes:
        id: Persona identifier
        label: Human-readable label
        goals: List of primary user goals
        proficiency_level: User expertise level
        session_style: Typical interaction pattern
        attention_biases: Signal kind → weight multiplier map
    """

    model_config = {"frozen": True}

    id: str
    label: str
    goals: list[str] = Field(default_factory=list)
    proficiency_level: str = "intermediate"  # novice, intermediate, expert
    session_style: str = "deep_work"  # glance, deep_work
    attention_biases: dict[str, float] = Field(default_factory=dict)

    @field_validator("proficiency_level")
    @classmethod
    def validate_proficiency_level(cls, v: str) -> str:
        """Validate proficiency level is one of allowed values."""
        if v not in ("novice", "intermediate", "expert"):
            raise ValueError(f"proficiency_level must be novice/intermediate/expert, got: {v}")
        return v

    @field_validator("session_style")
    @classmethod
    def validate_session_style(cls, v: str) -> str:
        """Validate session style is one of allowed values."""
        if v not in ("glance", "deep_work"):
            raise ValueError(f"session_style must be glance/deep_work, got: {v}")
        return v


class LayoutArchetype(str, Enum):
    """
    Named layout patterns with specific compositional rules.

    Each archetype defines a specific way to organize attention signals
    into a coherent UI structure.
    """

    FOCUS_METRIC = "focus_metric"  # Single dominant KPI/metric
    SCANNER_TABLE = "scanner_table"  # Table-centric with filters
    DUAL_PANE_FLOW = "dual_pane_flow"  # List + detail master-detail
    MONITOR_WALL = "monitor_wall"  # Multiple moderate-importance signals
    COMMAND_CENTER = "command_center"  # Dense, expert-focused dashboard


class LayoutSurface(BaseModel):
    """
    Named region within a layout where signals are rendered.

    Surfaces are the building blocks of layout archetypes. Each surface
    has a specific purpose and capacity constraints.

    Attributes:
        id: Surface identifier (e.g., "primary", "sidebar", "toolbar")
        archetype: Parent archetype
        capacity: Maximum attention weight this surface can hold
        priority: Surface priority for signal allocation
        assigned_signals: List of signal IDs assigned to this surface
        constraints: Surface-specific constraints
    """

    model_config = {"frozen": True}

    id: str
    archetype: LayoutArchetype
    capacity: float = Field(default=1.0, ge=0.0)
    priority: int = Field(default=1, ge=1)
    assigned_signals: list[str] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)


class LayoutPlan(BaseModel):
    """
    Deterministic output of the layout engine.

    The layout plan specifies exactly how a workspace should be rendered,
    including which archetype to use, where each signal appears, and
    any warnings about over-budget situations.

    Attributes:
        workspace_id: Source workspace identifier
        persona_id: Target persona identifier (if persona-specific)
        archetype: Selected layout archetype
        surfaces: List of surfaces with assigned signals
        over_budget_signals: Signal IDs that couldn't fit
        warnings: Layout warnings (e.g., attention budget exceeded)
        metadata: Additional metadata for debugging/logging
    """

    model_config = {"frozen": True}

    workspace_id: str
    persona_id: str | None = None
    archetype: LayoutArchetype
    surfaces: list[LayoutSurface] = Field(default_factory=list)
    over_budget_signals: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class UXLayouts(BaseModel):
    """
    Container for UX semantic layout specifications.

    Holds workspace layouts and persona definitions for the layout engine.

    Attributes:
        workspaces: List of workspace layout specifications
        personas: List of persona layout specifications
    """

    model_config = {"frozen": True}

    workspaces: list[WorkspaceLayout] = Field(default_factory=list)
    personas: list[PersonaLayout] = Field(default_factory=list)
