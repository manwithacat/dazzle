"""Composition analysis — deterministic visual hierarchy audit.

Computes attention weights for page elements using a 5-factor model
(font size, area, contrast, distinctness, interactivity) and evaluates
composition rules (ratio, ordering, consistency, minimum, balance)
to score visual hierarchy and layout quality.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .ir.sitespec import SectionSpec, SiteSpec

logger = logging.getLogger(__name__)

# ── Attention Weight System ──────────────────────────────────────────

# Known font sizes from Dazzle's CSS (in rem)
KNOWN_FONT_SIZES: dict[str, float] = {
    "h1": 3.5,
    "h2": 2.25,
    "h3": 1.125,
    "h4": 1.0,
    "subhead": 1.25,
    "pricing_price": 2.5,
    "step_number": 1.5,
    "body_text": 1.0,
    "caption": 0.75,
    "primary_cta": 1.0,
    "secondary_cta": 1.0,
    "card_cta": 1.0,
    "hero_image": 1.0,
    "split_image": 1.0,
    "card_icon": 1.5,
    "blockquote": 1.125,
}

_LARGE_AREA = {"hero_image", "split_image", "pricing_price"}
_MEDIUM_AREA = {"h1", "h2", "primary_cta", "blockquote"}
_SMALL_AREA = {"h3", "h4", "subhead", "secondary_cta", "step_number"}

_HIGH_CONTRAST = {"h1", "h2", "pricing_price", "primary_cta", "step_number"}
_MEDIUM_CONTRAST = {"h3", "h4", "secondary_cta", "blockquote", "hero_image"}

_DISTINCT = {
    "primary_cta",
    "secondary_cta",
    "card_cta",
    "pricing_price",
    "step_number",
    "card_icon",
    "hero_image",
    "split_image",
}

_INTERACTIVE = {"primary_cta", "secondary_cta", "card_cta"}

# Section-specific weight overrides (CSS differs per section context)
SECTION_WEIGHT_OVERRIDES: dict[str, dict[str, float]] = {
    "cta": {
        # CTA section uses h2 at 3rem/800wt/alt-bg → higher computed weight
        "h2": 7.09,
    },
}


def _font_size_score(role: str) -> float:
    size = KNOWN_FONT_SIZES.get(role, 1.0)
    return min(4.0, max(0.0, (size - 0.7) / (3.5 - 0.7) * 4.0))


def _area_score(role: str) -> float:
    if role in _LARGE_AREA:
        return 2.5
    if role in _MEDIUM_AREA:
        return 1.8
    if role in _SMALL_AREA:
        return 1.0
    return 0.5


def _contrast_score(role: str) -> float:
    if role in _HIGH_CONTRAST:
        return 1.3
    if role in _MEDIUM_CONTRAST:
        return 0.9
    return 0.4


def _distinctness_score(role: str) -> float:
    return 0.8 if role in _DISTINCT else 0.2


def _interactivity_score(role: str) -> float:
    return 0.4 if role in _INTERACTIVE else 0.0


def compute_attention_weight(role: str, section_type: str | None = None) -> float:
    """Compute 0-10 attention weight for a semantic role.

    Uses a 5-factor model: font size (0-4), area (0-3), contrast (0-1.5),
    distinctness (0-1), interactivity (0-0.5). Section-specific CSS
    overrides are applied when ``section_type`` is provided.
    """
    if section_type and section_type in SECTION_WEIGHT_OVERRIDES:
        override = SECTION_WEIGHT_OVERRIDES[section_type].get(role)
        if override is not None:
            return override

    total = (
        _font_size_score(role)
        + _area_score(role)
        + _contrast_score(role)
        + _distinctness_score(role)
        + _interactivity_score(role)
    )
    return round(min(10.0, total), 2)


# ── Section Element Derivation ───────────────────────────────────────


def derive_section_roles(section: SectionSpec) -> set[str]:
    """Derive semantic element roles present in a SectionSpec."""
    roles: set[str] = set()
    st = section.type.value if hasattr(section.type, "value") else str(section.type)

    if section.headline:
        roles.add("h1" if st in ("hero", "split_content") else "h2")
    if section.subhead:
        roles.add("subhead")
    if getattr(section, "body", None):
        roles.add("body_text")
    if section.primary_cta:
        roles.add("primary_cta")
    if section.secondary_cta:
        roles.add("secondary_cta")
    if section.media:
        roles.add("hero_image" if st == "hero" else "split_image")

    # Item-based roles (check first item to determine type)
    if section.items:
        for item in section.items:
            if hasattr(item, "title") and item.title:
                roles.add("h3")
            if hasattr(item, "icon") and item.icon:
                roles.add("card_icon")
            if hasattr(item, "step"):
                roles.add("step_number")
            if hasattr(item, "quote"):
                roles.add("blockquote")
            break  # all items same type

    if section.tiers:
        roles.add("h3")
        roles.add("pricing_price")
        if any(t.cta for t in section.tiers):
            roles.add("card_cta")

    return roles


# ── Default Composition Rules ────────────────────────────────────────

DEFAULT_SECTION_RULES: dict[str, list[dict[str, Any]]] = {
    "hero": [
        {
            "id": "hero-h1-dominance",
            "type": "ratio",
            "a": "h1",
            "b": "subhead",
            "min": 1.5,
            "severity": "high",
            "message": "h1 should be >= 1.5x the subhead attention weight",
        },
        {
            "id": "hero-cta-hierarchy",
            "type": "ordering",
            "order": ["primary_cta", "secondary_cta"],
            "severity": "medium",
            "message": "Primary CTA must have higher attention than secondary",
        },
        {
            "id": "hero-balance",
            "type": "balance",
            "left": ["h1", "subhead", "primary_cta", "secondary_cta"],
            "right": ["hero_image"],
            "max_imbalance": 0.30,
            "severity": "low",
            "message": "Left/right total weight within 30%",
        },
    ],
    "features": [
        {
            "id": "features-heading-hierarchy",
            "type": "ratio",
            "a": "h2",
            "b": "h3",
            "min": 1.5,
            "severity": "medium",
            "message": "Section heading should dominate card titles",
        },
    ],
    "feature_grid": [
        {
            "id": "feature-grid-heading-hierarchy",
            "type": "ratio",
            "a": "h2",
            "b": "h3",
            "min": 1.5,
            "severity": "medium",
            "message": "Section heading should dominate card titles",
        },
    ],
    "cta": [
        {
            "id": "cta-headline-prominence",
            "type": "minimum",
            "element": "h2",
            "min": 7.0,
            "severity": "high",
            "message": "CTA headline should have attention >= 7.0",
        },
    ],
    "pricing": [
        {
            "id": "pricing-price-prominence",
            "type": "minimum",
            "element": "pricing_price",
            "min": 5.0,
            "severity": "high",
            "message": "Price should have attention weight >= 5.0",
        },
        {
            "id": "pricing-heading-hierarchy",
            "type": "ratio",
            "a": "h2",
            "b": "h3",
            "min": 1.5,
            "severity": "medium",
            "message": "Section heading should dominate tier names",
        },
    ],
    "steps": [
        {
            "id": "steps-number-visibility",
            "type": "minimum",
            "element": "step_number",
            "min": 3.0,
            "severity": "medium",
            "message": "Step numbers should have attention weight >= 3.0",
        },
    ],
    "split_content": [
        {
            "id": "split-balance",
            "type": "balance",
            "left": ["h1", "subhead", "primary_cta"],
            "right": ["split_image"],
            "max_imbalance": 0.35,
            "severity": "low",
            "message": "Text/image balance within 35%",
        },
    ],
    "testimonials": [
        {
            "id": "testimonials-quote-prominence",
            "type": "minimum",
            "element": "blockquote",
            "min": 2.5,
            "severity": "medium",
            "message": "Testimonial quotes should be prominent",
        },
    ],
}

DEFAULT_PAGE_RULES: list[dict[str, Any]] = [
    {
        "id": "page-hero-first",
        "type": "position",
        "section": "hero",
        "expected_position": 0,
        "applies_to": ["landing"],
        "severity": "high",
        "message": "Hero section should be first on landing pages",
    },
    {
        "id": "page-cta-near-end",
        "type": "position_range",
        "section": "cta",
        "expected_range": [-3, -1],
        "applies_to": ["landing"],
        "severity": "medium",
        "message": "CTA section should be near the end of landing pages",
    },
]


# ── Rule Evaluation ──────────────────────────────────────────────────

_SEVERITY_DEDUCTIONS = {"high": 15, "medium": 5, "low": 2}


def _get_weight(role: str, roles: set[str], weights: dict[str, float]) -> float | None:
    if role not in roles:
        return None
    return weights.get(role)


def evaluate_rule(
    rule: dict[str, Any],
    roles: set[str],
    weights: dict[str, float],
) -> dict[str, Any] | None:
    """Evaluate a composition rule. Returns a violation dict, or ``None`` if the rule passes."""
    rule_type = rule["type"]

    if rule_type == "ratio":
        wa = _get_weight(rule["a"], roles, weights)
        wb = _get_weight(rule["b"], roles, weights)
        if wa is None or wb is None or wb == 0:
            return None
        ratio = wa / wb
        min_ratio = rule.get("min", 0)
        max_ratio = rule.get("max", float("inf"))
        if ratio < min_ratio or ratio > max_ratio:
            return {
                "rule_id": rule["id"],
                "severity": rule["severity"],
                "message": rule["message"],
                "detail": f"Ratio {rule['a']}/{rule['b']} = {ratio:.2f} (expected >= {min_ratio})",
            }

    elif rule_type == "ordering":
        order = rule["order"]
        prev_weight: float | None = None
        for role in order:
            w = _get_weight(role, roles, weights)
            if w is None:
                continue
            if prev_weight is not None and w >= prev_weight:
                return {
                    "rule_id": rule["id"],
                    "severity": rule["severity"],
                    "message": rule["message"],
                    "detail": f"Ordering violation in {order}",
                }
            prev_weight = w

    elif rule_type == "consistency":
        elements = rule["elements"]
        ws = [weights[r] for r in elements if r in roles and r in weights]
        if len(ws) < 2:
            return None
        variance = max(ws) - min(ws)
        if variance > rule["max_variance"]:
            return {
                "rule_id": rule["id"],
                "severity": rule["severity"],
                "message": rule["message"],
                "detail": f"Variance {variance:.2f} > max {rule['max_variance']}",
            }

    elif rule_type == "minimum":
        w = _get_weight(rule["element"], roles, weights)
        if w is None:
            return None
        if w < rule["min"]:
            return {
                "rule_id": rule["id"],
                "severity": rule["severity"],
                "message": rule["message"],
                "detail": f"{rule['element']} weight {w:.2f} < minimum {rule['min']}",
            }

    elif rule_type == "balance":
        left_present = any(_get_weight(r, roles, weights) is not None for r in rule["left"])
        right_present = any(_get_weight(r, roles, weights) is not None for r in rule["right"])
        if not left_present or not right_present:
            return None  # Balance N/A when one side intentionally empty
        left_total = sum(weights.get(r, 0) for r in rule["left"] if r in roles)
        right_total = sum(weights.get(r, 0) for r in rule["right"] if r in roles)
        total = left_total + right_total
        if total == 0:
            return None
        imbalance = abs(left_total - right_total) / total
        if imbalance > rule["max_imbalance"]:
            return {
                "rule_id": rule["id"],
                "severity": rule["severity"],
                "message": rule["message"],
                "detail": (
                    f"Imbalance {imbalance:.1%} > max {rule['max_imbalance']:.0%} "
                    f"(left={left_total:.1f}, right={right_total:.1f})"
                ),
            }

    return None


def evaluate_page_rule(
    rule: dict[str, Any],
    section_types: list[str],
    page_type: str,
) -> dict[str, Any] | None:
    """Evaluate a page-level rule. Returns violation dict or ``None``."""
    applies = rule.get("applies_to", [])
    if applies and page_type not in applies:
        return None

    rule_type = rule["type"]
    target = rule.get("section", "")

    if rule_type == "position":
        if target not in section_types:
            return None
        actual = section_types.index(target)
        expected = rule["expected_position"]
        if actual != expected:
            return {
                "rule_id": rule["id"],
                "severity": rule["severity"],
                "message": rule["message"],
                "detail": f"{target} at position {actual}, expected {expected}",
            }

    elif rule_type == "position_range":
        if target not in section_types:
            return None
        actual = section_types.index(target)
        n = len(section_types)
        lo, hi = rule["expected_range"]
        if lo < 0:
            lo = n + lo
        if hi < 0:
            hi = n + hi
        if actual < lo or actual > hi:
            return {
                "rule_id": rule["id"],
                "severity": rule["severity"],
                "message": rule["message"],
                "detail": f"{target} at position {actual}, expected in range [{lo}, {hi}]",
            }

    return None


# ── Scoring ──────────────────────────────────────────────────────────


def score_violations(violations: list[dict[str, Any]]) -> int:
    """Compute score (0-100) from violations."""
    deduction = sum(_SEVERITY_DEDUCTIONS.get(v["severity"], 5) for v in violations)
    return max(0, 100 - deduction)


# ── Audit Orchestration ──────────────────────────────────────────────


def audit_section(
    section_type: str,
    roles: set[str],
    rules: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Audit a single section against composition rules."""
    if rules is None:
        rules = DEFAULT_SECTION_RULES.get(section_type, [])

    weights: dict[str, float] = {}
    for role in roles:
        weights[role] = compute_attention_weight(role, section_type)

    violations: list[dict[str, Any]] = []
    rules_checked = 0
    for rule in rules:
        result = evaluate_rule(rule, roles, weights)
        rules_checked += 1
        if result is not None:
            violations.append(result)

    return {
        "type": section_type,
        "elements": weights,
        "violations": violations,
        "rules_checked": rules_checked,
    }


