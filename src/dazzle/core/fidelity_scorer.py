"""Structural fidelity scorer: measures how well rendered HTML embodies its AppSpec.

All functions are pure (no IO). The scorer parses HTML into a lightweight tree
and checks structural, semantic, and story dimensions against the spec.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

from dazzle.core.ir import (
    AppSpec,
    EntitySpec,
    FieldModifier,
    FieldTypeKind,
    SurfaceMode,
    SurfaceSpec,
)
from dazzle.core.ir.fidelity import (
    FidelityGap,
    FidelityGapCategory,
    FidelityReport,
    SurfaceFidelityScore,
)

# ── Field type → expected input type mapping ──────────────────────────

FIELD_TYPE_TO_INPUT: dict[FieldTypeKind, str] = {
    FieldTypeKind.BOOL: "checkbox",
    FieldTypeKind.DATE: "date",
    FieldTypeKind.DATETIME: "datetime-local",
    FieldTypeKind.INT: "number",
    FieldTypeKind.DECIMAL: "number",
    FieldTypeKind.MONEY: "number",
    FieldTypeKind.TEXT: "textarea",
    FieldTypeKind.EMAIL: "email",
    FieldTypeKind.URL: "url",
    FieldTypeKind.ENUM: "select",
}

DEFAULT_INPUT_TYPE = "text"

# ── Composite score weights ───────────────────────────────────────────

W_STRUCTURAL = 0.35
W_SEMANTIC = 0.30
W_STORY = 0.20
W_INTERACTION = 0.15


# ── Lightweight HTML tree ─────────────────────────────────────────────


@dataclass
class HTMLElement:
    """Minimal HTML element node."""

    tag: str
    attrs: dict[str, str | None] = field(default_factory=dict)
    children: list[HTMLElement] = field(default_factory=list)
    text: str = ""

    def find_all(self, tag: str) -> list[HTMLElement]:
        """Recursively find all descendants with the given tag."""
        result: list[HTMLElement] = []
        for child in self.children:
            if child.tag == tag:
                result.append(child)
            result.extend(child.find_all(tag))
        return result

    def has_attr(self, name: str) -> bool:
        return name in self.attrs

    def get_attr(self, name: str, default: str = "") -> str:
        return self.attrs.get(name, default) or default

    def get_text(self) -> str:
        """Get all text content recursively."""
        parts = [self.text]
        for child in self.children:
            parts.append(child.get_text())
        return "".join(parts)


class _TreeBuilder(HTMLParser):
    """Build an HTMLElement tree from raw HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.root = HTMLElement(tag="root")
        self._stack: list[HTMLElement] = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        elem = HTMLElement(tag=tag, attrs=dict(attrs))
        self._stack[-1].children.append(elem)
        # Void elements don't get pushed
        if tag not in {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "param",
            "source",
            "track",
            "wbr",
        }:
            self._stack.append(elem)

    def handle_endtag(self, tag: str) -> None:
        if len(self._stack) > 1 and self._stack[-1].tag == tag:
            self._stack.pop()

    def handle_data(self, data: str) -> None:
        if self._stack:
            self._stack[-1].text += data


def parse_html(html: str) -> HTMLElement:
    """Parse HTML string into an HTMLElement tree."""
    builder = _TreeBuilder()
    builder.feed(html)
    return builder.root


# ── Structural checks ─────────────────────────────────────────────────


def _field_names_from_surface(surface: SurfaceSpec) -> list[str]:
    """Extract field names from all surface sections."""
    names: list[str] = []
    for section in surface.sections:
        for elem in section.elements:
            names.append(elem.field_name)
    return names


