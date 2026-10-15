"""Typed sitespec section builders, pinned through ``render_typed_section``.

#1037 migrated every standard sitespec section from Jinja partials to pure
``dict -> str`` builders (hero; cta/generic/trust_bar/value_highlight/
logo_cloud/markdown; stats/steps/comparison/split_content/card_grid/team/
testimonials; features/pricing/faq); #1110 Part B added the five SaaS
marketing primitives. The builders keep the legacy templates' class names,
attribute structure and conditional blocks, and own HTML escaping.

Every case goes through the public dispatcher. The tables below are the
contract: ``RENDERS`` (fragments that must appear), ``OMITS`` (fragments that
must not), ``COUNTS`` (one element per item), ``ORDER`` and ``ESCAPES`` (one
row per hostile payload, each individually identifiable).
"""

from __future__ import annotations

import pytest

from dazzle.http.runtime.renderers.site_section_builder import (
    TYPED_SECTION_TYPES,
    render_typed_section,
)

# Section type -> the modifier class its <section> wrapper carries.
SECTION_CLASSES = {
    "hero": "dz-section-hero",
    "cta": "dz-section-cta",
    "generic": "dz-section-generic",
    "trust_bar": "dz-section-trust-bar",
    "value_highlight": "dz-section-value-highlight",
    "logo_cloud": "dz-section-logo-cloud",
    "markdown": "dz-section-markdown",
    "stats": "dz-section-stats",
    "steps": "dz-section-steps",
    "comparison": "dz-section-comparison",
    "split_content": "dz-section-split-content",
    "card_grid": "dz-section-card-grid",
    "team": "dz-section-team",
    "testimonials": "dz-section-testimonials",
    "features": "dz-section-features",
    "pricing": "dz-section-pricing",
    "faq": "dz-section-faq",
    "social_proof_strip": "dz-section-social-proof-strip",
    "integration_grid": "dz-section-integration-grid",
    "compliance_badge_row": "dz-section-compliance-badges",
    "before_after_comparison": "dz-section-before-after",
    "mid_page_cta_band": "dz-section-mid-page-cta-band",
}


def test_typed_section_types_is_exactly_the_dispatchable_set() -> None:
    """The whitelist non-override callers (sitespec validate, scaffold) read."""
    assert TYPED_SECTION_TYPES == frozenset(SECTION_CLASSES)


@pytest.mark.parametrize(("section_type", "modifier"), sorted(SECTION_CLASSES.items()))
def test_dispatch_emits_one_section_wrapper_with_its_class(
    section_type: str, modifier: str
) -> None:
    out = render_typed_section({"type": section_type})
    assert out.startswith("<section")
    assert out.endswith("</section>")
    assert f'class="dz-section {modifier}"' in out


def test_dispatch_raises_for_unknown_type() -> None:
    with pytest.raises(KeyError):
        render_typed_section({"type": "nonexistent"})


