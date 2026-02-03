"""Fidelity scoring models for measuring HTML-to-spec alignment."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class FidelityGapCategory(str, Enum):
    """Categories of fidelity gaps between spec and rendered output."""

    MISSING_FIELD = "missing_field"
    MISSING_NAVIGATION = "missing_navigation"
    INCORRECT_INPUT_TYPE = "incorrect_input_type"
    MISSING_VALIDATION_ATTRIBUTE = "missing_validation_attribute"
    MISSING_HTMX_ATTRIBUTE = "missing_htmx_attribute"
    MISSING_DISPLAY_NAME = "missing_display_name"
    INCORRECT_HTTP_METHOD = "incorrect_http_method"
    MISSING_DESIGN_TOKENS = "missing_design_tokens"
    MISSING_ACTION_AFFORDANCE = "missing_action_affordance"
    MISSING_LOADING_INDICATOR = "missing_loading_indicator"
    MISSING_EMPTY_STATE = "missing_empty_state"
    MISSING_DEBOUNCE = "missing_debounce"
    MISSING_ERROR_HANDLER = "missing_error_handler"
    MISSING_SOURCE_WIDGET = "missing_source_widget"
    STORY_PRECONDITION_MISSING = "story_precondition_missing"
    STORY_TRIGGER_MISSING = "story_trigger_missing"
    STORY_OUTCOME_MISSING = "story_outcome_missing"


class FidelityGap(BaseModel):
    """A single gap between the spec and the rendered HTML."""

    category: FidelityGapCategory
    dimension: str  # structural, semantic, or story
    severity: str  # critical, major, minor
    surface_name: str
    target: str  # what element is affected
    expected: str
    actual: str
    recommendation: str

    model_config = ConfigDict(frozen=True)


class SurfaceFidelityScore(BaseModel):
    """Per-surface fidelity scores."""

    surface_name: str
    structural: float = Field(ge=0.0, le=1.0)
    semantic: float = Field(ge=0.0, le=1.0)
    story: float = Field(ge=0.0, le=1.0)
    interaction: float = Field(ge=0.0, le=1.0, default=1.0)
    overall: float = Field(ge=0.0, le=1.0)
    gaps: list[FidelityGap] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)


class FidelityReport(BaseModel):
    """Project-level fidelity aggregation."""

    overall: float = Field(ge=0.0, le=1.0)
    surface_scores: list[SurfaceFidelityScore] = Field(default_factory=list)
    gap_counts: dict[str, int] = Field(default_factory=dict)
    total_gaps: int = 0
    story_coverage: float = Field(ge=0.0, le=1.0, default=0.0)
    integration_fidelity: float = Field(
        ge=0.0,
        le=1.0,
        default=1.0,
        description=(
            "Ratio of integration-referencing stories with verified API bindings "
            "to total integration-referencing stories. 1.0 if no integration stories."
        ),
    )

    model_config = ConfigDict(frozen=True)
