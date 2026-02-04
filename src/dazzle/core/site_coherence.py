"""
Site coherence validation for DAZZLE.

Validates that a generated site feels like a real, complete website:
- Navigation links resolve to actual pages
- CTAs lead somewhere meaningful
- Expected pages exist for the business type
- Content isn't placeholder text
- Internal linking is consistent
- User flows are complete (signup, pricing, etc.)

This is not schema validation (that's in sitespec_loader.py).
This is about whether the site would feel "real" to a visitor.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class Severity(Enum):
    """Severity levels for coherence issues."""

    ERROR = "error"  # Site is broken - won't work properly
    WARNING = "warning"  # Site works but feels incomplete
    SUGGESTION = "suggestion"  # Nice to have for polish


@dataclass
class CoherenceIssue:
    """A single coherence issue."""

    severity: Severity
    category: str
    message: str
    location: str | None = None
    suggestion: str | None = None

    def __str__(self) -> str:
        icon = {"error": "✗", "warning": "⚠", "suggestion": "→"}[self.severity.value]
        loc = f" [{self.location}]" if self.location else ""
        sug = f"\n  Suggestion: {self.suggestion}" if self.suggestion else ""
        return f"{icon} {self.message}{loc}{sug}"


@dataclass
class CoherenceReport:
    """Complete coherence validation report."""

    issues: list[CoherenceIssue] = field(default_factory=list)
    checks_passed: list[str] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.WARNING)

    @property
    def suggestion_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.SUGGESTION)

    @property
    def is_coherent(self) -> bool:
        """True if no errors (warnings and suggestions are OK)."""
        return self.error_count == 0

    @property
    def score(self) -> int:
        """Coherence score 0-100. Errors=-20, Warnings=-5, Suggestions=-1."""
        base = 100
        base -= self.error_count * 20
        base -= self.warning_count * 5
        base -= self.suggestion_count * 1
        return max(0, min(100, base))

    def add_error(
        self,
        category: str,
        message: str,
        location: str | None = None,
        suggestion: str | None = None,
    ) -> None:
        self.issues.append(CoherenceIssue(Severity.ERROR, category, message, location, suggestion))

    def add_warning(
        self,
        category: str,
        message: str,
        location: str | None = None,
        suggestion: str | None = None,
    ) -> None:
        self.issues.append(
            CoherenceIssue(Severity.WARNING, category, message, location, suggestion)
        )

    def add_suggestion(
        self,
        category: str,
        message: str,
        location: str | None = None,
        suggestion: str | None = None,
    ) -> None:
        self.issues.append(
            CoherenceIssue(Severity.SUGGESTION, category, message, location, suggestion)
        )

    def add_passed(self, check: str) -> None:
        self.checks_passed.append(check)

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_coherent": self.is_coherent,
            "score": self.score,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "suggestion_count": self.suggestion_count,
            "issues": [
                {
                    "severity": i.severity.value,
                    "category": i.category,
                    "message": i.message,
                    "location": i.location,
                    "suggestion": i.suggestion,
                }
                for i in self.issues
            ],
            "checks_passed": self.checks_passed,
        }

    def format(self) -> str:
        """Format report for display."""
        lines = []

        if self.is_coherent:
            lines.append(f"✓ Site is coherent (score: {self.score}/100)")
        else:
            lines.append(f"✗ Site has coherence issues (score: {self.score}/100)")

        lines.append("")

        # Group by category
        by_category: dict[str, list[CoherenceIssue]] = {}
        for issue in self.issues:
            by_category.setdefault(issue.category, []).append(issue)

        for category, issues in sorted(by_category.items()):
            lines.append(f"## {category}")
            for issue in issues:
                lines.append(f"  {issue}")
            lines.append("")

        if self.checks_passed:
            lines.append("## Passed")
            for check in self.checks_passed:
                lines.append(f"  ✓ {check}")

        return "\n".join(lines)


# =============================================================================
# Placeholder Detection
# =============================================================================

PLACEHOLDER_PATTERNS = [
    r"\bYour\s+(?:Tagline|App|Product|Company)\s+Here\b",
    r"\bLorem\s+ipsum\b",
    r"\bTODO\b",
    r"\bFIXME\b",
    r"\bXXX\b",
    r"\[.*?\]\s*$",  # [placeholder] at end of line
    r"<.*?>",  # <placeholder>
    r"\{\{.*?\}\}",  # {{placeholder}}
    r"example\.com",
    r"test@test\.com",
    r"john\.?doe",
    r"jane\.?doe",
    r"acme\s+(?:corp|inc|company)",
    r"\$\d+\.00",  # Suspiciously round prices like $99.00
    r"Feature\s+\d+",  # Generic "Feature 1", "Feature 2"
    r"Benefit\s+\d+",
    r"Step\s+\d+:\s*$",  # "Step 1:" with nothing after
]

PLACEHOLDER_REGEX = re.compile("|".join(PLACEHOLDER_PATTERNS), re.IGNORECASE)


def detect_placeholders(text: str) -> list[str]:
    """Find placeholder text that shouldn't ship."""
    # Use finditer to get full match text, not capture groups
    matches = [m.group(0) for m in PLACEHOLDER_REGEX.finditer(text)]
    return list(set(matches))


