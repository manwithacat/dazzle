"""Bootstrap synthetic reference images for the composition reference library.

Generates minimum-viable reference images using PIL (no external templates
needed).  Each image is a stylised section mock-up that demonstrates good
or bad composition patterns for LLM few-shot evaluation.

Usage::

    from dazzle.core.composition_references_bootstrap import bootstrap_references
    bootstrap_references(Path(".dazzle/composition/references"))
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .composition_references import ReferenceImage, save_manifest

logger = logging.getLogger(__name__)

# ── Color Palette ────────────────────────────────────────────────────

# Dazzle-style brand palette
BRAND_NAVY = (30, 58, 138)  # oklch(0.45 0.12 230) approx
BRAND_TEAL = (20, 184, 166)  # oklch(0.65 0.15 290) approx
WHITE = (255, 255, 255)
LIGHT_GRAY = (243, 244, 246)
DARK_TEXT = (17, 24, 39)
MID_GRAY = (156, 163, 175)
ALT_BG = (30, 41, 59)  # dark section bg
RED_ERROR = (220, 38, 38)
BLACK = (0, 0, 0)

# Section dimensions matching typical Dazzle captures
SECTION_WIDTH = 1280
HERO_HEIGHT = 500
FEATURE_HEIGHT = 450
PRICING_HEIGHT = 400
CTA_HEIGHT = 300
TESTIMONIAL_HEIGHT = 350
STEPS_HEIGHT = 400


# ── Drawing Helpers ──────────────────────────────────────────────────


def _draw_rect(
    draw: Any,
    x: int,
    y: int,
    w: int,
    h: int,
    fill: tuple[int, int, int],
) -> None:
    """Draw a filled rectangle."""
    draw.rectangle([x, y, x + w, y + h], fill=fill)


def _draw_text_block(
    draw: Any,
    x: int,
    y: int,
    w: int,
    h: int,
    fill: tuple[int, int, int],
    lines: int = 1,
) -> None:
    """Draw text-like horizontal bars."""
    line_h = max(4, h // max(1, lines * 2))
    gap = max(2, line_h // 2)
    for i in range(lines):
        cy = y + i * (line_h + gap)
        if cy + line_h > y + h:
            break
        line_w = w if i == 0 else int(w * (0.6 + 0.3 * (i % 2)))
        _draw_rect(draw, x, cy, line_w, line_h, fill)


def _draw_button(
    draw: Any,
    x: int,
    y: int,
    w: int,
    h: int,
    fill: tuple[int, int, int],
) -> None:
    """Draw a button-shaped rounded rect."""
    draw.rounded_rectangle([x, y, x + w, y + h], radius=6, fill=fill)


def _draw_icon_circle(
    draw: Any,
    cx: int,
    cy: int,
    r: int,
    fill: tuple[int, int, int],
) -> None:
    """Draw a circular icon placeholder."""
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill)


def _draw_card(
    draw: Any,
    x: int,
    y: int,
    w: int,
    h: int,
    *,
    has_icon: bool = True,
    icon_color: tuple[int, int, int] = BRAND_TEAL,
    highlighted: bool = False,
) -> None:
    """Draw a feature/pricing card."""
    bg = WHITE if not highlighted else (239, 246, 255)
    border = BRAND_NAVY if highlighted else MID_GRAY
    draw.rounded_rectangle([x, y, x + w, y + h], radius=8, fill=bg, outline=border)

    inner_x = x + 20
    inner_y = y + 20

    if has_icon:
        _draw_icon_circle(draw, inner_x + 16, inner_y + 16, 16, icon_color)
        inner_y += 48

    # Title bar
    _draw_text_block(draw, inner_x, inner_y, w - 40, 14, DARK_TEXT, lines=1)
    inner_y += 28

    # Description lines
    _draw_text_block(draw, inner_x, inner_y, w - 40, 40, MID_GRAY, lines=3)


# ── Section Generators ───────────────────────────────────────────────


def _gen_good_hero(output_dir: Path) -> ReferenceImage:
    """Good hero: large h1, subhead, 2 CTAs, hero image."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (SECTION_WIDTH, HERO_HEIGHT), WHITE)
    draw = ImageDraw.Draw(img)

    # Left side: text content
    # H1 (large, dark)
    _draw_text_block(draw, 60, 80, 500, 36, DARK_TEXT, lines=2)
    # Subhead
    _draw_text_block(draw, 60, 170, 450, 16, MID_GRAY, lines=2)
    # Primary CTA
    _draw_button(draw, 60, 240, 180, 48, BRAND_NAVY)
    # Secondary CTA
    _draw_button(draw, 260, 240, 160, 48, LIGHT_GRAY)

    # Right side: hero image placeholder
    _draw_rect(draw, 680, 60, 540, 380, LIGHT_GRAY)
    # Image content indicator
    _draw_icon_circle(draw, 950, 250, 60, MID_GRAY)

    path = output_dir / "good-synthetic-hero.png"
    img.save(path)
    return ReferenceImage(
        filename=path.name,
        label="good",
        section_type="hero",
        dimensions=["content_rendering", "visual_hierarchy"],
        description="Clear hierarchy: large headline, subhead, dual CTAs, hero image",
        source="synthetic-bootstrap",
    )


