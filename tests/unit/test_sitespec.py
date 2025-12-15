"""Unit tests for SiteSpec IR types and loader."""

import tempfile
from pathlib import Path

import pytest
import yaml

from dazzle.core.ir.sitespec import (
    BrandSpec,
    ContentFormat,
    ContentSourceSpec,
    CTASpec,
    FAQItem,
    FeatureItem,
    FooterColumnSpec,
    FooterSpec,
    LayoutSpec,
    LogoMode,
    LogoSpec,
    NavItemSpec,
    NavSpec,
    PageKind,
    PageSpec,
    PricingTier,
    SectionKind,
    SectionSpec,
    SiteSpec,
    ThemeKind,
    create_default_sitespec,
)
from dazzle.core.sitespec_loader import (
    SiteSpecError,
    load_sitespec,
    render_template_vars,
    scaffold_site,
    sitespec_exists,
    validate_sitespec,
)


class TestSiteSpecIR:
    """Tests for SiteSpec IR types."""

    def test_brand_spec(self) -> None:
        """Test BrandSpec creation."""
        brand = BrandSpec(
            product_name="TestApp",
            tagline="Build amazing things",
            support_email="support@example.com",
        )
        assert brand.product_name == "TestApp"
        assert brand.tagline == "Build amazing things"

    def test_logo_spec(self) -> None:
        """Test LogoSpec with different modes."""
        text_logo = LogoSpec(mode=LogoMode.TEXT, text="MyApp")
        assert text_logo.mode == LogoMode.TEXT
        assert text_logo.text == "MyApp"

        image_logo = LogoSpec(mode=LogoMode.IMAGE, image_path="/img/logo.png")
        assert image_logo.mode == LogoMode.IMAGE

    def test_nav_item_spec(self) -> None:
        """Test NavItemSpec creation."""
        item = NavItemSpec(label="Home", href="/")
        assert item.label == "Home"
        assert item.href == "/"

    def test_section_spec_hero(self) -> None:
        """Test hero section."""
        section = SectionSpec(
            type=SectionKind.HERO,
            headline="Welcome",
            subhead="Get started today",
            primary_cta=CTASpec(label="Sign Up", href="/signup"),
        )
        assert section.type == SectionKind.HERO
        assert section.headline == "Welcome"
        assert section.primary_cta is not None
        assert section.primary_cta.label == "Sign Up"

    def test_section_spec_features(self) -> None:
        """Test features section."""
        section = SectionSpec(
            type=SectionKind.FEATURES,
            headline="Features",
            items=[
                FeatureItem(title="Fast", body="Lightning fast performance"),
                FeatureItem(title="Secure", body="Enterprise-grade security"),
            ],
        )
        assert section.type == SectionKind.FEATURES
        assert len(section.items) == 2

    def test_section_spec_faq(self) -> None:
        """Test FAQ section."""
        section = SectionSpec(
            type=SectionKind.FAQ,
            headline="FAQ",
            items=[
                FAQItem(question="What is it?", answer="A great product!"),
            ],
        )
        assert section.type == SectionKind.FAQ
        assert len(section.items) == 1

    def test_section_spec_pricing(self) -> None:
        """Test pricing section."""
        section = SectionSpec(
            type=SectionKind.PRICING,
            headline="Pricing",
            tiers=[
                PricingTier(
                    name="Free",
                    price="$0",
                    features=["Basic support", "1 user"],
                ),
                PricingTier(
                    name="Pro",
                    price="$29",
                    features=["Priority support", "10 users"],
                    highlighted=True,
                ),
            ],
        )
        assert section.type == SectionKind.PRICING
        assert len(section.tiers) == 2
        assert section.tiers[1].highlighted is True

    def test_page_spec_landing(self) -> None:
        """Test landing page spec."""
        page = PageSpec(
            route="/",
            type=PageKind.LANDING,
            title="Home",
            sections=[
                SectionSpec(type=SectionKind.HERO, headline="Welcome"),
            ],
        )
        assert page.route == "/"
        assert page.type == PageKind.LANDING
        assert len(page.sections) == 1

    def test_page_spec_markdown(self) -> None:
        """Test markdown page spec."""
        page = PageSpec(
            route="/about",
            type=PageKind.MARKDOWN,
            title="About",
            source=ContentSourceSpec(
                format=ContentFormat.MARKDOWN,
                path="pages/about.md",
            ),
        )
        assert page.type == PageKind.MARKDOWN
        assert page.source is not None
        assert page.source.path == "pages/about.md"

    def test_sitespec_complete(self) -> None:
        """Test complete SiteSpec creation."""
        spec = SiteSpec(
            version=1,
            brand=BrandSpec(product_name="TestApp"),
            layout=LayoutSpec(
                theme=ThemeKind.SAAS_DEFAULT,
                nav=NavSpec(
                    public=[NavItemSpec(label="Home", href="/")],
                ),
                footer=FooterSpec(
                    columns=[
                        FooterColumnSpec(
                            title="Links",
                            links=[NavItemSpec(label="Home", href="/")],
                        )
                    ],
                    disclaimer="© 2025 TestApp",
                ),
            ),
            pages=[
                PageSpec(
                    route="/",
                    type=PageKind.LANDING,
                    title="Home",
                ),
            ],
        )
        assert spec.version == 1
        assert spec.brand.product_name == "TestApp"
        assert len(spec.pages) == 1

    def test_sitespec_get_page(self) -> None:
        """Test SiteSpec.get_page method."""
        spec = SiteSpec(
            brand=BrandSpec(product_name="Test"),
            pages=[
                PageSpec(route="/", type=PageKind.LANDING, title="Home"),
                PageSpec(route="/about", type=PageKind.MARKDOWN, title="About"),
            ],
        )
        home = spec.get_page("/")
        assert home is not None
        assert home.title == "Home"

        about = spec.get_page("/about")
        assert about is not None
        assert about.title == "About"

        missing = spec.get_page("/missing")
        assert missing is None

    def test_sitespec_get_all_routes(self) -> None:
        """Test SiteSpec.get_all_routes method."""
        spec = create_default_sitespec()
        routes = spec.get_all_routes()

        assert "/" in routes
        assert "/about" in routes
        assert "/pricing" in routes
        assert "/terms" in routes
        assert "/privacy" in routes
        assert "/login" in routes
        assert "/signup" in routes


