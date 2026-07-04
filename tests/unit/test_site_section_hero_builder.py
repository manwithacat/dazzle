"""Issue #1037 (v0.67.25): regression tests for the typed `hero`
sitespec section builder.

First section migrated to typed-Fragment rendering. Subsequent
section types (footer, features, pricing-table, faq, etc.) follow
the same shape — pure-function HTML builder consuming the section
dict and emitting class-stable HTML.

Tests pin the byte-shape contract against the legacy Jinja
template (`site/sections/hero.html`) — same class names, same
attribute structure, same conditional rendering of subhead/CTAs/
media. HTML escape responsibility lives with the builder.
"""

from __future__ import annotations

import pytest

from dazzle.http.runtime.renderers.site_section_builder import (
    TYPED_SECTION_TYPES,
    _build_hero_section,
    render_typed_section,
)


def test_hero_in_typed_section_types() -> None:
    """`render_typed_section` should accept hero — the dispatch
    membership check is the entrypoint."""
    assert "hero" in TYPED_SECTION_TYPES


def test_render_typed_section_dispatches_hero() -> None:
    out = render_typed_section({"type": "hero", "headline": "Welcome"})
    assert "<section" in out
    assert "dz-section-hero" in out


def test_render_typed_section_raises_for_unknown_type() -> None:
    with pytest.raises(KeyError):
        render_typed_section({"type": "nonexistent"})


# ───────────────── Hero builder shape ────────────────────


def test_hero_emits_section_wrapper_with_class() -> None:
    out = _build_hero_section({"type": "hero", "headline": "Hi"})
    assert "<section" in out
    assert 'class="dz-section dz-section-hero"' in out
    assert out.endswith("</section>")


def test_hero_emits_headline_in_h1_with_dz_hero_text_class() -> None:
    out = _build_hero_section({"type": "hero", "headline": "Welcome to Dazzle"})
    assert '<h1 class="dz-hero-text">Welcome to Dazzle</h1>' in out


def test_hero_emits_subhead_p_when_provided() -> None:
    out = _build_hero_section({"type": "hero", "headline": "Hi", "subhead": "Get started today"})
    assert '<p class="dz-subhead">Get started today</p>' in out


def test_hero_omits_subhead_p_when_absent() -> None:
    out = _build_hero_section({"type": "hero", "headline": "Hi"})
    assert "dz-subhead" not in out


def test_hero_emits_primary_cta_when_provided() -> None:
    out = _build_hero_section(
        {
            "type": "hero",
            "headline": "Hi",
            "primary_cta": {"label": "Sign Up", "href": "/signup"},
        }
    )
    assert "dz-cta-group" in out
    assert '<a href="/signup" class="dz-button" data-dz-variant="primary">Sign Up</a>' in out


def test_hero_emits_secondary_cta_with_outline_class() -> None:
    out = _build_hero_section(
        {
            "type": "hero",
            "headline": "Hi",
            "secondary_cta": {"label": "Docs", "href": "/docs"},
        }
    )
    assert '<a href="/docs" class="dz-button" data-dz-variant="outline">Docs</a>' in out


def test_hero_emits_both_ctas_when_both_provided() -> None:
    out = _build_hero_section(
        {
            "type": "hero",
            "headline": "Hi",
            "primary_cta": {"label": "Start", "href": "/s"},
            "secondary_cta": {"label": "Learn", "href": "/l"},
        }
    )
    assert 'data-dz-variant="primary"' in out
    assert 'data-dz-variant="outline"' in out
    # Primary first, secondary second.
    primary_pos = out.index('data-dz-variant="primary"')
    secondary_pos = out.index('data-dz-variant="outline"')
    assert primary_pos < secondary_pos


def test_hero_omits_cta_group_when_neither_cta_provided() -> None:
    out = _build_hero_section({"type": "hero", "headline": "Hi"})
    assert "dz-cta-group" not in out


def test_hero_cta_falls_back_to_default_href_and_label() -> None:
    """When a CTA dict is present but missing `label` / `href`, the
    Jinja template defaults href to `'#'` and labels to
    'Get Started' / 'Learn More'. Match that — but note: an EMPTY
    CTA dict is falsy in Jinja's `{% if section.primary_cta %}`
    gate and skips entirely. The default-render path requires the
    dict to be truthy (any key / non-empty)."""
    out = _build_hero_section(
        {
            "type": "hero",
            "headline": "Hi",
            "primary_cta": {"_present": True},  # truthy, but no label/href
            "secondary_cta": {"_present": True},
        }
    )
    assert 'href="#"' in out
    assert ">Get Started<" in out
    assert ">Learn More<" in out