RENDERS = [
    # ── hero ──
    pytest.param(
        {"type": "hero", "headline": "Welcome to Dazzle"},
        ['<h1 class="dz-hero-text">Welcome to Dazzle</h1>'],
        id="hero-headline-in-h1",
    ),
    pytest.param(
        {"type": "hero", "headline": "Hi", "subhead": "Get started today"},
        ['<p class="dz-subhead">Get started today</p>'],
        id="hero-subhead",
    ),
    pytest.param(
        {"type": "hero", "headline": "Hi", "primary_cta": {"label": "Sign Up", "href": "/signup"}},
        [
            "dz-cta-group",
            '<a href="/signup" class="dz-button" data-dz-variant="primary">Sign Up</a>',
        ],
        id="hero-primary-cta",
    ),
    pytest.param(
        {"type": "hero", "headline": "Hi", "secondary_cta": {"label": "Docs", "href": "/docs"}},
        ['<a href="/docs" class="dz-button" data-dz-variant="outline">Docs</a>'],
        id="hero-secondary-cta-is-outline",
    ),
    pytest.param(
        # A truthy CTA dict without label/href takes the template defaults;
        # an empty dict is falsy and skips (see OMITS).
        {
            "type": "hero",
            "headline": "Hi",
            "primary_cta": {"_present": True},
            "secondary_cta": {"_present": True},
        },
        ['href="#"', ">Get Started<", ">Learn More<"],
        id="hero-cta-defaults-href-and-labels",
    ),
    pytest.param(
        {
            "type": "hero",
            "headline": "Hi",
            "media": {"kind": "image", "src": "/img/hero.png", "alt": "Hero"},
        },
        [
            "dz-hero-with-media",
            '<div class="dz-hero-media"><img src="/img/hero.png" alt="Hero" class="dz-hero-image"></div>',
        ],
        id="hero-image-media",
    ),
    pytest.param(
        {"type": "hero", "id": "main-hero", "headline": "Hi"},
        [' id="main-hero"'],
        id="hero-explicit-id",
    ),
    pytest.param(
        {"type": "hero", "headline": "Welcome to Dazzle 2026"},
        [' id="welcome-to-dazzle-2026"'],
        id="hero-id-slugified-from-headline",
    ),
    # ── cta ──
    pytest.param(
        {
            "type": "cta",
            "headline": "Try it",
            "subhead": "Free trial",
            "primary_cta": {"label": "Start", "href": "/start"},
            "secondary_cta": {"label": "Docs", "href": "/docs"},
        },
        [
            "<h2>Try it</h2>",
            '<p class="dz-subhead">Free trial</p>',
            'href="/start"',
            'data-dz-variant="primary"',
            'data-dz-variant="outline"',
        ],
        id="cta-headline-subhead-and-both-ctas",
    ),
    # ── generic ──
    pytest.param(
        {"type": "generic", "headline": "Hello", "subhead": "World"},
        ["dz-section-header", "<h2>Hello</h2>", '<p class="dz-subhead">World</p>'],
        id="generic-section-header",
    ),
    pytest.param(
        # Trusted pre-rendered HTML (the Jinja `| safe` filter).
        {"type": "generic", "content": "<p>Trusted <strong>HTML</strong></p>"},
        ["<p>Trusted <strong>HTML</strong></p>"],
        id="generic-content-is-trusted-html",
    ),
    # ── trust_bar ──
    pytest.param(
        {
            "type": "trust_bar",
            "items": [{"icon": "shield", "text": "SOC 2"}, {"icon": "lock", "text": "Encrypted"}],
        },
        ['data-lucide="shield"', ">SOC 2<", 'data-lucide="lock"'],
        id="trust-bar-items-with-icons",
    ),
    pytest.param(
        {"type": "trust_bar", "items": [{"text": "Just text"}]},
        [">Just text<"],
        id="trust-bar-text-only-item",
    ),
    # ── value_highlight ──
    pytest.param(
        {"type": "value_highlight", "headline": "Big"},
        ['<h2 class="dz-value-headline">Big</h2>'],
        id="value-highlight-headline",
    ),
    pytest.param(
        {"type": "value_highlight", "headline": "H", "subhead": "S", "body": "B"},
        ['<p class="dz-subhead">S</p>', '<p class="dz-value-body">B</p>'],
        id="value-highlight-subhead-and-body",
    ),
    # ── logo_cloud ──
    pytest.param(
        {
            "type": "logo_cloud",
            "items": [
                {"name": "Acme", "src": "/acme.png", "href": "https://acme.com"},
                {"name": "Beta", "src": "/beta.png", "href": "https://beta.com"},
            ],
        },
        [
            "dz-logos-grid",
            'href="https://acme.com"',
            'src="/acme.png"',
            'alt="Acme"',
            'title="Acme"',
        ],
        id="logo-cloud-anchor-per-item",
    ),
    pytest.param(
        {"type": "logo_cloud", "headline": "Trusted by", "items": []},
        ["dz-section-header", ">Trusted by<"],
        id="logo-cloud-section-header",
    ),
    # ── markdown ──
    pytest.param(
        {"type": "markdown", "content": "<h2>Title</h2><p>Body with <em>emphasis</em></p>"},
        ["<h2>Title</h2>", "<em>emphasis</em>"],
        id="markdown-content-is-trusted-html",
    ),
    pytest.param(
        {"type": "markdown"},
        ['class="dz-section-content prose max-w-none"'],
        id="markdown-missing-content-still-emits-content-slot",
    ),
    # ── stats (#1113: Dazzle-native grid, not DaisyUI `stats`) ──
    pytest.param({"type": "stats"}, ['class="dz-stats-grid"'], id="stats-native-grid-1113"),
    pytest.param(
        {
            "type": "stats",
            "items": [
                {"value": "99.9%", "label": "Uptime"},
                {"value": "<1ms", "label": "p50 latency"},
            ],
        },
        [">99.9%<", ">Uptime<", "&lt;1ms", ">p50 latency<"],
        id="stats-value-and-label",
    ),
    # ── steps ──
    pytest.param({"type": "steps"}, ["dz-section-steps-list"], id="steps-list-wrapper"),
    # ── comparison ──
    pytest.param({"type": "comparison"}, ["dz-comparison-table"], id="comparison-table-wrapper"),
    pytest.param(
        {
            "type": "comparison",
            "columns": [{"label": "Free"}, {"label": "Pro", "highlighted": True}],
        },
        ["<th></th>", "<th>Free</th>", '<th class="dz-comparison-highlighted">Pro</th>'],
        id="comparison-columns-in-thead",
    ),
    pytest.param(
        {
            "type": "comparison",
            "columns": [{"label": "A"}, {"label": "B", "highlighted": True}],
            "items": [{"feature": "API access", "cells": ["✓", "✓"]}],
        },
        [">API access<", '<td class="dz-comparison-highlighted">'],
        id="comparison-highlighted-column-cells",
    ),
    # ── split_content ──
    pytest.param(
        {"type": "split_content", "alignment": "right"},
        ["dz-split--reversed"],
        id="split-content-right-reverses",
    ),
    pytest.param(
        {
            "type": "split_content",
            "headline": "Big idea",
            "body": "Long-form copy",
            "primary_cta": {"label": "Read", "href": "/r"},
        },
        ["<h2>Big idea</h2>", "<p>Long-form copy</p>", "dz-cta-group--left", 'href="/r"'],
        id="split-content-text-body-and-cta",
    ),
    pytest.param(
        {
            "type": "split_content",
            "headline": "Hi",
            "media": {"kind": "image", "src": "/x.png", "alt": "X"},
        },
        ["dz-split-media", 'src="/x.png"'],
        id="split-content-image-media",
    ),
    # ── card_grid ──
    pytest.param({"type": "card_grid"}, ["dz-card-grid"], id="card-grid-wrapper"),
    pytest.param(
        {
            "type": "card_grid",
            "items": [{"title": "Plan", "body": "Details", "cta": {"label": "Pick", "href": "/p"}}],
        },
        ['href="/p"', ">Pick<"],
        id="card-grid-per-item-cta",
    ),
    pytest.param(
        {"type": "card_grid", "media": {"kind": "image", "src": "/banner.png", "alt": "Banner"}},
        ["dz-section-media", 'src="/banner.png"'],
        id="card-grid-section-media",
    ),
    # ── team ──
    pytest.param({"type": "team"}, ["dz-team-grid"], id="team-grid-wrapper"),
    pytest.param(
        {"type": "team", "items": [{"name": "Bob Builder"}]},
        ["dz-team-initials", ">BB<"],
        id="team-initials-fallback",
    ),
    pytest.param(
        {"type": "team", "items": [{"name": "Anne Marie de Beaufort"}]},
        [">AM<"],
        id="team-initials-from-first-two-words",
    ),
    pytest.param(
        {"type": "team", "items": [{}]}, [">?<"], id="team-member-without-name-is-question-mark"
    ),
    pytest.param(
        {"type": "team", "items": [{"name": "X", "role": "Engineer", "bio": "Builds things"}]},
        ["dz-team-role", "dz-team-bio"],
        id="team-role-and-bio",
    ),
    pytest.param(
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
                        {"type": "blog", "href": "https://b/x"},
                    ],
                }
            ],
        },
        [
            'data-lucide="linkedin"',
            'data-lucide="mail"',
            'data-lucide="twitter"',
            'data-lucide="github"',
            'data-lucide="globe"',
        ],
        id="team-link-icons-email-is-mail-unknown-is-globe",
    ),
    pytest.param(
        {
            "type": "team",
            "items": [{"name": "X", "links": [{"type": "linkedin", "href": "https://li/x"}]}],
        },
        ['target="_blank"', 'rel="noopener"'],
        id="team-external-links-are-noopener",
    ),
    # ── testimonials ──
    pytest.param(
        {"type": "testimonials"}, ["dz-testimonials-grid"], id="testimonials-grid-wrapper"
    ),
    pytest.param(
        {
            "type": "testimonials",
            "items": [{"quote": "Best product ever", "name": "Alice", "role": "CEO"}],
        },
        [
            '<blockquote>"Best product ever"</blockquote>',
            "<strong>Alice</strong>",
            "<span>CEO</span>",
        ],
        id="testimonials-quote-name-and-role",
    ),
    # ── features ──
    pytest.param({"type": "features"}, ["dz-features-grid"], id="features-grid-wrapper"),
    pytest.param(
        {
            "type": "features",
            "items": [
                {"icon": "shield", "title": "Secure", "body": "TLS 1.3"},
                {"icon": "zap", "title": "Fast", "body": "p50 < 10ms"},
            ],
        },
        ['data-lucide="shield"', 'data-lucide="zap"', "<h3>Secure</h3>", "<h3>Fast</h3>"],
        id="features-items-with-icons",
    ),
    pytest.param(
        {"type": "features", "headline": "Why us", "items": []},
        ["dz-section-header", ">Why us<"],
        id="features-section-header",
    ),
    pytest.param(
        {"type": "features", "media": {"kind": "image", "src": "/banner.png", "alt": "B"}},
        ["dz-section-media", 'src="/banner.png"'],
        id="features-section-media",
    ),
    # ── pricing ──
    pytest.param({"type": "pricing"}, ["dz-pricing-grid"], id="pricing-grid-wrapper"),
    pytest.param(
        {
            "type": "pricing",
            "tiers": [{"name": "Free", "price": "$0"}, {"name": "Pro", "price": "$9"}],
        },
        ["<h3>Free</h3>", "<h3>Pro</h3>"],
        id="pricing-tier-names",
    ),
    pytest.param(
        {"type": "pricing", "tiers": [{"name": "X", "price": "$5"}]},
        [">/month<"],
        id="pricing-period-defaults-to-per-month",
    ),
    pytest.param(
        {"type": "pricing", "tiers": [{"name": "X", "price": "$50", "period": "/year"}]},
        [">/year<"],
        id="pricing-period-override",
    ),
    pytest.param(
        {
            "type": "pricing",
            "tiers": [
                {"name": "Free", "price": "$0"},
                {"name": "Pro", "price": "$9", "highlighted": True},
            ],
        },
        ["dz-pricing-highlighted"],
        id="pricing-highlighted-tier-modifier",
    ),
    pytest.param(
        {
            "type": "pricing",
            "tiers": [{"name": "X", "price": "$1", "features": ["First", "Second", "Third"]}],
        },
        ["<li>First</li>", "<li>Second</li>", "<li>Third</li>"],
        id="pricing-features-as-li",
    ),
    pytest.param(
        {"type": "pricing", "tiers": [{"name": "X", "price": "$1", "cta": {"href": "/x"}}]},
        [">Choose Plan<"],
        id="pricing-cta-default-label",
    ),
    # ── faq ──
    pytest.param({"type": "faq"}, ["dz-faq-list"], id="faq-list-wrapper"),
    pytest.param(
        {
            "type": "faq",
            "items": [
                {"question": "How fast?", "answer": "Very fast."},
                {"question": "How secure?", "answer": "Very secure."},
            ],
        },
        ["<summary>How fast?</summary>", "<p>Very fast.</p>", "<summary>How secure?</summary>"],
        id="faq-native-details-summary",
    ),
    pytest.param(
        {"type": "faq", "headline": "Common questions", "items": []},
        ["dz-section-header", ">Common questions<"],
        id="faq-section-header",
    ),
    # ── #1110 Part B ──
    pytest.param(
        {
            "type": "social_proof_strip",
            "items": [
                {"count": "10,000+", "label": "active users", "icon": "users"},
                {"count": "$2M", "label": "ARR"},
            ],
        },
        ["10,000+", "active users", "$2M", 'data-lucide="users"'],
        id="social-proof-count-and-label",
    ),
    pytest.param(
        {
            "type": "integration_grid",
            "items": [
                {"name": "Slack", "logo": "/static/slack.svg", "href": "/integrations/slack"},
                {"name": "GitHub", "logo": "/static/gh.svg"},
            ],
        },
        ["Slack", 'href="/integrations/slack"', "GitHub", 'src="/static/slack.svg"'],
        id="integration-grid-tiles",
    ),
    pytest.param(
        {
            "type": "compliance_badge_row",
            "badges": [
                {
                    "label": "SOC 2 Type II",
                    "logo": "/static/soc2.svg",
                    "tooltip": "Audited annually since 2024.",
                }
            ],
        },
        ["SOC 2 Type II", "Audited annually since 2024.", "dz-compliance-tooltip"],
        id="compliance-badge-string-tooltip",
    ),
    pytest.param(
        {
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
        },
        [
            "EU data residency available on request.",
            'href="/trust/gdpr"',
            ">Read more<",
            "dz-compliance-tooltip-link",
        ],
        id="compliance-badge-object-tooltip-with-link",
    ),
    pytest.param(
        {
            "type": "compliance_badge_row",
            "badges": [
                {
                    "label": "GDPR Ready",
                    "logo": "/x.svg",
                    "tooltip": {"body": "x", "link": "/trust/gdpr"},
                }
            ],
        },
        ["Learn more"],
        id="compliance-badge-tooltip-link-text-defaults-to-learn-more",
    ),
    pytest.param(
        {
            "type": "before_after_comparison",
            "before": {
                "headline": "The old way",
                "items": ["3 tools", "5 logins", "manual reconciliation"],
            },
            "after": {"headline": "The new way", "items": ["1 tool", "1 login", "automated"]},
        },
        [
            "The old way",
            "The new way",
            "3 tools",
            "automated",
            "dz-before-after-before",
            "dz-before-after-after",
        ],
        id="before-after-two-columns",
    ),
    pytest.param(
        {
            "type": "mid_page_cta_band",
            "headline": "Ready to scale?",
            "subhead": "Start free, upgrade when you're ready.",
            "cta": {"label": "Start now", "href": "/signup"},
        },
        ["Ready to scale?", "Start free", 'href="/signup"', "Start now"],
        id="mid-page-cta-band-headline-subhead-and-cta",
    ),
    pytest.param(
        {"type": "mid_page_cta_band", "headline": "Standalone callout"},
        ["Standalone callout"],
        id="mid-page-cta-band-without-cta",
    ),
]


