"""HM design-context — the unified facade over Dazzle's three design-quality rubrics.

Dazzle measures HM design quality with three rubrics that live apart:

- **taste** (`core.taste_rubric`) — judged, app-internals density/craft.
- **sitespec vision** (`core.sitespec_vision_rubric`) — judged, marketing landing pages.
- **sitespec hygiene** (`core.sitespec_hygiene`) — deterministic, marketing CSS structure.

They share overlapping *concepts* measured differently (type, whitespace/rhythm, finish
appear across more than one rubric). This module is the single place that names those
concepts, maps every rubric dimension to exactly one concept, and lays the rubrics on a
surface x method matrix. It is the source of truth the generated
``docs/reference/hm-design-context.md`` renders (via ``scripts/gen_design_context.py``) and
that the claim-integrity gate in ``tests/unit/test_design_context.py`` enforces — the same
guide-and-gate pattern as ``docs/reference/taste.md`` <- ``core.taste_rubric``.

Scope (#1566) is the unification of the *measurement/standard* only. Exemplars, the
Hyperpart taste-gate (#1567), the customise-affordance, and any MCP tool are out of scope.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dazzle.core.component_hygiene import COMPONENT_HYGIENE_DIMENSIONS
from dazzle.core.sitespec_hygiene import SITESPEC_HYGIENE_DIMENSIONS
from dazzle.core.sitespec_vision_rubric import SITESPEC_VISION_DIMENSIONS
from dazzle.core.taste_rubric import TASTE_DIMENSIONS

__all__ = [
    "RubricRef",
    "DesignConcept",
    "RUBRICS",
    "DESIGN_CONCEPTS",
    "CONCEPT_MAP",
    "SURFACES",
    "METHODS",
    "concepts",
    "dimensions_for",
    "matrix",
    "all_dimension_ids",
    "rubric_of",
    "method_of",
    "surface_of",
    "render_markdown",
    "DOC_PATH",
]

SURFACES: tuple[str, str] = ("marketing", "app_internals")
METHODS: tuple[str, str] = ("deterministic", "judged")


@dataclass(frozen=True)
class RubricRef:
    """One measurement rubric, placed on the two structural axes.

    ``dimension_keys`` are the rubric's own bare keys; a fully-qualified dimension
    id used by the concept map is ``f"{name}.{key}"``.
    """

    name: str  # "hygiene" | "vision" | "taste"
    surface: str  # one of SURFACES
    method: str  # one of METHODS
    dimension_keys: tuple[str, ...]


RUBRICS: tuple[RubricRef, ...] = (
    RubricRef(
        "hygiene",
        "marketing",
        "deterministic",
        tuple(d.key for d in SITESPEC_HYGIENE_DIMENSIONS),
    ),
    RubricRef(
        "vision",
        "marketing",
        "judged",
        tuple(d.key for d in SITESPEC_VISION_DIMENSIONS),
    ),
    RubricRef(
        "taste",
        "app_internals",
        "judged",
        tuple(d.key for d in TASTE_DIMENSIONS),
    ),
    RubricRef(
        "component",
        "app_internals",
        "deterministic",
        tuple(d.key for d in COMPONENT_HYGIENE_DIMENSIONS),
    ),
)

_RUBRIC_BY_NAME: dict[str, RubricRef] = {r.name: r for r in RUBRICS}


@dataclass(frozen=True)
class DesignConcept:
    """A canonical HM design concept — one design idea the rubrics measure, possibly
    several times across surfaces/methods.

    ``dimensions`` are fully-qualified rubric dimension ids (``"<rubric>.<key>"``).
    """

    key: str
    definition: str
    dimensions: tuple[str, ...]


# The concept vocabulary. Every rubric dimension is claimed by exactly one concept
# (enforced by tests/unit/test_design_context.py); a concept may own many dimensions
# across rubrics — that overlap is the reconciliation this module exists to make.
DESIGN_CONCEPTS: tuple[DesignConcept, ...] = (
    DesignConcept(
        "type",
        "Type from a real scale: token-driven sizes, fluid display, modern faces.",
        ("hygiene.type_system", "hygiene.fluid_type", "vision.type_modernity"),
    ),
    DesignConcept(
        "rhythm",
        "Whitespace and vertical rhythm: consistent, confident spacing between things.",
        (
            "hygiene.section_rhythm",
            "vision.whitespace_rhythm",
            "taste.spatial_rhythm",
            "component.sizing_tokens",
        ),
    ),
    DesignConcept(
        "hierarchy",
        "Editorial reading order: one dominant element leads; the eye is led, not lost.",
        ("vision.visual_hierarchy", "vision.hero_impact", "taste.typographic_hierarchy"),
    ),
    DesignConcept(
        "colour",
        "Cohesive palette used with intent: a clear accent, tasteful depth.",
        ("vision.colour_confidence", "taste.color_discipline", "component.colour_tokens"),
    ),
    DesignConcept(
        "motion",
        "Subtle, consistent, token-driven motion that reads as considered.",
        ("hygiene.motion", "component.motion_tokens"),
    ),
    DesignConcept(
        "structure",
        "Layout skeleton: responsive reflow and width-constrained, readable content.",
        ("hygiene.responsive", "hygiene.container", "component.namespace"),
    ),
    DesignConcept(
        "finish",
        "Overall craft: alignment, state completeness, dark-mode integrity, no rough edges.",
        (
            "vision.finish_polish",
            "taste.perceived_craft",
            "taste.state_completeness",
            "taste.dark_mode_integrity",
        ),
    ),
    DesignConcept(
        "cta",
        "The primary action is unmistakable, inviting, and reinforced at decision points.",
        ("vision.cta_prominence",),
    ),
    DesignConcept(
        "family_fidelity",
        "The page convincingly reads as its intended aesthetic-family vernacular.",
        ("vision.family_fidelity",),
    ),
)

CONCEPT_MAP: dict[str, tuple[str, ...]] = {c.key: c.dimensions for c in DESIGN_CONCEPTS}


def concepts() -> tuple[DesignConcept, ...]:
    """All design concepts, in canonical order."""
    return DESIGN_CONCEPTS


def dimensions_for(concept_key: str) -> tuple[str, ...]:
    """The qualified rubric dimension ids that measure ``concept_key``."""
    return CONCEPT_MAP[concept_key]


def all_dimension_ids() -> frozenset[str]:
    """Every fully-qualified rubric dimension id across all rubrics."""
    return frozenset(f"{r.name}.{k}" for r in RUBRICS for k in r.dimension_keys)


def rubric_of(qualified_id: str) -> RubricRef:
    """The rubric owning a ``"<rubric>.<key>"`` dimension id."""
    return _RUBRIC_BY_NAME[qualified_id.split(".", 1)[0]]


def method_of(qualified_id: str) -> str:
    """ "deterministic" | "judged" for a qualified dimension id."""
    return rubric_of(qualified_id).method


def surface_of(qualified_id: str) -> str:
    """ "marketing" | "app_internals" for a qualified dimension id."""
    return rubric_of(qualified_id).surface


def matrix() -> dict[tuple[str, str], RubricRef | None]:
    """The surface x method matrix. A cell with no rubric is ``None`` (an honest,
    visible gap, not a hidden capability); all four cells are filled today."""
    cell: dict[tuple[str, str], RubricRef | None] = {
        (s, m): None for s in SURFACES for m in METHODS
    }
    for r in RUBRICS:
        cell[(r.surface, r.method)] = r
    return cell


# --- doc generation (render logic lives here so it is importable + unit-tested) -----

DOC_PATH: Path = Path(__file__).resolve().parents[3] / "docs" / "reference" / "hm-design-context.md"

_SURFACE_LABEL = {"marketing": "Marketing / sitespec", "app_internals": "App internals"}
_METHOD_LABEL = {"deterministic": "Deterministic", "judged": "Judged (LLM panel)"}
_RUBRIC_SOURCE = {
    "hygiene": "`core/sitespec_hygiene.py`",
    "vision": "`core/sitespec_vision_rubric.py`",
    "taste": "`core/taste_rubric.py`",
    "component": "`core/component_hygiene.py`",
}


def render_markdown() -> str:
    """Render the design-context reference doc from this module (the source of truth)."""
    lines: list[str] = []
    lines.append("<!-- GENERATED by scripts/gen_design_context.py — do not edit by hand. -->")
    lines.append("<!-- Source of truth: src/dazzle/core/design_context.py -->")
    lines.append("")
    lines.append("# HM Design Context")
    lines.append("")
    lines.append(
        "The single entry-point for HM design quality. When you customise HM for a new "
        "property, this is the standard your work is measured against — spanning both "
        "marketing/sitespec pages and app internals. It unifies three rubrics that "
        "otherwise live apart, on two axes: **surface** (marketing vs app internals) x "
        "**method** (deterministic structure vs judged perception)."
    )
    lines.append("")
    lines.append(
        "The *vernacular* — how to actually make something on-family — lives in the "
        "aesthetic families (`packages/hatchi-maxchi/families/*.css`) and the house "
        "taste principles in [taste.md](taste.md). This page is the *measurement*."
    )
    lines.append("")

    # Matrix
    lines.append("## Surface x method matrix")
    lines.append("")
    lines.append("| Surface \\ Method | Deterministic | Judged (LLM panel) |")
    lines.append("|---|---|---|")
    m = matrix()
    for s in SURFACES:
        cells = []
        for meth in METHODS:
            r = m[(s, meth)]
            cells.append(
                f"{_RUBRIC_SOURCE[r.name]} ({len(r.dimension_keys)} dims)"
                if r
                else "— (none today)"
            )
        lines.append(f"| **{_SURFACE_LABEL[s]}** | {cells[0]} | {cells[1]} |")
    lines.append("")
    if any(v is None for v in m.values()):
        lines.append(
            "> Cells marked “— (none today)” have no rubric yet — shown so the gap is "
            "visible, not hidden."
        )
        lines.append("")

    # Concept map
    lines.append("## Concept map")
    lines.append("")
    lines.append(
        "Each concept is one design idea; the rubrics measure it in the columns below. "
        "Every rubric dimension is claimed by exactly one concept (enforced by "
        "`tests/unit/test_design_context.py`)."
    )
    lines.append("")
    lines.append("| Concept | What it means | Measured by |")
    lines.append("|---|---|---|")
    for c in DESIGN_CONCEPTS:
        dims = ", ".join(f"`{d}` ({method_of(d)[0]})" for d in c.dimensions)
        lines.append(f"| `{c.key}` | {c.definition} | {dims} |")
    lines.append("")
    lines.append("_Method key: (d) deterministic, (j) judged._")
    lines.append("")

    # Rubric sources
    lines.append("## Rubric sources")
    lines.append("")
    for r in RUBRICS:
        lines.append(
            f"- **{r.name}** — {_RUBRIC_SOURCE[r.name]} — "
            f"{_SURFACE_LABEL[r.surface].lower()}, {_METHOD_LABEL[r.method].lower()}; "
            f"{len(r.dimension_keys)} dimensions."
        )
    lines.append("")

    # Authoring workflow (Part E, #1567) — the live, discoverable entry-point.
    lines.append("## Authoring a new Hyperpart")
    lines.append("")
    lines.append(
        "1. Use HM tokens (`var(--dz-…)`), the `.dz-` namespace, and `--dz-transition*` "
        "for motion. The **component-discipline floor** "
        "(`tests/unit/test_component_hygiene.py`) scores every component on this and "
        "fails a new one that sprays raw values."
    )
    lines.append(
        "2. If your component renders a card or region, the **card-safety composite gate** "
        "(`tests/unit/test_htmx_workspace_composite.py`) covers its rendered DOM "
        "automatically."
    )
    lines.append(
        "3. For a judged “does it look right” read, run "
        "`dazzle qa component-vision <name>` (on-demand, advisory, subscription-billed)."
    )
    lines.append("")

    # New-property workflow (Part E, #1567 slice 2) — pick-or-author, then auto-score.
    lines.append("## Standing up a new property")
    lines.append("")
    lines.append(
        "1. **Pick** a shipped family when one fits the brand — `[ui] theme = "
        '"stripe" | "paper" | "linear-dark" | "expressive"` — done.'
    )
    lines.append(
        "2. **Or author**: study the target family's exemplars (capture via "
        "`scripts/taste/capture_sitespec_references.py`), then `sitespec scaffold_theme` "
        "and edit `themespec.yaml` (a compact parametric spec — not raw tokens)."
    )
    lines.append(
        "3. **Deterministic floor (must pass):** `validate_theme` — WCAG-AA "
        "contrast-gated on the generated palette, both modes; then `generate_tokens`."
    )
    lines.append(
        "4. **Judged read (advisory):** `dazzle qa property-vision <url> --family <name>` "
        "against the family's exemplars."
    )
    lines.append("")
    return "\n".join(lines)