def test_hero_skips_cta_when_dict_is_empty_dict() -> None:
    """Defensive parity with Jinja: empty dict is falsy → skip
    the CTA. This matches the legacy template's `{% if %}` gate
    behaviour."""
    out = _build_hero_section(
        {"type": "hero", "headline": "Hi", "primary_cta": {}, "secondary_cta": {}}
    )
    assert "dz-cta-group" not in out


def test_hero_emits_media_block_when_image_kind() -> None:
    out = _build_hero_section(
        {
            "type": "hero",
            "headline": "Hi",
            "media": {"kind": "image", "src": "/img/hero.png", "alt": "Hero"},
        }
    )
    assert "dz-hero-with-media" in out  # modifier class
    assert (
        '<div class="dz-hero-media"><img src="/img/hero.png" alt="Hero" class="dz-hero-image"></div>'
        in out
    )


def test_hero_omits_media_block_when_kind_not_image() -> None:
    out = _build_hero_section(
        {
            "type": "hero",
            "headline": "Hi",
            "media": {"kind": "video", "src": "/v.mp4"},
        }
    )
    assert "dz-hero-with-media" not in out
    assert "dz-hero-media" not in out


def test_hero_omits_media_block_when_src_missing() -> None:
    out = _build_hero_section({"type": "hero", "headline": "Hi", "media": {"kind": "image"}})
    assert "dz-hero-with-media" not in out


# ───────────────── id attribute ────────────────────


def test_hero_uses_explicit_section_id_when_provided() -> None:
    out = _build_hero_section({"type": "hero", "id": "main-hero", "headline": "Hi"})
    assert ' id="main-hero"' in out


def test_hero_falls_back_to_slugified_headline_when_no_id() -> None:
    out = _build_hero_section({"type": "hero", "headline": "Welcome to Dazzle 2026"})
    assert ' id="welcome-to-dazzle-2026"' in out


def test_hero_omits_id_when_no_id_or_headline_for_slug() -> None:
    out = _build_hero_section({"type": "hero"})
    assert " id=" not in out


# ───────────────── HTML escape safety ────────────────────


def test_hero_escapes_headline_text() -> None:
    out = _build_hero_section({"type": "hero", "headline": "<script>alert(1)</script>"})
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_hero_escapes_subhead_text() -> None:
    out = _build_hero_section({"type": "hero", "headline": "Hi", "subhead": "<img src=x>"})
    assert "<img" not in out
    assert "&lt;img" in out


def test_hero_escapes_cta_label_and_href() -> None:
    out = _build_hero_section(
        {
            "type": "hero",
            "headline": "Hi",
            "primary_cta": {
                "label": "<script>",
                "href": '"><script>x</script>',
            },
        }
    )
    # Label escapes — the literal <script> opening tag must not
    # appear as raw markup; only its escaped form.
    assert "<script>" not in out
    assert "&lt;script&gt;" in out
    # The href-injection payload's quote-break must be escaped:
    # `"` → `&quot;`. Pre-fix would emit href="..."><script>...
    # which would close the attribute and inject a script tag.
    assert "&quot;&gt;&lt;script&gt;" in out


def test_hero_escapes_media_src_and_alt() -> None:
    out = _build_hero_section(
        {
            "type": "hero",
            "headline": "Hi",
            "media": {
                "kind": "image",
                "src": '"><svg/onload=alert(1)>',
                "alt": '"><img src=x>',
            },
        }
    )
    # Both attribute-injection payloads must be escaped — the raw
    # `<svg` and `<img` tag-opens should not appear in the output.
    # Inside the actual escaped attribute values they look like
    # `&quot;&gt;&lt;svg/onload...&gt;`. The substring `onload=alert`
    # itself appears in the escaped attribute body and is harmless
    # there because the surrounding `<svg` is already neutered.
    assert "&quot;&gt;&lt;svg" in out
    assert "&quot;&gt;&lt;img" in out
    # Critical: no raw `<svg` opening tag escaped the attribute.
    assert "<svg" not in out
    assert "<img src=x>" not in out  # alt-attr break attempt neutralised


def test_hero_escapes_explicit_section_id() -> None:
    out = _build_hero_section({"type": "hero", "id": '"><script>', "headline": "Hi"})
    assert '"><script>' not in out
