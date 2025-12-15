"""
SiteSpec persistence layer for DAZZLE public site shell.

Handles reading and writing SiteSpec configurations to sitespec.yaml
in the project root. SiteSpec is separate from the DSL and AppSpec.

Default location: {project_root}/sitespec.yaml
Content directory: {project_root}/site/content/
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

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

    # Validate navigation links
    _validate_nav_links(sitespec, routes, result)

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
) -> None:
    """Validate navigation links point to defined routes or valid URLs."""
    all_nav_items = list(sitespec.layout.nav.public) + list(sitespec.layout.nav.authenticated)

    for col in sitespec.layout.footer.columns:
        all_nav_items.extend(col.links)

    for item in all_nav_items:
        href = item.href
        # External links are always valid
        if href.startswith(("http://", "https://", "mailto:", "tel:")):
            continue
        # Internal links should be defined
        if href.startswith("/"):
            if href not in defined_routes and href != sitespec.integrations.app_mount_route:
                result.add_warning(
                    f"Navigation link '{item.label}': href '{href}' is not a defined route"
                )


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
) -> list[Path]:
    """Create default site content files.

    Creates the site/content/ directory structure with default
    template files for terms, privacy, and about pages.

    Args:
        project_root: Root directory of the DAZZLE project.
        sitespec: SiteSpec for template variable substitution.
            If None, uses defaults from create_default_sitespec().
        overwrite: If True, overwrite existing files.

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
    - site/content/legal/terms.md
    - site/content/legal/privacy.md
    - site/content/pages/about.md

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