class TestDefaultSiteSpec:
    """Tests for create_default_sitespec factory."""

    def test_create_default(self) -> None:
        """Test default SiteSpec creation."""
        spec = create_default_sitespec()
        assert spec.brand.product_name == "My App"
        assert spec.layout.theme == ThemeKind.SAAS_DEFAULT

    def test_create_with_custom_name(self) -> None:
        """Test default SiteSpec with custom product name."""
        spec = create_default_sitespec(product_name="Solar CRM")
        assert spec.brand.product_name == "Solar CRM"

    def test_default_has_hero_section(self) -> None:
        """Test default has hero section on home page."""
        spec = create_default_sitespec()
        home = spec.get_page("/")
        assert home is not None
        assert len(home.sections) > 0
        assert home.sections[0].type == SectionKind.HERO

    def test_default_has_pricing_page(self) -> None:
        """Test default has pricing page with tiers."""
        spec = create_default_sitespec()
        pricing = spec.get_page("/pricing")
        assert pricing is not None
        assert pricing.type == PageKind.PRICING
        assert len(pricing.sections) == 1
        assert len(pricing.sections[0].tiers) == 3


class TestSiteSpecLoader:
    """Tests for SiteSpec loading from YAML."""

    def test_load_with_defaults(self) -> None:
        """Test loading from non-existent file returns defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            spec = load_sitespec(Path(tmpdir), use_defaults=True)
            assert spec.brand.product_name == "My App"

    def test_load_without_defaults_raises(self) -> None:
        """Test loading without defaults raises error when file missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(SiteSpecError):
                load_sitespec(Path(tmpdir), use_defaults=False)

    def test_sitespec_exists(self) -> None:
        """Test sitespec_exists function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            assert sitespec_exists(project_root) is False

            # Create sitespec.yaml
            sitespec_file = project_root / "sitespec.yaml"
            sitespec_file.write_text("version: 1\nbrand:\n  product_name: Test\n")
            assert sitespec_exists(project_root) is True

    def test_load_from_yaml(self) -> None:
        """Test loading from YAML file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            sitespec_file = project_root / "sitespec.yaml"
            sitespec_file.write_text(
                yaml.dump(
                    {
                        "version": 1,
                        "brand": {
                            "product_name": "YAML App",
                            "tagline": "From YAML",
                        },
                        "pages": [
                            {
                                "route": "/",
                                "type": "landing",
                                "title": "Home",
                                "sections": [
                                    {
                                        "type": "hero",
                                        "headline": "Welcome",
                                    }
                                ],
                            }
                        ],
                    }
                )
            )

            spec = load_sitespec(project_root)
            assert spec.brand.product_name == "YAML App"
            assert spec.brand.tagline == "From YAML"
            assert len(spec.pages) == 1
            assert spec.pages[0].sections[0].headline == "Welcome"