@pytest.mark.parametrize(("section", "fragments"), RENDERS)
def test_renders(section: dict, fragments: list[str]) -> None:
    out = render_typed_section(section)
    for fragment in fragments:
        assert fragment in out


OMITS = [
    pytest.param(
        {"type": "hero", "headline": "Hi"},
        ["dz-subhead", "dz-cta-group"],
        id="hero-no-subhead-no-ctas",
    ),
    pytest.param(
        {"type": "hero", "headline": "Hi", "primary_cta": {}, "secondary_cta": {}},
        ["dz-cta-group"],
        id="hero-empty-cta-dicts-skip",
    ),
    pytest.param(
        {"type": "hero", "headline": "Hi", "media": {"kind": "video", "src": "/v.mp4"}},
        ["dz-hero-with-media", "dz-hero-media"],
        id="hero-non-image-media",
    ),
    pytest.param(
        {"type": "hero", "headline": "Hi", "media": {"kind": "image"}},
        ["dz-hero-with-media"],
        id="hero-image-media-without-src",
    ),
    pytest.param({"type": "hero"}, [" id="], id="hero-no-id-without-id-or-headline"),
    pytest.param({"type": "cta"}, ["<h2>", "dz-subhead", "dz-cta-group"], id="cta-bare"),
    pytest.param(
        {"type": "generic"}, ["dz-section-header"], id="generic-no-header-without-headline"
    ),
    pytest.param({"type": "trust_bar"}, ["dz-trust-item"], id="trust-bar-empty-items"),
    pytest.param(
        {"type": "trust_bar", "items": [{"text": "Just text"}]},
        ["data-lucide"],
        id="trust-bar-no-icon",
    ),
    pytest.param(
        # value_highlight has no secondary CTA, unlike hero/cta.
        {
            "type": "value_highlight",
            "headline": "H",
            "primary_cta": {"label": "Go", "href": "/g"},
            "secondary_cta": {"label": "Docs", "href": "/d"},
        },
        ['data-dz-variant="outline"'],
        id="value-highlight-ignores-secondary-cta",
    ),
    pytest.param(
        {"type": "value_highlight", "headline": "H"},
        ["dz-subhead", "dz-value-body", "dz-cta-group"],
        id="value-highlight-bare",
    ),
    pytest.param({"type": "stats"}, ['class="dz-stat"'], id="stats-empty-items"),
    pytest.param(
        {"type": "steps", "items": [{"title": "Only", "body": "step"}]},
        ["dz-step-connector", "is-not-last"],
        id="steps-single-item-no-connector",
    ),
    pytest.param(
        {"type": "split_content"}, ["dz-split--reversed"], id="split-content-default-not-reversed"
    ),
    pytest.param(
        {"type": "split_content", "headline": "Hi", "media": {"kind": "video"}},
        ["dz-split-media"],
        id="split-content-non-image-media",
    ),
    pytest.param(
        {"type": "team", "items": [{"name": "Alice Wong", "role": "CEO", "image": "/alice.jpg"}]},
        ["dz-team-initials"],
        id="team-no-initials-when-image",
    ),
    pytest.param(
        {"type": "testimonials", "items": [{"quote": "x", "name": "A"}]},
        ["<span>"],
        id="testimonials-no-role",
    ),
    pytest.param(
        {"type": "features", "items": [{"title": "Plain", "body": "No icon"}]},
        ["data-lucide"],
        id="features-no-icon",
    ),
    pytest.param(
        {"type": "pricing", "tiers": [{"name": "X", "price": "$1"}]},
        ["dz-button"],
        id="pricing-no-cta",
    ),
    pytest.param({"type": "faq"}, ["<details"], id="faq-empty-items"),
    pytest.param(
        {
            "type": "compliance_badge_row",
            "badges": [{"label": "SOC 2", "logo": "/s.svg", "tooltip": "Plain string."}],
        },
        ["dz-compliance-tooltip-link"],
        id="compliance-badge-string-tooltip-has-no-link",
    ),
    pytest.param(
        {
            "type": "compliance_badge_row",
            "badges": [{"label": "ISO 27001", "logo": "/static/iso.svg"}],
        },
        ["dz-compliance-tooltip"],
        id="compliance-badge-without-tooltip",
    ),
    # A malformed tooltip (typo'd shape) renders no tooltip, never crashes the page.
    *[
        pytest.param(
            {
                "type": "compliance_badge_row",
                "badges": [{"label": "ISO", "logo": "/i.svg", "tooltip": bad}],
            },
            ["dz-compliance-tooltip"],
            id=f"compliance-badge-malformed-tooltip-{name}",
        )
        for name, bad in [
            ("empty-string", ""),
            ("list", [1, 2, 3]),
            ("int", 42),
            ("empty-body-dict", {"body": ""}),
        ]
    ],
    pytest.param(
        {"type": "before_after_comparison", "before": {"headline": "Old", "items": ["a"]}},
        ["dz-before-after-after"],
        id="before-after-missing-after-column",
    ),
]