def _gen_good_hero_alt(output_dir: Path) -> ReferenceImage:
    """Good hero variant: centered text layout."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (SECTION_WIDTH, HERO_HEIGHT), LIGHT_GRAY)
    draw = ImageDraw.Draw(img)

    # Centered layout
    cx = SECTION_WIDTH // 2
    _draw_text_block(draw, cx - 300, 100, 600, 40, DARK_TEXT, lines=2)
    _draw_text_block(draw, cx - 250, 200, 500, 16, MID_GRAY, lines=2)
    _draw_button(draw, cx - 100, 270, 200, 48, BRAND_NAVY)

    path = output_dir / "good-synthetic-hero-centered.png"
    img.save(path)
    return ReferenceImage(
        filename=path.name,
        label="good",
        section_type="hero",
        dimensions=["content_rendering", "visual_hierarchy"],
        description="Centered hero with strong headline hierarchy and prominent CTA",
        source="synthetic-bootstrap",
    )


def _gen_bad_hero(output_dir: Path) -> ReferenceImage:
    """Bad hero: empty image area, no visible content."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (SECTION_WIDTH, HERO_HEIGHT), WHITE)
    draw = ImageDraw.Draw(img)

    # Tiny, barely visible text
    _draw_text_block(draw, 60, 200, 200, 10, MID_GRAY, lines=1)
    # Empty image area (white on white)
    draw.rectangle([680, 60, 1220, 440], outline=LIGHT_GRAY)

    path = output_dir / "bad-empty-hero.png"
    img.save(path)
    return ReferenceImage(
        filename=path.name,
        label="bad",
        section_type="hero",
        dimensions=["content_rendering"],
        description="Missing hero content: no headline, empty image placeholder",
        source="synthetic-bootstrap",
    )


