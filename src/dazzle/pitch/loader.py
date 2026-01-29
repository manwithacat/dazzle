"""
PitchSpec persistence layer for DAZZLE pitch deck generation.

Handles reading and writing PitchSpec configurations to pitchspec.yaml.

Default location: {project_root}/pitchspec.yaml
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from .ir import (
    BrandColors,
    BusinessModelSpec,
    CompanySpec,
    Competitor,
    ExtraSlide,
    FinancialsSpec,
    FundAllocation,
    KeyHire,
    MarketSize,
    MarketSpec,
    MilestonesSpec,
    PitchSpec,
    PricingTier,
    ProblemSpec,
    SolutionSpec,
    TeamMember,
    TeamSpec,
    YearProjection,
)

logger = logging.getLogger(__name__)

PITCHSPEC_FILE = "pitchspec.yaml"


class PitchSpecError(Exception):
    """Error loading or validating PitchSpec."""

    pass


def get_pitchspec_path(project_root: Path) -> Path:
    """Get the pitchspec.yaml file path."""
    return project_root / PITCHSPEC_FILE


def pitchspec_exists(project_root: Path) -> bool:
    """Check if a pitchspec.yaml exists in the project."""
    return get_pitchspec_path(project_root).exists()


def load_pitchspec(project_root: Path) -> PitchSpec:
    """Load PitchSpec from pitchspec.yaml.

    Args:
        project_root: Root directory of the DAZZLE project.

    Returns:
        PitchSpec instance.

    Raises:
        PitchSpecError: If file doesn't exist or contains invalid YAML/schema.
    """
    pitchspec_path = get_pitchspec_path(project_root)

    if not pitchspec_path.exists():
        raise PitchSpecError(f"PitchSpec not found: {pitchspec_path}")

    try:
        content = pitchspec_path.read_text(encoding="utf-8")
        data = yaml.safe_load(content)

        if not data or not isinstance(data, dict):
            raise PitchSpecError(f"Empty or invalid YAML in {pitchspec_path}")

        return _parse_pitchspec_data(data)

    except yaml.YAMLError as e:
        raise PitchSpecError(f"Invalid YAML in {pitchspec_path}: {e}") from e
    except ValidationError as e:
        raise PitchSpecError(f"Invalid PitchSpec schema in {pitchspec_path}: {e}") from e


def _parse_pitchspec_data(data: dict[str, Any]) -> PitchSpec:
    """Parse PitchSpec from raw YAML data."""
    try:
        # Parse company
        company_data = data.get("company", {})
        company = CompanySpec(**company_data) if company_data else CompanySpec(name="My App")

        # Parse problem
        problem = None
        if "problem" in data and data["problem"]:
            problem = ProblemSpec(**data["problem"])

        # Parse solution
        solution = None
        if "solution" in data and data["solution"]:
            solution = SolutionSpec(**data["solution"])

        # Parse market
        market = None
        if "market" in data and data["market"]:
            market_data = data["market"]
            tam = MarketSize(**market_data["tam"]) if market_data.get("tam") else None
            sam = MarketSize(**market_data["sam"]) if market_data.get("sam") else None
            som = MarketSize(**market_data["som"]) if market_data.get("som") else None
            market = MarketSpec(
                tam=tam,
                sam=sam,
                som=som,
                drivers=market_data.get("drivers", []),
            )

        # Parse business model
        business_model = None
        if "business_model" in data and data["business_model"]:
            bm_data = data["business_model"]
            tiers = [PricingTier(**t) for t in bm_data.get("tiers", [])]
            business_model = BusinessModelSpec(tiers=tiers)

        # Parse financials
        financials = None
        if "financials" in data and data["financials"]:
            fin_data = data["financials"]
            projections = [YearProjection(**p) for p in fin_data.get("projections", [])]
            use_of_funds = [FundAllocation(**f) for f in fin_data.get("use_of_funds", [])]
            financials = FinancialsSpec(projections=projections, use_of_funds=use_of_funds)

        # Parse team
        team = None
        if "team" in data and data["team"]:
            team_data = data["team"]
            founders = [TeamMember(**m) for m in team_data.get("founders", [])]
            advisors = [TeamMember(**m) for m in team_data.get("advisors", [])]
            key_hires = [KeyHire(**h) for h in team_data.get("key_hires", [])]
            team = TeamSpec(founders=founders, advisors=advisors, key_hires=key_hires)

        # Parse competitors
        competitors = [Competitor(**c) for c in data.get("competitors", [])]

        # Parse milestones
        milestones = None
        if "milestones" in data and data["milestones"]:
            milestones = MilestonesSpec(**data["milestones"])

        # Parse brand colors
        brand = BrandColors()
        if "brand" in data and data["brand"]:
            brand = BrandColors(**data["brand"])

        # Parse extra slides
        extra_slides = [ExtraSlide(**es) for es in data.get("extra_slides", [])]

        # Parse slide order
        slide_order = data.get("slide_order")

        return PitchSpec(
            version=data.get("version", 1),
            company=company,
            problem=problem,
            solution=solution,
            market=market,
            business_model=business_model,
            financials=financials,
            team=team,
            competitors=competitors,
            milestones=milestones,
            brand=brand,
            extra_slides=extra_slides,
            slide_order=slide_order,
        )
    except (KeyError, ValueError, TypeError) as e:
        raise PitchSpecError(f"Failed to parse PitchSpec: {e}") from e


def save_pitchspec(project_root: Path, spec: PitchSpec) -> Path:
    """Save PitchSpec to pitchspec.yaml.

    Args:
        project_root: Root directory of the DAZZLE project.
        spec: PitchSpec to save.

    Returns:
        Path to the saved pitchspec.yaml file.
    """
    pitchspec_path = get_pitchspec_path(project_root)

    data = spec.model_dump(mode="json", exclude_none=True)

    pitchspec_path.write_text(
        yaml.dump(
            data,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    logger.info(f"Saved PitchSpec to {pitchspec_path}")
    return pitchspec_path


class PitchSpecValidationResult:
    """Result of PitchSpec validation."""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def add_error(self, message: str) -> None:
        self.errors.append(message)

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0


def validate_pitchspec(spec: PitchSpec) -> PitchSpecValidationResult:
    """Validate a PitchSpec for completeness and correctness.

    Checks:
        - Company name is set
        - Funding ask is positive if set
        - Fund allocations sum to 100%
        - Projections are in chronological order
        - Brand colors are valid hex

    Returns:
        PitchSpecValidationResult with errors and warnings.
    """
    result = PitchSpecValidationResult()

    # Company validation
    if not spec.company.name or spec.company.name == "My App":
        result.add_warning("Company: Name is still the default 'My App'")

    if spec.company.funding_ask is not None and spec.company.funding_ask <= 0:
        result.add_error("Company: funding_ask must be positive")

    if spec.company.runway_months is not None and spec.company.runway_months <= 0:
        result.add_error("Company: runway_months must be positive")

    # Content completeness warnings
    if not spec.problem:
        result.add_warning("Problem: No problem section defined")
    if not spec.solution:
        result.add_warning("Solution: No solution section defined")
    if not spec.market:
        result.add_warning("Market: No market sizing defined")
    if not spec.team:
        result.add_warning("Team: No team section defined")

    # Financials validation
    if spec.financials:
        # Check projections are chronological
        years = [p.year for p in spec.financials.projections]
        if years != sorted(years):
            result.add_error("Financials: Projections must be in chronological order")

        # Check fund allocations sum to ~100%
        if spec.financials.use_of_funds:
            total = sum(f.percent for f in spec.financials.use_of_funds)
            if total != 100:
                result.add_warning(
                    f"Financials: Use of funds allocations sum to {total}%, expected 100%"
                )

    # Validate slide_order entries
    if spec.slide_order is not None:
        known_names = {name for name, _, _ in _get_known_slide_names()}
        # Add extra slide slugs
        for es in spec.extra_slides:
            known_names.add(es.title.lower().replace(" ", "_"))
        for entry in spec.slide_order:
            if entry not in known_names:
                result.add_error(f"slide_order: Unknown slide name '{entry}'")

    # Validate extra_slides with image layout have image_path
    for es in spec.extra_slides:
        if es.layout.value == "image" and not es.image_path:
            result.add_error(
                f"extra_slides: Slide '{es.title}' uses image layout but has no image_path"
            )

    # Brand color validation
    for field_name in ["primary", "accent", "highlight", "success", "light"]:
        color = getattr(spec.brand, field_name)
        if not color.startswith("#") or len(color) not in (4, 7):
            result.add_error(f"Brand: Invalid color for {field_name}: {color}")

    return result


def _get_known_slide_names() -> list[tuple[str, str, str]]:
    """Return known built-in slide names for validation."""
    return [
        ("title", "", ""),
        ("problem", "", ""),
        ("solution", "", ""),
        ("platform", "", ""),
        ("personas", "", ""),
        ("market", "", ""),
        ("business_model", "", ""),
        ("financials", "", ""),
        ("team", "", ""),
        ("competition", "", ""),
        ("milestones", "", ""),
        ("ask", "", ""),
        ("closing", "", ""),
    ]


def scaffold_pitchspec(
    project_root: Path,
    *,
    overwrite: bool = False,
) -> Path | None:
    """Create a starter pitchspec.yaml with placeholder content.

    Args:
        project_root: Root directory of the DAZZLE project.
        overwrite: If True, overwrite existing file.

    Returns:
        Path to created file, or None if skipped.
    """
    pitchspec_path = get_pitchspec_path(project_root)

    if pitchspec_path.exists() and not overwrite:
        logger.debug(f"Skipping existing pitchspec: {pitchspec_path}")
        return None

    template = _get_scaffold_template()
    pitchspec_path.write_text(template, encoding="utf-8")
    logger.info(f"Created pitchspec at {pitchspec_path}")
    return pitchspec_path


def _get_scaffold_template() -> str:
    """Get the scaffold YAML template with comments."""
    return """# PitchSpec - Investor pitch deck configuration
