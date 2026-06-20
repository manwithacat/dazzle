"""Issue #1037 (v0.67.26): regression tests for the second batch of
typed sitespec section builders — `cta`, `generic`, `trust_bar`,
`value_highlight`, `logo_cloud`, `markdown`.

Six section types migrated in one ship — all are simple shape +
small surface area, picked per the v0.67.25 sequencing guidance
(start with the simplest after hero). Pricing-table and faq are
deferred until last per CHANGELOG agent guidance.
"""

from __future__ import annotations

from dazzle.http.runtime.renderers.site_section_builder import (
    TYPED_SECTION_TYPES,
    _build_cta_section,
    _build_generic_section,
    _build_logo_cloud_section,
    _build_markdown_section,
    _build_trust_bar_section,
    _build_value_highlight_section,
    render_typed_section,
)


def test_six_new_section_types_in_typed_set() -> None:
    for t in ("cta", "generic", "trust_bar", "value_highlight", "logo_cloud", "markdown"):
        assert t in TYPED_SECTION_TYPES


# ───────────────── cta ────────────────────


def test_cta_emits_section_class() -> None:
    out = _build_cta_section({"type": "cta"})
    assert 'class="dz-section dz-section-cta"' in out


def test_cta_renders_headline_subhead_and_ctas() -> None:
    out = _build_cta_section(
        {
            "type": "cta",
            "headline": "Try it",
            "subhead": "Free trial",
            "primary_cta": {"label": "Start", "href": "/start"},
            "secondary_cta": {"label": "Docs", "href": "/docs"},
        }
    )
    assert "<h2>Try it</h2>" in out
    assert '<p class="dz-subhead">Free trial</p>' in out
    assert 'href="/start"' in out
    assert "dz-button-primary" in out
    assert "dz-button-outline" in out


def test_cta_omits_blocks_when_fields_absent() -> None:
    out = _build_cta_section({"type": "cta"})
    assert "<h2>" not in out
    assert "dz-subhead" not in out
    assert "dz-cta-group" not in out


def test_cta_escapes_user_supplied_fields() -> None:
    out = _build_cta_section(
        {
            "type": "cta",
            "headline": "<script>",
            "subhead": "<img src=x>",
            "primary_cta": {"label": "<svg>", "href": '"><x>'},
        }
    )
    assert "<script>" not in out
    assert "<img" not in out
    assert "<svg>" not in out
    assert "&lt;script&gt;" in out


# ───────────────── generic ────────────────────


def test_generic_section_class_derives_from_type_with_dashes() -> None:
    out = _build_generic_section({"type": "my_block"})
    assert 'class="dz-section dz-section-my-block"' in out


def test_generic_renders_section_header_when_headline_present() -> None:
    out = _build_generic_section({"type": "x", "headline": "Hello", "subhead": "World"})
    assert "dz-section-header" in out
    assert "<h2>Hello</h2>" in out
    assert '<p class="dz-subhead">World</p>' in out


def test_generic_omits_section_header_when_no_headline_or_subhead() -> None:
    out = _build_generic_section({"type": "x"})
    assert "dz-section-header" not in out


def test_generic_renders_content_unescaped() -> None:
    """Mirrors the Jinja `| safe` filter — content is trusted
    pre-rendered HTML (typically server-side Markdown)."""
    out = _build_generic_section({"type": "x", "content": "<p>Trusted <strong>HTML</strong></p>"})
    assert "<p>Trusted <strong>HTML</strong></p>" in out


def test_generic_class_falls_back_to_unknown_when_type_missing() -> None:
    out = _build_generic_section({})
    assert "dz-section-unknown" in out


# ───────────────── trust_bar ────────────────────


def test_trust_bar_emits_section_class() -> None:
    out = _build_trust_bar_section({"type": "trust_bar"})
    assert 'class="dz-section dz-section-trust-bar"' in out


def test_trust_bar_renders_one_item_per_entry() -> None:
    out = _build_trust_bar_section(
        {
            "type": "trust_bar",
            "items": [
                {"icon": "shield", "text": "SOC 2"},
                {"icon": "lock", "text": "Encrypted"},
            ],
        }
    )
    assert out.count("dz-trust-item") == 2
    assert 'data-lucide="shield"' in out
    assert ">SOC 2<" in out
    assert 'data-lucide="lock"' in out


def test_trust_bar_omits_icon_when_absent() -> None:
    out = _build_trust_bar_section({"type": "trust_bar", "items": [{"text": "Just text"}]})
    assert "data-lucide" not in out
    assert ">Just text<" in out


