"""
Marketing copy parser for single-file content management.

Parses a structured markdown file (site/content/copy.md) into content blocks
that can be used by the site renderer. Designed for founder-friendly editing
of LLM-generated marketing copy.

Format:
    # Section Name

    Content for the section...

    ## Subsection
    Content for subsection...

    ---

    # Next Section
    ...

Supported section types:
    - hero: Main landing section with headline, subheadline, CTAs
    - features: Feature grid with title, description per feature
    - testimonials: Customer quotes (blockquotes)
    - pricing: Pricing tiers
    - faq: Question/answer pairs
    - cta: Call-to-action blocks
    - custom: Any other named section
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ContentBlock:
    """A parsed content block from the copy file."""

    section_type: str  # hero, features, testimonials, etc.
    title: str | None = None
    content: str | None = None
    subsections: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedCopy:
    """Complete parsed marketing copy."""

    sections: list[ContentBlock] = field(default_factory=list)
    raw_markdown: str = ""

    def get_section(self, section_type: str) -> ContentBlock | None:
        """Get a section by type."""
        for section in self.sections:
            if section.section_type.lower() == section_type.lower():
                return section
        return None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "sections": [
                {
                    "type": s.section_type,
                    "title": s.title,
                    "content": s.content,
                    "subsections": s.subsections,
                    "metadata": s.metadata,
                }
                for s in self.sections
            ]
        }


def parse_copy_file(content: str) -> ParsedCopy:
    """
    Parse a marketing copy markdown file into structured content.

    Args:
        content: Raw markdown content

    Returns:
        ParsedCopy with all sections parsed
    """
    result = ParsedCopy(raw_markdown=content)

    # Split by horizontal rules to get major sections
    # Use regex to handle various hr formats (---, ***, ___)
    raw_sections = re.split(r"\n---+\n|\n\*\*\*+\n|\n___+\n", content)

    for raw_section in raw_sections:
        raw_section = raw_section.strip()
        if not raw_section:
            continue

        block = _parse_section(raw_section)
        if block:
            result.sections.append(block)

    return result


def _parse_section(raw: str) -> ContentBlock | None:
    """Parse a single section from markdown."""
    lines = raw.split("\n")

    # Find the section header (# Section Name)
    section_type = "custom"
    title = None
    content_start = 0

    for i, line in enumerate(lines):
        if line.startswith("# ") and not line.startswith("## "):
            title = line[2:].strip()
            section_type = _normalize_section_type(title)
            content_start = i + 1
            break

    if title is None:
        # No header found, treat entire content as custom section
        return ContentBlock(
            section_type="custom",
            content=raw.strip(),
        )

    # Get remaining content after the header
    remaining = "\n".join(lines[content_start:]).strip()

    # Parse based on section type
    if section_type == "hero":
        return _parse_hero_section(title, remaining)
    elif section_type == "features":
        return _parse_features_section(title, remaining)
    elif section_type == "testimonials":
        return _parse_testimonials_section(title, remaining)
    elif section_type == "pricing":
        return _parse_pricing_section(title, remaining)
    elif section_type == "faq":
        return _parse_faq_section(title, remaining)
    elif section_type == "cta":
        return _parse_cta_section(title, remaining)
    else:
        return _parse_generic_section(title, section_type, remaining)


def _normalize_section_type(title: str) -> str:
    """Convert section title to normalized type."""
    lower = title.lower().strip()

    # Map common variations to standard types
    mappings = {
        "hero": "hero",
        "header": "hero",
        "main": "hero",
        "features": "features",
        "feature": "features",
        "benefits": "features",
        "testimonials": "testimonials",
        "testimonial": "testimonials",
        "reviews": "testimonials",
        "quotes": "testimonials",
        "pricing": "pricing",
        "plans": "pricing",
        "faq": "faq",
        "faqs": "faq",
        "questions": "faq",
        "cta": "cta",
        "call to action": "cta",
        "get started": "cta",
        "about": "about",
        "about us": "about",
        "how it works": "how-it-works",
        "process": "how-it-works",
    }

    return mappings.get(lower, lower.replace(" ", "-"))


def _parse_hero_section(title: str, content: str) -> ContentBlock:
    """Parse hero section with headline, subheadline, CTAs."""
    block = ContentBlock(section_type="hero", title=title)

    lines = content.split("\n")
    headline = None
    subheadline_lines: list[str] = []
    ctas: list[dict[str, str]] = []

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Bold text at start is headline: **Headline here**
        if line.startswith("**") and line.endswith("**") and headline is None:
            headline = line[2:-2]
            i += 1
            continue

        # Links are CTAs: [Text](/path) or [Text](url)
        link_matches = re.findall(r"\[([^\]]+)\]\(([^)]+)\)", line)
        if link_matches:
            for text, url in link_matches:
                ctas.append({"text": text, "url": url})
            i += 1
            continue

        # Regular text is subheadline
        if line and not line.startswith("#"):
            subheadline_lines.append(line)

        i += 1

    block.metadata["headline"] = headline
    block.metadata["subheadline"] = " ".join(subheadline_lines).strip()
    block.metadata["ctas"] = ctas
    block.content = content

    return block


def _parse_features_section(title: str, content: str) -> ContentBlock:
    """Parse features section with individual feature blocks."""
    block = ContentBlock(section_type="features", title=title)

    # Split by ## headers to get individual features
    parts = re.split(r"\n(?=## )", content)

    for part in parts:
        part = part.strip()
        if not part:
            continue

        # Check if this part starts with a feature header
        if part.startswith("## "):
            lines = part.split("\n")
            feature_title = lines[0][3:].strip()
            feature_desc = "\n".join(lines[1:]).strip()

            # Check for icon hint: [icon: rocket] or similar
            icon = None
            icon_match = re.search(r"\[icon:\s*([^\]]+)\]", feature_desc)
            if icon_match:
                icon = icon_match.group(1).strip()
                feature_desc = re.sub(r"\[icon:\s*[^\]]+\]", "", feature_desc).strip()

            block.subsections.append(
                {
                    "title": feature_title,
                    "description": feature_desc,
                    "icon": icon,
                }
            )
        else:
            # Intro text before features
            block.content = part

    return block


def _parse_testimonials_section(title: str, content: str) -> ContentBlock:
    """Parse testimonials section with blockquotes."""
    block = ContentBlock(section_type="testimonials", title=title)

    # Find all blockquotes
    # Format: > "Quote text"
    #         > — Attribution
    quote_pattern = re.compile(
        r'>\s*["\u201c]?(.+?)["\u201d]?\s*\n>\s*[-\u2014]\s*(.+?)(?=\n\n|\n>|\Z)',
        re.DOTALL,
    )

    for match in quote_pattern.finditer(content):
        quote = match.group(1).strip()
        attribution = match.group(2).strip()

        # Parse attribution: "Name, Title at Company"
        attr_parts = attribution.split(",", 1)
        name = attr_parts[0].strip()
        role = attr_parts[1].strip() if len(attr_parts) > 1 else None

        block.subsections.append(
            {
                "quote": quote,
                "name": name,
                "role": role,
                "attribution": attribution,
            }
        )

    # Also try simpler blockquote format
    if not block.subsections:
        simple_quotes = re.findall(r">\s*(.+?)(?=\n\n|\n>|\Z)", content, re.DOTALL)
        for quote in simple_quotes:
            quote = quote.strip()
            if quote:
                block.subsections.append({"quote": quote})

    block.content = content
    return block


def _parse_pricing_section(title: str, content: str) -> ContentBlock:
    """Parse pricing section with tiers.

    Note: Pricing is inherently structured data (price, period, features).
    For complex pricing, prefer defining tiers in sitespec.yaml directly.
    copy.md pricing parsing is best-effort for simple formats like:
        $29/month, £49/month, €99/year, Free, Contact us
    """
    block = ContentBlock(section_type="pricing", title=title)

    # Split by ## headers to get pricing tiers
    parts = re.split(r"\n(?=## )", content)

    for part in parts:
        part = part.strip()
        if not part or not part.startswith("## "):
            if part:
                block.content = part
            continue

        lines = part.split("\n")
        tier_name = lines[0][3:].strip()

        # Look for price pattern: $X/month, £X/month, €X/year, Free, Contact us, etc.
        # Supports: $29, £49/month, €99.99/year, Free, Contact us, Custom
        price = None
        price_period = None
        features: list[str] = []

        for line in lines[1:]:
            line = line.strip()

            # Skip empty lines
            if not line:
                continue

            # Feature list items (process before price to avoid false matches)
            if line.startswith("- ") or line.startswith("* "):
                features.append(line[2:].strip())
                continue

            # Price patterns - handle multiple currencies and formats
            # Pattern: optional currency symbol, number or word, optional /period
            if price is None:
                # Try structured format: £49/month, $29.99/year, €99/mo
                currency_match = re.match(
                    r"^[£$€]?\s*(\d+(?:[.,]\d{2})?)\s*/\s*(\w+)",
                    line.replace(",", ""),
                )
                if currency_match:
                    price = currency_match.group(1)
                    price_period = currency_match.group(2)
                    # Normalize period
                    if price_period in ("mo", "mth"):
                        price_period = "month"
                    elif price_period in ("yr", "pa", "annual"):
                        price_period = "year"
                    continue

                # Try simple number: $29, £49, €99
                simple_price = re.match(r"^[£$€]?\s*(\d+(?:[.,]\d{2})?)\s*$", line)
                if simple_price:
                    price = simple_price.group(1)
                    price_period = "month"  # Default to month
                    continue

                # Try word-based: Free, Contact us, Custom, Enterprise
                word_price = re.match(
                    r"^(free|contact\s+us|custom|enterprise|call\s+us)$",
                    line.lower(),
                )
                if word_price:
                    price = line  # Keep original case
                    price_period = None  # No period for non-numeric
                    continue

        block.subsections.append(
            {
                "name": tier_name,
                "price": price,
                "period": price_period,
                "features": features,
            }
        )

    return block


def _parse_faq_section(title: str, content: str) -> ContentBlock:
    """Parse FAQ section with Q&A pairs."""
    block = ContentBlock(section_type="faq", title=title)

    # Split by ## headers to get Q&A pairs
    parts = re.split(r"\n(?=## )", content)

    for part in parts:
        part = part.strip()
        if not part or not part.startswith("## "):
            if part:
                block.content = part
            continue

        lines = part.split("\n")
        question = lines[0][3:].strip()

        # Remove trailing ? if present (we'll add it back in display)
        question = question.rstrip("?")

        answer = "\n".join(lines[1:]).strip()

        block.subsections.append(
            {
                "question": question,
                "answer": answer,
            }
        )

    return block


def _parse_cta_section(title: str, content: str) -> ContentBlock:
    """Parse CTA section with headline and action buttons."""
    block = ContentBlock(section_type="cta", title=title)

    lines = content.split("\n")
    headline = None
    description_lines: list[str] = []
    ctas: list[dict[str, str]] = []

    for line in lines:
        line_stripped = line.strip()

        # ## is the CTA headline
        if line_stripped.startswith("## "):
            headline = line_stripped[3:].strip()
            continue

        # Links are CTA buttons
        link_matches = re.findall(r"\[([^\]]+)\]\(([^)]+)\)", line_stripped)
        if link_matches:
            for text, url in link_matches:
                ctas.append({"text": text, "url": url})
            continue

        # Regular text is description
        if line_stripped:
            description_lines.append(line_stripped)

    block.metadata["headline"] = headline
    block.metadata["description"] = " ".join(description_lines).strip()
    block.metadata["ctas"] = ctas
    block.content = content

    return block


def _parse_generic_section(title: str, section_type: str, content: str) -> ContentBlock:
    """Parse a generic section with subsections."""
    block = ContentBlock(section_type=section_type, title=title, content=content)

    # Split by ## headers to get subsections
    parts = re.split(r"\n(?=## )", content)

    for part in parts:
        part = part.strip()
        if not part:
            continue

        if part.startswith("## "):
            lines = part.split("\n")
            sub_title = lines[0][3:].strip()
            sub_content = "\n".join(lines[1:]).strip()
            block.subsections.append(
                {
                    "title": sub_title,
                    "content": sub_content,
                }
            )

    return block


def load_copy_file(project_root: Path) -> ParsedCopy | None:
    """
    Load and parse the copy file from a project.

    Args:
        project_root: Project root directory

    Returns:
        ParsedCopy if file exists, None otherwise
    """
    copy_path = project_root / "site" / "content" / "copy.md"

    if not copy_path.exists():
        return None

    content = copy_path.read_text(encoding="utf-8")
    return parse_copy_file(content)


def generate_copy_template(app_name: str = "Your App") -> str:
    """
    Generate a template copy.md file for a new project.

    Args:
        app_name: Name of the application

    Returns:
        Template markdown content
    """
    return f"""# Hero