# Generate with: dazzle pitch generate --format pptx
# Validate with: dazzle pitch validate
version: 1

company:
  name: "My App"
  tagline: "One line that explains the value"
  stage: pre_seed  # pre_seed, seed, series_a, series_b, growth
  funding_ask: 500000
  currency: GBP
  runway_months: 18

problem:
  headline: "The Problem We Solve"
  points:
    - "Pain point 1 that your target market faces"
    - "Pain point 2 that costs time or money"
    - "Pain point 3 that existing solutions miss"
  market_failure:
    - "Why current solutions fall short"
  speaker_notes: "Emphasize the cost of inaction"

solution:
  headline: "Our Solution"
  how_it_works:
    - "Step 1: How it works"
    - "Step 2: What happens next"
    - "Step 3: The outcome"
  value_props:
    - "Key benefit 1"
    - "Key benefit 2"
    - "Key benefit 3"

market:
  tam:
    value: 10000000000
    label: "Total Addressable Market"
    description: "Global market for X"
  sam:
    value: 1000000000
    label: "Serviceable Addressable Market"
    description: "UK market for X"
  som:
    value: 50000000
    label: "Serviceable Obtainable Market"
    description: "First-year target"
  drivers:
    - "Market trend 1"
    - "Market trend 2"

business_model:
  tiers:
    - name: Starter
      price: 0
      period: month
      features: "Basic features"
    - name: Pro
      price: 49
      period: month
      features: "Advanced features, priority support"
      highlighted: true
    - name: Enterprise
      price: 199
      period: month
      features: "Custom integrations, SLA, dedicated support"