def test_trust_bar_handles_empty_items() -> None:
    out = _build_trust_bar_section({"type": "trust_bar"})
    assert "dz-trust-strip" in out
    assert "dz-trust-item" not in out


def test_trust_bar_escapes_text_and_icon() -> None:
    out = _build_trust_bar_section(
        {
            "type": "trust_bar",
            "items": [{"icon": '"><script>', "text": "<svg/>"}],
        }
    )
    assert "<script>" not in out
    assert "<svg" not in out
    assert "&lt;svg" in out


# ───────────────── value_highlight ────────────────────


def test_value_highlight_emits_required_classes() -> None:
    out = _build_value_highlight_section({"type": "value_highlight", "headline": "Big"})
    assert 'class="dz-section dz-section-value-highlight"' in out
    assert '<h2 class="dz-value-headline">Big</h2>' in out


def test_value_highlight_renders_optional_subhead_and_body() -> None:
    out = _build_value_highlight_section(
        {
            "type": "value_highlight",
            "headline": "H",
            "subhead": "S",
            "body": "B",
        }
    )
    assert '<p class="dz-subhead">S</p>' in out
    assert '<p class="dz-value-body">B</p>' in out


def test_value_highlight_renders_primary_cta_only() -> None:
    """No secondary_cta support — different from hero/cta."""
    out = _build_value_highlight_section(
        {
            "type": "value_highlight",
            "headline": "H",
            "primary_cta": {"label": "Go", "href": "/g"},
            "secondary_cta": {"label": "Docs", "href": "/d"},
        }
    )
    assert "dz-button-primary" in out
    assert "dz-button-outline" not in out


def test_value_highlight_omits_optional_blocks_when_absent() -> None:
    out = _build_value_highlight_section({"type": "value_highlight", "headline": "H"})
    assert "dz-subhead" not in out
    assert "dz-value-body" not in out
    assert "dz-cta-group" not in out


# ───────────────── logo_cloud ────────────────────


def test_logo_cloud_emits_section_class_and_grid() -> None:
    out = _build_logo_cloud_section({"type": "logo_cloud"})
    assert 'class="dz-section dz-section-logo-cloud"' in out
    assert "dz-logos-grid" in out


def test_logo_cloud_renders_one_anchor_per_item() -> None:
    out = _build_logo_cloud_section(
        {
            "type": "logo_cloud",
            "items": [
                {"name": "Acme", "src": "/acme.png", "href": "https://acme.com"},
                {"name": "Beta", "src": "/beta.png", "href": "https://beta.com"},
            ],
        }
    )
    assert out.count("dz-logo-item") == 2
    assert 'href="https://acme.com"' in out
    assert 'src="/acme.png"' in out
    assert 'alt="Acme"' in out
    assert 'title="Acme"' in out


def test_logo_cloud_renders_section_header_when_provided() -> None:
    out = _build_logo_cloud_section({"type": "logo_cloud", "headline": "Trusted by", "items": []})
    assert "dz-section-header" in out
    assert ">Trusted by<" in out


def test_logo_cloud_escapes_item_fields() -> None:
    out = _build_logo_cloud_section(
        {
            "type": "logo_cloud",
            "items": [
                {
                    "name": "<script>",
                    "src": '"><svg>',
                    "href": '"><x>',
                }
            ],
        }
    )
    assert "<script>" not in out
    assert "<svg>" not in out


# ───────────────── markdown ────────────────────


def test_markdown_emits_section_class() -> None:
    out = _build_markdown_section({"type": "markdown", "content": "<p>Hi</p>"})
    assert 'class="dz-section dz-section-markdown"' in out


def test_markdown_renders_content_unescaped() -> None:
    """Mirrors the Jinja `| safe` filter — content is trusted
    pre-rendered Markdown HTML."""
    out = _build_markdown_section(
        {"type": "markdown", "content": "<h2>Title</h2><p>Body with <em>emphasis</em></p>"}
    )
    assert "<h2>Title</h2>" in out
    assert "<em>emphasis</em>" in out


def test_markdown_handles_missing_content() -> None:
    """Pre-fix would crash on .get()-without-default; defensive
    coverage."""
    out = _build_markdown_section({"type": "markdown"})
    assert 'class="dz-section dz-section-markdown"' in out
    # Empty content slot should still emit a content div.
    assert 'class="dz-section-content prose max-w-none"' in out


# ───────────────── render_typed_section dispatch ────────────────────


def test_render_typed_section_dispatches_each_new_type() -> None:
    """Sanity: render_typed_section dispatches all six new types
    without raising KeyError."""
    for t in ("cta", "generic", "trust_bar", "value_highlight", "logo_cloud", "markdown"):
        out = render_typed_section({"type": t})
        assert "<section" in out
