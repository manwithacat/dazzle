"""
SiteSpec persistence layer for DAZZLE public site shell.

Handles reading and writing SiteSpec configurations to sitespec.yaml
in the project root. SiteSpec is separate from the DSL and AppSpec.

Default location: {project_root}/sitespec.yaml
Content directory: {project_root}/site/content/
"""

from __future__ import annotations

import difflib
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from pydantic import ValidationError

if TYPE_CHECKING:
    from .ir.appspec import AppSpec

from .ir.sitespec import (
    AuthEntrySpec,
    AuthPageSpec,
    AuthPagesSpec,
    BrandSpec,
    ContentSourceSpec,
    CTASpec,
    FAQItem,
    FeatureItem,
    FooterColumnSpec,
    FooterSpec,
    IntegrationsSpec,
    LayoutSpec,
    LegalPageSpec,
    LegalPagesSpec,
    LogoItem,
    LogoSpec,
    MediaSpec,
    NavItemSpec,
    NavSpec,
    PageKind,
    PageSpec,
    PricingTier,
    SectionKind,
    SectionSpec,
    SiteSpec,
    StatItem,
    StepItem,
    TestimonialItem,
    ThemeKind,
    create_default_sitespec,
)

logger = logging.getLogger(__name__)

# Default file paths
SITESPEC_FILE = "sitespec.yaml"
SITE_CONTENT_DIR = "site/content"
COPY_FILE = "copy.md"


class SiteSpecError(Exception):
    """Error loading or validating SiteSpec."""

    pass


def get_sitespec_path(project_root: Path) -> Path:
    """Get the sitespec.yaml file path.

    Args:
        project_root: Root directory of the DAZZLE project.

    Returns:
        Path to sitespec.yaml.
    """
    return project_root / SITESPEC_FILE


def get_content_dir(project_root: Path) -> Path:
    """Get the site content directory path.

    Args:
        project_root: Root directory of the DAZZLE project.

    Returns:
        Path to site/content/ directory.
    """
    return project_root / SITE_CONTENT_DIR


def sitespec_exists(project_root: Path) -> bool:
    """Check if a sitespec.yaml exists in the project.

    Args:
        project_root: Root directory of the DAZZLE project.

    Returns:
        True if sitespec.yaml exists.
    """
    return get_sitespec_path(project_root).exists()


def _parse_section_items(section_type: SectionKind, items_data: list[dict[str, Any]]) -> list[Any]:
    """Parse section items based on section type.

    Args:
        section_type: Type of section.
        items_data: Raw item data from YAML.

    Returns:
        List of typed item objects.
    """
    if section_type in (SectionKind.FEATURES, SectionKind.FEATURE_GRID):
        return [FeatureItem(**item) for item in items_data]
    elif section_type == SectionKind.FAQ:
        return [FAQItem(**item) for item in items_data]
    elif section_type == SectionKind.TESTIMONIALS:
        return [TestimonialItem(**item) for item in items_data]
    elif section_type == SectionKind.STATS:
        return [StatItem(**item) for item in items_data]
    elif section_type == SectionKind.STEPS:
        return [StepItem(**item) for item in items_data]
    elif section_type == SectionKind.LOGO_CLOUD:
        return [LogoItem(**item) for item in items_data]
    return items_data


def _parse_section(data: dict[str, Any]) -> SectionSpec:
    """Parse a section from raw YAML data.

    Args:
        data: Raw section data.

    Returns:
        SectionSpec object.
    """
    # Get section type first
    section_type = SectionKind(data.get("type", "hero"))

    # Parse items based on section type
    items = []
    if "items" in data:
        items = _parse_section_items(section_type, data["items"])

    # Parse CTAs
    primary_cta = None
    if "primary_cta" in data and data["primary_cta"]:
        primary_cta = CTASpec(**data["primary_cta"])

    secondary_cta = None
    if "secondary_cta" in data and data["secondary_cta"]:
        secondary_cta = CTASpec(**data["secondary_cta"])

    # Parse media
    media = None
    if "media" in data and data["media"]:
        media = MediaSpec(**data["media"])

    # Parse pricing tiers
    tiers = []
    if "tiers" in data:
        for tier_data in data["tiers"]:
            cta = None
            if "cta" in tier_data:
                cta = CTASpec(**tier_data["cta"])
                tier_data = {k: v for k, v in tier_data.items() if k != "cta"}
            tiers.append(PricingTier(**tier_data, cta=cta))

    return SectionSpec(
        type=section_type,
        headline=data.get("headline"),
        subhead=data.get("subhead"),
        body=data.get("body"),
        primary_cta=primary_cta,
        secondary_cta=secondary_cta,
        media=media,
        items=items,
        tiers=tiers,
    )