def audit_page(
    route: str,
    sections: list[dict[str, Any]],
    page_type: str = "landing",
    section_rules: dict[str, list[dict[str, Any]]] | None = None,
    page_rules: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Audit a page: evaluate section rules then page-level rules."""
    if section_rules is None:
        section_rules = DEFAULT_SECTION_RULES
    if page_rules is None:
        page_rules = DEFAULT_PAGE_RULES

    audited: list[dict[str, Any]] = []
    all_violations: list[dict[str, Any]] = []
    total_rules = 0

    for sec in sections:
        rules = section_rules.get(sec["type"], [])
        result = audit_section(sec["type"], sec["roles"], rules)
        audited.append(result)
        all_violations.extend(result["violations"])
        total_rules += result["rules_checked"]

    section_types = [s["type"] for s in sections]
    page_violations: list[dict[str, Any]] = []
    for rule in page_rules:
        page_result = evaluate_page_rule(rule, section_types, page_type)
        total_rules += 1
        if page_result is not None:
            page_violations.append(page_result)
            all_violations.append(page_result)

    severity_counts: dict[str, int] = {"high": 0, "medium": 0, "low": 0}
    for v in all_violations:
        sev = v.get("severity", "medium")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    return {
        "route": route,
        "score": score_violations(all_violations),
        "sections": audited,
        "page_violations": page_violations,
        "rules_checked": total_rules,
        "violations_count": severity_counts,
    }


def run_composition_audit(
    sitespec: SiteSpec,
    *,
    routes_filter: list[str] | None = None,
) -> dict[str, Any]:
    """Run full composition audit from sitespec structure.

    Args:
        sitespec: Loaded SiteSpec with pages and sections.
        routes_filter: If set, only audit pages matching these routes.

    Returns:
        Audit report with per-page results, overall score, and markdown.
    """
    pages: list[dict[str, Any]] = []

    for page in sitespec.pages:
        route = page.route
        if routes_filter and route not in routes_filter:
            continue

        page_type = page.type.value if hasattr(page.type, "value") else str(page.type)
        sections: list[dict[str, Any]] = []
        for section in page.sections:
            sec_type = section.type.value if hasattr(section.type, "value") else str(section.type)
            roles = derive_section_roles(section)
            sections.append({"type": sec_type, "roles": roles})

        page_result = audit_page(route, sections, page_type)
        pages.append(page_result)

    overall_score = min((p["score"] for p in pages), default=100)
    total_violations = sum(sum(p["violations_count"].values()) for p in pages)

    page_parts = [f"{p['route']} ({p['score']}/100)" for p in pages]
    summary = f"{len(pages)} pages audited: {', '.join(page_parts)}"
    if total_violations == 0:
        summary += " — all rules pass"

    return {
        "pages": pages,
        "overall_score": overall_score,
        "summary": summary,
        "markdown": _build_markdown(pages, overall_score),
    }


# ── Markdown Report ──────────────────────────────────────────────────


def _build_markdown(pages: list[dict[str, Any]], overall_score: int) -> str:
    lines = [f"# Composition Audit: {overall_score}/100", ""]

    for page in pages:
        lines.append(f"## {page['route']} — {page['score']}/100")
        lines.append("")

        for sec in page["sections"]:
            n_v = len(sec["violations"])
            marker = "[ok]" if n_v == 0 else f"[{n_v}!]"
            lines.append(f"  {marker} {sec['type']}")

            for role, weight in sorted(sec["elements"].items(), key=lambda x: -x[1]):
                lines.append(f"      {role}: {weight:.2f}")

            for v in sec["violations"]:
                sev = v["severity"].upper()
                lines.append(f"      [{sev}] {v['message']}")
                if v.get("detail"):
                    lines.append(f"             {v['detail']}")
            lines.append("")

        if page["page_violations"]:
            lines.append("  Page-level violations:")
            for v in page["page_violations"]:
                sev = v["severity"].upper()
                lines.append(f"    [{sev}] {v['message']}")
            lines.append("")

    return "\n".join(lines)