def _gen_good_features(output_dir: Path) -> ReferenceImage:
    """Good features: 6 cards with icons, consistent sizing."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (SECTION_WIDTH, FEATURE_HEIGHT), WHITE)
    draw = ImageDraw.Draw(img)

    # Section heading
    _draw_text_block(draw, 400, 30, 480, 24, DARK_TEXT, lines=1)
    _draw_text_block(draw, 420, 65, 440, 12, MID_GRAY, lines=1)

    # 3x2 card grid
    card_w, card_h = 360, 160
    gap = 30
    start_x = (SECTION_WIDTH - 3 * card_w - 2 * gap) // 2
    for row in range(2):
        for col in range(3):
            x = start_x + col * (card_w + gap)
            y = 100 + row * (card_h + gap)
            _draw_card(draw, x, y, card_w, card_h, has_icon=True)

    path = output_dir / "good-synthetic-features.png"
    img.save(path)
    return ReferenceImage(
        filename=path.name,
        label="good",
        section_type="features",
        dimensions=["content_rendering", "icon_media", "layout_overflow"],
        description="6 feature cards with icons, consistent sizing, no overflow",
        source="synthetic-bootstrap",
    )


def _gen_good_features_alt(output_dir: Path) -> ReferenceImage:
    """Good features variant: 3-column layout."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (SECTION_WIDTH, 300), LIGHT_GRAY)
    draw = ImageDraw.Draw(img)

    _draw_text_block(draw, 440, 20, 400, 20, DARK_TEXT, lines=1)

    card_w, card_h = 380, 220
    gap = 20
    start_x = (SECTION_WIDTH - 3 * card_w - 2 * gap) // 2
    for col in range(3):
        x = start_x + col * (card_w + gap)
        _draw_card(draw, x, 60, card_w, card_h, has_icon=True, icon_color=BRAND_NAVY)

    path = output_dir / "good-synthetic-features-3col.png"
    img.save(path)
    return ReferenceImage(
        filename=path.name,
        label="good",
        section_type="features",
        dimensions=["icon_media", "layout_overflow"],
        description="3-column feature cards with navy icons and balanced layout",
        source="synthetic-bootstrap",
    )


def _gen_bad_features_no_icons(output_dir: Path) -> ReferenceImage:
    """Bad features: cards with blank icon placeholders."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (SECTION_WIDTH, FEATURE_HEIGHT), WHITE)
    draw = ImageDraw.Draw(img)

    _draw_text_block(draw, 400, 30, 480, 24, DARK_TEXT, lines=1)

    card_w, card_h = 360, 160
    gap = 30
    start_x = (SECTION_WIDTH - 3 * card_w - 2 * gap) // 2
    for row in range(2):
        for col in range(3):
            x = start_x + col * (card_w + gap)
            y = 80 + row * (card_h + gap)
            # Cards with empty icon squares instead of icons
            _draw_card(draw, x, y, card_w, card_h, has_icon=False)
            # Draw empty square placeholder where icon should be
            draw.rectangle(
                [x + 20, y + 20, x + 52, y + 52],
                outline=MID_GRAY,
            )

    path = output_dir / "bad-no-icons-features.png"
    img.save(path)
    return ReferenceImage(
        filename=path.name,
        label="bad",
        section_type="features",
        dimensions=["icon_media"],
        description="Feature cards with blank icon placeholders — icons failed to render",
        source="synthetic-bootstrap",
    )


def _gen_bad_features_inconsistent(output_dir: Path) -> ReferenceImage:
    """Bad features: inconsistent card heights and spacing."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (SECTION_WIDTH, FEATURE_HEIGHT), WHITE)
    draw = ImageDraw.Draw(img)

    _draw_text_block(draw, 400, 30, 480, 24, DARK_TEXT, lines=1)

    # Inconsistent cards
    cards = [
        (60, 90, 350, 180),
        (440, 90, 380, 140),
        (850, 90, 340, 200),
        (60, 300, 370, 120),
        (460, 290, 330, 130),
        # 6th card orphaned on new row
    ]
    for x, y, w, h in cards:
        _draw_card(draw, x, y, w, h, has_icon=True)

    path = output_dir / "bad-inconsistent-features.png"
    img.save(path)
    return ReferenceImage(
        filename=path.name,
        label="bad",
        section_type="features",
        dimensions=["layout_overflow"],
        description="Inconsistent card sizes and spacing with orphaned wrapping",
        source="synthetic-bootstrap",
    )