def _parse_page(data: dict[str, Any]) -> PageSpec:
    """Parse a page from raw YAML data.

    Args:
        data: Raw page data.

    Returns:
        PageSpec object.
    """
    # Parse sections
    sections = []
    if "sections" in data:
        sections = [_parse_section(s) for s in data["sections"]]

    # Parse content source
    source = None
    if "source" in data and data["source"]:
        source = ContentSourceSpec(**data["source"])

    page_type = PageKind(data.get("type", "landing"))

    return PageSpec(
        route=data["route"],
        type=page_type,
        title=data.get("title"),
        sections=sections,
        source=source,
        redirect_to=data.get("redirect_to"),
    )


def _parse_nav_items(items_data: list[dict[str, Any]]) -> list[NavItemSpec]:
    """Parse navigation items from raw YAML data.

    Args:
        items_data: Raw nav item data.

    Returns:
        List of NavItemSpec objects.
    """
    return [NavItemSpec(**item) for item in items_data]


def _parse_footer_columns(columns_data: list[dict[str, Any]]) -> list[FooterColumnSpec]:
    """Parse footer columns from raw YAML data.

    Args:
        columns_data: Raw column data.

    Returns:
        List of FooterColumnSpec objects.
    """
    columns = []
    for col_data in columns_data:
        links = []
        if "links" in col_data:
            links = _parse_nav_items(col_data["links"])
        columns.append(
            FooterColumnSpec(
                title=col_data["title"],
                links=links,
            )
        )
    return columns


def _parse_sitespec_data(data: dict[str, Any]) -> SiteSpec:
    """Parse SiteSpec from raw YAML data with type coercion.

    Args:
        data: Raw YAML data.

    Returns:
        SiteSpec object.

    Raises:
        SiteSpecError: If parsing fails.
    """
    try:
        # Parse brand
        brand_data = data.get("brand", {})
        logo = None
        if "logo" in brand_data:
            logo = LogoSpec(**brand_data["logo"])
        brand = BrandSpec(
            product_name=brand_data.get("product_name", "My App"),
            tagline=brand_data.get("tagline"),
            logo=logo or LogoSpec(),
            support_email=brand_data.get("support_email"),
            company_legal_name=brand_data.get("company_legal_name"),
        )

        # Parse layout
        layout_data = data.get("layout", {})

        # Parse auth entry
        auth = AuthEntrySpec()
        if "auth" in layout_data:
            auth = AuthEntrySpec(**layout_data["auth"])

        # Parse nav
        nav = NavSpec()
        if "nav" in layout_data:
            nav_data = layout_data["nav"]
            nav = NavSpec(
                public=_parse_nav_items(nav_data.get("public", [])),
                authenticated=_parse_nav_items(nav_data.get("authenticated", [])),
            )

        # Parse footer
        footer = FooterSpec()
        if "footer" in layout_data:
            footer_data = layout_data["footer"]
            footer = FooterSpec(
                columns=_parse_footer_columns(footer_data.get("columns", [])),
                disclaimer=footer_data.get("disclaimer"),
            )

        # Parse theme
        theme = ThemeKind.SAAS_DEFAULT
        if "theme" in layout_data:
            theme = ThemeKind(layout_data["theme"])

        layout = LayoutSpec(
            theme=theme,
            auth=auth,
            nav=nav,
            footer=footer,
        )

        # Parse pages
        pages = []
        if "pages" in data:
            pages = [_parse_page(p) for p in data["pages"]]

        # Parse legal pages
        legal = LegalPagesSpec()
        if "legal" in data:
            legal_data = data["legal"]
            terms = None
            privacy = None
            if "terms" in legal_data:
                terms = LegalPageSpec(
                    route=legal_data["terms"]["route"],
                    source=ContentSourceSpec(**legal_data["terms"]["source"]),
                )
            if "privacy" in legal_data:
                privacy = LegalPageSpec(
                    route=legal_data["privacy"]["route"],
                    source=ContentSourceSpec(**legal_data["privacy"]["source"]),
                )
            legal = LegalPagesSpec(terms=terms, privacy=privacy)

        # Parse auth pages
        auth_pages = AuthPagesSpec()
        if "auth_pages" in data:
            auth_data = data["auth_pages"]
            login = AuthPageSpec(route="/login")
            signup = AuthPageSpec(route="/signup")
            if "login" in auth_data:
                login = AuthPageSpec(**auth_data["login"])
            if "signup" in auth_data:
                signup = AuthPageSpec(**auth_data["signup"])
            auth_pages = AuthPagesSpec(login=login, signup=signup)

        # Parse integrations
        integrations = IntegrationsSpec()
        if "integrations" in data:
            integrations = IntegrationsSpec(**data["integrations"])

        return SiteSpec(
            version=data.get("version", 1),
            brand=brand,
            layout=layout,
            pages=pages,
            legal=legal,
            auth_pages=auth_pages,
            integrations=integrations,
        )
    except (KeyError, ValueError, TypeError) as e:
        raise SiteSpecError(f"Failed to parse SiteSpec: {e}") from e


