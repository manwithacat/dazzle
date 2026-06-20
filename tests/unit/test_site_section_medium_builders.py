"""Issue #1037 (v0.67.27): regression tests for the third batch of
typed sitespec section builders — `stats`, `steps`, `comparison`,
`split_content`, `card_grid`, `team`, `testimonials`.

7 medium-shape sections migrated. Combined with the v0.67.25 hero
+ v0.67.26 simple six, **14 of 19 sections (74%) are now typed.**
The remaining 5 — features, pricing, faq, qa_personas, and any
sitespec author's custom types — fall through to the Jinja partial.
"""

from __future__ import annotations

from dazzle.http.runtime.renderers.site_section_builder import (
    TYPED_SECTION_TYPES,
    _build_card_grid_section,
    _build_comparison_section,
    _build_split_content_section,
    _build_stats_section,
    _build_steps_section,
    _build_team_section,
    _build_testimonials_section,
    render_typed_section,
)


def test_seven_new_section_types_in_typed_set() -> None:
    for t in (
        "stats",
        "steps",
        "comparison",
        "split_content",
        "card_grid",
        "team",
        "testimonials",
    ):
        assert t in TYPED_SECTION_TYPES


def test_render_typed_section_dispatches_each_new_type() -> None:
    for t in (
        "stats",
        "steps",
        "comparison",
        "split_content",
        "card_grid",
        "team",
        "testimonials",
    ):
        out = render_typed_section({"type": t})
        assert "<section" in out


# ───────────────── stats ────────────────────


def test_stats_emits_section_class_and_stats_wrapper() -> None:
    out = _build_stats_section({"type": "stats"})
    assert 'class="dz-section dz-section-stats"' in out
    # #1113 — Dazzle-native grid replaces DaisyUI `stats stats-vertical
    # lg:stats-horizontal shadow` (CDN-only styling).
    assert 'class="dz-stats-grid"' in out


def test_stats_renders_one_stat_per_item() -> None:
    out = _build_stats_section(
        {
            "type": "stats",
            "items": [
                {"value": "99.9%", "label": "Uptime"},
                {"value": "<1ms", "label": "p50 latency"},
            ],
        }
    )
    assert out.count('class="dz-stat"') == 2
    assert out.count('class="dz-stat-value"') == 2
    assert out.count('class="dz-stat-title"') == 2
    assert ">99.9%<" in out
    assert ">Uptime<" in out
    # < in <1ms must be escaped.
    assert "&lt;1ms" in out
    # p50 latency rendered.
    assert ">p50 latency<" in out


def test_stats_handles_empty_items() -> None:
    out = _build_stats_section({"type": "stats"})
    assert 'class="dz-stats-grid"' in out
    assert 'class="dz-stat"' not in out


# ───────────────── steps ────────────────────


def test_steps_emits_section_class() -> None:
    out = _build_steps_section({"type": "steps"})
    assert 'class="dz-section dz-section-steps"' in out
    assert "dz-section-steps-list" in out


def test_steps_numbers_each_item_starting_at_one() -> None:
    out = _build_steps_section(
        {
            "type": "steps",
            "items": [
                {"title": "First", "body": "do this"},
                {"title": "Second", "body": "then this"},
                {"title": "Third", "body": "finally"},
            ],
        }
    )
    # Numbering: 1, 2, 3 in that order.
    pos1 = out.index(">1<")
    pos2 = out.index(">2<")
    pos3 = out.index(">3<")
    assert pos1 < pos2 < pos3


def test_steps_marks_non_last_items_with_modifier_class_and_connector() -> None:
    out = _build_steps_section(
        {
            "type": "steps",
            "items": [
                {"title": "A"},
                {"title": "B"},
            ],
        }
    )
    # 1 connector for 2 items (after #1; not after #2).
    assert out.count("dz-step-connector") == 1
    # is-not-last on first item only.
    assert out.count("is-not-last") == 1


def test_steps_handles_single_item_no_connector() -> None:
    out = _build_steps_section({"type": "steps", "items": [{"title": "Only", "body": "step"}]})
    assert "dz-step-connector" not in out
    assert "is-not-last" not in out


def test_steps_escapes_title_and_body() -> None:
    out = _build_steps_section(
        {
            "type": "steps",
            "items": [{"title": "<script>", "body": "<img src=x>"}],
        }
    )
    assert "<script>" not in out
    assert "<img" not in out


# ───────────────── comparison ────────────────────


def test_comparison_emits_section_class_and_table() -> None:
    out = _build_comparison_section({"type": "comparison"})
    assert 'class="dz-section dz-section-comparison"' in out
    assert "dz-comparison-table" in out