# =============================================================================
# Main Validation
# =============================================================================


def validate_site_coherence(
    sitespec_data: dict[str, Any],
    copy_data: dict[str, Any] | None = None,
    project_root: Path | None = None,
    business_context: str | None = None,
) -> CoherenceReport:
    """
    Validate site coherence - does it feel like a real website?

    Args:
        sitespec_data: SiteSpec as dict
        copy_data: Parsed copy.md data (optional)
        project_root: Project root for file checks
        business_context: Hint about business type (e.g., "saas", "marketplace")

    Returns:
        CoherenceReport with all issues found
    """
    report = CoherenceReport()

    # Collect all defined routes
    all_routes = _collect_all_routes(sitespec_data)

    # Run all checks
    _check_navigation(sitespec_data, all_routes, report)
    _check_ctas(sitespec_data, all_routes, report)
    _check_required_pages(sitespec_data, all_routes, report, business_context)
    _check_legal_pages(sitespec_data, report)
    _check_auth_flow(sitespec_data, all_routes, report)
    _check_content_completeness(sitespec_data, copy_data, report)
    _check_placeholder_content(sitespec_data, copy_data, report)
    _check_footer(sitespec_data, all_routes, report)
    _check_branding(sitespec_data, report)

    return report


def _collect_all_routes(sitespec_data: dict[str, Any]) -> set[str]:
    """Collect all defined routes in the site."""
    routes: set[str] = set()

    # Pages
    for page in sitespec_data.get("pages", []):
        route = page.get("route")
        if route:
            routes.add(route)

    # Legal pages (handle None values - keys may exist with None values)
    legal = sitespec_data.get("legal") or {}
    terms = legal.get("terms") or {}
    privacy = legal.get("privacy") or {}
    if terms.get("route"):
        routes.add(terms["route"])
    if privacy.get("route"):
        routes.add(privacy["route"])

    # Auth pages (handle None values - keys may exist with None values)
    auth = sitespec_data.get("auth_pages") or {}
    login_config = auth.get("login") or {}
    signup_config = auth.get("signup") or {}
    if login_config.get("enabled", True):
        routes.add(login_config.get("route", "/login"))
    if signup_config.get("enabled", True):
        routes.add(signup_config.get("route", "/signup"))

    # App mount route (handle None values)
    integrations = sitespec_data.get("integrations") or {}
    app_mount = integrations.get("app_mount_route", "/app")
    routes.add(app_mount)

    return routes