def _check_table_structure(
    surface: SurfaceSpec,
    entity: EntitySpec | None,
    root: HTMLElement,
) -> list[FidelityGap]:
    """Check LIST surface: table, th headers, HTMX attrs."""
    gaps: list[FidelityGap] = []
    tables = root.find_all("table")
    if not tables:
        gaps.append(
            FidelityGap(
                category=FidelityGapCategory.MISSING_FIELD,
                dimension="structural",
                severity="critical",
                surface_name=surface.name,
                target="table",
                expected="<table> element for list surface",
                actual="no table found",
                recommendation="Add a <table> to render the entity list.",
            )
        )
        return gaps

    # Check header columns match surface fields
    ths = root.find_all("th")
    th_texts = {th.get_text().strip().lower() for th in ths}
    field_names = _field_names_from_surface(surface)
    for fname in field_names:
        label = fname.replace("_", " ").lower()
        if not any(label in t or fname.lower() in t for t in th_texts):
            gaps.append(
                FidelityGap(
                    category=FidelityGapCategory.MISSING_FIELD,
                    dimension="structural",
                    severity="major",
                    surface_name=surface.name,
                    target=f"th[{fname}]",
                    expected=f"<th> for field '{fname}'",
                    actual="not found in table headers",
                    recommendation=f"Add a <th> column for '{fname}'.",
                )
            )

    # Check HTMX attributes on tbody or table
    tbodies = root.find_all("tbody")
    has_htmx = any(el.has_attr("hx-get") or el.has_attr("hx-target") for el in tbodies + tables)
    if not has_htmx:
        gaps.append(
            FidelityGap(
                category=FidelityGapCategory.MISSING_HTMX_ATTRIBUTE,
                dimension="structural",
                severity="minor",
                surface_name=surface.name,
                target="tbody",
                expected="hx-get or hx-target on table/tbody",
                actual="no HTMX attributes found",
                recommendation="Add hx-get to tbody for dynamic data loading.",
            )
        )

    return gaps


def _check_form_structure(
    surface: SurfaceSpec,
    entity: EntitySpec | None,
    root: HTMLElement,
) -> list[FidelityGap]:
    """Check CREATE/EDIT surface: form, inputs, method, types."""
    gaps: list[FidelityGap] = []
    forms = root.find_all("form")
    if not forms:
        gaps.append(
            FidelityGap(
                category=FidelityGapCategory.MISSING_FIELD,
                dimension="structural",
                severity="critical",
                surface_name=surface.name,
                target="form",
                expected="<form> element for create/edit surface",
                actual="no form found",
                recommendation="Add a <form> element.",
            )
        )
        return gaps

    form = forms[0]
    field_names = _field_names_from_surface(surface)

    # Collect all inputs/textareas/selects
    inputs = root.find_all("input") + root.find_all("textarea") + root.find_all("select")
    input_names = {inp.get_attr("name") for inp in inputs}

    for fname in field_names:
        if fname not in input_names:
            gaps.append(
                FidelityGap(
                    category=FidelityGapCategory.MISSING_FIELD,
                    dimension="structural",
                    severity="major",
                    surface_name=surface.name,
                    target=f"input[{fname}]",
                    expected=f"input with name='{fname}'",
                    actual="not found",
                    recommendation=f"Add an input element with name='{fname}'.",
                )
            )

    # Check correct HTTP method via hx-post / hx-put
    is_edit = surface.mode == SurfaceMode.EDIT
    expected_method_attr = "hx-put" if is_edit else "hx-post"
    if not form.has_attr(expected_method_attr):
        # Also accept standard method attr
        form_method = form.get_attr("method", "").lower()
        expected_std = "put" if is_edit else "post"
        if form_method != expected_std and not form.has_attr(expected_method_attr):
            gaps.append(
                FidelityGap(
                    category=FidelityGapCategory.INCORRECT_HTTP_METHOD,
                    dimension="structural",
                    severity="major",
                    surface_name=surface.name,
                    target="form",
                    expected=f"{expected_method_attr} or method='{expected_std}'",
                    actual=f"method='{form_method}'",
                    recommendation=f"Set {expected_method_attr} on the form.",
                )
            )

    # Check input types match field types
    if entity:
        entity_field_map = {f.name: f for f in entity.fields}
        for inp in root.find_all("input"):
            name = inp.get_attr("name")
            if name in entity_field_map:
                fspec = entity_field_map[name]
                expected_type = FIELD_TYPE_TO_INPUT.get(fspec.type.kind, DEFAULT_INPUT_TYPE)
                actual_type = inp.get_attr("type", "text")
                if expected_type != actual_type and expected_type != "textarea":
                    gaps.append(
                        FidelityGap(
                            category=FidelityGapCategory.INCORRECT_INPUT_TYPE,
                            dimension="structural",
                            severity="major",
                            surface_name=surface.name,
                            target=f"input[{name}]",
                            expected=f"type='{expected_type}'",
                            actual=f"type='{actual_type}'",
                            recommendation=(
                                f"Change input type to '{expected_type}' "
                                f"for {fspec.type.kind.value} field."
                            ),
                        )
                    )

    return gaps


