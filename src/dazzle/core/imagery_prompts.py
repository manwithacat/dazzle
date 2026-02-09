"""
Deterministic diffusion prompt assembly from ThemeSpec imagery vocabulary.

Generates section-appropriate image prompts for hero images, feature
illustrations, and other site sections. Prompts combine style, mood,
and color vocabulary from the ThemeSpec.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .ir.sitespec import SiteSpec
    from .ir.themespec import ThemeSpecYAML


# Default section contexts when sitespec is not available
_DEFAULT_SECTION_CONTEXTS: dict[str, str] = {
    "hero": "hero banner, wide landscape, above the fold",
    "features": "feature illustration, clean icon-style imagery",
    "testimonials": "professional headshot background, warm tone",
    "about": "team or office environment, welcoming atmosphere",
    "pricing": "abstract geometric pattern, business context",
    "cta": "motivational imagery, action-oriented composition",
    "blog": "editorial photography, readable background",
}


@dataclass
class ImageryPrompt:
    """A generated imagery prompt for a specific section."""

    section: str
    prompt: str
    negative_prompt: str
    aspect_ratio: str
    resolution: str


def _build_prompt(
    section_context: str,
    style_keywords: list[str],
    mood_keywords: list[str],
    color_reference: str,
) -> str:
    """Assemble a diffusion prompt from components."""
    parts: list[str] = []

    if style_keywords:
        parts.append(", ".join(style_keywords))

    parts.append(section_context)

    if mood_keywords:
        parts.append(", ".join(mood_keywords))

    if color_reference:
        parts.append(f"color palette: {color_reference}")

    return ", ".join(parts)


def _build_negative_prompt(exclusions: list[str]) -> str:
    """Assemble a negative prompt from exclusions."""
    if not exclusions:
        return "text, watermark, logo, blurry, low quality"
    return ", ".join(exclusions)


def generate_imagery_prompts(
    themespec: ThemeSpecYAML,
    sitespec: SiteSpec | None = None,
) -> list[ImageryPrompt]:
    """Generate imagery prompts for all relevant sections.

    Args:
        themespec: ThemeSpecYAML with imagery vocabulary.
        sitespec: Optional SiteSpec to derive section contexts from pages.

    Returns:
        List of ImageryPrompt objects.
    """
    vocab = themespec.imagery.vocabulary
    aspect_ratio = themespec.imagery.default_aspect_ratio
    resolution = themespec.imagery.default_resolution

    # Determine sections to generate prompts for
    section_contexts: dict[str, str] = dict(_DEFAULT_SECTION_CONTEXTS)

    # Override with sitespec page/section info if available
    if sitespec is not None:
        for page in sitespec.pages:
            for section in page.sections:
                section_type = (
                    section.type.value if hasattr(section.type, "value") else str(section.type)
                )
                # Build context from section headline if available
                context_parts = [section_type]
                if section.headline:
                    context_parts.append(f"themed around: {section.headline}")
                section_contexts[section_type] = ", ".join(context_parts)

    negative_prompt = _build_negative_prompt(vocab.exclusions)

    prompts: list[ImageryPrompt] = []
    for section_name, section_context in section_contexts.items():
        prompt = _build_prompt(
            section_context,
            vocab.style_keywords,
            vocab.mood_keywords,
            vocab.color_reference,
        )
        prompts.append(
            ImageryPrompt(
                section=section_name,
                prompt=prompt,
                negative_prompt=negative_prompt,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
            )
        )

    return prompts