def _check_navigation(
    sitespec_data: dict[str, Any],
    all_routes: set[str],
    report: CoherenceReport,
) -> None:
    """Check that navigation links resolve."""
    layout = sitespec_data.get("layout") or {}
    nav = layout.get("nav", {})

    all_nav_items = []
    all_nav_items.extend(nav.get("public", []))
    all_nav_items.extend(nav.get("authenticated", []))

    broken_links = []
    for item in all_nav_items:
        href = item.get("href", "")
        label = item.get("label", "Unknown")

        # Skip external links
        if href.startswith(("http://", "https://", "mailto:", "tel:")):
            continue

        # Check internal links
        if href.startswith("/"):
            # Normalize: /app/* is valid if /app exists
            base_route = "/" + href.split("/")[1] if "/" in href[1:] else href
            if href not in all_routes and base_route not in all_routes:
                broken_links.append((label, href))

    if broken_links:
        for label, href in broken_links:
            report.add_error(
                "Navigation",
                f"Link '{label}' points to '{href}' which doesn't exist",
                location="nav",
                suggestion=f"Create a page at {href} or update the link",
            )
    else:
        report.add_passed("All navigation links resolve")


def _check_ctas(
    sitespec_data: dict[str, Any],
    all_routes: set[str],
    report: CoherenceReport,
) -> None:
    """Check that CTAs lead somewhere meaningful."""
    broken_ctas = []
    empty_ctas = []

    for page in sitespec_data.get("pages", []):
        page_route = page.get("route", "unknown")

        for i, section in enumerate(page.get("sections", [])):
            section_loc = f"{page_route} section {i + 1}"

            # Check primary CTA
            primary = section.get("primary_cta")
            if primary:
                href = primary.get("href", "")
                label = primary.get("label", "")

                if not label:
                    empty_ctas.append((section_loc, "primary CTA has no label"))
                elif not href:
                    empty_ctas.append((section_loc, f"'{label}' has no destination"))
                elif href.startswith("/") and href not in all_routes:
                    # Check if it's an app route
                    integrations = sitespec_data.get("integrations") or {}
                    app_mount = integrations.get("app_mount_route", "/app")
                    if not href.startswith(app_mount):
                        broken_ctas.append((section_loc, label, href))

            # Check secondary CTA
            secondary = section.get("secondary_cta")
            if secondary:
                href = secondary.get("href", "")
                label = secondary.get("label", "")

                if label and href.startswith("/") and href not in all_routes:
                    integrations = sitespec_data.get("integrations") or {}
                    app_mount = integrations.get("app_mount_route", "/app")
                    if not href.startswith(app_mount):
                        broken_ctas.append((section_loc, label, href))

    for loc, issue in empty_ctas:
        report.add_warning(
            "CTAs",
            issue,
            location=loc,
            suggestion="Add a label and destination for the CTA",
        )

    for loc, label, href in broken_ctas:
        report.add_error(
            "CTAs",
            f"CTA '{label}' links to '{href}' which doesn't exist",
            location=loc,
            suggestion=f"Create {href} or update the CTA destination",
        )

    if not broken_ctas and not empty_ctas:
        report.add_passed("All CTAs have valid destinations")


def _check_required_pages(
    sitespec_data: dict[str, Any],
    all_routes: set[str],
    report: CoherenceReport,
    business_context: str | None,
) -> None:
    """Check that expected pages exist for the business type."""
    # Universal expectations for any site
    universal_pages = {
        "/": "Landing page",
    }

    # Business-specific expectations
    business_pages: dict[str, dict[str, str]] = {
        "saas": {
            "/pricing": "Pricing page",
            "/features": "Features page",
        },
        "marketplace": {
            "/how-it-works": "How it works page",
            "/pricing": "Pricing/fees page",
        },
        "agency": {
            "/services": "Services page",
            "/portfolio": "Portfolio page",
            "/contact": "Contact page",
        },
        "ecommerce": {
            "/products": "Products page",
            "/shipping": "Shipping info page",
        },
    }

    # Check universal pages
    for route, desc in universal_pages.items():
        if route not in all_routes:
            report.add_error(
                "Required Pages",
                f"Missing {desc} ({route})",
                suggestion=f"Add a page at {route}",
            )

    # Check business-specific pages
    if business_context and business_context.lower() in business_pages:
        expected = business_pages[business_context.lower()]
        for route, desc in expected.items():
            if route not in all_routes:
                report.add_warning(
                    "Required Pages",
                    f"Missing {desc} ({route}) - typical for {business_context} sites",
                    suggestion=f"Consider adding {route}",
                )

    # Check we have more than just the landing page
    content_pages = [r for r in all_routes if r not in ("/login", "/signup", "/app")]
    if len(content_pages) < 2:
        report.add_warning(
            "Required Pages",
            "Site has very few content pages",
            suggestion="Add pages like /about, /pricing, or /features",
        )
    else:
        report.add_passed(f"Site has {len(content_pages)} content pages")