def load_sitespec(project_root: Path, *, use_defaults: bool = True) -> SiteSpec:
    """Load SiteSpec from sitespec.yaml.

    Args:
        project_root: Root directory of the DAZZLE project.
        use_defaults: If True, return default SiteSpec when file doesn't exist.
            If False, raise SiteSpecError.

    Returns:
        SiteSpec instance.

    Raises:
        SiteSpecError: If file doesn't exist (when use_defaults=False) or
            contains invalid YAML/schema.
    """
    sitespec_path = get_sitespec_path(project_root)

    if not sitespec_path.exists():
        if use_defaults:
            logger.debug("No sitespec.yaml found, using defaults")
            return create_default_sitespec()
        raise SiteSpecError(f"SiteSpec not found: {sitespec_path}")

    try:
        content = sitespec_path.read_text(encoding="utf-8")
        data = yaml.safe_load(content)

        if not data:
            if use_defaults:
                logger.warning(f"Empty sitespec.yaml at {sitespec_path}, using defaults")
                return create_default_sitespec()
            raise SiteSpecError(f"Empty or invalid YAML in {sitespec_path}")

        return _parse_sitespec_data(data)

    except yaml.YAMLError as e:
        raise SiteSpecError(f"Invalid YAML in {sitespec_path}: {e}") from e
    except ValidationError as e:
        raise SiteSpecError(f"Invalid SiteSpec schema in {sitespec_path}: {e}") from e


