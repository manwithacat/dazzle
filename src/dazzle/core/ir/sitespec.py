"""
SiteSpec types for DAZZLE IR.

This module contains the specification for public-facing site shell pages:
- Landing pages with marketing sections (hero, features, CTA, etc.)
- Content pages (about, legal) sourced from Markdown
- Navigation, footer, and branding

SiteSpec is separate from AppSpec to keep domain logic clean.

Design Document: dev_docs/content_management.md
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

# =============================================================================
# Brand and Identity
# =============================================================================


class LogoMode(StrEnum):
    """How the logo is displayed."""

    TEXT = "text"
    IMAGE = "image"


class LogoSpec(BaseModel):
    """
    Logo configuration.

    Attributes:
        mode: Display mode (text or image)
        text: Text to display when mode is 'text'
        image_path: Path to logo image when mode is 'image'
        alt: Alt text for the logo image
    """

    mode: LogoMode = LogoMode.TEXT
    text: str | None = None
    image_path: str | None = None
    alt: str | None = None

    model_config = ConfigDict(frozen=True)


class BrandSpec(BaseModel):
    """
    Brand identity configuration.

    Attributes:
        product_name: The product/service name
        tagline: Short value proposition
        logo: Logo configuration
        support_email: Support contact email
        company_legal_name: Legal entity name (for footer, terms, etc.)
    """

    product_name: str
    tagline: str | None = None
    logo: LogoSpec = Field(default_factory=LogoSpec)
    support_email: str | None = None
    company_legal_name: str | None = None

    model_config = ConfigDict(frozen=True)


# =============================================================================
# Navigation
# =============================================================================


class NavItemSpec(BaseModel):
    """
    A navigation menu item.

    Attributes:
        label: Display text
        href: Target URL or route
    """

    label: str
    href: str

    model_config = ConfigDict(frozen=True)


class FooterColumnSpec(BaseModel):
    """
    A column in the footer with links.

    Attributes:
        title: Column heading
        links: List of navigation items
    """

    title: str
    links: list[NavItemSpec] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)


class FooterSpec(BaseModel):
    """
    Footer configuration.

    Attributes:
        columns: Footer link columns
        disclaimer: Copyright/legal disclaimer (supports {{year}}, {{company_legal_name}})
    """

    columns: list[FooterColumnSpec] = Field(default_factory=list)
    disclaimer: str | None = None

    model_config = ConfigDict(frozen=True)


class AuthEntrySpec(BaseModel):
    """
    Authentication entry point configuration.

    Attributes:
        primary_entry: Where CTAs point for unauthenticated users
    """

    primary_entry: str = "/login"

    model_config = ConfigDict(frozen=True)


class NavSpec(BaseModel):
    """
    Navigation configuration.

    Attributes:
        public: Navigation items visible to unauthenticated users
        authenticated: Navigation items visible to authenticated users
    """

    public: list[NavItemSpec] = Field(default_factory=list)
    authenticated: list[NavItemSpec] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)


class ThemeKind(StrEnum):
    """Available site themes."""

    SAAS_DEFAULT = "saas-default"
    MINIMAL = "minimal"
    CUSTOM = "custom"


class LayoutSpec(BaseModel):
    """
    Site layout configuration.

    Attributes:
        theme: Visual theme
        auth: Authentication entry configuration
        nav: Navigation configuration
        footer: Footer configuration
    """

    theme: ThemeKind = ThemeKind.SAAS_DEFAULT
    auth: AuthEntrySpec = Field(default_factory=AuthEntrySpec)
    nav: NavSpec = Field(default_factory=NavSpec)
    footer: FooterSpec = Field(default_factory=FooterSpec)

    model_config = ConfigDict(frozen=True)


# =============================================================================
# Page Sections
# =============================================================================


class CTASpec(BaseModel):
    """
    Call-to-action button.

    Attributes:
        label: Button text
        href: Target URL or route
    """

    label: str
    href: str

    model_config = ConfigDict(frozen=True)


class MediaKind(StrEnum):
    """Media types for sections."""

    NONE = "none"
    IMAGE = "image"
    VIDEO = "video"


class MediaSpec(BaseModel):
    """
    Media configuration for sections.

    Attributes:
        kind: Type of media
        src: Source path or URL
        alt: Alt text for accessibility
    """

    kind: MediaKind = MediaKind.NONE
    src: str | None = None
    alt: str | None = None

    model_config = ConfigDict(frozen=True)


class SectionKind(StrEnum):
    """Types of page sections."""

    HERO = "hero"
    FEATURES = "features"
    FEATURE_GRID = "feature_grid"
    CTA = "cta"
    FAQ = "faq"
    TESTIMONIALS = "testimonials"
    STATS = "stats"
    STEPS = "steps"
    LOGO_CLOUD = "logo_cloud"
    PRICING = "pricing"
    MARKDOWN = "markdown"
    COMPARISON = "comparison"
    VALUE_HIGHLIGHT = "value_highlight"
    SPLIT_CONTENT = "split_content"
    CARD_GRID = "card_grid"
    TRUST_BAR = "trust_bar"


class FeatureItem(BaseModel):
    """A feature in a features section."""

    title: str
    body: str
    icon: str | None = None

    model_config = ConfigDict(frozen=True)


class FAQItem(BaseModel):
    """A question/answer in an FAQ section."""

    question: str
    answer: str

    model_config = ConfigDict(frozen=True)


class TestimonialItem(BaseModel):
    """A testimonial quote."""

    quote: str
    author: str
    role: str | None = None
    company: str | None = None
    avatar: str | None = None

    model_config = ConfigDict(frozen=True)


class StatItem(BaseModel):
    """A statistic for display."""

    value: str
    label: str

    model_config = ConfigDict(frozen=True)


class StepItem(BaseModel):
    """A step in a process."""

    step: int
    title: str
    body: str

    model_config = ConfigDict(frozen=True)


class LogoItem(BaseModel):
    """A logo in a logo cloud."""

    name: str
    src: str
    href: str | None = None

    model_config = ConfigDict(frozen=True)


class PricingTier(BaseModel):
    """A pricing tier."""

    name: str
    price: str
    period: str = "month"
    description: str | None = None
    features: list[str] = Field(default_factory=list)
    cta: CTASpec | None = None
    highlighted: bool = False

    model_config = ConfigDict(frozen=True)


class ComparisonColumn(BaseModel):
    """A column in a comparison table."""

    label: str
    highlighted: bool = False

    model_config = ConfigDict(frozen=True)


class ComparisonRow(BaseModel):
    """A row in a comparison table."""

    feature: str
    cells: list[str] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)


class CardItem(BaseModel):
    """A card in a card grid."""

    title: str
    body: str
    icon: str | None = None
    cta: CTASpec | None = None

    model_config = ConfigDict(frozen=True)


class TrustBarItem(BaseModel):
    """An item in a trust bar strip."""

    text: str
    icon: str | None = None

    model_config = ConfigDict(frozen=True)


class SectionSpec(BaseModel):
    """
    A section within a landing page.

    Each section has a type and type-specific content.
    Only fields relevant to the section type are used.

    Attributes:
        type: Section type
        headline: Main heading (hero, cta)
        subhead: Secondary heading (hero)
        body: Body text (cta, value_highlight)
        primary_cta: Primary call-to-action (hero, cta)
        secondary_cta: Secondary call-to-action (hero)
        media: Media content (hero, split_content)
        items: List items (features, faq, testimonials, etc.)
        tiers: Pricing tiers (pricing)
        source: Content source (markdown sections)
        columns: Comparison table columns (comparison)
        alignment: Layout alignment (split_content)
    """

    type: SectionKind
    headline: str | None = None
    subhead: str | None = None
    body: str | None = None
    primary_cta: CTASpec | None = None
    secondary_cta: CTASpec | None = None
    media: MediaSpec | None = None

    # Type-specific item lists (only one will be used based on type)
    items: (
        list[FeatureItem]
        | list[FAQItem]
        | list[TestimonialItem]
        | list[StatItem]
        | list[StepItem]
        | list[LogoItem]
        | list[ComparisonRow]
        | list[CardItem]
        | list[TrustBarItem]
    ) = Field(default_factory=list)

    # Pricing-specific
    tiers: list[PricingTier] = Field(default_factory=list)

    # Markdown section source
    source: ContentSourceSpec | None = None

    # Comparison-specific
    columns: list[ComparisonColumn] = Field(default_factory=list)

    # Split content alignment
    alignment: str | None = None

    model_config = ConfigDict(frozen=True)


# =============================================================================
# Content Sources
# =============================================================================


class ContentFormat(StrEnum):
    """Supported content formats."""

    MARKDOWN = "md"
    MDX = "mdx"  # Reserved for future use


class ContentSourceSpec(BaseModel):
    """
    Reference to file-based content.

    Attributes:
        format: Content format (md, mdx)
        path: Path relative to site/content/
    """

    format: ContentFormat = ContentFormat.MARKDOWN
    path: str

    model_config = ConfigDict(frozen=True)


# =============================================================================
# Pages
# =============================================================================


class PageKind(StrEnum):
    """Types of pages."""

    LANDING = "landing"
    MARKDOWN = "markdown"
    LEGAL = "legal"
    PRICING = "pricing"
    REDIRECT = "redirect"


class PageSpec(BaseModel):
    """
    A page in the site.

    Attributes:
        route: URL path (must start with /)
        type: Page type
        title: Page title (for <title> tag and nav)
        sections: List of sections (for landing/pricing pages)
        source: Content source (for markdown/legal pages)
        redirect_to: Target route (for redirect pages)
    """

    route: str
    type: PageKind = PageKind.LANDING
    title: str | None = None
    sections: list[SectionSpec] = Field(default_factory=list)
    source: ContentSourceSpec | None = None
    redirect_to: str | None = None

    model_config = ConfigDict(frozen=True)


class LegalPageSpec(BaseModel):
    """
    A legal page (terms, privacy, etc.).

    Attributes:
        route: URL path
        source: Content source
    """

    route: str
    source: ContentSourceSpec

    model_config = ConfigDict(frozen=True)


class AuthPageMode(StrEnum):
    """Auth page generation mode."""

    GENERATED = "generated"
    CUSTOM = "custom"


class AuthPageSpec(BaseModel):
    """
    Authentication page configuration.

    Attributes:
        route: URL path
        mode: Generation mode
        enabled: Whether this auth page is enabled
    """

    route: str
    mode: AuthPageMode = AuthPageMode.GENERATED
    enabled: bool = True

    model_config = ConfigDict(frozen=True)


class AuthPagesSpec(BaseModel):
    """
    Authentication pages configuration.

    Attributes:
        login: Login page config
        signup: Signup page config
    """

    login: AuthPageSpec = Field(default_factory=lambda: AuthPageSpec(route="/login"))
    signup: AuthPageSpec = Field(default_factory=lambda: AuthPageSpec(route="/signup"))

    model_config = ConfigDict(frozen=True)


class LegalPagesSpec(BaseModel):
    """
    Legal pages configuration.

    Attributes:
        terms: Terms of service page
        privacy: Privacy policy page
    """

    terms: LegalPageSpec | None = None
    privacy: LegalPageSpec | None = None

    model_config = ConfigDict(frozen=True)


# =============================================================================
# Integration Points
# =============================================================================


class AuthProvider(StrEnum):
    """Authentication provider options."""

    DAZZLE = "dazzle"
    EXTERNAL = "external"


class IntegrationsSpec(BaseModel):
    """
    Integration points with the generated application.

    Attributes:
        app_mount_route: Where the app is mounted (default /app)
        auth_provider: Authentication provider
    """

    app_mount_route: str = "/app"
    auth_provider: AuthProvider = AuthProvider.DAZZLE

    model_config = ConfigDict(frozen=True)


# =============================================================================
# Site Specification
# =============================================================================


class SiteSpec(BaseModel):
    """
    Complete site specification.

    SiteSpec defines the public-facing site shell that wraps
    a Dazzle-generated application. It is loaded from sitespec.yaml
    and kept separate from the AppSpec.

    Attributes:
        version: Spec version (currently 1)
        brand: Brand identity
        layout: Layout configuration (theme, nav, footer)
        pages: List of pages
        legal: Legal pages (terms, privacy)
        auth_pages: Authentication pages
        integrations: Integration with the app
    """

    version: int = 1
    brand: BrandSpec = Field(default_factory=lambda: BrandSpec(product_name="My App"))
    layout: LayoutSpec = Field(default_factory=LayoutSpec)
    pages: list[PageSpec] = Field(default_factory=list)
    legal: LegalPagesSpec = Field(default_factory=LegalPagesSpec)
    auth_pages: AuthPagesSpec = Field(default_factory=AuthPagesSpec)
    integrations: IntegrationsSpec = Field(default_factory=IntegrationsSpec)

    model_config = ConfigDict(frozen=True)

    def get_page(self, route: str) -> PageSpec | None:
        """Get a page by route."""
        for page in self.pages:
            if page.route == route:
                return page
        return None

    def get_all_routes(self) -> list[str]:
        """Get all defined routes."""
        routes = [page.route for page in self.pages]

        if self.legal.terms:
            routes.append(self.legal.terms.route)
        if self.legal.privacy:
            routes.append(self.legal.privacy.route)

        if self.auth_pages.login.enabled:
            routes.append(self.auth_pages.login.route)
        if self.auth_pages.signup.enabled:
            routes.append(self.auth_pages.signup.route)

        return routes


# =============================================================================
# Default SiteSpec Factory
# =============================================================================


def create_default_sitespec(
    product_name: str = "My App",
    tagline: str = "Build something amazing.",
    support_email: str = "support@example.com",
    company_legal_name: str = "My Company Ltd",
) -> SiteSpec:
    """
    Create a default SiteSpec with sensible defaults.

    This is used when no sitespec.yaml is provided.
    """
    return SiteSpec(
        version=1,
        brand=BrandSpec(
            product_name=product_name,
            tagline=tagline,
            logo=LogoSpec(mode=LogoMode.TEXT, text=product_name),
            support_email=support_email,
            company_legal_name=company_legal_name,
        ),
        layout=LayoutSpec(
            theme=ThemeKind.SAAS_DEFAULT,
            auth=AuthEntrySpec(primary_entry="/login"),
            nav=NavSpec(
                public=[
                    NavItemSpec(label="Home", href="/"),
                    NavItemSpec(label="Pricing", href="/pricing"),
                    NavItemSpec(label="About", href="/about"),
                ],
                authenticated=[
                    NavItemSpec(label="App", href="/app"),
                ],
            ),
            footer=FooterSpec(
                columns=[
                    FooterColumnSpec(
                        title="Product",
                        links=[
                            NavItemSpec(label="Home", href="/"),
                            NavItemSpec(label="Pricing", href="/pricing"),
                        ],
                    ),
                    FooterColumnSpec(
                        title="Legal",
                        links=[
                            NavItemSpec(label="Terms", href="/terms"),
                            NavItemSpec(label="Privacy", href="/privacy"),
                        ],
                    ),
                ],
                disclaimer="© {{year}} {{company_legal_name}}",
            ),
        ),
        pages=[
            PageSpec(
                route="/",
                type=PageKind.LANDING,
                title="Welcome",
                sections=[
                    SectionSpec(
                        type=SectionKind.HERO,
                        headline=tagline,
                        subhead="Get started in minutes with our intuitive platform.",
                        primary_cta=CTASpec(label="Get Started", href="/login"),
                        secondary_cta=CTASpec(label="Learn More", href="/about"),
                    ),
                    SectionSpec(
                        type=SectionKind.FEATURES,
                        headline="Why Choose Us",
                        items=[
                            FeatureItem(
                                title="Easy Setup",
                                body="Get up and running in minutes, not hours.",
                            ),
                            FeatureItem(
                                title="Powerful Features",
                                body="Everything you need to run your business.",
                            ),
                            FeatureItem(
                                title="Great Support",
                                body="We're here to help when you need us.",
                            ),
                        ],
                    ),
                    SectionSpec(
                        type=SectionKind.CTA,
                        headline="Ready to get started?",
                        primary_cta=CTASpec(label="Sign Up Free", href="/signup"),
                    ),
                ],
            ),
            PageSpec(
                route="/about",
                type=PageKind.MARKDOWN,
                title="About",
                source=ContentSourceSpec(
                    format=ContentFormat.MARKDOWN,
                    path="pages/about.md",
                ),
            ),
            PageSpec(
                route="/pricing",
                type=PageKind.PRICING,
                title="Pricing",
                sections=[
                    SectionSpec(
                        type=SectionKind.PRICING,
                        headline="Simple, Transparent Pricing",
                        subhead="Choose the plan that works for you.",
                        tiers=[
                            PricingTier(
                                name="Free",
                                price="$0",
                                description="For individuals getting started.",
                                features=["Up to 3 projects", "Basic support", "1 user"],
                                cta=CTASpec(label="Start Free", href="/signup"),
                            ),
                            PricingTier(
                                name="Pro",
                                price="$29",
                                description="For growing teams.",
                                features=[
                                    "Unlimited projects",
                                    "Priority support",
                                    "Up to 10 users",
                                    "Advanced features",
                                ],
                                cta=CTASpec(label="Start Trial", href="/signup?plan=pro"),
                                highlighted=True,
                            ),
                            PricingTier(
                                name="Enterprise",
                                price="Custom",
                                description="For large organizations.",
                                features=[
                                    "Everything in Pro",
                                    "Dedicated support",
                                    "Unlimited users",
                                    "Custom integrations",
                                    "SLA guarantee",
                                ],
                                cta=CTASpec(label="Contact Sales", href="/contact"),
                            ),
                        ],
                    ),
                ],
            ),
        ],
        legal=LegalPagesSpec(
            terms=LegalPageSpec(
                route="/terms",
                source=ContentSourceSpec(
                    format=ContentFormat.MARKDOWN,
                    path="legal/terms.md",
                ),
            ),
            privacy=LegalPageSpec(
                route="/privacy",
                source=ContentSourceSpec(
                    format=ContentFormat.MARKDOWN,
                    path="legal/privacy.md",
                ),
            ),
        ),
        auth_pages=AuthPagesSpec(
            login=AuthPageSpec(route="/login", mode=AuthPageMode.GENERATED, enabled=True),
            signup=AuthPageSpec(route="/signup", mode=AuthPageMode.GENERATED, enabled=True),
        ),
        integrations=IntegrationsSpec(
            app_mount_route="/app",
            auth_provider=AuthProvider.DAZZLE,
        ),
    )