def _check_legal_pages(sitespec_data: dict[str, Any], report: CoherenceReport) -> None:
    """Check legal pages are configured."""
    legal = sitespec_data.get("legal") or {}
    terms = legal.get("terms") or {}
    privacy = legal.get("privacy") or {}

    has_terms = bool(terms.get("route"))
    has_privacy = bool(privacy.get("route"))

    if not has_terms:
        report.add_warning(
            "Legal",
            "No Terms of Service page configured",
            suggestion="Add terms page in sitespec.yaml legal section",
        )

    if not has_privacy:
        report.add_warning(
            "Legal",
            "No Privacy Policy page configured",
            suggestion="Add privacy page in sitespec.yaml legal section",
        )

    if has_terms and has_privacy:
        report.add_passed("Legal pages configured")


def _check_auth_flow(
    sitespec_data: dict[str, Any],
    all_routes: set[str],
    report: CoherenceReport,
) -> None:
    """Check authentication flow is complete."""
    auth_pages = sitespec_data.get("auth_pages") or {}
    layout = sitespec_data.get("layout") or {}
    auth_entry = layout.get("auth") or {}
    login_config = auth_pages.get("login") or {}
    signup_config = auth_pages.get("signup") or {}

    login_enabled = login_config.get("enabled", True)
    signup_enabled = signup_config.get("enabled", True)

    # Check if there's a way to sign up from the site
    has_signup_cta = False
    for page in sitespec_data.get("pages", []):
        for section in page.get("sections", []):
            for cta in [section.get("primary_cta"), section.get("secondary_cta")]:
                if cta and cta.get("href") in ("/signup", "/login", "/app"):
                    has_signup_cta = True
                    break

    if signup_enabled and not has_signup_cta:
        report.add_warning(
            "Auth Flow",
            "No CTA leads to signup",
            suggestion="Add a 'Sign Up' or 'Get Started' CTA that links to /signup",
        )

    # Check auth entry point is configured
    primary_entry = auth_entry.get("primary_entry", "signup")
    if login_enabled and signup_enabled:
        report.add_passed(f"Auth flow configured (entry: {primary_entry})")


def _check_content_completeness(
    sitespec_data: dict[str, Any],
    copy_data: dict[str, Any] | None,
    report: CoherenceReport,
) -> None:
    """Check that pages have content."""
    empty_pages = []

    for page in sitespec_data.get("pages", []):
        route = page.get("route", "unknown")
        sections = page.get("sections", [])
        source = page.get("source")

        # Page has no sections and no markdown source
        if not sections and not source:
            empty_pages.append(route)
        elif sections:
            # Check if sections have content
            has_content = False
            for section in sections:
                if section.get("headline") or section.get("body") or section.get("items"):
                    has_content = True
                    break
            if not has_content:
                empty_pages.append(route)

    if empty_pages:
        for route in empty_pages:
            report.add_warning(
                "Content",
                f"Page '{route}' appears to have no content",
                suggestion="Add sections or content source to the page",
            )
    else:
        report.add_passed("All pages have content")

    # Check copy.md coverage if available
    if copy_data:
        sections = copy_data.get("sections", [])
        section_types = {s.get("type") for s in sections}

        recommended = {"hero", "features", "cta"}
        missing = recommended - section_types

        if missing:
            report.add_suggestion(
                "Content",
                f"copy.md missing common sections: {', '.join(sorted(missing))}",
                suggestion="Add these sections for a more complete landing page",
            )