@pytest.mark.parametrize(("section", "fragments"), OMITS)
def test_omits(section: dict, fragments: list[str]) -> None:
    out = render_typed_section(section)
    for fragment in fragments:
        assert fragment not in out


COUNTS = [
    pytest.param(
        {
            "type": "trust_bar",
            "items": [{"icon": "shield", "text": "SOC 2"}, {"icon": "lock", "text": "Encrypted"}],
        },
        "dz-trust-item",
        2,
        id="trust-bar-item-per-entry",
    ),
    pytest.param(
        {
            "type": "logo_cloud",
            "items": [{"name": "A", "src": "/a.png"}, {"name": "B", "src": "/b.png"}],
        },
        "dz-logo-item",
        2,
        id="logo-cloud-item-per-entry",
    ),
    *[
        pytest.param(
            {
                "type": "stats",
                "items": [{"value": "1", "label": "a"}, {"value": "2", "label": "b"}],
            },
            marker,
            2,
            id=f"stats-{name}-per-item",
        )
        for name, marker in [
            ("stat", 'class="dz-stat"'),
            ("value", 'class="dz-stat-value"'),
            ("title", 'class="dz-stat-title"'),
        ]
    ],
    # One connector and one is-not-last for two steps: every item but the last.
    pytest.param(
        {"type": "steps", "items": [{"title": "A"}, {"title": "B"}]},
        "dz-step-connector",
        1,
        id="steps-connector",
    ),
    pytest.param(
        {"type": "steps", "items": [{"title": "A"}, {"title": "B"}]},
        "is-not-last",
        1,
        id="steps-not-last",
    ),
    pytest.param(
        {
            "type": "comparison",
            "columns": [{"label": "A"}],
            "items": [{"feature": "API", "cells": ["1"]}, {"feature": "Support", "cells": ["2"]}],
        },
        "dz-comparison-feature",
        2,
        id="comparison-row-per-item",
    ),
    pytest.param(
        # Defensive: cells beyond the declared columns still render.
        {
            "type": "comparison",
            "columns": [{"label": "A"}],
            "items": [{"feature": "x", "cells": ["1", "2", "3"]}],
        },
        "<td>",
        3,
        id="comparison-extra-cells-render",
    ),
    pytest.param(
        {"type": "card_grid", "items": [{"icon": "shield", "title": "Secure"}, {"title": "Fast"}]},
        "dz-card-item",
        2,
        id="card-grid-card-per-item",
    ),
    pytest.param(
        {"type": "card_grid", "items": [{"icon": "shield", "title": "Secure"}, {"title": "Fast"}]},
        "dz-card-icon",
        1,
        id="card-grid-icon-only-when-set",
    ),
    pytest.param(
        {"type": "features", "items": [{"title": "A"}, {"title": "B"}]},
        "dz-feature-item",
        2,
        id="features-item-per-entry",
    ),
    pytest.param(
        {
            "type": "pricing",
            "tiers": [{"name": "Free", "price": "$0"}, {"name": "Pro", "price": "$9"}],
        },
        "dz-pricing-tier",
        2,
        id="pricing-tier-per-entry",
    ),
    pytest.param(
        {
            "type": "pricing",
            "tiers": [{"name": "X", "price": "$1", "features": ["First", "Second", "Third"]}],
        },
        "<li>",
        3,
        id="pricing-li-per-feature",
    ),
    pytest.param(
        {
            "type": "faq",
            "items": [{"question": "a", "answer": "b"}, {"question": "c", "answer": "d"}],
        },
        '<details class="dz-faq-item">',
        2,
        id="faq-details-per-item",
    ),
]


