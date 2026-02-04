"""Tests for marketing copy parser."""

from dazzle.core.copy_parser import (
    generate_copy_template,
    parse_copy_file,
)
from dazzle.core.sitespec_loader import (
    SiteSpec,
    merge_copy_into_sitespec,
)


class TestParseCopyFile:
    """Tests for parse_copy_file function."""

    def test_empty_content(self) -> None:
        """Empty content returns empty ParsedCopy."""
        result = parse_copy_file("")
        assert result.sections == []

    def test_single_section(self) -> None:
        """Single section is parsed correctly."""
        content = """# Hero

**Welcome to Our App**

This is the subheadline.

[Get Started](/signup)
"""
        result = parse_copy_file(content)
        assert len(result.sections) == 1
        assert result.sections[0].section_type == "hero"
        assert result.sections[0].metadata["headline"] == "Welcome to Our App"
        assert "subheadline" in result.sections[0].metadata["subheadline"]
        assert len(result.sections[0].metadata["ctas"]) == 1
        assert result.sections[0].metadata["ctas"][0]["text"] == "Get Started"
        assert result.sections[0].metadata["ctas"][0]["url"] == "/signup"

    def test_multiple_sections(self) -> None:
        """Multiple sections separated by --- are parsed."""
        content = """# Hero

**Headline**

---

# Features

## Feature One
Description one.

## Feature Two
Description two.

---

# CTA

## Ready?

[Sign Up](/signup)
"""
        result = parse_copy_file(content)
        assert len(result.sections) == 3
        assert result.sections[0].section_type == "hero"
        assert result.sections[1].section_type == "features"
        assert result.sections[2].section_type == "cta"

    def test_features_parsing(self) -> None:
        """Features section parses subsections correctly."""
        content = """# Features

## Fast Performance
Our app is blazingly fast.

## Easy to Use
Simple and intuitive interface.

## Secure
Enterprise-grade security built in.
"""
        result = parse_copy_file(content)
        assert len(result.sections) == 1
        features = result.sections[0]
        assert features.section_type == "features"
        assert len(features.subsections) == 3
        assert features.subsections[0]["title"] == "Fast Performance"
        assert "blazingly fast" in features.subsections[0]["description"]
        assert features.subsections[1]["title"] == "Easy to Use"
        assert features.subsections[2]["title"] == "Secure"

    def test_features_with_icons(self) -> None:
        """Features can include icon hints."""
        content = """# Features

## Speed
Lightning fast performance. [icon: bolt]

## Security
Bank-level encryption. [icon: shield]
"""
        result = parse_copy_file(content)
        features = result.sections[0]
        assert features.subsections[0]["icon"] == "bolt"
        assert features.subsections[1]["icon"] == "shield"
        # Icon hint should be removed from description
        assert "[icon:" not in features.subsections[0]["description"]

    def test_testimonials_parsing(self) -> None:
        """Testimonials section parses blockquotes."""
        content = """# Testimonials

> "This product is amazing!"
> — Jane Doe, CEO at StartupCo

> "Transformed our workflow completely."
> — John Smith, CTO at TechCorp
"""
        result = parse_copy_file(content)
        testimonials = result.sections[0]
        assert testimonials.section_type == "testimonials"
        assert len(testimonials.subsections) >= 1

    def test_pricing_parsing(self) -> None:
        """Pricing section parses tiers."""
        content = """# Pricing

## Free
$0/month

- Basic features
- Community support

## Pro
$29/month

- All features
- Priority support
- API access
"""
        result = parse_copy_file(content)
        pricing = result.sections[0]
        assert pricing.section_type == "pricing"
        assert len(pricing.subsections) == 2
        assert pricing.subsections[0]["name"] == "Free"
        assert pricing.subsections[0]["price"] == "0"
        assert pricing.subsections[1]["name"] == "Pro"
        assert pricing.subsections[1]["price"] == "29"
        assert len(pricing.subsections[1]["features"]) == 3

    def test_pricing_multi_currency(self) -> None:
        """Pricing section handles GBP, EUR, and other currencies."""
        content = """# Pricing

## Starter
£49/month

- Up to 25 clients

## Professional
€99/year

- Unlimited clients

## Enterprise
Contact us

- Custom pricing
"""
        result = parse_copy_file(content)
        pricing = result.sections[0]
        assert len(pricing.subsections) == 3

        # GBP
        assert pricing.subsections[0]["name"] == "Starter"
        assert pricing.subsections[0]["price"] == "49"
        assert pricing.subsections[0]["period"] == "month"

        # EUR with year
        assert pricing.subsections[1]["name"] == "Professional"
        assert pricing.subsections[1]["price"] == "99"
        assert pricing.subsections[1]["period"] == "year"

        # Contact us (non-numeric)
        assert pricing.subsections[2]["name"] == "Enterprise"
        assert pricing.subsections[2]["price"] == "Contact us"
        assert pricing.subsections[2]["period"] is None

    def test_faq_parsing(self) -> None:
        """FAQ section parses Q&A pairs."""
        content = """# FAQ

## What is this product?
It's a tool that helps you build apps faster.

## How do I get started?
Sign up for a free account and follow the tutorial.

## Is there a free trial?
Yes, we offer a 14-day free trial with full access.
"""
        result = parse_copy_file(content)
        faq = result.sections[0]
        assert faq.section_type == "faq"
        assert len(faq.subsections) == 3
        assert faq.subsections[0]["question"] == "What is this product"
        assert "build apps faster" in faq.subsections[0]["answer"]

    def test_cta_parsing(self) -> None:
        """CTA section parses headline and buttons."""
        content = """# CTA

## Ready to transform your business?

Join thousands of companies already using our platform.

[Start Free Trial](/signup) | [Contact Sales](/contact)
"""
        result = parse_copy_file(content)
        cta = result.sections[0]
        assert cta.section_type == "cta"
        assert cta.metadata["headline"] == "Ready to transform your business?"
        assert len(cta.metadata["ctas"]) == 2

    def test_section_type_normalization(self) -> None:
        """Various section titles map to standard types."""
        test_cases = [
            ("# Header", "hero"),
            ("# Main", "hero"),
            ("# Benefits", "features"),
            ("# Reviews", "testimonials"),
            ("# Plans", "pricing"),
            ("# FAQs", "faq"),
            ("# Questions", "faq"),
            ("# Get Started", "cta"),
            ("# Call to Action", "cta"),
            ("# About Us", "about"),
            ("# How It Works", "how-it-works"),
        ]
        for header, expected_type in test_cases:
            content = f"{header}\n\nSome content here."
            result = parse_copy_file(content)
            assert result.sections[0].section_type == expected_type, (
                f"Expected {header} to map to {expected_type}"
            )

    def test_multiple_ctas_in_hero(self) -> None:
        """Hero can have multiple CTA buttons."""
        content = """# Hero

**Welcome**

Description text here.

[Primary CTA](/signup) | [Secondary CTA](/demo) | [Tertiary](/learn)
"""
        result = parse_copy_file(content)
        hero = result.sections[0]
        assert len(hero.metadata["ctas"]) == 3

    def test_get_section(self) -> None:
        """ParsedCopy.get_section finds sections by type."""
        content = """# Hero

**Test**

---

# Features

## Feature
Desc
"""
        result = parse_copy_file(content)
        hero = result.get_section("hero")
        assert hero is not None
        assert hero.section_type == "hero"

        features = result.get_section("features")
        assert features is not None

        missing = result.get_section("nonexistent")
        assert missing is None

    def test_to_dict(self) -> None:
        """ParsedCopy converts to dictionary."""
        content = """# Hero

**Test Headline**
"""
        result = parse_copy_file(content)
        data = result.to_dict()
        assert "sections" in data
        assert len(data["sections"]) == 1
        assert data["sections"][0]["type"] == "hero"


