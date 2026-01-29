"""
PitchSpec types for DAZZLE pitch deck generation.

Defines the specification for investor pitch materials:
- Company info, funding stage
- Problem/solution narrative
- Market sizing (TAM/SAM/SOM)
- Business model and pricing
- Financial projections
- Team and milestones
- Brand colors for slide theming
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class FundingStage(str, Enum):
    PRE_SEED = "pre_seed"
    SEED = "seed"
    SERIES_A = "series_a"
    SERIES_B = "series_b"
    GROWTH = "growth"


class CompanySpec(BaseModel):
    name: str
    tagline: str | None = None
    stage: FundingStage = FundingStage.PRE_SEED
    funding_ask: int | None = None
    currency: str = "GBP"
    runway_months: int | None = None
    model_config = ConfigDict(frozen=True)


class ProblemSpec(BaseModel):
    headline: str
    points: list[str] = Field(default_factory=list)
    market_failure: list[str] = Field(default_factory=list)
    model_config = ConfigDict(frozen=True)


class SolutionSpec(BaseModel):
    headline: str
    how_it_works: list[str] = Field(default_factory=list)
    value_props: list[str] = Field(default_factory=list)
    entities_count: int | None = None
    surfaces_count: int | None = None
    personas: list[str] = Field(default_factory=list)
    model_config = ConfigDict(frozen=True)


class MarketSize(BaseModel):
    value: int
    label: str
    description: str | None = None
    model_config = ConfigDict(frozen=True)


class MarketSpec(BaseModel):
    tam: MarketSize | None = None
    sam: MarketSize | None = None
    som: MarketSize | None = None
    drivers: list[str] = Field(default_factory=list)
    model_config = ConfigDict(frozen=True)


class PricingTier(BaseModel):
    name: str
    price: int
    period: str = "year"
    features: str | None = None
    highlighted: bool = False
    model_config = ConfigDict(frozen=True)


class BusinessModelSpec(BaseModel):
    tiers: list[PricingTier] = Field(default_factory=list)
    model_config = ConfigDict(frozen=True)


class YearProjection(BaseModel):
    year: int
    customers: int = 0
    revenue: int = 0
    costs: int | None = None
    model_config = ConfigDict(frozen=True)


class FundAllocation(BaseModel):
    category: str
    percent: int
    description: str | None = None
    model_config = ConfigDict(frozen=True)


class FinancialsSpec(BaseModel):
    projections: list[YearProjection] = Field(default_factory=list)
    use_of_funds: list[FundAllocation] = Field(default_factory=list)
    model_config = ConfigDict(frozen=True)


class TeamMember(BaseModel):
    name: str
    role: str
    bio: str | None = None
    model_config = ConfigDict(frozen=True)


class KeyHire(BaseModel):
    role: str
    timing: str | None = None
    description: str | None = None
    model_config = ConfigDict(frozen=True)


class TeamSpec(BaseModel):
    founders: list[TeamMember] = Field(default_factory=list)
    advisors: list[TeamMember] = Field(default_factory=list)
    key_hires: list[KeyHire] = Field(default_factory=list)
    model_config = ConfigDict(frozen=True)


class Competitor(BaseModel):
    name: str
    strength: str | None = None
    weakness: str | None = None
    model_config = ConfigDict(frozen=True)


class MilestonesSpec(BaseModel):
    completed: list[str] = Field(default_factory=list)
    next_12_months: list[str] = Field(default_factory=list)
    long_term: list[str] = Field(default_factory=list)
    model_config = ConfigDict(frozen=True)


class BrandColors(BaseModel):
    primary: str = "#0F1A2E"
    accent: str = "#2E86AB"
    highlight: str = "#E86F2C"
    success: str = "#28A745"
    light: str = "#F8F9FA"
    model_config = ConfigDict(frozen=True)


class PitchSpec(BaseModel):
    version: int = 1
    company: CompanySpec = Field(default_factory=lambda: CompanySpec(name="My App"))
    problem: ProblemSpec | None = None
    solution: SolutionSpec | None = None
    market: MarketSpec | None = None
    business_model: BusinessModelSpec | None = None
    financials: FinancialsSpec | None = None
    team: TeamSpec | None = None
    competitors: list[Competitor] = Field(default_factory=list)
    milestones: MilestonesSpec | None = None
    brand: BrandColors = Field(default_factory=BrandColors)
    model_config = ConfigDict(frozen=True)


def create_default_pitchspec(
    name: str = "My App",
    tagline: str | None = None,
) -> PitchSpec:
    """Create a default PitchSpec with minimal content."""
    return PitchSpec(
        version=1,
        company=CompanySpec(name=name, tagline=tagline),
        brand=BrandColors(),
    )
