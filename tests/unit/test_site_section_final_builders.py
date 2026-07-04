"""Issue #1037 (v0.67.28): regression tests for the final batch of
typed sitespec section builders — `features`, `pricing`, `faq`.

Closes the section migration arc: 17 of 19 section types are now
typed (89%). Only `qa_personas` remains on Jinja, and it's a
deliberate dev-only exception (gated on `{% if qa_personas %}` —
never fires in production where cyfuture's stop condition matters).

With this ship, a chrome=on production sitespec render produces
**zero `Template.render()` calls** for any of the standard 18
non-dev section types — `jinja2` retirement is now within reach
for any sitespec that doesn't author custom non-standard types.
"""

from __future__ import annotations

from dazzle.http.runtime.renderers.site_section_builder import (
    TYPED_SECTION_TYPES,
    _build_faq_section,
    _build_features_section,
    _build_pricing_section,
    render_typed_section,
)


def test_three_new_section_types_in_typed_set() -> None:
    for t in ("features", "pricing", "faq"):
        assert t in TYPED_SECTION_TYPES


def test_render_typed_section_dispatches_each_new_type() -> None:
    for t in ("features", "pricing", "faq"):
        out = render_typed_section({"type": t})
        assert "<section" in out


# ───────────────── features ────────────────────


def test_features_emits_section_class_and_grid() -> None:
    out = _build_features_section({"type": "features"})
    assert 'class="dz-section dz-section-features"' in out
    assert "dz-features-grid" in out


def test_features_renders_one_item_per_entry() -> None:
    out = _build_features_section(
        {
            "type": "features",
            "items": [
                {"icon": "shield", "title": "Secure", "body": "TLS 1.3"},
                {"icon": "zap", "title": "Fast", "body": "p50 < 10ms"},
            ],
        }
    )
    assert out.count("dz-feature-item") == 2
    assert 'data-lucide="shield"' in out
    assert 'data-lucide="zap"' in out
    assert "<h3>Secure</h3>" in out
    assert "<h3>Fast</h3>" in out


def test_features_omits_icon_when_absent() -> None:
    out = _build_features_section(
        {"type": "features", "items": [{"title": "Plain", "body": "No icon"}]}
    )
    assert "data-lucide" not in out
    assert "<h3>Plain</h3>" in out


def test_features_renders_section_header_when_provided() -> None:
    out = _build_features_section({"type": "features", "headline": "Why us", "items": []})
    assert "dz-section-header" in out
    assert ">Why us<" in out


def test_features_renders_section_media_when_image_provided() -> None:
    """`features` uses both `section_header` AND `section_media`
    (matches the Jinja partial's macro imports)."""
    out = _build_features_section(
        {
            "type": "features",
            "media": {"kind": "image", "src": "/banner.png", "alt": "B"},
        }
    )
    assert "dz-section-media" in out
    assert 'src="/banner.png"' in out


def test_features_escapes_user_supplied_fields() -> None:
    out = _build_features_section(
        {
            "type": "features",
            "items": [
                {
                    "icon": '"><script>',
                    "title": "<svg/>",
                    "body": "<img src=x>",
                }
            ],
        }
    )
    assert "<script>" not in out
    assert "<svg/>" not in out
    assert "<img " not in out


# ───────────────── pricing ────────────────────


def test_pricing_emits_section_class_and_grid() -> None:
    out = _build_pricing_section({"type": "pricing"})
    assert 'class="dz-section dz-section-pricing"' in out
    assert "dz-pricing-grid" in out


def test_pricing_renders_one_tier_per_entry() -> None:
    out = _build_pricing_section(
        {
            "type": "pricing",
            "tiers": [
                {
                    "name": "Free",
                    "price": "$0",
                    "features": ["1 project"],
                },
                {
                    "name": "Pro",
                    "price": "$9",
                    "features": ["Unlimited projects", "Priority support"],
                },
            ],
        }
    )
    assert out.count("dz-pricing-tier") == 2
    assert "<h3>Free</h3>" in out
    assert "<h3>Pro</h3>" in out


def test_pricing_period_defaults_to_per_month() -> None:
    out = _build_pricing_section({"type": "pricing", "tiers": [{"name": "X", "price": "$5"}]})
    # Default period is /month per the Jinja `default('/month')`.
    assert ">/month<" in out


def test_pricing_period_override_respected() -> None:
    out = _build_pricing_section(
        {
            "type": "pricing",
            "tiers": [{"name": "X", "price": "$50", "period": "/year"}],
        }
    )
    assert ">/year<" in out


def test_pricing_highlighted_tier_gets_modifier_class() -> None:
    out = _build_pricing_section(
        {
            "type": "pricing",
            "tiers": [
                {"name": "Free", "price": "$0"},
                {"name": "Pro", "price": "$9", "highlighted": True},
            ],
        }
    )
    assert "dz-pricing-highlighted" in out