def _gen_good_pricing(output_dir: Path) -> ReferenceImage:
    """Good pricing: 3 tiers with highlighted middle."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (SECTION_WIDTH, PRICING_HEIGHT), WHITE)
    draw = ImageDraw.Draw(img)

    _draw_text_block(draw, 440, 20, 400, 24, DARK_TEXT, lines=1)

    card_w, card_h = 360, 340
    gap = 30
    start_x = (SECTION_WIDTH - 3 * card_w - 2 * gap) // 2
    for col in range(3):
        x = start_x + col * (card_w + gap)
        highlighted = col == 1
        _draw_card(
            draw,
            x,
            60,
            card_w,
            card_h,
            has_icon=False,
            highlighted=highlighted,
        )
        # Price text (large)
        _draw_text_block(draw, x + 20, 80, 100, 28, DARK_TEXT, lines=1)
        # Features list
        for i in range(4):
            _draw_text_block(draw, x + 20, 140 + i * 30, card_w - 40, 10, MID_GRAY, lines=1)
        # CTA button
        btn_color = BRAND_NAVY if highlighted else LIGHT_GRAY
        _draw_button(draw, x + 40, card_h + 60 - 60, card_w - 80, 44, btn_color)

    path = output_dir / "good-synthetic-pricing.png"
    img.save(path)
    return ReferenceImage(
        filename=path.name,
        label="good",
        section_type="pricing",
        dimensions=["content_rendering", "color_consistency", "layout_overflow"],
        description="3 pricing tiers with highlighted recommended tier and brand CTAs",
        source="synthetic-bootstrap",
    )


def _gen_good_pricing_alt(output_dir: Path) -> ReferenceImage:
    """Good pricing variant: 2 tiers side by side."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (SECTION_WIDTH, PRICING_HEIGHT), LIGHT_GRAY)
    draw = ImageDraw.Draw(img)

    _draw_text_block(draw, 440, 20, 400, 24, DARK_TEXT, lines=1)

    card_w, card_h = 500, 320
    gap = 40
    start_x = (SECTION_WIDTH - 2 * card_w - gap) // 2
    for col in range(2):
        x = start_x + col * (card_w + gap)
        _draw_card(draw, x, 60, card_w, card_h, has_icon=False, highlighted=col == 1)
        _draw_text_block(draw, x + 30, 90, 120, 28, DARK_TEXT, lines=1)
        for i in range(5):
            _draw_text_block(draw, x + 30, 150 + i * 28, card_w - 60, 10, MID_GRAY)
        _draw_button(draw, x + 60, 310, card_w - 120, 44, BRAND_NAVY)

    path = output_dir / "good-synthetic-pricing-2tier.png"
    img.save(path)
    return ReferenceImage(
        filename=path.name,
        label="good",
        section_type="pricing",
        dimensions=["layout_overflow", "color_consistency"],
        description="Clean 2-tier pricing with highlighted premium and brand buttons",
        source="synthetic-bootstrap",
    )


def _gen_bad_pricing_no_highlight(output_dir: Path) -> ReferenceImage:
    """Bad pricing: no visual distinction between tiers."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (SECTION_WIDTH, PRICING_HEIGHT), WHITE)
    draw = ImageDraw.Draw(img)

    _draw_text_block(draw, 440, 20, 400, 24, DARK_TEXT, lines=1)

    card_w, card_h = 360, 320
    gap = 30
    start_x = (SECTION_WIDTH - 3 * card_w - 2 * gap) // 2
    for col in range(3):
        x = start_x + col * (card_w + gap)
        # All cards identical — no highlighted tier
        _draw_card(draw, x, 60, card_w, card_h, has_icon=False)
        _draw_text_block(draw, x + 20, 80, 100, 28, DARK_TEXT, lines=1)
        # All buttons same gray — no brand color
        _draw_button(draw, x + 40, 320, card_w - 80, 44, MID_GRAY)

    path = output_dir / "bad-no-highlight-pricing.png"
    img.save(path)
    return ReferenceImage(
        filename=path.name,
        label="bad",
        section_type="pricing",
        dimensions=["color_consistency"],
        description="No tier visually highlighted — all cards identical, gray buttons",
        source="synthetic-bootstrap",
    )


def _gen_bad_pricing_wrap(output_dir: Path) -> ReferenceImage:
    """Bad pricing: 4th tier orphaned on second row."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (SECTION_WIDTH, PRICING_HEIGHT + 100), WHITE)
    draw = ImageDraw.Draw(img)

    _draw_text_block(draw, 440, 20, 400, 24, DARK_TEXT, lines=1)

    # 3 cards on row 1 + 1 orphan on row 2
    card_w, card_h = 380, 280
    gap = 20
    start_x = (SECTION_WIDTH - 3 * card_w - 2 * gap) // 2
    for col in range(3):
        x = start_x + col * (card_w + gap)
        _draw_card(draw, x, 60, card_w, card_h, has_icon=False)

    # Orphaned 4th card
    _draw_card(draw, start_x, 360, card_w, card_h, has_icon=False)

    path = output_dir / "bad-orphan-wrap-pricing.png"
    img.save(path)
    return ReferenceImage(
        filename=path.name,
        label="bad",
        section_type="pricing",
        dimensions=["layout_overflow"],
        description="4th pricing tier wraps alone to second row — orphan layout",
        source="synthetic-bootstrap",
    )


