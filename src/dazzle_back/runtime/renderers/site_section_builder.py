"""Issue #1037 (v0.67.25+): typed-Fragment renderers for sitespec
section types.

Each builder consumes a section dict (already shaped at sitespec
parse time) and returns a pre-rendered HTML string. The chrome-on
sitespec route assembles the inner body from these builders for
migrated section types and falls back to the Jinja partial for
unmigrated types — see `site_routes._render_site_page_chromed`.

Migrated section types per ship:
    v0.67.25: hero

Section migration sequencing (per CHANGELOG agent guidance for
v0.67.24): start with hero (single block) and footer (columns +
disclaimer); pricing-table and faq are largest, defer until last.

Each builder is a pure function — no DB query, no per-request
state. HTML escaping is the builder's responsibility for any
user-supplied field; class names + attribute structure pass
through verbatim from the Jinja templates so visual parity holds.
"""

from __future__ import annotations

import html as _html
import re as _re
from typing import Any

# Section types this module knows how to render via the typed path.
# Unmigrated types fall through to their Jinja partials in the
# chrome-on sitespec render. The set is read from the wiring layer
# (site_routes._render_site_page_chromed) — keep in lockstep.
TYPED_SECTION_TYPES: frozenset[str] = frozenset(
    {
        "hero",
        "cta",
        "generic",
        "trust_bar",
        "value_highlight",
        "logo_cloud",
        "markdown",
    }
)


def render_typed_section(section: dict[str, Any]) -> str:
    """Dispatch to the right builder for a typed-section dict.

    Raises KeyError when the section type isn't in
    `TYPED_SECTION_TYPES` — callers should check membership first
    and fall through to the Jinja partial when the type isn't
    registered."""
    section_type = str(section.get("type", "") or "")
    if section_type == "hero":
        return _build_hero_section(section)
    if section_type == "cta":
        return _build_cta_section(section)
    if section_type == "generic":
        return _build_generic_section(section)
    if section_type == "trust_bar":
        return _build_trust_bar_section(section)
    if section_type == "value_highlight":
        return _build_value_highlight_section(section)
    if section_type == "logo_cloud":
        return _build_logo_cloud_section(section)
    if section_type == "markdown":
        return _build_markdown_section(section)
    raise KeyError(f"No typed builder for section type {section_type!r}")


def _slugify(value: str) -> str:
    """Mirror the `slugify` Jinja filter used by `_helpers.html`'s
    `section_id_attr` macro. Lowercase, replace non-alphanumeric
    runs with single hyphen, strip trailing/leading hyphens.

    This is a minimal port — the full Jinja filter implementation
    lives in `template_renderer.py`. Keep the contract identical so
    `<section id="...">` attrs match the Jinja-rendered output."""
    if not value:
        return ""
    s = _re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return s


def _section_id_attr(section: dict[str, Any]) -> str:
    """Reproduce the `section_id_attr` macro from
    `site/sections/_helpers.html`. Returns either ` id="..."`
    (with leading space) or `""`."""
    section_id = section.get("id")
    if section_id:
        return f' id="{_html.escape(str(section_id), quote=True)}"'
    headline = section.get("headline")
    if headline:
        slug = _slugify(str(headline))
        if slug:
            return f' id="{_html.escape(slug, quote=True)}"'
    return ""


def _build_hero_section(section: dict[str, Any]) -> str:
    """Typed builder for `type: hero` sitespec sections.

    Mirrors `src/dazzle_ui/templates/site/sections/hero.html`
    byte-for-byte where field values match. Inputs:
      headline (str), subhead (str, optional),
      primary_cta ({label, href}, optional),
      secondary_cta ({label, href}, optional),
      media ({kind, src, alt}, optional, kind=='image' triggers
        the `.dz-hero-with-media` modifier class)
    """
    media = section.get("media") or {}
    has_media = isinstance(media, dict) and media.get("kind") == "image" and media.get("src")
    section_class = "dz-section dz-section-hero"
    if has_media:
        section_class += " dz-hero-with-media"

    parts: list[str] = []
    parts.append(f'<section{_section_id_attr(section)} class="{section_class}">')

    # Content block.
    content_inner: list[str] = []
    headline = str(section.get("headline", "") or "")
    content_inner.append(f'<h1 class="dz-hero-text">{_html.escape(headline)}</h1>')
    subhead = section.get("subhead")
    if subhead:
        content_inner.append(f'<p class="dz-subhead">{_html.escape(str(subhead))}</p>')

    primary_cta = section.get("primary_cta") or {}
    secondary_cta = section.get("secondary_cta") or {}
    if primary_cta or secondary_cta:
        cta_parts: list[str] = []
        if primary_cta:
            href = str(primary_cta.get("href", "#") or "#")
            label = str(primary_cta.get("label", "Get Started") or "Get Started")
            cta_parts.append(
                f'<a href="{_html.escape(href, quote=True)}" '
                f'class="dz-button dz-button-primary">'
                f"{_html.escape(label)}</a>"
            )
        if secondary_cta:
            href = str(secondary_cta.get("href", "#") or "#")
            label = str(secondary_cta.get("label", "Learn More") or "Learn More")
            cta_parts.append(
                f'<a href="{_html.escape(href, quote=True)}" '
                f'class="dz-button dz-button-outline">'
                f"{_html.escape(label)}</a>"
            )
        content_inner.append(f'<div class="dz-cta-group">{"".join(cta_parts)}</div>')

    parts.append(f'<div class="dz-section-content">{"".join(content_inner)}</div>')

    if has_media:
        src = str(media.get("src", "") or "")
        alt = str(media.get("alt", "") or "")
        parts.append(
            f'<div class="dz-hero-media">'
            f'<img src="{_html.escape(src, quote=True)}" '
            f'alt="{_html.escape(alt, quote=True)}" '
            f'class="dz-hero-image">'
            f"</div>"
        )

    parts.append("</section>")
    return "".join(parts)