def _check_detail_structure(
    surface: SurfaceSpec,
    entity: EntitySpec | None,
    root: HTMLElement,
) -> list[FidelityGap]:
    """Check VIEW surface: dl/dd detail fields."""
    gaps: list[FidelityGap] = []
    dls = root.find_all("dl")
    dds = root.find_all("dd")
    # Also accept div-based detail layouts
    if not dls and not dds:
        gaps.append(
            FidelityGap(
                category=FidelityGapCategory.MISSING_FIELD,
                dimension="structural",
                severity="major",
                surface_name=surface.name,
                target="dl",
                expected="<dl> or detail elements for view surface",
                actual="no detail structure found",
                recommendation="Use <dl>/<dt>/<dd> for field display.",
            )
        )
    return gaps


# ── Semantic checks ───────────────────────────────────────────────────

_SNAKE_RE = re.compile(r"^[a-z]+(_[a-z]+)+$")


def _check_semantic_fidelity(
    surface: SurfaceSpec,
    entity: EntitySpec | None,
    root: HTMLElement,
) -> list[FidelityGap]:
    """Check display names, required attrs, design tokens."""
    gaps: list[FidelityGap] = []
    all_text = root.get_text()

    # Check for raw snake_case field names used as display labels
    field_names = _field_names_from_surface(surface)
    for fname in field_names:
        if _SNAKE_RE.match(fname) and fname in all_text:
            gaps.append(
                FidelityGap(
                    category=FidelityGapCategory.MISSING_DISPLAY_NAME,
                    dimension="semantic",
                    severity="major",
                    surface_name=surface.name,
                    target=f"label[{fname}]",
                    expected=f"Human-readable label (e.g. '{fname.replace('_', ' ').title()}')",
                    actual=f"Raw snake_case '{fname}' in output",
                    recommendation=f"Replace '{fname}' with a display label.",
                )
            )

    # Check required attributes on inputs
    if entity and surface.mode in (SurfaceMode.CREATE, SurfaceMode.EDIT):
        required_fields = {f.name for f in entity.fields if FieldModifier.REQUIRED in f.modifiers}
        present_fields = _field_names_from_surface(surface)
        required_in_surface = required_fields & set(present_fields)

        inputs = root.find_all("input") + root.find_all("textarea") + root.find_all("select")
        for inp in inputs:
            name = inp.get_attr("name")
            if name in required_in_surface and not inp.has_attr("required"):
                gaps.append(
                    FidelityGap(
                        category=FidelityGapCategory.MISSING_VALIDATION_ATTRIBUTE,
                        dimension="semantic",
                        severity="minor",
                        surface_name=surface.name,
                        target=f"input[{name}]",
                        expected="required attribute",
                        actual="not present",
                        recommendation=f"Add 'required' attribute to '{name}' input.",
                    )
                )

    # Check design tokens in style
    styles = root.find_all("style")
    if not styles:
        # Check for inline style or link to CSS
        links = root.find_all("link")
        has_css = any(
            "css" in (lnk.get_attr("href", "") + lnk.get_attr("rel", "")) for lnk in links
        )
        if not has_css:
            gaps.append(
                FidelityGap(
                    category=FidelityGapCategory.MISSING_DESIGN_TOKENS,
                    dimension="semantic",
                    severity="minor",
                    surface_name=surface.name,
                    target="style",
                    expected="Design tokens in <style> or linked CSS",
                    actual="no styles found",
                    recommendation="Include design tokens via <style> or CSS link.",
                )
            )

    return gaps


# ── Story embodiment checks ───────────────────────────────────────────