**{app_name}: Your Tagline Here**

A compelling one-sentence description of what your product does
and why it matters to your customers.

[Get Started Free](/signup) | [See How It Works](/demo)

---

# Features

## Feature One
Describe your first key feature. Focus on the benefit to the user,
not just what it does technically.

## Feature Two
Another important capability. What problem does this solve?
How does it make your users' lives better?

## Feature Three
A third differentiator. Why should someone choose your solution
over alternatives?

---

# How It Works

## Step 1: Sign Up
Brief description of the first step in getting started.

## Step 2: Configure
What does the user do next?

## Step 3: Launch
The outcome - what do they get?

---

# Testimonials

> "This product transformed how we work. We shipped in half the time."
> — Sarah Chen, Founder at TechStartup

> "Finally, a solution that just works. Highly recommended."
> — Marcus Johnson, CTO at GrowthCo

---

# Pricing

## Free
$0/month

- Up to 3 projects
- Community support
- Basic features

## Pro
$29/month

- Unlimited projects
- Priority support
- Advanced features
- API access

## Enterprise
Contact us

- Custom deployment
- Dedicated support
- SLA guarantee
- SSO & audit logs

---

# FAQ

## What is {app_name}?
A clear, concise answer to the most basic question about your product.

## How do I get started?
Walk through the initial steps a new user should take.

## What support do you offer?
Describe your support channels and response times.

## Can I cancel anytime?
Be transparent about your cancellation policy.

---

# CTA

## Ready to get started?

Join thousands of teams already using {app_name} to ship faster.

[Start Your Free Trial](/signup)
"""