def _gen_good_cta(output_dir: Path) -> ReferenceImage:
    """Good CTA: prominent headline with brand button on alt background."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (SECTION_WIDTH, CTA_HEIGHT), ALT_BG)
    draw = ImageDraw.Draw(img)

    cx = SECTION_WIDTH // 2
    # Large headline (white on dark)
    _draw_text_block(draw, cx - 300, 60, 600, 36, WHITE, lines=2)
    # Subtext
    _draw_text_block(draw, cx - 250, 150, 500, 14, MID_GRAY, lines=1)
    # Brand CTA button
    _draw_button(draw, cx - 110, 200, 220, 52, BRAND_TEAL)

    path = output_dir / "good-synthetic-cta.png"
    img.save(path)
    return ReferenceImage(
        filename=path.name,
        label="good",
        section_type="cta",
        dimensions=["content_rendering", "visual_hierarchy", "color_consistency"],
        description="Prominent CTA headline on dark background with teal brand button",
        source="synthetic-bootstrap",
    )


def _gen_good_cta_alt(output_dir: Path) -> ReferenceImage:
    """Good CTA variant: light bg with navy button."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (SECTION_WIDTH, CTA_HEIGHT), LIGHT_GRAY)
    draw = ImageDraw.Draw(img)

    cx = SECTION_WIDTH // 2
    _draw_text_block(draw, cx - 280, 70, 560, 32, DARK_TEXT, lines=2)
    _draw_text_block(draw, cx - 220, 150, 440, 12, MID_GRAY, lines=1)
    _draw_button(draw, cx - 100, 200, 200, 48, BRAND_NAVY)

    path = output_dir / "good-synthetic-cta-light.png"
    img.save(path)
    return ReferenceImage(
        filename=path.name,
        label="good",
        section_type="cta",
        dimensions=["visual_hierarchy", "color_consistency"],
        description="CTA with large headline and prominent navy brand button",
        source="synthetic-bootstrap",
    )