def _check_story_embodiment(
    surface: SurfaceSpec,
    entity: EntitySpec | None,
    root: HTMLElement,
    appspec: AppSpec | None,
) -> list[FidelityGap]:
    """Check that story-referenced entities have action affordances."""
    gaps: list[FidelityGap] = []
    if appspec is None:
        return gaps

    # Find stories that reference this surface's entity
    entity_name = surface.entity_ref
    if not entity_name:
        return gaps

    relevant_stories = [
        s
        for s in appspec.stories
        if entity_name.lower() in (s.title or "").lower()
        or entity_name.lower() in (getattr(s, "entity_ref", "") or "").lower()
    ]
    if not relevant_stories:
        return gaps

    # Check for action affordances (buttons, links with action semantics)
    buttons = root.find_all("button")
    links = root.find_all("a")
    action_elements = buttons + links
    has_actions = len(action_elements) > 0

    if not has_actions:
        gaps.append(
            FidelityGap(
                category=FidelityGapCategory.MISSING_ACTION_AFFORDANCE,
                dimension="story",
                severity="major",
                surface_name=surface.name,
                target="actions",
                expected="Action buttons/links for story interactions",
                actual="no action affordances found",
                recommendation="Add buttons or links for entity actions.",
            )
        )

    return gaps


# ── Interaction checks ─────────────────────────────────────────────────


def _check_interaction_fidelity(
    surface: SurfaceSpec,
    root: HTMLElement,
    html: str,
) -> list[FidelityGap]:
    """Check interaction patterns for surfaces using search_select fragments."""
    gaps: list[FidelityGap] = []

    # Only check surfaces that contain search/fragment patterns
    has_search_select = (
        "search-results-" in html or "hx-get" in html and "_fragments/search" in html
    )
    if not has_search_select:
        return gaps

    # Check for loading indicator (hx-indicator)
    if "hx-indicator" not in html:
        gaps.append(
            FidelityGap(
                category=FidelityGapCategory.MISSING_LOADING_INDICATOR,
                dimension="interaction",
                severity="minor",
                surface_name=surface.name,
                target="search_select",
                expected="hx-indicator attribute for loading state",
                actual="no hx-indicator found",
                recommendation="Add hx-indicator to search inputs for loading feedback.",
            )
        )

    # Check for debounce in hx-trigger
    if "delay:" not in html:
        gaps.append(
            FidelityGap(
                category=FidelityGapCategory.MISSING_DEBOUNCE,
                dimension="interaction",
                severity="major",
                surface_name=surface.name,
                target="search_select",
                expected="delay: in hx-trigger for debounced search",
                actual="no delay found in triggers",
                recommendation="Add delay:400ms to hx-trigger to debounce search requests.",
            )
        )

    # Check for empty state handling
    if "no results" not in html.lower() and "type at least" not in html.lower():
        gaps.append(
            FidelityGap(
                category=FidelityGapCategory.MISSING_EMPTY_STATE,
                dimension="interaction",
                severity="minor",
                surface_name=surface.name,
                target="search_select",
                expected="Empty state message for no results",
                actual="no empty state text found",
                recommendation="Add an empty state message for when no results are found.",
            )
        )

    # Check for error handling elements
    if "text-error" not in html:
        gaps.append(
            FidelityGap(
                category=FidelityGapCategory.MISSING_ERROR_HANDLER,
                dimension="interaction",
                severity="minor",
                surface_name=surface.name,
                target="search_select",
                expected="Error display element for failed searches",
                actual="no error handler found",
                recommendation="Add error state handling for failed search requests.",
            )
        )

    # Composition penalty: surfaces >300 lines with no fragment decomposition
    line_count = html.count("\n") + 1
    if line_count > 300 and "hx-target" not in html:
        gaps.append(
            FidelityGap(
                category=FidelityGapCategory.MISSING_HTMX_ATTRIBUTE,
                dimension="interaction",
                severity="minor",
                surface_name=surface.name,
                target="composition",
                expected="Fragment decomposition for large surfaces",
                actual=f"Surface has {line_count} lines with no fragment targets",
                recommendation="Decompose large surfaces into composable HTMX fragments.",
            )
        )

    return gaps


# ── Public API ────────────────────────────────────────────────────────