def _check_placeholder_content(
    sitespec_data: dict[str, Any],
    copy_data: dict[str, Any] | None,
    report: CoherenceReport,
) -> None:
    """Check for placeholder text that shouldn't ship."""
    placeholders_found: list[tuple[str, str]] = []

    # Check brand
    brand = sitespec_data.get("brand") or {}
    product_name = brand.get("product_name", "")
    tagline = brand.get("tagline", "")

    if product_name:
        matches = detect_placeholders(product_name)
        if matches:
            placeholders_found.append(("brand.product_name", ", ".join(matches)))

    if tagline:
        matches = detect_placeholders(tagline)
        if matches:
            placeholders_found.append(("brand.tagline", ", ".join(matches)))

    # Check page content
    for page in sitespec_data.get("pages", []):
        route = page.get("route", "unknown")
        for i, section in enumerate(page.get("sections", [])):
            loc = f"{route} section {i + 1}"

            for field_name in ["headline", "subhead", "body"]:
                text = section.get(field_name, "")
                if text:
                    matches = detect_placeholders(text)
                    if matches:
                        placeholders_found.append((f"{loc}.{field_name}", ", ".join(matches)))

    # Check copy.md
    if copy_data:
        raw = copy_data.get("raw_markdown") or ""
        # Just get the sections, not specific locations
        if raw:
            matches = detect_placeholders(raw)
            if matches:
                # Dedupe
                unique_matches = list(set(matches))[:5]  # Limit to 5
                placeholders_found.append(("copy.md", ", ".join(unique_matches)))

    if placeholders_found:
        for loc, matched_text in placeholders_found:
            report.add_warning(
                "Placeholders",
                f"Placeholder text detected: {matched_text}",
                location=loc,
                suggestion="Replace with real content before launch",
            )
    else:
        report.add_passed("No placeholder text detected")


def _check_footer(
    sitespec_data: dict[str, Any],
    all_routes: set[str],
    report: CoherenceReport,
) -> None:
    """Check footer has expected links."""
    layout = sitespec_data.get("layout") or {}
    footer = layout.get("footer", {})
    columns = footer.get("columns", [])

    if not columns:
        report.add_warning(
            "Footer",
            "No footer columns configured",
            suggestion="Add footer with links to important pages",
        )
        return

    # Collect all footer links
    footer_hrefs: set[str] = set()
    for col in columns:
        for link in col.get("links", []):
            footer_hrefs.add(link.get("href", ""))

    # Check for legal links
    legal = sitespec_data.get("legal") or {}
    terms_config = legal.get("terms") or {}
    privacy_config = legal.get("privacy") or {}
    terms_route = terms_config.get("route")
    privacy_route = privacy_config.get("route")

    if terms_route and terms_route not in footer_hrefs:
        report.add_suggestion(
            "Footer",
            "Terms of Service not in footer",
            suggestion=f"Add link to {terms_route} in footer",
        )

    if privacy_route and privacy_route not in footer_hrefs:
        report.add_suggestion(
            "Footer",
            "Privacy Policy not in footer",
            suggestion=f"Add link to {privacy_route} in footer",
        )

    # Check footer links resolve
    broken = []
    for href in footer_hrefs:
        if href.startswith("/") and href not in all_routes:
            broken.append(href)

    if broken:
        for href in broken:
            report.add_error(
                "Footer",
                f"Footer link '{href}' doesn't exist",
                suggestion=f"Create {href} or remove the link",
            )
    else:
        report.add_passed("Footer links resolve")


def _check_branding(sitespec_data: dict[str, Any], report: CoherenceReport) -> None:
    """Check branding is configured."""
    brand = sitespec_data.get("brand") or {}

    product_name = brand.get("product_name", "")
    tagline = brand.get("tagline", "")
    support_email = brand.get("support_email", "")
    company_name = brand.get("company_legal_name", "")

    issues = []

    if not product_name or product_name == "My App":
        issues.append("product_name is default or missing")

    if not tagline:
        issues.append("no tagline configured")

    if not support_email:
        issues.append("no support email configured")

    if not company_name:
        issues.append("no company legal name configured")

    if issues:
        for issue in issues:
            report.add_warning(
                "Branding",
                f"Incomplete branding: {issue}",
                suggestion="Update brand section in sitespec.yaml",
            )
    else:
        report.add_passed("Branding is complete")