@pytest.mark.parametrize(("section", "marker", "expected"), COUNTS)
def test_counts(section: dict, marker: str, expected: int) -> None:
    assert render_typed_section(section).count(marker) == expected


ORDER = [
    pytest.param(
        {
            "type": "hero",
            "headline": "Hi",
            "primary_cta": {"label": "Start", "href": "/s"},
            "secondary_cta": {"label": "Learn", "href": "/l"},
        },
        ['data-dz-variant="primary"', 'data-dz-variant="outline"'],
        id="hero-primary-cta-before-secondary",
    ),
    pytest.param(
        {"type": "steps", "items": [{"title": "First"}, {"title": "Second"}, {"title": "Third"}]},
        [">1<", ">2<", ">3<"],
        id="steps-numbered-from-one",
    ),
]


@pytest.mark.parametrize(("section", "fragments"), ORDER)
def test_order(section: dict, fragments: list[str]) -> None:
    out = render_typed_section(section)
    positions = [out.index(fragment) for fragment in fragments]
    assert positions == sorted(positions)


def _variant_before(out: str, label: str) -> str:
    """The ``data-dz-variant`` of the CTA anchor whose text is ``label``."""
    anchor_start = out.rindex("<a ", 0, out.index(f">{label}<"))
    anchor = out[anchor_start : out.index(f">{label}<")]
    return anchor.split('data-dz-variant="', 1)[1].split('"', 1)[0]