def _section_header(section: dict[str, Any]) -> str:
    """Reproduce the `section_header` macro from `_helpers.html`.

    Emits a `<div class="dz-section-header">` with optional
    `<h2>{headline}</h2>` and `<p class="dz-subhead">{subhead}</p>`
    inside, OR empty string when both are absent."""
    headline = section.get("headline")
    subhead = section.get("subhead")
    if not headline and not subhead:
        return ""
    inner: list[str] = []
    if headline:
        inner.append(f"<h2>{_html.escape(str(headline))}</h2>")
    if subhead:
        inner.append(f'<p class="dz-subhead">{_html.escape(str(subhead))}</p>')
    return f'<div class="dz-section-header">{"".join(inner)}</div>'


def _build_cta_section(section: dict[str, Any]) -> str:
    """Typed builder for `type: cta` sitespec sections (#1037, v0.67.26).

    Subset of hero — no media, single content block. The class names
    + button composition (dz-button + dz-button-primary / -outline)
    match `cta.html` byte-for-byte."""
    parts: list[str] = []
    parts.append(f'<section{_section_id_attr(section)} class="dz-section dz-section-cta">')
    inner: list[str] = []
    headline = section.get("headline")
    if headline:
        inner.append(f"<h2>{_html.escape(str(headline))}</h2>")
    subhead = section.get("subhead")
    if subhead:
        inner.append(f'<p class="dz-subhead">{_html.escape(str(subhead))}</p>')
    primary_cta = section.get("primary_cta") or {}
    secondary_cta = section.get("secondary_cta") or {}
    if primary_cta or secondary_cta:
        cta_parts: list[str] = []
        if primary_cta:
            href = str(primary_cta.get("href", "#") or "#")
            label = str(primary_cta.get("label", "Get Started") or "Get Started")
            cta_parts.append(
                f'<a href="{_html.escape(href, quote=True)}" '
                f'class="dz-button dz-button-primary">'
                f"{_html.escape(label)}</a>"
            )
        if secondary_cta:
            href = str(secondary_cta.get("href", "#") or "#")
            label = str(secondary_cta.get("label", "Learn More") or "Learn More")
            cta_parts.append(
                f'<a href="{_html.escape(href, quote=True)}" '
                f'class="dz-button dz-button-outline">'
                f"{_html.escape(label)}</a>"
            )
        inner.append(f'<div class="dz-cta-group">{"".join(cta_parts)}</div>')
    parts.append(f'<div class="dz-section-content">{"".join(inner)}</div>')
    parts.append("</section>")
    return "".join(parts)


def _build_generic_section(section: dict[str, Any]) -> str:
    """Typed builder for `type: generic` sitespec sections.

    Section class is derived from the actual `type` value with
    underscores → hyphens (`my_block` → `dz-section-my-block`),
    matching the Jinja template's `replace('_', '-')` filter. The
    `content` field is rendered raw (`| safe` in Jinja) — sitespec
    authors who supply HTML content own the trust contract."""
    section_type = str(section.get("type", "unknown") or "unknown")
    section_class = f"dz-section dz-section-{section_type.replace('_', '-')}"
    parts: list[str] = []
    parts.append(
        f'<section{_section_id_attr(section)} class="{_html.escape(section_class, quote=True)}">'
    )
    inner: list[str] = []
    inner.append(_section_header(section))
    content = section.get("content")
    if content:
        # `| safe` parity — content is trusted (typically server-side
        # rendered Markdown).
        inner.append(f'<div class="prose max-w-none">{content}</div>')
    parts.append(f'<div class="dz-section-content">{"".join(inner)}</div>')
    parts.append("</section>")
    return "".join(parts)