def _gen_bad_cta(output_dir: Path) -> ReferenceImage:
    """Bad CTA: small headline, black button instead of brand color."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (SECTION_WIDTH, CTA_HEIGHT), WHITE)
    draw = ImageDraw.Draw(img)

    cx = SECTION_WIDTH // 2
    # Small, low-prominence headline
    _draw_text_block(draw, cx - 150, 120, 300, 14, MID_GRAY, lines=1)
    # Black button instead of brand
    _draw_button(draw, cx - 80, 170, 160, 40, BLACK)

    path = output_dir / "bad-low-prominence-cta.png"
    img.save(path)
    return ReferenceImage(
        filename=path.name,
        label="bad",
        section_type="cta",
        dimensions=["visual_hierarchy", "color_consistency"],
        description="CTA headline too small, button is black instead of brand color",
        source="synthetic-bootstrap",
    )


def _gen_good_testimonials(output_dir: Path) -> ReferenceImage:
    """Good testimonials: quote cards with attribution."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (SECTION_WIDTH, TESTIMONIAL_HEIGHT), LIGHT_GRAY)
    draw = ImageDraw.Draw(img)

    _draw_text_block(draw, 440, 20, 400, 20, DARK_TEXT, lines=1)

    card_w, card_h = 380, 260
    gap = 20
    start_x = (SECTION_WIDTH - 3 * card_w - 2 * gap) // 2
    for col in range(3):
        x = start_x + col * (card_w + gap)
        draw.rounded_rectangle([x, 60, x + card_w, 60 + card_h], radius=8, fill=WHITE)
        # Quote text
        _draw_text_block(draw, x + 20, 80, card_w - 40, 80, MID_GRAY, lines=4)
        # Avatar circle
        _draw_icon_circle(draw, x + 36, 240, 16, BRAND_NAVY)
        # Name
        _draw_text_block(draw, x + 60, 230, 120, 10, DARK_TEXT, lines=1)
        _draw_text_block(draw, x + 60, 248, 100, 8, MID_GRAY, lines=1)

    path = output_dir / "good-synthetic-testimonials.png"
    img.save(path)
    return ReferenceImage(
        filename=path.name,
        label="good",
        section_type="testimonials",
        dimensions=["content_rendering", "layout_overflow"],
        description="3 testimonial cards with quotes, avatars, and attribution",
        source="synthetic-bootstrap",
    )