def test_comparison_renders_columns_in_thead() -> None:
    out = _build_comparison_section(
        {
            "type": "comparison",
            "columns": [
                {"label": "Free"},
                {"label": "Pro", "highlighted": True},
            ],
        }
    )
    # Empty leading <th></th> + columns.
    assert "<th></th>" in out
    assert "<th>Free</th>" in out
    assert '<th class="dz-comparison-highlighted">Pro</th>' in out


def test_comparison_renders_one_row_per_item() -> None:
    out = _build_comparison_section(
        {
            "type": "comparison",
            "columns": [{"label": "A"}, {"label": "B", "highlighted": True}],
            "items": [
                {"feature": "API access", "cells": ["✓", "✓"]},
                {"feature": "Support", "cells": ["email", "24/7"]},
            ],
        }
    )
    assert out.count("dz-comparison-feature") == 2
    assert ">API access<" in out
    # Highlight class on cells in the highlighted column too.
    assert '<td class="dz-comparison-highlighted">' in out


def test_comparison_handles_more_cells_than_columns() -> None:
    """Defensive: extra cells beyond column count don't crash."""
    out = _build_comparison_section(
        {
            "type": "comparison",
            "columns": [{"label": "A"}],
            "items": [{"feature": "x", "cells": ["1", "2", "3"]}],
        }
    )
    # 3 cells render even though only 1 column declared.
    assert out.count("<td>") + out.count("<td class=") >= 3


def test_comparison_escapes_cells_and_features() -> None:
    out = _build_comparison_section(
        {
            "type": "comparison",
            "columns": [{"label": "<x>"}],
            "items": [{"feature": "<y>", "cells": ["<z>"]}],
        }
    )
    assert "<x>" not in out
    assert "<y>" not in out
    assert "<z>" not in out


# ───────────────── split_content ────────────────────


def test_split_content_emits_section_class() -> None:
    out = _build_split_content_section({"type": "split_content"})
    assert 'class="dz-section dz-section-split-content"' in out


def test_split_content_alignment_right_swaps_order() -> None:
    out = _build_split_content_section({"type": "split_content", "alignment": "right"})
    assert "dz-split--reversed" in out


def test_split_content_alignment_default_no_swap_class() -> None:
    out = _build_split_content_section({"type": "split_content"})
    assert "dz-split--reversed" not in out


def test_split_content_renders_text_with_optional_body_and_cta() -> None:
    out = _build_split_content_section(
        {
            "type": "split_content",
            "headline": "Big idea",
            "body": "Long-form copy",
            "primary_cta": {"label": "Read", "href": "/r"},
        }
    )
    assert "<h2>Big idea</h2>" in out
    assert "<p>Long-form copy</p>" in out
    assert "dz-cta-group--left" in out
    assert 'href="/r"' in out


def test_split_content_renders_media_when_image() -> None:
    out = _build_split_content_section(
        {
            "type": "split_content",
            "headline": "Hi",
            "media": {"kind": "image", "src": "/x.png", "alt": "X"},
        }
    )
    assert "dz-split-media" in out
    assert 'src="/x.png"' in out


def test_split_content_omits_media_when_kind_not_image() -> None:
    out = _build_split_content_section(
        {
            "type": "split_content",
            "headline": "Hi",
            "media": {"kind": "video"},
        }
    )
    assert "dz-split-media" not in out


# ───────────────── card_grid ────────────────────


def test_card_grid_emits_section_class_and_grid() -> None:
    out = _build_card_grid_section({"type": "card_grid"})
    assert 'class="dz-section dz-section-card-grid"' in out
    assert "dz-card-grid" in out


def test_card_grid_renders_one_card_per_item() -> None:
    out = _build_card_grid_section(
        {
            "type": "card_grid",
            "items": [
                {"icon": "shield", "title": "Secure", "body": "TLS 1.3"},
                {"title": "Fast", "body": "p50 < 10ms"},
            ],
        }
    )
    assert out.count("dz-card-item") == 2
    assert 'data-lucide="shield"' in out
    assert "<h3>Secure</h3>" in out
    # Second card has no icon.
    second_card_pos = out.find("Fast")
    pre_text = out[:second_card_pos]
    # Only one icon block in the whole render.
    assert pre_text.count("dz-card-icon") == 1


def test_card_grid_renders_optional_per_item_cta() -> None:
    out = _build_card_grid_section(
        {
            "type": "card_grid",
            "items": [
                {
                    "title": "Plan",
                    "body": "Details",
                    "cta": {"label": "Pick", "href": "/p"},
                }
            ],
        }
    )
    assert 'href="/p"' in out
    assert ">Pick<" in out