def save_sitespec(project_root: Path, sitespec: SiteSpec) -> Path:
    """Save SiteSpec to sitespec.yaml.

    Args:
        project_root: Root directory of the DAZZLE project.
        sitespec: SiteSpec to save.

    Returns:
        Path to the saved sitespec.yaml file.
    """
    sitespec_path = get_sitespec_path(project_root)

    # Convert to dict, handling enum serialization
    data = sitespec.model_dump(mode="json")

    # Write YAML
    sitespec_path.write_text(
        yaml.dump(
            data,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    logger.info(f"Saved SiteSpec to {sitespec_path}")
    return sitespec_path


def get_content_file_path(project_root: Path, content_path: str) -> Path:
    """Get the full path to a content file.

    Args:
        project_root: Root directory of the DAZZLE project.
        content_path: Relative path within site/content/.

    Returns:
        Full path to the content file.
    """
    return get_content_dir(project_root) / content_path


def content_file_exists(project_root: Path, content_path: str) -> bool:
    """Check if a content file exists.

    Args:
        project_root: Root directory of the DAZZLE project.
        content_path: Relative path within site/content/.

    Returns:
        True if the content file exists.
    """
    return get_content_file_path(project_root, content_path).exists()


def load_content_file(project_root: Path, content_path: str) -> str:
    """Load content from a file in site/content/.

    Args:
        project_root: Root directory of the DAZZLE project.
        content_path: Relative path within site/content/.

    Returns:
        Content as string.

    Raises:
        SiteSpecError: If file doesn't exist.
    """
    full_path = get_content_file_path(project_root, content_path)

    if not full_path.exists():
        raise SiteSpecError(f"Content file not found: {full_path}")

    return full_path.read_text(encoding="utf-8")


def ensure_content_dir(project_root: Path) -> Path:
    """Ensure the site/content/ directory exists.

    Args:
        project_root: Root directory of the DAZZLE project.

    Returns:
        Path to the content directory.
    """
    content_dir = get_content_dir(project_root)
    content_dir.mkdir(parents=True, exist_ok=True)
    return content_dir


def render_template_vars(
    content: str,
    sitespec: SiteSpec,
    *,
    extra_vars: dict[str, str] | None = None,
) -> str:
    """Render template variables in content.

    Supported variables:
        - {{product_name}}: Brand product name
        - {{company_legal_name}}: Legal company name
        - {{support_email}}: Support email
        - {{year}}: Current year

    Args:
        content: Content string with template variables.
        sitespec: SiteSpec for variable values.
        extra_vars: Additional variables to render.

    Returns:
        Content with variables replaced.
    """
    from datetime import datetime

    vars_map = {
        "{{product_name}}": sitespec.brand.product_name,
        "{{company_legal_name}}": sitespec.brand.company_legal_name or "",
        "{{support_email}}": sitespec.brand.support_email or "",
        "{{year}}": str(datetime.now().year),
    }

    if extra_vars:
        for key, value in extra_vars.items():
            vars_map[f"{{{{{key}}}}}"] = value

    result = content
    for var, value in vars_map.items():
        result = result.replace(var, value)

    return result


# =============================================================================
# Validation
# =============================================================================


class SiteSpecValidationResult:
    """Result of SiteSpec validation."""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def add_error(self, message: str) -> None:
        """Add an error message."""
        self.errors.append(message)

    def add_warning(self, message: str) -> None:
        """Add a warning message."""
        self.warnings.append(message)

    @property
    def is_valid(self) -> bool:
        """True if no errors (warnings are allowed)."""
        return len(self.errors) == 0

    def __repr__(self) -> str:
        return f"SiteSpecValidationResult(errors={len(self.errors)}, warnings={len(self.warnings)})"


def validate_sitespec(
    sitespec: SiteSpec,
    project_root: Path | None = None,
    *,
    check_content_files: bool = True,
    appspec: AppSpec | None = None,
) -> SiteSpecValidationResult:
    """Validate a SiteSpec for semantic correctness.

    Checks:
        - Route uniqueness
        - Route format (must start with /)
        - Content file existence (if project_root provided)
        - CTA href format
        - Legal page consistency
        - Navigation consistency
        - Brand completeness for production

    Args:
        sitespec: SiteSpec to validate.
        project_root: Project root for file existence checks.
        check_content_files: Whether to check content file existence.
        appspec: Optional AppSpec to derive DSL app routes for nav link validation.

    Returns:
        SiteSpecValidationResult with errors and warnings.
    """
    result = SiteSpecValidationResult()

    # Collect all routes for uniqueness check
    routes: dict[str, str] = {}

    def check_route(route: str, source: str) -> None:
        """Check route format and uniqueness."""
        if not route.startswith("/"):
            result.add_error(f"{source}: Route must start with /: {route}")
        if route in routes:
            result.add_error(
                f"{source}: Duplicate route '{route}' (also defined in {routes[route]})"
            )
        else:
            routes[route] = source

    # Validate pages
    for page in sitespec.pages:
        check_route(page.route, f"Page '{page.title or page.route}'")

        # Check content source for markdown pages
        if page.type in (PageKind.MARKDOWN, PageKind.LEGAL) and page.source:
            if check_content_files and project_root:
                if not content_file_exists(project_root, page.source.path):
                    result.add_warning(
                        f"Page '{page.route}': Content file not found: {page.source.path}"
                    )

        # Check redirect pages
        if page.type == PageKind.REDIRECT:
            if not page.redirect_to:
                result.add_error(f"Page '{page.route}': Redirect page must have redirect_to")

        # Validate sections
        for i, section in enumerate(page.sections):
            _validate_section(section, f"Page '{page.route}' section {i + 1}", result)

    # Validate legal pages
    if sitespec.legal.terms:
        check_route(sitespec.legal.terms.route, "Legal terms")
        if check_content_files and project_root:
            if not content_file_exists(project_root, sitespec.legal.terms.source.path):
                result.add_warning(
                    f"Legal terms: Content file not found: {sitespec.legal.terms.source.path}"
                )

    if sitespec.legal.privacy:
        check_route(sitespec.legal.privacy.route, "Legal privacy")
        if check_content_files and project_root:
            if not content_file_exists(project_root, sitespec.legal.privacy.source.path):
                result.add_warning(
                    f"Legal privacy: Content file not found: {sitespec.legal.privacy.source.path}"
                )

    # Validate auth pages
    if sitespec.auth_pages.login.enabled:
        check_route(sitespec.auth_pages.login.route, "Auth login")
    if sitespec.auth_pages.signup.enabled:
        check_route(sitespec.auth_pages.signup.route, "Auth signup")

    # Derive DSL app routes if appspec is available
    dsl_routes: list[str] = []
    if appspec is not None:
        dsl_routes = _derive_dsl_routes(appspec, sitespec)
        for dsl_route in dsl_routes:
            if dsl_route not in routes:
                routes[dsl_route] = "DSL app route"

    # Validate navigation links
    _validate_nav_links(sitespec, routes, result, dsl_routes=dsl_routes)

    # Brand completeness warnings
    if not sitespec.brand.tagline:
        result.add_warning("Brand: No tagline defined")
    if not sitespec.brand.support_email:
        result.add_warning("Brand: No support email defined")
    if not sitespec.brand.company_legal_name:
        result.add_warning("Brand: No company legal name defined (needed for legal pages)")

    # Check legal pages exist for production readiness
    if not sitespec.legal.terms:
        result.add_warning("Legal: No terms of service page defined")
    if not sitespec.legal.privacy:
        result.add_warning("Legal: No privacy policy page defined")

    return result


def _validate_section(
    section: SectionSpec,
    context: str,
    result: SiteSpecValidationResult,
) -> None:
    """Validate a section."""
    # Check CTAs
    if section.primary_cta:
        _validate_cta(section.primary_cta, f"{context} primary_cta", result)
    if section.secondary_cta:
        _validate_cta(section.secondary_cta, f"{context} secondary_cta", result)

    # Section-specific validation
    if section.type == SectionKind.HERO:
        if not section.headline:
            result.add_warning(f"{context}: Hero section should have a headline")

    elif section.type in (SectionKind.FEATURES, SectionKind.FEATURE_GRID):
        if not section.items:
            result.add_warning(f"{context}: Features section has no items")

    elif section.type == SectionKind.PRICING:
        if not section.tiers:
            result.add_error(f"{context}: Pricing section must have tiers")
        for tier in section.tiers:
            if tier.cta:
                _validate_cta(tier.cta, f"{context} tier '{tier.name}'", result)

    elif section.type == SectionKind.FAQ:
        if not section.items:
            result.add_warning(f"{context}: FAQ section has no items")

    elif section.type == SectionKind.TESTIMONIALS:
        if not section.items:
            result.add_warning(f"{context}: Testimonials section has no items")


def _derive_dsl_routes(appspec: AppSpec, sitespec: SiteSpec) -> list[str]:
    """Derive app routes from AppSpec surfaces/workspaces.

    Lightweight inline version of frontend_spec_export._build_route_map()
    to avoid circular imports.
    """
    routes: list[str] = []
    mount = sitespec.integrations.app_mount_route.rstrip("/")

    for surface in appspec.surfaces:
        entity_name = surface.entity_ref or "general"
        slug = _pluralize_slug(entity_name.lower())

        # Find workspace containing this entity
        workspace_slug: str | None = None
        for ws in appspec.workspaces:
            for region in ws.regions:
                if region.source == entity_name:
                    workspace_slug = ws.name
                    break
            if workspace_slug:
                break

        base = f"{mount}/{workspace_slug}/{slug}" if workspace_slug else f"{mount}/{slug}"
        mode = surface.mode.value

        if mode == "list":
            routes.append(base)
        elif mode == "view":
            routes.append(f"{base}/:id")
        elif mode == "create":
            routes.append(f"{base}/new")
        elif mode == "edit":
            routes.append(f"{base}/:id/edit")

    return routes


def _pluralize_slug(name: str) -> str:
    """Naive pluralization for URL slugs."""
    if name.endswith("s"):
        return name + "es"
    if name.endswith("y") and name[-2:] not in ("ay", "ey", "oy", "uy"):
        return name[:-1] + "ies"
    return name + "s"


def _validate_cta(cta: CTASpec, context: str, result: SiteSpecValidationResult) -> None:
    """Validate a CTA."""
    if not cta.label:
        result.add_error(f"{context}: CTA must have a label")
    if not cta.href:
        result.add_error(f"{context}: CTA must have an href")
    elif not cta.href.startswith(("/", "http://", "https://", "mailto:", "tel:")):
        result.add_warning(f"{context}: CTA href '{cta.href}' may not be valid")


def _validate_nav_links(
    sitespec: SiteSpec,
    defined_routes: dict[str, str],
    result: SiteSpecValidationResult,
    *,
    dsl_routes: list[str] | None = None,
) -> None:
    """Validate navigation links point to defined routes or valid URLs."""
    all_nav_items = list(sitespec.layout.nav.public) + list(sitespec.layout.nav.authenticated)

    for col in sitespec.layout.footer.columns:
        all_nav_items.extend(col.links)

    all_known_routes = list(defined_routes.keys()) + (dsl_routes or [])

    for item in all_nav_items:
        href = item.href
        # External links are always valid
        if href.startswith(("http://", "https://", "mailto:", "tel:")):
            continue
        # Internal links should be defined
        if href.startswith("/"):
            if href not in defined_routes and href != sitespec.integrations.app_mount_route:
                msg = f"Navigation link '{item.label}': href '{href}' is not a defined route"
                # Suggest closest match
                matches = difflib.get_close_matches(href, all_known_routes, n=1, cutoff=0.4)
                if matches:
                    msg += f" — did you mean '{matches[0]}'?"
                result.add_warning(msg)


# =============================================================================
# Scaffolding
# =============================================================================


# Default content templates
DEFAULT_TERMS_TEMPLATE = """# Terms of Service

**Last Updated:** {{year}}

These Terms of Service ("Terms") govern your use of {{product_name}} ("Service").

## 1. Acceptance of Terms

By accessing or using the Service, you agree to be bound by these Terms.

## 2. Description of Service

{{product_name}} provides [describe your service here].

## 3. User Accounts

You are responsible for maintaining the confidentiality of your account credentials.

## 4. Acceptable Use

You agree not to use the Service for any unlawful purpose or in violation of these Terms.

## 5. Intellectual Property

All content and materials available on the Service are the property of {{company_legal_name}}.

## 6. Limitation of Liability

TO THE MAXIMUM EXTENT PERMITTED BY LAW, {{company_legal_name}} SHALL NOT BE LIABLE FOR ANY INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, OR PUNITIVE DAMAGES.

## 7. Changes to Terms

We reserve the right to modify these Terms at any time.

## 8. Contact

For questions about these Terms, contact us at {{support_email}}.

---

© {{year}} {{company_legal_name}}. All rights reserved.
"""

DEFAULT_PRIVACY_TEMPLATE = """# Privacy Policy

**Last Updated:** {{year}}

This Privacy Policy describes how {{company_legal_name}} ("we", "us", or "our") collects, uses, and shares your personal information when you use {{product_name}} ("Service").

## 1. Information We Collect

### Information You Provide
- Account information (email, name)
- Content you create or upload
- Communications with us

### Information Collected Automatically
- Usage data and analytics
- Device and browser information
- IP address

## 2. How We Use Your Information

We use your information to:
- Provide and maintain the Service
- Communicate with you
- Improve our Service
- Comply with legal obligations

## 3. Data Sharing

We do not sell your personal information. We may share data with:
- Service providers who assist us
- Legal authorities when required by law

## 4. Data Retention

We retain your information for as long as your account is active or as needed to provide services.

## 5. Your Rights

You have the right to:
- Access your personal data
- Correct inaccurate data
- Request deletion of your data
- Export your data

## 6. Security

We implement appropriate security measures to protect your information.

## 7. Changes to This Policy

We may update this Privacy Policy from time to time.

## 8. Contact Us

For questions about this Privacy Policy, contact us at {{support_email}}.

---

© {{year}} {{company_legal_name}}. All rights reserved.
"""

DEFAULT_ABOUT_TEMPLATE = """# About {{product_name}}

{{product_name}} is designed to help you [describe your product's purpose].

## Our Mission

[Describe your mission here]

## Features

- **Feature 1**: Description of feature 1
- **Feature 2**: Description of feature 2
- **Feature 3**: Description of feature 3

## Contact Us

Have questions? Reach out to us at {{support_email}}.

---

© {{year}} {{company_legal_name}}
"""


def scaffold_site_content(
    project_root: Path,
    sitespec: SiteSpec | None = None,
    *,
    overwrite: bool = False,
    include_copy: bool = True,
) -> list[Path]:
    """Create default site content files.

    Creates the site/content/ directory structure with default
    template files for terms, privacy, about pages, and marketing copy.

    Args:
        project_root: Root directory of the DAZZLE project.
        sitespec: SiteSpec for template variable substitution.
            If None, uses defaults from create_default_sitespec().
        overwrite: If True, overwrite existing files.
        include_copy: If True, also create copy.md for marketing content.

    Returns:
        List of created file paths.
    """
    if sitespec is None:
        sitespec = create_default_sitespec()

    content_dir = ensure_content_dir(project_root)
    created_files: list[Path] = []

    # Define files to create
    files_to_create = [
        ("legal/terms.md", DEFAULT_TERMS_TEMPLATE),
        ("legal/privacy.md", DEFAULT_PRIVACY_TEMPLATE),
        ("pages/about.md", DEFAULT_ABOUT_TEMPLATE),
    ]

    for relative_path, template in files_to_create:
        file_path = content_dir / relative_path

        if file_path.exists() and not overwrite:
            logger.debug(f"Skipping existing file: {file_path}")
            continue

        # Ensure parent directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Render template variables
        content = render_template_vars(template, sitespec)

        # Write file
        file_path.write_text(content, encoding="utf-8")
        created_files.append(file_path)
        logger.info(f"Created content file: {file_path}")

    # Create copy.md for marketing content
    if include_copy:
        from dazzle.core.copy_parser import generate_copy_template

        copy_path = content_dir / COPY_FILE

        if not copy_path.exists() or overwrite:
            content = generate_copy_template(sitespec.brand.product_name)
            copy_path.write_text(content, encoding="utf-8")
            created_files.append(copy_path)
            logger.info(f"Created copy file: {copy_path}")

    return created_files


def scaffold_sitespec(
    project_root: Path,
    product_name: str = "My App",
    *,
    overwrite: bool = False,
) -> Path | None:
    """Create a default sitespec.yaml file.

    Args:
        project_root: Root directory of the DAZZLE project.
        product_name: Product name to use in the template.
        overwrite: If True, overwrite existing file.

    Returns:
        Path to created file, or None if skipped.
    """
    sitespec_path = get_sitespec_path(project_root)

    if sitespec_path.exists() and not overwrite:
        logger.debug(f"Skipping existing sitespec: {sitespec_path}")
        return None

    # Create a minimal sitespec with sensible defaults
    sitespec = create_default_sitespec(product_name=product_name)
    return save_sitespec(project_root, sitespec)


def scaffold_site(
    project_root: Path,
    product_name: str = "My App",
    *,
    overwrite: bool = False,
) -> dict[str, list[Path] | Path | None]:
    """Scaffold a complete site structure.

    Creates:
    - sitespec.yaml
    - site/content/copy.md (founder-friendly marketing content)
    - site/content/legal/terms.md
    - site/content/legal/privacy.md
    - site/content/pages/about.md

    The copy.md file is the primary place for founders to edit marketing
    content. It uses a simple markdown format that's easy to read and
    works well with LLM-generated content.

    Args:
        project_root: Root directory of the DAZZLE project.
        product_name: Product name to use in templates.
        overwrite: If True, overwrite existing files.

    Returns:
        Dict with 'sitespec' (Path or None) and 'content' (list of Paths).
    """
    sitespec = create_default_sitespec(product_name=product_name)

    sitespec_path = scaffold_sitespec(project_root, product_name, overwrite=overwrite)
    content_files = scaffold_site_content(project_root, sitespec, overwrite=overwrite)

    return {
        "sitespec": sitespec_path,
        "content": content_files,
    }


# =============================================================================
# Copy File Integration (v0.22.0)
# =============================================================================


def get_copy_file_path(project_root: Path) -> Path:
    """Get the path to the copy.md file.

    Args:
        project_root: Root directory of the DAZZLE project.

    Returns:
        Path to site/content/copy.md.
    """
    return get_content_dir(project_root) / COPY_FILE


def copy_file_exists(project_root: Path) -> bool:
    """Check if copy.md exists in the project.

    Args:
        project_root: Root directory of the DAZZLE project.

    Returns:
        True if copy.md exists.
    """
    return get_copy_file_path(project_root).exists()


def load_copy(project_root: Path) -> dict[str, Any] | None:
    """Load and parse copy.md from the project.

    Args:
        project_root: Root directory of the DAZZLE project.

    Returns:
        Parsed copy as dictionary, or None if file doesn't exist.
    """
    from dazzle.core.copy_parser import load_copy_file

    parsed = load_copy_file(project_root)
    if parsed is None:
        return None

    return parsed.to_dict()


def merge_copy_into_sitespec(
    sitespec: SiteSpec,
    copy_data: dict[str, Any],
) -> SiteSpec:
    """Merge parsed copy data into SiteSpec sections.

    This allows founders to write marketing copy in copy.md while
    keeping structural configuration in sitespec.yaml. Copy content
    takes precedence over inline sitespec content.

    Args:
        sitespec: Base SiteSpec (from sitespec.yaml).
        copy_data: Parsed copy data (from copy.md).

    Returns:
        SiteSpec with merged content.
    """
    if not copy_data or "sections" not in copy_data:
        return sitespec

    # Build section lookup from copy data
    copy_sections = {s["type"]: s for s in copy_data["sections"]}

    # Convert copy sections to sitespec sections
    copy_spec_sections = _copy_sections_to_sitespec(copy_sections)

    if not copy_spec_sections:
        return sitespec

    # Build lookup of copy.md section types that were successfully parsed
    copy_section_types = {s.type for s in copy_spec_sections}

    # Find landing page index or create new
    landing_idx = None
    for i, page in enumerate(sitespec.pages):
        if page.route == "/":
            landing_idx = i
            break

    # Build updated pages list (Pydantic models are frozen)
    new_pages = list(sitespec.pages)
    if landing_idx is not None:
        old_landing = new_pages[landing_idx]

        # MERGE sections: copy.md sections replace same-type sitespec sections,
        # but sitespec sections NOT in copy.md are preserved (e.g., pricing)
        merged_sections: list[SectionSpec] = []

        # First, add sections from copy.md in their order
        merged_sections.extend(copy_spec_sections)

        # Then, add sitespec sections that weren't in copy.md
        for existing_section in old_landing.sections:
            if existing_section.type not in copy_section_types:
                merged_sections.append(existing_section)

        new_landing = old_landing.model_copy(update={"sections": merged_sections})
        new_pages[landing_idx] = new_landing
    else:
        # Create a new landing page
        new_landing = PageSpec(
            route="/", type=PageKind.LANDING, title="Home", sections=copy_spec_sections
        )
        new_pages.insert(0, new_landing)

    # Return updated SiteSpec
    return sitespec.model_copy(update={"pages": new_pages})


def _copy_sections_to_sitespec(copy_sections: dict[str, Any]) -> list[SectionSpec]:
    """Convert copy sections to SiteSpec sections.

    Args:
        copy_sections: Dict of section_type -> section_data from copy parser.

    Returns:
        List of SectionSpec objects.
    """
    result: list[SectionSpec] = []

    # Map section types to their order
    section_order = ["hero", "features", "how-it-works", "testimonials", "pricing", "faq", "cta"]

    for section_type in section_order:
        if section_type not in copy_sections:
            continue

        section_data = copy_sections[section_type]
        spec = _copy_section_to_spec(section_type, section_data)
        if spec:
            result.append(spec)

    # Add any remaining sections not in the standard order
    for section_type, section_data in copy_sections.items():
        if section_type not in section_order:
            spec = _copy_section_to_spec(section_type, section_data)
            if spec:
                result.append(spec)

    return result


def _copy_section_to_spec(section_type: str, data: dict[str, Any]) -> SectionSpec | None:
    """Convert a single copy section to a SectionSpec.

    Args:
        section_type: Type of section (hero, features, etc.).
        data: Section data from copy parser.

    Returns:
        SectionSpec or None if conversion fails.
    """
    metadata = data.get("metadata", {})
    subsections = data.get("subsections", [])

    # Map section types to SectionKind
    type_mapping = {
        "hero": SectionKind.HERO,
        "features": SectionKind.FEATURES,
        "how-it-works": SectionKind.STEPS,
        "testimonials": SectionKind.TESTIMONIALS,
        "pricing": SectionKind.PRICING,
        "faq": SectionKind.FAQ,
        "cta": SectionKind.CTA,
        "about": SectionKind.HERO,  # Treat about as a hero-style section
    }

    kind = type_mapping.get(section_type, SectionKind.HERO)

    # Build the section spec
    primary_cta = None
    secondary_cta = None

    # Extract CTAs from metadata
    ctas = metadata.get("ctas", [])
    if ctas:
        primary_cta = CTASpec(label=ctas[0].get("text", ""), href=ctas[0].get("url", "/"))
        if len(ctas) > 1:
            secondary_cta = CTASpec(label=ctas[1].get("text", ""), href=ctas[1].get("url", "/"))

    # Build items from subsections
    items: list[Any] = []
    tiers: list[PricingTier] = []

    if kind == SectionKind.FEATURES:
        items = [
            FeatureItem(
                title=sub.get("title", ""),
                body=sub.get("description", ""),
                icon=sub.get("icon"),
            )
            for sub in subsections
        ]
    elif kind == SectionKind.STEPS:
        items = [
            StepItem(
                step=i + 1,
                title=sub.get("title", ""),
                body=sub.get("content", sub.get("description", "")),
            )
            for i, sub in enumerate(subsections)
        ]
    elif kind == SectionKind.TESTIMONIALS:
        items = [
            TestimonialItem(
                quote=sub.get("quote", ""),
                author=sub.get("name", sub.get("attribution", "")),
                role=sub.get("role"),
            )
            for sub in subsections
        ]
    elif kind == SectionKind.PRICING:
        for sub in subsections:
            # Skip tiers with missing required fields (price parsing failed)
            # This prevents copy.md from overwriting valid sitespec pricing
            tier_price = sub.get("price")
            if tier_price is None:
                logger.debug(
                    f"Skipping pricing tier '{sub.get('name')}' - price not parsed. "
                    "Define structured pricing in sitespec.yaml instead."
                )
                continue

            tier_cta = None
            tier_name = sub.get("name", "")
            if tier_name:
                tier_cta = CTASpec(label=f"Get {tier_name}", href="/signup")

            # Use parsed values, with sensible defaults for optional fields
            tiers.append(
                PricingTier(
                    name=tier_name,
                    price=str(tier_price),  # Ensure string
                    period=sub.get("period") or "month",
                    features=sub.get("features") or [],
                    cta=tier_cta,
                )
            )
    elif kind == SectionKind.FAQ:
        items = [
            FAQItem(
                question=sub.get("question", ""),
                answer=sub.get("answer", ""),
            )
            for sub in subsections
        ]

    # Skip pricing sections with no valid tiers (parsing failed)
    # This prevents copy.md from overwriting valid sitespec pricing
    if kind == SectionKind.PRICING and not tiers:
        logger.debug(
            "Skipping pricing section from copy.md - no valid tiers parsed. "
            "Define structured pricing in sitespec.yaml instead."
        )
        return None

    return SectionSpec(
        type=kind,
        headline=metadata.get("headline") or data.get("title"),
        subhead=metadata.get("subheadline") or metadata.get("description"),
        primary_cta=primary_cta,
        secondary_cta=secondary_cta,
        items=items if items else [],
        tiers=tiers if tiers else [],
    )


def load_sitespec_with_copy(
    project_root: Path,
    *,
    use_defaults: bool = True,
) -> SiteSpec:
    """Load SiteSpec and merge copy.md content if available.

    This is the recommended way to load site configuration as it
    combines both sitespec.yaml (structure) and copy.md (content).

    Args:
        project_root: Root directory of the DAZZLE project.
        use_defaults: If True, return default SiteSpec when file doesn't exist.

    Returns:
        SiteSpec with copy content merged in.
    """
    sitespec = load_sitespec(project_root, use_defaults=use_defaults)

    # Load and merge copy if available
    copy_data = load_copy(project_root)
    if copy_data:
        logger.debug("Merging copy.md content into SiteSpec")
        sitespec = merge_copy_into_sitespec(sitespec, copy_data)

    return sitespec


def scaffold_copy_file(
    project_root: Path,
    product_name: str = "My App",
    *,
    overwrite: bool = False,
) -> Path | None:
    """Create a template copy.md file.

    Args:
        project_root: Root directory of the DAZZLE project.
        product_name: Product name to use in the template.
        overwrite: If True, overwrite existing file.

    Returns:
        Path to created file, or None if skipped.
    """
    from dazzle.core.copy_parser import generate_copy_template

    copy_path = get_copy_file_path(project_root)

    if copy_path.exists() and not overwrite:
        logger.debug(f"Skipping existing copy file: {copy_path}")
        return None

    # Ensure parent directory exists
    copy_path.parent.mkdir(parents=True, exist_ok=True)

    # Generate and write template
    content = generate_copy_template(product_name)
    copy_path.write_text(content, encoding="utf-8")
    logger.info(f"Created copy file: {copy_path}")

    return copy_path