def _gen_bad_testimonials(output_dir: Path) -> ReferenceImage:
    """Bad testimonials: empty quote cards."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (SECTION_WIDTH, TESTIMONIAL_HEIGHT), LIGHT_GRAY)
    draw = ImageDraw.Draw(img)

    _draw_text_block(draw, 440, 20, 400, 20, DARK_TEXT, lines=1)

    card_w, card_h = 380, 260
    gap = 20
    start_x = (SECTION_WIDTH - 3 * card_w - 2 * gap) // 2
    for col in range(3):
        x = start_x + col * (card_w + gap)
        # Empty white cards
        draw.rounded_rectangle([x, 60, x + card_w, 60 + card_h], radius=8, fill=WHITE)

    path = output_dir / "bad-empty-testimonials.png"
    img.save(path)
    return ReferenceImage(
        filename=path.name,
        label="bad",
        section_type="testimonials",
        dimensions=["content_rendering"],
        description="Empty testimonial cards — no quotes, avatars, or names rendered",
        source="synthetic-bootstrap",
    )


def _gen_good_steps(output_dir: Path) -> ReferenceImage:
    """Good steps: numbered steps with descriptions."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (SECTION_WIDTH, STEPS_HEIGHT), WHITE)
    draw = ImageDraw.Draw(img)

    _draw_text_block(draw, 440, 20, 400, 24, DARK_TEXT, lines=1)

    step_w = 340
    gap = 40
    start_x = (SECTION_WIDTH - 3 * step_w - 2 * gap) // 2
    for col in range(3):
        x = start_x + col * (step_w + gap)
        # Step number circle
        _draw_icon_circle(draw, x + step_w // 2, 100, 28, BRAND_NAVY)
        # Step title
        _draw_text_block(draw, x + 40, 150, step_w - 80, 16, DARK_TEXT, lines=1)
        # Step description
        _draw_text_block(draw, x + 20, 185, step_w - 40, 60, MID_GRAY, lines=3)

    # Connecting line between steps
    y_line = 100
    for col in range(2):
        x1 = start_x + col * (step_w + gap) + step_w // 2 + 30
        x2 = start_x + (col + 1) * (step_w + gap) + step_w // 2 - 30
        draw.line([(x1, y_line), (x2, y_line)], fill=MID_GRAY, width=2)

    path = output_dir / "good-synthetic-steps.png"
    img.save(path)
    return ReferenceImage(
        filename=path.name,
        label="good",
        section_type="steps",
        dimensions=["content_rendering", "visual_hierarchy"],
        description="3 numbered steps with titles, descriptions, and connecting lines",
        source="synthetic-bootstrap",
    )


def _gen_bad_steps(output_dir: Path) -> ReferenceImage:
    """Bad steps: duplicate step numbers, no descriptions."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (SECTION_WIDTH, STEPS_HEIGHT), WHITE)
    draw = ImageDraw.Draw(img)

    _draw_text_block(draw, 440, 20, 400, 24, DARK_TEXT, lines=1)

    step_w = 340
    gap = 40
    start_x = (SECTION_WIDTH - 3 * step_w - 2 * gap) // 2
    for col in range(3):
        x = start_x + col * (step_w + gap)
        # All circles same color (no step numbers differentiation)
        _draw_icon_circle(draw, x + step_w // 2, 100, 28, MID_GRAY)
        # No title or description — just empty space

    path = output_dir / "bad-empty-steps.png"
    img.save(path)
    return ReferenceImage(
        filename=path.name,
        label="bad",
        section_type="steps",
        dimensions=["content_rendering"],
        description="Steps with blank content — no titles or descriptions rendered",
        source="synthetic-bootstrap",
    )


# ── Main Bootstrap Function ──────────────────────────────────────────


# All generators in the order they should be created
_GENERATORS = [
    # hero: 2 good + 1 bad = 3
    _gen_good_hero,
    _gen_good_hero_alt,
    _gen_bad_hero,
    # features: 2 good + 2 bad = 4
    _gen_good_features,
    _gen_good_features_alt,
    _gen_bad_features_no_icons,
    _gen_bad_features_inconsistent,
    # pricing: 2 good + 2 bad = 4
    _gen_good_pricing,
    _gen_good_pricing_alt,
    _gen_bad_pricing_no_highlight,
    _gen_bad_pricing_wrap,
    # cta: 2 good + 1 bad = 3
    _gen_good_cta,
    _gen_good_cta_alt,
    _gen_bad_cta,
    # testimonials: 1 good + 1 bad = 2
    _gen_good_testimonials,
    _gen_bad_testimonials,
    # steps: 1 good + 1 bad = 2
    _gen_good_steps,
    _gen_bad_steps,
]


def bootstrap_references(ref_dir: Path) -> dict[str, list[ReferenceImage]]:
    """Generate the minimum viable reference library.

    Creates 18 synthetic section screenshots (10 good, 8 bad) across
    6 section types, with manifest.json files for each.

    Args:
        ref_dir: Root directory for references
            (e.g. ``.dazzle/composition/references``).

    Returns:
        Dict mapping section_type -> list of ReferenceImage.
    """
    ref_dir.mkdir(parents=True, exist_ok=True)

    # Group by section type
    by_section: dict[str, list[ReferenceImage]] = {}

    for gen_fn in _GENERATORS:
        # Determine section type from function name
        # All generators produce a single ref with a section_type
        # We need the section dir to exist before generating
        # Parse section type from generator name pattern: _gen_{good|bad}_{section}...
        parts = gen_fn.__name__.split("_")
        # Find section type: skip _gen, good/bad, and join the rest
        sec_idx = 3  # _gen_{label}_{section}
        sec_type = parts[sec_idx] if len(parts) > sec_idx else "unknown"

        section_dir = ref_dir / sec_type
        section_dir.mkdir(parents=True, exist_ok=True)

        ref = gen_fn(section_dir)
        by_section.setdefault(ref.section_type, []).append(ref)

    # Write manifests
    for sec_type, refs in by_section.items():
        section_dir = ref_dir / sec_type
        save_manifest(section_dir, refs)

    total = sum(len(refs) for refs in by_section.values())
    good = sum(1 for refs in by_section.values() for r in refs if r.label == "good")
    bad = total - good

    logger.info(
        "Bootstrapped %d reference images (%d good, %d bad) across %d section types",
        total,
        good,
        bad,
        len(by_section),
    )

    return by_section