def test_card_grid_renders_section_media_when_provided() -> None:
    out = _build_card_grid_section(
        {
            "type": "card_grid",
            "media": {"kind": "image", "src": "/banner.png", "alt": "Banner"},
        }
    )
    assert "dz-section-media" in out
    assert 'src="/banner.png"' in out


# ───────────────── team ────────────────────


def test_team_emits_section_class_and_grid() -> None:
    out = _build_team_section({"type": "team"})
    assert 'class="dz-section dz-section-team"' in out
    assert "dz-team-grid" in out


def test_team_renders_avatar_image_when_provided() -> None:
    out = _build_team_section(
        {
            "type": "team",
            "items": [
                {
                    "name": "Alice Wong",
                    "role": "CEO",
                    "image": "/alice.jpg",
                }
            ],
        }
    )
    assert 'src="/alice.jpg"' in out
    assert 'alt="Alice Wong"' in out
    # Initials fallback should NOT fire when image is present.
    assert "dz-team-initials" not in out


def test_team_renders_initials_fallback_when_no_image() -> None:
    out = _build_team_section({"type": "team", "items": [{"name": "Bob Builder"}]})
    assert "dz-team-initials" in out
    assert ">BB<" in out


def test_team_initials_uses_first_letter_of_first_two_words() -> None:
    out = _build_team_section({"type": "team", "items": [{"name": "Anne Marie de Beaufort"}]})
    # First two words: Anne, Marie → AM.
    assert ">AM<" in out


def test_team_renders_optional_role_and_bio() -> None:
    out = _build_team_section(
        {
            "type": "team",
            "items": [{"name": "X", "role": "Engineer", "bio": "Builds things"}],
        }
    )
    assert "dz-team-role" in out
    assert "dz-team-bio" in out


def test_team_renders_links_with_correct_lucide_icons() -> None:
    out = _build_team_section(
        {
            "type": "team",
            "items": [
                {
                    "name": "X",
                    "links": [
                        {"type": "linkedin", "href": "https://li/x"},
                        {"type": "email", "href": "mailto:x@x"},
                        {"type": "twitter", "href": "https://t/x"},
                        {"type": "github", "href": "https://gh/x"},
                        {"type": "blog", "href": "https://b/x"},  # → globe
                    ],
                }
            ],
        }
    )
    assert 'data-lucide="linkedin"' in out
    assert 'data-lucide="mail"' in out  # email → mail icon
    assert 'data-lucide="twitter"' in out
    assert 'data-lucide="github"' in out
    assert 'data-lucide="globe"' in out  # unknown type → globe


def test_team_link_anchors_have_security_attributes() -> None:
    out = _build_team_section(
        {
            "type": "team",
            "items": [
                {
                    "name": "X",
                    "links": [{"type": "linkedin", "href": "https://li/x"}],
                }
            ],
        }
    )
    assert 'target="_blank"' in out
    assert 'rel="noopener"' in out


def test_team_handles_member_without_name() -> None:
    """Missing name falls back to '?' (matches the Jinja default)."""
    out = _build_team_section({"type": "team", "items": [{}]})
    # Initials of '?' = '?' (single non-whitespace token, first char).
    assert ">?<" in out


# ───────────────── testimonials ────────────────────


def test_testimonials_emits_section_class_and_grid() -> None:
    out = _build_testimonials_section({"type": "testimonials"})
    assert 'class="dz-section dz-section-testimonials"' in out
    assert "dz-testimonials-grid" in out


def test_testimonials_renders_blockquote_with_quote_marks() -> None:
    out = _build_testimonials_section(
        {
            "type": "testimonials",
            "items": [{"quote": "Best product ever", "name": "Alice"}],
        }
    )
    assert '<blockquote>"Best product ever"</blockquote>' in out
    assert "<strong>Alice</strong>" in out


def test_testimonials_renders_optional_role() -> None:
    out = _build_testimonials_section(
        {
            "type": "testimonials",
            "items": [{"quote": "x", "name": "A", "role": "CEO"}],
        }
    )
    assert "<span>CEO</span>" in out


def test_testimonials_omits_role_when_absent() -> None:
    out = _build_testimonials_section(
        {"type": "testimonials", "items": [{"quote": "x", "name": "A"}]}
    )
    assert "<span>" not in out


def test_testimonials_escapes_quote_and_name_and_role() -> None:
    out = _build_testimonials_section(
        {
            "type": "testimonials",
            "items": [
                {
                    "quote": "<script>alert(1)</script>",
                    "name": "<img src=x>",
                    "role": "<svg/>",
                }
            ],
        }
    )
    assert "<script>" not in out
    assert "<img " not in out
    assert "<svg/>" not in out