class TestTemplateVars:
    """Tests for template variable rendering."""

    def test_render_template_vars(self) -> None:
        """Test template variable substitution."""
        spec = create_default_sitespec(
            product_name="TestApp",
            company_legal_name="Test Company Ltd",
            support_email="help@test.com",
        )

        content = "Welcome to {{product_name}}. Contact {{support_email}}."
        rendered = render_template_vars(content, spec)
        assert "Welcome to TestApp" in rendered
        assert "Contact help@test.com" in rendered

    def test_render_year_var(self) -> None:
        """Test year variable substitution."""
        spec = create_default_sitespec()
        content = "© {{year}} Company"
        rendered = render_template_vars(content, spec)
        assert "© 2025" in rendered or "© 2024" in rendered  # Year depends on when test runs


class TestSiteSpecValidation:
    """Tests for SiteSpec validation."""

    def test_valid_spec(self) -> None:
        """Test validation of valid spec."""
        spec = create_default_sitespec()
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            result = validate_sitespec(spec, project_root, check_content_files=False)
            assert result.is_valid

    def test_duplicate_route_error(self) -> None:
        """Test validation catches duplicate routes."""
        spec = SiteSpec(
            brand=BrandSpec(product_name="Test"),
            pages=[
                PageSpec(route="/about", type=PageKind.LANDING, title="About 1"),
                PageSpec(route="/about", type=PageKind.LANDING, title="About 2"),
            ],
        )
        result = validate_sitespec(spec, check_content_files=False)
        assert not result.is_valid
        assert any("Duplicate route" in e for e in result.errors)

    def test_invalid_route_format(self) -> None:
        """Test validation catches invalid route format."""
        spec = SiteSpec(
            brand=BrandSpec(product_name="Test"),
            pages=[
                PageSpec(route="about", type=PageKind.LANDING, title="About"),  # Missing /
            ],
        )
        result = validate_sitespec(spec, check_content_files=False)
        assert not result.is_valid
        assert any("must start with /" in e for e in result.errors)

    def test_content_file_warning(self) -> None:
        """Test validation warns about missing content files."""
        spec = SiteSpec(
            brand=BrandSpec(product_name="Test"),
            pages=[
                PageSpec(
                    route="/about",
                    type=PageKind.MARKDOWN,
                    title="About",
                    source=ContentSourceSpec(
                        format=ContentFormat.MARKDOWN,
                        path="pages/about.md",
                    ),
                ),
            ],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            result = validate_sitespec(spec, project_root, check_content_files=True)
            # Should be valid but have warnings
            assert result.is_valid
            assert any("Content file not found" in w for w in result.warnings)


class TestScaffolding:
    """Tests for site scaffolding."""

    def test_scaffold_site(self) -> None:
        """Test scaffolding creates expected files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            result = scaffold_site(project_root, product_name="Scaffold Test")

            # Check sitespec was created
            assert result["sitespec"] is not None
            assert (project_root / "sitespec.yaml").exists()

            # Check content files were created
            assert len(result["content"]) == 3
            assert (project_root / "site/content/legal/terms.md").exists()
            assert (project_root / "site/content/legal/privacy.md").exists()
            assert (project_root / "site/content/pages/about.md").exists()

    def test_scaffold_idempotent(self) -> None:
        """Test scaffolding doesn't overwrite existing files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # First scaffold
            result1 = scaffold_site(project_root, product_name="First")
            assert result1["sitespec"] is not None

            # Second scaffold should skip existing
            result2 = scaffold_site(project_root, product_name="Second")
            assert result2["sitespec"] is None  # Skipped
            assert len(result2["content"]) == 0  # All skipped

            # Verify original content preserved
            spec = load_sitespec(project_root)
            assert spec.brand.product_name == "First"

    def test_scaffold_overwrite(self) -> None:
        """Test scaffolding with overwrite=True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # First scaffold
            scaffold_site(project_root, product_name="First")

            # Second scaffold with overwrite
            result = scaffold_site(project_root, product_name="Second", overwrite=True)
            assert result["sitespec"] is not None

            # Verify content updated
            spec = load_sitespec(project_root)
            assert spec.brand.product_name == "Second"