class TestGenerateCopyTemplate:
    """Tests for copy template generation."""

    def test_template_includes_all_sections(self) -> None:
        """Generated template includes standard sections."""
        template = generate_copy_template("TestApp")
        assert "# Hero" in template
        assert "# Features" in template
        assert "# Testimonials" in template
        assert "# Pricing" in template
        assert "# FAQ" in template
        assert "# CTA" in template

    def test_template_uses_app_name(self) -> None:
        """Template substitutes app name."""
        template = generate_copy_template("MyAwesomeApp")
        assert "MyAwesomeApp" in template

    def test_template_is_parseable(self) -> None:
        """Generated template can be parsed back."""
        template = generate_copy_template("TestApp")
        result = parse_copy_file(template)
        assert len(result.sections) >= 6  # At least 6 standard sections
        assert result.get_section("hero") is not None
        assert result.get_section("features") is not None


class TestMergeCopyIntoSitespec:
    """Tests for merging copy.md into SiteSpec."""

    def test_empty_copy_returns_original(self) -> None:
        """Empty copy data returns original sitespec unchanged."""
        sitespec = SiteSpec()
        result = merge_copy_into_sitespec(sitespec, {})
        assert result == sitespec

    def test_none_copy_returns_original(self) -> None:
        """None copy data returns original sitespec unchanged."""
        sitespec = SiteSpec()
        result = merge_copy_into_sitespec(sitespec, None)  # type: ignore
        assert result == sitespec

    def test_hero_section_merged(self) -> None:
        """Hero section from copy.md is merged into landing page."""
        sitespec = SiteSpec()
        copy_data = {
            "sections": [
                {
                    "type": "hero",
                    "title": "Hero",
                    "metadata": {
                        "headline": "Welcome to FreshMeals",
                        "subheadline": "Chef-quality meals delivered",
                        "ctas": [{"text": "Get Started", "url": "/signup"}],
                    },
                    "subsections": [],
                }
            ]
        }

        result = merge_copy_into_sitespec(sitespec, copy_data)

        # Should have created a landing page
        landing = next((p for p in result.pages if p.route == "/"), None)
        assert landing is not None
        assert len(landing.sections) == 1
        assert landing.sections[0].headline == "Welcome to FreshMeals"

    def test_features_section_merged(self) -> None:
        """Features section from copy.md is converted correctly."""
        sitespec = SiteSpec()
        copy_data = {
            "sections": [
                {
                    "type": "features",
                    "title": "Features",
                    "metadata": {},
                    "subsections": [
                        {"title": "Fast", "description": "Lightning speed"},
                        {"title": "Secure", "description": "Bank-level security"},
                    ],
                }
            ]
        }

        result = merge_copy_into_sitespec(sitespec, copy_data)

        landing = next((p for p in result.pages if p.route == "/"), None)
        assert landing is not None
        assert len(landing.sections) == 1
        assert len(landing.sections[0].items) == 2
        assert landing.sections[0].items[0].title == "Fast"

    def test_copy_replaces_sitespec_sections(self) -> None:
        """Copy.md sections replace existing inline sitespec sections."""
        from dazzle.core.sitespec_loader import PageSpec, SectionKind, SectionSpec

        # Create sitespec with existing landing page sections
        sitespec = SiteSpec(
            pages=[
                PageSpec(
                    route="/",
                    title="Home",
                    sections=[
                        SectionSpec(
                            type=SectionKind.HERO,
                            headline="Old Headline",
                        )
                    ],
                )
            ]
        )

        # Copy.md with new content
        copy_data = {
            "sections": [
                {
                    "type": "hero",
                    "title": "Hero",
                    "metadata": {"headline": "New Headline from copy.md"},
                    "subsections": [],
                }
            ]
        }

        result = merge_copy_into_sitespec(sitespec, copy_data)

        landing = next((p for p in result.pages if p.route == "/"), None)
        assert landing is not None
        # copy.md content should take precedence
        assert landing.sections[0].headline == "New Headline from copy.md"

    def test_multiple_sections_in_order(self) -> None:
        """Multiple sections are added in standard order."""
        sitespec = SiteSpec()
        copy_data = {
            "sections": [
                {"type": "cta", "title": "CTA", "metadata": {}, "subsections": []},
                {"type": "hero", "title": "Hero", "metadata": {}, "subsections": []},
                {
                    "type": "features",
                    "title": "Features",
                    "metadata": {},
                    "subsections": [],
                },
            ]
        }

        result = merge_copy_into_sitespec(sitespec, copy_data)

        landing = next((p for p in result.pages if p.route == "/"), None)
        assert landing is not None
        # Should be ordered: hero, features, cta
        assert len(landing.sections) == 3
        section_types = [s.type.value for s in landing.sections]
        assert section_types == ["hero", "features", "cta"]

    def test_pricing_with_null_price_skipped(self) -> None:
        """Pricing tiers with null prices are skipped to avoid validation errors."""
        sitespec = SiteSpec()
        copy_data = {
            "sections": [
                {
                    "type": "pricing",
                    "title": "Pricing",
                    "metadata": {},
                    "subsections": [
                        # This tier has no price (parsing failed)
                        {"name": "Starter", "price": None, "period": None, "features": []},
                        # This tier is valid
                        {"name": "Pro", "price": "29", "period": "month", "features": []},
                    ],
                }
            ]
        }

        result = merge_copy_into_sitespec(sitespec, copy_data)

        landing = next((p for p in result.pages if p.route == "/"), None)
        assert landing is not None
        # Pricing section should exist with only the valid tier
        assert len(landing.sections) == 1
        assert landing.sections[0].type.value == "pricing"
        assert len(landing.sections[0].tiers) == 1
        assert landing.sections[0].tiers[0].name == "Pro"

    def test_pricing_all_null_skips_section(self) -> None:
        """Pricing section is skipped entirely if no tiers have valid prices."""
        sitespec = SiteSpec()
        copy_data = {
            "sections": [
                {"type": "hero", "title": "Hero", "metadata": {}, "subsections": []},
                {
                    "type": "pricing",
                    "title": "Pricing",
                    "metadata": {},
                    "subsections": [
                        # All tiers have null prices
                        {"name": "Starter", "price": None, "features": []},
                        {"name": "Pro", "price": None, "features": []},
                    ],
                },
            ]
        }

        result = merge_copy_into_sitespec(sitespec, copy_data)

        landing = next((p for p in result.pages if p.route == "/"), None)
        assert landing is not None
        # Should only have hero section, pricing skipped
        assert len(landing.sections) == 1
        assert landing.sections[0].type.value == "hero"

    def test_sitespec_sections_preserved_when_not_in_copy(self) -> None:
        """Sitespec sections not present in copy.md are preserved after merge."""
        from dazzle.core.sitespec_loader import (
            PageSpec,
            PricingTier,
            SectionKind,
            SectionSpec,
        )

        # Create sitespec with hero AND pricing
        sitespec = SiteSpec(
            pages=[
                PageSpec(
                    route="/",
                    title="Home",
                    sections=[
                        SectionSpec(type=SectionKind.HERO, headline="Old Hero"),
                        SectionSpec(
                            type=SectionKind.PRICING,
                            tiers=[
                                PricingTier(name="Pro", price="49", period="month", features=[])
                            ],
                        ),
                    ],
                )
            ]
        )

        # copy.md only has hero (no pricing)
        copy_data = {
            "sections": [
                {
                    "type": "hero",
                    "title": "Hero",
                    "metadata": {"headline": "New Hero from copy.md"},
                    "subsections": [],
                }
            ]
        }

        result = merge_copy_into_sitespec(sitespec, copy_data)

        landing = next((p for p in result.pages if p.route == "/"), None)
        assert landing is not None

        # Should have both hero and pricing
        section_types = [s.type.value for s in landing.sections]
        assert "hero" in section_types
        assert "pricing" in section_types

        # Hero should be updated from copy.md
        hero = next(s for s in landing.sections if s.type.value == "hero")
        assert hero.headline == "New Hero from copy.md"

        # Pricing should be preserved from sitespec
        pricing = next(s for s in landing.sections if s.type.value == "pricing")
        assert len(pricing.tiers) == 1
        assert pricing.tiers[0].name == "Pro"
        assert pricing.tiers[0].price == "49"