def test_pricing_highlighted_tier_defaults_cta_to_primary() -> None:
    """#1263: the default flipped. Highlighted tier's CTA now defaults to
    `data-dz-variant=primary` (matches Stripe/Linear convention — the
    recommended action looks like the recommended action);
    non-highlighted tiers default to `data-dz-variant=outline` to recede."""
    out = _build_pricing_section(
        {
            "type": "pricing",
            "tiers": [
                {
                    "name": "Free",
                    "price": "$0",
                    "cta": {"label": "Pick", "href": "/f"},
                },
                {
                    "name": "Pro",
                    "price": "$9",
                    "highlighted": True,
                    "cta": {"label": "Pick Pro", "href": "/p"},
                },
            ],
        }
    )
    free_pos = out.index(">Pick<")
    free_section = out[max(0, free_pos - 200) : free_pos]
    assert 'data-dz-variant="outline"' in free_section
    pro_pos = out.index(">Pick Pro<")
    pro_section = out[max(0, pro_pos - 200) : pro_pos]
    assert 'data-dz-variant="primary"' in pro_section


def test_pricing_cta_variant_override_wins_over_default_1263() -> None:
    """#1263: explicit `cta.variant` overrides the highlighted-based
    default in both directions — a non-highlighted tier can opt into
    primary, and a highlighted tier can opt back to outline."""
    out = _build_pricing_section(
        {
            "type": "pricing",
            "tiers": [
                {
                    "name": "Free",
                    "price": "$0",
                    "cta": {"label": "FreeCTA", "href": "/f", "variant": "primary"},
                },
                {
                    "name": "Pro",
                    "price": "$9",
                    "highlighted": True,
                    "cta": {"label": "ProCTA", "href": "/p", "variant": "outline"},
                },
                {
                    "name": "Ent",
                    "price": "Custom",
                    "cta": {"label": "EntCTA", "href": "/e", "variant": "ghost"},
                },
            ],
        }
    )
    free_section = out[max(0, out.index(">FreeCTA<") - 200) : out.index(">FreeCTA<")]
    assert 'data-dz-variant="primary"' in free_section, (
        "non-highlighted tier with variant=primary must use data-dz-variant=primary"
    )
    pro_section = out[max(0, out.index(">ProCTA<") - 200) : out.index(">ProCTA<")]
    assert 'data-dz-variant="outline"' in pro_section, (
        "highlighted tier with variant=outline must use data-dz-variant=outline (the old default, opted into explicitly)"
    )
    ent_section = out[max(0, out.index(">EntCTA<") - 200) : out.index(">EntCTA<")]
    assert 'data-dz-variant="ghost"' in ent_section, "variant=ghost must use data-dz-variant=ghost"


def test_pricing_features_list_renders_each_as_li() -> None:
    out = _build_pricing_section(
        {
            "type": "pricing",
            "tiers": [
                {
                    "name": "X",
                    "price": "$1",
                    "features": ["First", "Second", "Third"],
                }
            ],
        }
    )
    assert out.count("<li>") == 3
    assert "<li>First</li>" in out
    assert "<li>Second</li>" in out


def test_pricing_renders_cta_with_default_label() -> None:
    out = _build_pricing_section(
        {
            "type": "pricing",
            "tiers": [
                {"name": "X", "price": "$1", "cta": {"href": "/x"}},
            ],
        }
    )
    assert ">Choose Plan<" in out  # default label


def test_pricing_omits_cta_when_absent() -> None:
    out = _build_pricing_section({"type": "pricing", "tiers": [{"name": "X", "price": "$1"}]})
    assert "dz-button" not in out


def test_pricing_escapes_tier_fields() -> None:
    out = _build_pricing_section(
        {
            "type": "pricing",
            "tiers": [
                {
                    "name": "<script>",
                    "price": "<svg/>",
                    "period": "<img>",
                    "features": ["<x>"],
                    "cta": {"label": "<y>", "href": '"><z>'},
                }
            ],
        }
    )
    assert "<script>" not in out
    assert "<svg/>" not in out
    assert "<img>" not in out
    assert "<x>" not in out
    assert "<y>" not in out


# ───────────────── faq ────────────────────


def test_faq_emits_section_class_and_list() -> None:
    out = _build_faq_section({"type": "faq"})
    assert 'class="dz-section dz-section-faq"' in out
    assert "dz-faq-list" in out


def test_faq_renders_native_details_summary_per_item() -> None:
    out = _build_faq_section(
        {
            "type": "faq",
            "items": [
                {"question": "How fast?", "answer": "Very fast."},
                {"question": "How secure?", "answer": "Very secure."},
            ],
        }
    )
    assert out.count('<details class="dz-faq-item">') == 2
    assert "<summary>How fast?</summary>" in out
    assert "<p>Very fast.</p>" in out
    assert "<summary>How secure?</summary>" in out


def test_faq_renders_section_header_when_provided() -> None:
    out = _build_faq_section(
        {
            "type": "faq",
            "headline": "Common questions",
            "items": [],
        }
    )
    assert "dz-section-header" in out
    assert ">Common questions<" in out


def test_faq_handles_empty_items() -> None:
    out = _build_faq_section({"type": "faq"})
    assert "dz-faq-list" in out
    assert "<details" not in out


def test_faq_escapes_question_and_answer() -> None:
    out = _build_faq_section(
        {
            "type": "faq",
            "items": [
                {
                    "question": "<script>alert(1)</script>",
                    "answer": "<img src=x onerror=alert(1)>",
                }
            ],
        }
    )
    assert "<script>" not in out
    assert "<img " not in out
    assert "&lt;script&gt;" in out