def _build_trust_bar_section(section: dict[str, Any]) -> str:
    """Typed builder for `type: trust_bar` sitespec sections.

    Renders a horizontal strip of icon + text items. Each item:
    optional `icon` (lucide name), `text` (plain string)."""
    parts: list[str] = []
    parts.append(f'<section{_section_id_attr(section)} class="dz-section dz-section-trust-bar">')
    inner: list[str] = []
    inner.append(_section_header(section))
    items = list(section.get("items") or [])
    item_parts: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        item_inner: list[str] = []
        icon = item.get("icon")
        if icon:
            item_inner.append(f'<i data-lucide="{_html.escape(str(icon), quote=True)}"></i>')
        text = str(item.get("text", "") or "")
        item_inner.append(f"<span>{_html.escape(text)}</span>")
        item_parts.append(f'<div class="dz-trust-item">{"".join(item_inner)}</div>')
    inner.append(f'<div class="dz-trust-strip">{"".join(item_parts)}</div>')
    parts.append(f'<div class="dz-section-content">{"".join(inner)}</div>')
    parts.append("</section>")
    return "".join(parts)


def _build_value_highlight_section(section: dict[str, Any]) -> str:
    """Typed builder for `type: value_highlight` sitespec sections.

    Single highlight block — headline (h2 with `.dz-value-headline`),
    optional subhead, optional body paragraph (`.dz-value-body`),
    optional single primary CTA. No secondary CTA (deliberate vs
    hero/cta which support both)."""
    parts: list[str] = []
    parts.append(
        f'<section{_section_id_attr(section)} class="dz-section dz-section-value-highlight">'
    )
    inner: list[str] = []
    headline = str(section.get("headline", "") or "")
    inner.append(f'<h2 class="dz-value-headline">{_html.escape(headline)}</h2>')
    subhead = section.get("subhead")
    if subhead:
        inner.append(f'<p class="dz-subhead">{_html.escape(str(subhead))}</p>')
    body = section.get("body")
    if body:
        inner.append(f'<p class="dz-value-body">{_html.escape(str(body))}</p>')
    primary_cta = section.get("primary_cta") or {}
    if primary_cta:
        href = str(primary_cta.get("href", "#") or "#")
        label = str(primary_cta.get("label", "Get Started") or "Get Started")
        inner.append(
            f'<div class="dz-cta-group">'
            f'<a href="{_html.escape(href, quote=True)}" '
            f'class="dz-button dz-button-primary">'
            f"{_html.escape(label)}</a>"
            f"</div>"
        )
    parts.append(f'<div class="dz-section-content">{"".join(inner)}</div>')
    parts.append("</section>")
    return "".join(parts)


def _build_logo_cloud_section(section: dict[str, Any]) -> str:
    """Typed builder for `type: logo_cloud` sitespec sections.

    Grid of clickable logos. Each item: `name`, `src`, `href`."""
    parts: list[str] = []
    parts.append(f'<section{_section_id_attr(section)} class="dz-section dz-section-logo-cloud">')
    inner: list[str] = []
    inner.append(_section_header(section))
    items = list(section.get("items") or [])
    item_parts: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        href = str(item.get("href", "#") or "#")
        name = str(item.get("name", "") or "")
        src = str(item.get("src", "") or "")
        item_parts.append(
            f'<a href="{_html.escape(href, quote=True)}" '
            f'class="dz-logo-item" '
            f'title="{_html.escape(name, quote=True)}">'
            f'<img src="{_html.escape(src, quote=True)}" '
            f'alt="{_html.escape(name, quote=True)}"></a>'
        )
    inner.append(f'<div class="dz-logos-grid">{"".join(item_parts)}</div>')
    parts.append(f'<div class="dz-section-content">{"".join(inner)}</div>')
    parts.append("</section>")
    return "".join(parts)


def _build_markdown_section(section: dict[str, Any]) -> str:
    """Typed builder for `type: markdown` sitespec sections.

    Pre-rendered Markdown HTML lives in `content`. The Jinja
    template uses `| safe` — sitespec authors who supply this
    field own the trust contract."""
    content = section.get("content") or ""
    parts: list[str] = []
    parts.append(f'<section{_section_id_attr(section)} class="dz-section dz-section-markdown">')
    parts.append(f'<div class="dz-section-content prose max-w-none">{content}</div>')
    parts.append("</section>")
    return "".join(parts)