@pytest.mark.parametrize(
    ("tier", "variant"),
    [
        # #1263: the highlighted tier's CTA defaults to primary; others recede to outline.
        pytest.param(
            {"name": "Free", "price": "$0"}, "outline", id="plain-tier-defaults-outline-1263"
        ),
        pytest.param(
            {"name": "Pro", "price": "$9", "highlighted": True},
            "primary",
            id="highlighted-defaults-primary-1263",
        ),
        # An explicit cta.variant wins in both directions.
        pytest.param(
            {"name": "Free", "price": "$0", "variant": "primary"},
            "primary",
            id="override-plain-to-primary-1263",
        ),
        pytest.param(
            {"name": "Pro", "price": "$9", "highlighted": True, "variant": "outline"},
            "outline",
            id="override-highlighted-to-outline-1263",
        ),
        pytest.param(
            {"name": "Ent", "price": "Custom", "variant": "ghost"},
            "ghost",
            id="override-ghost-1263",
        ),
    ],
)
def test_pricing_cta_variant(tier: dict, variant: str) -> None:
    cta = {"label": "Pick", "href": "/p"}
    if "variant" in tier:
        cta["variant"] = tier.pop("variant")
    decoy = {"name": "Other", "price": "$1", "cta": {"label": "Decoy", "href": "/d"}}
    out = render_typed_section({"type": "pricing", "tiers": [decoy, {**tier, "cta": cta}]})
    assert _variant_before(out, "Pick") == variant


