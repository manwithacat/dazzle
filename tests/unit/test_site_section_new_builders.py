"""Tests for the 5 new SaaS-marketing section builders (#1110 Part B).

Each builder is a pure function `dict -> str`; tests assert HTML
structure + escaping + tooltip union-shape handling.
"""

from dazzle.http.runtime.renderers.site_section_builder import (
    TYPED_SECTION_TYPES,
    _render_compliance_tooltip,
    render_typed_section,
)

# ---------------------------------------------------------------------------
# social_proof_strip
# ---------------------------------------------------------------------------


def test_social_proof_strip_renders_count_and_label() -> None:
    section = {
        "type": "social_proof_strip",
        "items": [
            {"count": "10,000+", "label": "active users", "icon": "users"},
            {"count": "$2M", "label": "ARR"},
        ],
    }
    html = render_typed_section(section)
    assert "dz-section-social-proof-strip" in html
    assert "10,000+" in html
    assert "active users" in html
    assert "$2M" in html
    assert 'data-lucide="users"' in html


def test_social_proof_strip_escapes_user_input() -> None:
    section = {
        "type": "social_proof_strip",
        "items": [{"count": "<script>", "label": "</section>"}],
    }
    html = render_typed_section(section)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


# ---------------------------------------------------------------------------
# integration_grid
# ---------------------------------------------------------------------------


def test_integration_grid_renders_tile_with_logo_and_name() -> None:
    section = {
        "type": "integration_grid",
        "items": [
            {"name": "Slack", "logo": "/static/slack.svg", "href": "/integrations/slack"},
            {"name": "GitHub", "logo": "/static/gh.svg"},
        ],
    }
    html = render_typed_section(section)
    assert "dz-section-integration-grid" in html
    assert "Slack" in html
    assert "/integrations/slack" in html
    # Tile without href renders as div, not anchor.
    assert "GitHub" in html


# ---------------------------------------------------------------------------
# compliance_badge_row + tooltip union shape
# ---------------------------------------------------------------------------


def test_compliance_badge_row_string_tooltip() -> None:
    """tooltip can be a plain string — simplest case."""
    section = {
        "type": "compliance_badge_row",
        "badges": [
            {
                "label": "SOC 2 Type II",
                "logo": "/static/soc2.svg",
                "tooltip": "Audited annually since 2024.",
            }
        ],
    }
    html = render_typed_section(section)
    assert "SOC 2 Type II" in html
    assert "Audited annually since 2024." in html
    assert "dz-compliance-tooltip" in html
    # No link rendered when tooltip is a plain string.
    assert "dz-compliance-tooltip-link" not in html


def test_compliance_badge_row_object_tooltip_with_link() -> None:
    """tooltip can be {body, link, link_text} for enriched tooltips."""
    section = {
        "type": "compliance_badge_row",
        "badges": [
            {
                "label": "GDPR Ready",
                "logo": "/static/gdpr.svg",
                "tooltip": {
                    "body": "EU data residency available on request.",
                    "link": "/trust/gdpr",
                    "link_text": "Read more",
                },
            }
        ],
    }
    html = render_typed_section(section)
    assert "EU data residency available on request." in html
    assert "/trust/gdpr" in html
    assert "Read more" in html


def test_compliance_badge_row_object_tooltip_default_link_text() -> None:
    """link without link_text defaults to 'Learn more'."""
    section = {
        "type": "compliance_badge_row",
        "badges": [
            {
                "label": "GDPR Ready",
                "logo": "/static/gdpr.svg",
                "tooltip": {"body": "x", "link": "/trust/gdpr"},
            }
        ],
    }
    html = render_typed_section(section)
    assert "Learn more" in html


def test_compliance_badge_row_handles_missing_tooltip() -> None:
    """No tooltip → badge renders cleanly without a tooltip div."""
    section = {
        "type": "compliance_badge_row",
        "badges": [{"label": "ISO 27001", "logo": "/static/iso.svg"}],
    }
    html = render_typed_section(section)
    assert "ISO 27001" in html
    assert "dz-compliance-tooltip" not in html


def test_render_compliance_tooltip_unknown_shape_falls_through_silently() -> None:
    """A typo (list, int, etc.) doesn't crash the page render."""
    assert _render_compliance_tooltip(None) == ""
    assert _render_compliance_tooltip("") == ""
    assert _render_compliance_tooltip([1, 2, 3]) == ""
    assert _render_compliance_tooltip(42) == ""
    # Empty-body dict also falls through (renders nothing).
    assert _render_compliance_tooltip({"body": ""}) == ""


# ---------------------------------------------------------------------------
# before_after_comparison
# ---------------------------------------------------------------------------


def test_before_after_renders_two_columns_with_lists() -> None:
    section = {
        "type": "before_after_comparison",
        "before": {
            "headline": "The old way",
            "items": ["3 tools", "5 logins", "manual reconciliation"],
        },
        "after": {
            "headline": "The new way",
            "items": ["1 tool", "1 login", "automated"],
        },
    }
    html = render_typed_section(section)
    assert "dz-section-before-after" in html
    assert "The old way" in html
    assert "The new way" in html
    assert "3 tools" in html
    assert "automated" in html
    assert "dz-before-after-before" in html
    assert "dz-before-after-after" in html


def test_before_after_handles_missing_column() -> None:
    """A missing 'after' column renders the present 'before' column cleanly."""
    section = {
        "type": "before_after_comparison",
        "before": {"headline": "Old", "items": ["a"]},
    }
    html = render_typed_section(section)
    assert "Old" in html
    # No after column.
    assert "dz-before-after-after" not in html


# ---------------------------------------------------------------------------
# mid_page_cta_band
# ---------------------------------------------------------------------------


def test_mid_page_cta_band_renders_headline_subhead_and_cta() -> None:
    section = {
        "type": "mid_page_cta_band",
        "headline": "Ready to scale?",
        "subhead": "Start free, upgrade when you're ready.",
        "cta": {"label": "Start now", "href": "/signup"},
    }
    html = render_typed_section(section)
    assert "Ready to scale?" in html
    assert "Start free" in html
    assert 'href="/signup"' in html
    assert "Start now" in html


def test_mid_page_cta_band_missing_cta_is_safe() -> None:
    """No CTA at all → headline + subhead still render."""
    section = {
        "type": "mid_page_cta_band",
        "headline": "Standalone callout",
    }
    html = render_typed_section(section)
    assert "Standalone callout" in html


# ---------------------------------------------------------------------------
# Whitelist
# ---------------------------------------------------------------------------


def test_typed_section_types_includes_all_5_new_types() -> None:
    """The dispatch whitelist must include each Part B section type
    so non-override callers ([sitespec validate], scaffold) accept them."""
    for t in [
        "social_proof_strip",
        "integration_grid",
        "compliance_badge_row",
        "before_after_comparison",
        "mid_page_cta_band",
    ]:
        assert t in TYPED_SECTION_TYPES, f"{t} missing from TYPED_SECTION_TYPES"