financials:
  projections:
    - year: 2025
      customers: 100
      revenue: 50000
      costs: 200000
    - year: 2026
      customers: 500
      revenue: 300000
      costs: 350000
    - year: 2027
      customers: 2000
      revenue: 1200000
      costs: 600000
  use_of_funds:
    - category: Engineering
      percent: 45
      description: "Product development and infrastructure"
    - category: Sales & Marketing
      percent: 30
      description: "Customer acquisition and brand"
    - category: Operations
      percent: 15
      description: "Office, legal, accounting"
    - category: Reserve
      percent: 10
      description: "Contingency buffer"

team:
  founders:
    - name: "Founder Name"
      role: "CEO"
      bio: "Background and relevant experience"
  advisors:
    - name: "Advisor Name"
      role: "Technical Advisor"
      bio: "Domain expertise"
  key_hires:
    - role: "CTO"
      timing: "Q1 2025"
      description: "Technical leadership"

competitors:
  - name: "Competitor A"
    strength: "Large user base"
    weakness: "Complex, expensive"
  - name: "Competitor B"
    strength: "Easy to use"
    weakness: "Limited features"

milestones:
  completed:
    - "MVP launched"
    - "First paying customers"
  next_12_months:
    - "Reach 500 users"
    - "Launch enterprise tier"
    - "Achieve product-market fit"
  long_term:
    - "International expansion"
    - "Series A fundraise"

# Optional: company logo (path relative to project root)
# logo_path: "assets/logo.png"

# Optional: extra slides added to the deck
# extra_slides:
#   - title: "Case Study"
#     layout: bullets  # bullets, stats, cards, image
#     items:
#       - "Customer saw 3x improvement"
#       - "Deployed in under a week"
#     speaker_notes: "Walk through the case study"

# Optional: custom slide ordering (default order if omitted)
# slide_order:
#   - title
#   - problem
#   - solution
#   - market
#   - business_model
#   - financials
#   - team
#   - ask
#   - closing

# Slide theme colors (hex)
brand:
  primary: "#0F1A2E"
  accent: "#2E86AB"
  highlight: "#E86F2C"
  success: "#28A745"
  light: "#F8F9FA"
"""