# User-supplied strings are HTML-escaped: each hostile payload is one row.
ESCAPES = [
    pytest.param(
        {"type": "hero", "headline": "<script>alert(1)</script>"},
        ["<script>"],
        ["&lt;script&gt;"],
        id="hero-headline",
    ),
    pytest.param(
        {"type": "hero", "headline": "Hi", "subhead": "<img src=x>"},
        ["<img"],
        ["&lt;img"],
        id="hero-subhead",
    ),
    pytest.param(
        # The href quote-break must become &quot; — unescaped it would close the
        # attribute and inject a script tag.
        {
            "type": "hero",
            "headline": "Hi",
            "primary_cta": {"label": "<script>", "href": '"><script>x</script>'},
        },
        ["<script>"],
        ["&lt;script&gt;", "&quot;&gt;&lt;script&gt;"],
        id="hero-cta-label-and-href-attribute-break",
    ),
    pytest.param(
        {
            "type": "hero",
            "headline": "Hi",
            "media": {"kind": "image", "src": '"><svg/onload=alert(1)>', "alt": '"><img src=x>'},
        },
        ["<svg", "<img src=x>"],
        ["&quot;&gt;&lt;svg", "&quot;&gt;&lt;img"],
        id="hero-media-src-and-alt-attribute-break",
    ),
    pytest.param(
        {"type": "hero", "id": '"><script>', "headline": "Hi"},
        ['"><script>'],
        [],
        id="hero-explicit-id",
    ),
    pytest.param(
        {
            "type": "cta",
            "headline": "<script>",
            "subhead": "<img src=x>",
            "primary_cta": {"label": "<svg>", "href": '"><x>'},
        },
        ["<script>", "<img", "<svg>", '"><x>'],
        ["&lt;script&gt;"],
        id="cta-headline-subhead-and-cta",
    ),
    pytest.param(
        {"type": "trust_bar", "items": [{"icon": '"><script>', "text": "<svg/>"}]},
        ["<script>", "<svg"],
        ["&lt;svg"],
        id="trust-bar-text-and-icon",
    ),
    pytest.param(
        {"type": "logo_cloud", "items": [{"name": "<script>", "src": '"><svg>', "href": '"><x>'}]},
        ["<script>", "<svg>", '"><x>'],
        [],
        id="logo-cloud-name-src-href",
    ),
    pytest.param(
        {"type": "stats", "items": [{"value": "<1ms", "label": "<b>"}]},
        ["<1ms", "<b>"],
        ["&lt;1ms"],
        id="stats-value",
    ),
    pytest.param(
        {"type": "steps", "items": [{"title": "<script>", "body": "<img src=x>"}]},
        ["<script>", "<img"],
        [],
        id="steps-title-and-body",
    ),
    pytest.param(
        {
            "type": "comparison",
            "columns": [{"label": "<x>"}],
            "items": [{"feature": "<y>", "cells": ["<z>"]}],
        },
        ["<x>", "<y>", "<z>"],
        [],
        id="comparison-columns-features-cells",
    ),
    pytest.param(
        {
            "type": "testimonials",
            "items": [
                {"quote": "<script>alert(1)</script>", "name": "<img src=x>", "role": "<svg/>"}
            ],
        },
        ["<script>", "<img ", "<svg/>"],
        [],
        id="testimonials-quote-name-role",
    ),
    pytest.param(
        {
            "type": "features",
            "items": [{"icon": '"><script>', "title": "<svg/>", "body": "<img src=x>"}],
        },
        ["<script>", "<svg/>", "<img "],
        [],
        id="features-icon-title-body",
    ),
    pytest.param(
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
        },
        ["<script>", "<svg/>", "<img>", "<x>", "<y>", '"><z>'],
        [],
        id="pricing-tier-fields",
    ),
    pytest.param(
        {
            "type": "faq",
            "items": [
                {"question": "<script>alert(1)</script>", "answer": "<img src=x onerror=alert(1)>"}
            ],
        },
        ["<script>", "<img "],
        ["&lt;script&gt;"],
        id="faq-question-and-answer",
    ),
    pytest.param(
        {"type": "social_proof_strip", "items": [{"count": "<script>", "label": "</section><b>"}]},
        ["<script>", "<b>"],
        ["&lt;script&gt;"],
        id="social-proof-count-and-label",
    ),
]


@pytest.mark.parametrize(("section", "forbidden", "escaped"), ESCAPES)
def test_escapes_user_content(section: dict, forbidden: list[str], escaped: list[str]) -> None:
    out = render_typed_section(section)
    for raw in forbidden:
        assert raw not in out
    for fragment in escaped:
        assert fragment in out
    # A payload can never close the section early: exactly one wrapper.
    assert out.count("</section>") == 1