def score_surface_fidelity(
    surface: SurfaceSpec,
    entity: EntitySpec | None,
    html: str,
    appspec: AppSpec | None = None,
) -> SurfaceFidelityScore:
    """Score how well the rendered HTML embodies the surface spec.

    Args:
        surface: The surface specification.
        entity: The entity referenced by the surface (if any).
        html: Rendered HTML string.
        appspec: Full app spec (optional, enables story checks).

    Returns:
        Per-surface fidelity score with gaps.
    """
    root = parse_html(html)
    all_gaps: list[FidelityGap] = []

    # Structural checks based on surface mode
    if surface.mode == SurfaceMode.LIST:
        all_gaps.extend(_check_table_structure(surface, entity, root))
    elif surface.mode in (SurfaceMode.CREATE, SurfaceMode.EDIT):
        all_gaps.extend(_check_form_structure(surface, entity, root))
    elif surface.mode == SurfaceMode.VIEW:
        all_gaps.extend(_check_detail_structure(surface, entity, root))

    # Semantic checks
    all_gaps.extend(_check_semantic_fidelity(surface, entity, root))

    # Story checks
    all_gaps.extend(_check_story_embodiment(surface, entity, root, appspec))

    # Interaction checks (search_select fragments)
    all_gaps.extend(_check_interaction_fidelity(surface, root, html))

    # Compute dimension scores
    structural_gaps = [g for g in all_gaps if g.dimension == "structural"]
    semantic_gaps = [g for g in all_gaps if g.dimension == "semantic"]
    story_gaps = [g for g in all_gaps if g.dimension == "story"]
    interaction_gaps = [g for g in all_gaps if g.dimension == "interaction"]

    structural = _dimension_score(structural_gaps)
    semantic = _dimension_score(semantic_gaps)
    story = _dimension_score(story_gaps)
    interaction = _dimension_score(interaction_gaps)

    overall = (
        W_STRUCTURAL * structural
        + W_SEMANTIC * semantic
        + W_STORY * story
        + W_INTERACTION * interaction
    )

    return SurfaceFidelityScore(
        surface_name=surface.name,
        structural=round(structural, 4),
        semantic=round(semantic, 4),
        story=round(story, 4),
        interaction=round(interaction, 4),
        overall=round(overall, 4),
        gaps=all_gaps,
    )


def _dimension_score(gaps: list[FidelityGap]) -> float:
    """Compute a 0–1 score from gaps. More/worse gaps → lower score."""
    if not gaps:
        return 1.0
    penalty = 0.0
    for g in gaps:
        if g.severity == "critical":
            penalty += 0.5
        elif g.severity == "major":
            penalty += 0.2
        else:
            penalty += 0.05
    return max(0.0, 1.0 - penalty)


def score_appspec_fidelity(
    appspec: AppSpec,
    rendered_pages: dict[str, str],
    surface_filter: str | None = None,
) -> FidelityReport:
    """Score all surfaces in an AppSpec against their rendered HTML.

    Args:
        appspec: Full application specification.
        rendered_pages: Mapping of surface_name → rendered HTML.
        surface_filter: Optional surface name to score only one surface.

    Returns:
        Project-level fidelity report.
    """
    surface_scores: list[SurfaceFidelityScore] = []
    all_gap_counts: dict[str, int] = {}
    total_gaps = 0

    for surface in appspec.surfaces:
        if surface_filter and surface.name != surface_filter:
            continue

        html = rendered_pages.get(surface.name, "")
        if not html:
            continue

        entity = appspec.get_entity(surface.entity_ref) if surface.entity_ref else None
        score = score_surface_fidelity(surface, entity, html, appspec)
        surface_scores.append(score)

        for gap in score.gaps:
            cat = gap.category.value
            all_gap_counts[cat] = all_gap_counts.get(cat, 0) + 1
            total_gaps += 1

    overall = (
        sum(s.overall for s in surface_scores) / len(surface_scores) if surface_scores else 0.0
    )

    # Story coverage: fraction of surfaces with story score > 0
    story_scores = [s for s in surface_scores if s.story > 0.0]
    story_coverage = len(story_scores) / len(surface_scores) if surface_scores else 0.0

    return FidelityReport(
        overall=round(overall, 4),
        surface_scores=surface_scores,
        gap_counts=all_gap_counts,
        total_gaps=total_gaps,
        story_coverage=round(story_coverage, 4),
    )
