"""
Site page renderer for DNR runtime.

Extracts HTML/JS template generation from combined_server.py for better maintainability.
Includes support for TaskContext injection when rendering surfaces as human tasks.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from dazzle_ui.runtime.task_context import TaskContext


def get_shared_head_html(title: str) -> str:
    """
    Return shared <head> content for all DNR pages.

    Provides unified styling between site pages and workspace pages by including
    the same DaisyUI + Tailwind CSS/JS as the workspace renderer.

    Args:
        title: Page title

    Returns:
        HTML string for the <head> section (without opening/closing tags)
    """
    return f"""<meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <link rel="icon" href="/static/assets/dazzle-favicon.svg" type="image/svg+xml">
    <!-- Inter font -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <!-- DaisyUI - semantic component classes (same as workspace) -->
    <link href="https://cdn.jsdelivr.net/npm/daisyui@5/daisyui.css" rel="stylesheet" type="text/css" />
    <!-- Tailwind Browser - minimal utilities for layout -->
    <script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
    <!-- DAZZLE design system layer -->
    <link rel="stylesheet" href="/styles/dazzle.css">
    <!-- Lucide icons for feature/section icons -->
    <script src="https://unpkg.com/lucide@0.468.0/dist/umd/lucide.min.js"></script>"""


def render_site_page_html(
    sitespec_data: dict[str, Any],
    path: str,
    page_data: dict[str, Any] | None = None,
) -> str:
    """
    Render a site page with server-side rendered content.

    When *page_data* is provided, sections are rendered into the initial HTML
    so that search engines and users with JS disabled see full content.  The
    ``site.js`` script is still included for theme toggling and Lucide icons.

    Args:
        sitespec_data: Site specification data.
        path: Current page route.
        page_data: Pre-resolved page data (sections, title, etc.) for SSR.

    Returns:
        Complete HTML page string.
    """
    brand = sitespec_data.get("brand", {})
    product_name = brand.get("product_name", "My App")
    layout = sitespec_data.get("layout", {})
    nav = layout.get("nav", {})
    auth_config = layout.get("auth") or {}
    footer = layout.get("footer", {})

    # Build nav HTML
    nav_items_html = _build_nav_items(nav, auth_config=auth_config)

    # Build footer HTML
    footer_html = _build_footer(footer)
    copyright_text = _build_copyright(footer, brand)

    # OG meta tags from page data
    og_meta = ""
    page_title = product_name
    page_description = ""
    if page_data:
        page_title = page_data.get("title") or product_name
        sections = page_data.get("sections", [])
        # Extract description from hero section subhead
        for sec in sections:
            if sec.get("type") == "hero":
                page_description = sec.get("subhead", "")
                break
        og_meta = _build_og_meta(product_name, page_title, page_description, path)

    # Render sections server-side
    if page_data and page_data.get("sections"):
        sections_html = _render_sections_ssr(page_data["sections"])
    else:
        sections_html = '<div class="dz-loading">Loading...</div>'

    return f"""<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
    {get_shared_head_html(page_title)}
    {og_meta}
</head>
<body class="dz-site bg-base-100">
    <header class="dz-site-header">
        <nav class="dz-site-nav">
            <a href="/" class="dz-site-logo">{product_name}</a>
            <div class="dz-nav-items">
                {nav_items_html}
            </div>
        </nav>
    </header>

    <main id="dz-site-main" data-route="{path}">
        {sections_html}
    </main>

    <footer class="dz-site-footer">
        <div class="dz-footer-content">
            {footer_html}
        </div>
        <div class="dz-footer-bottom">
            <p>{copyright_text}</p>
        </div>
    </footer>

    <script src="/site.js"></script>
</body>
</html>"""


def render_404_page_html(
    sitespec_data: dict[str, Any],
    path: str = "/",
) -> str:
    """
    Render a styled 404 page with site chrome (nav, footer).

    Args:
        sitespec_data: Site specification data
        path: The path that was not found

    Returns:
        Complete HTML page string
    """
    brand = sitespec_data.get("brand", {})
    product_name = brand.get("product_name", "My App")
    layout = sitespec_data.get("layout", {})
    nav = layout.get("nav", {})
    auth_config = layout.get("auth") or {}
    footer = layout.get("footer", {})

    nav_items_html = _build_nav_items(nav, auth_config=auth_config)
    footer_html = _build_footer(footer)
    copyright_text = _build_copyright(footer, brand)

    return f"""<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
    {get_shared_head_html(f"Page Not Found - {product_name}")}
</head>
<body class="dz-site bg-base-100">
    <header class="dz-site-header">
        <nav class="dz-site-nav">
            <a href="/" class="dz-site-logo">{product_name}</a>
            <div class="dz-nav-items">
                {nav_items_html}
            </div>
        </nav>
    </header>

    <main>
        <section class="dz-section dz-section-hero">
            <div class="dz-section-content dz-404-section">
                <h1 class="dz-404-headline">404</h1>
                <p class="dz-subhead">The page you're looking for doesn't exist.</p>
                <div class="dz-cta-group dz-404-cta">
                    <a href="/" class="btn btn-primary">Go Home</a>
                </div>
            </div>
        </section>
    </main>

    <footer class="dz-site-footer">
        <div class="dz-footer-content">
            {footer_html}
        </div>
        <div class="dz-footer-bottom">
            <p>{copyright_text}</p>
        </div>
    </footer>
</body>
</html>"""


def _build_nav_items(
    nav: dict[str, Any],
    auth_config: dict[str, Any] | None = None,
) -> str:
    """Build navigation items HTML.

    Args:
        nav: Navigation config with ``public`` (and optionally ``authenticated``) item lists.
        auth_config: Auth layout config (``primary_entry``, etc.) used to add a login CTA.
    """
    nav_items_html = ""
    # NavSpec model uses 'public' and 'authenticated' keys (not 'items')
    items = nav.get("public") or nav.get("items") or []
    for item in items:
        label = item.get("label", "")
        href = item.get("href", "#")
        # Use DaisyUI-compatible link styling
        nav_items_html += f'<a href="{href}" class="dz-nav-link">{label}</a>\n'

    # Add explicit CTA if present, otherwise derive from auth config
    cta = nav.get("cta")
    if cta:
        cta_label = cta.get("label", "Get Started")
        cta_href = cta.get("href", "/app")
        nav_items_html += f'<a href="{cta_href}" class="btn btn-primary btn-sm">{cta_label}</a>\n'
    elif auth_config:
        primary_entry = auth_config.get("primary_entry", "/login")
        label = "Sign In" if "login" in primary_entry else "Get Started"
        nav_items_html += f'<a href="{primary_entry}" class="btn btn-primary btn-sm">{label}</a>\n'

    # Add theme toggle button - use DaisyUI btn-ghost for consistency
    nav_items_html += """<button class="btn btn-ghost btn-sm btn-circle dz-theme-toggle" id="dz-theme-toggle" aria-label="Toggle dark mode" title="Toggle dark mode">
                <svg class="dz-theme-toggle__icon dz-theme-toggle__sun w-5 h-5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
                </svg>
                <svg class="dz-theme-toggle__icon dz-theme-toggle__moon w-5 h-5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
                </svg>
            </button>\n"""

    return nav_items_html


def _build_footer(footer: dict[str, Any]) -> str:
    """Build footer HTML."""
    footer_html = ""
    for col in footer.get("columns", []):
        col_title = col.get("title", "")
        footer_html += f'<div class="dz-footer-col"><h4>{col_title}</h4><ul>'
        for link in col.get("links", []):
            link_label = link.get("label", "")
            link_href = link.get("href", "#")
            footer_html += f'<li><a href="{link_href}">{link_label}</a></li>'
        footer_html += "</ul></div>"
    return footer_html


def _build_copyright(footer: dict[str, Any], brand: dict[str, Any]) -> str:
    """Build copyright/disclaimer text with template variable substitution."""
    product_name = brand.get("product_name", "My App")
    text = (
        footer.get("disclaimer")
        or footer.get("copyright")
        or f"\u00a9 {datetime.now(tz=UTC).year} {product_name}"
    )
    # Substitute template variables
    text = text.replace("{{year}}", str(datetime.now(tz=UTC).year))
    text = text.replace(
        "{{company_legal_name}}",
        brand.get("company_legal_name", product_name),
    )
    return text


def _build_og_meta(
    product_name: str,
    page_title: str,
    description: str,
    path: str,
) -> str:
    """Build Open Graph and basic SEO meta tags."""
    from html import escape

    desc = escape(description) if description else escape(product_name)
    title = escape(page_title)
    return f"""<meta name="description" content="{desc}">
    <meta property="og:title" content="{title}">
    <meta property="og:description" content="{desc}">
    <meta property="og:type" content="website">
    <meta name="twitter:card" content="summary">
    <meta name="twitter:title" content="{title}">
    <meta name="twitter:description" content="{desc}">"""


def _render_sections_ssr(sections: list[dict[str, Any]]) -> str:
    """Render page sections as server-side HTML.

    Mirrors the JavaScript renderers in ``get_site_js()`` to produce
    the same HTML structure, allowing search engines and no-JS users
    to see the full page content.
    """
    html_parts: list[str] = []
    for section in sections:
        sec_type = section.get("type", "")
        renderer = _SSR_RENDERERS.get(sec_type)
        if renderer:
            html_parts.append(renderer(section))
        else:
            # Fallback: render as generic section with headline/subhead
            html_parts.append(_ssr_generic(section))
    return "\n".join(html_parts)


def _ssr_section_id(section: dict[str, Any]) -> str:
    """Build an id attribute for a section element."""
    sec_id = section.get("id")
    if not sec_id:
        headline = section.get("headline", "")
        if headline:
            sec_id = headline.lower().replace(" ", "-")
            sec_id = "".join(c for c in sec_id if c.isalnum() or c == "-").strip("-")
    return f' id="{sec_id}"' if sec_id else ""


def _ssr_section_header(section: dict[str, Any]) -> str:
    """Render section header (headline + subhead)."""
    headline = section.get("headline", "")
    subhead = section.get("subhead", "")
    if not headline and not subhead:
        return ""
    parts = ['<div class="dz-section-header">']
    if headline:
        parts.append(f"<h2>{headline}</h2>")
    if subhead:
        parts.append(f'<p class="dz-subhead">{subhead}</p>')
    parts.append("</div>")
    return "\n".join(parts)


def _ssr_hero(section: dict[str, Any]) -> str:
    headline = section.get("headline", "")
    subhead = section.get("subhead", "")
    primary_cta = section.get("primary_cta")
    secondary_cta = section.get("secondary_cta")
    media = section.get("media")

    cta_html = ""
    if primary_cta:
        href = primary_cta.get("href", "#")
        label = primary_cta.get("label", "Get Started")
        cta_html += f'<a href="{href}" class="btn btn-primary">{label}</a>'
    if secondary_cta:
        href = secondary_cta.get("href", "#")
        label = secondary_cta.get("label", "Learn More")
        cta_html += f'<a href="{href}" class="btn btn-secondary btn-outline">{label}</a>'

    media_html = ""
    has_media = ""
    if media and media.get("kind") == "image" and media.get("src"):
        alt = media.get("alt", "")
        media_html = f'<div class="dz-hero-media"><img src="{media["src"]}" alt="{alt}" class="dz-hero-image"></div>'
        has_media = " dz-hero-with-media"

    return f"""<section{_ssr_section_id(section)} class="dz-section dz-section-hero{has_media}">
    <div class="dz-section-content">
        <h1 class="dz-hero-text">{headline}</h1>
        {'<p class="dz-subhead">' + subhead + "</p>" if subhead else ""}
        {'<div class="dz-cta-group">' + cta_html + "</div>" if cta_html else ""}
    </div>
    {media_html}
</section>"""


def _ssr_features(section: dict[str, Any]) -> str:
    items = section.get("items", [])
    items_html = ""
    for item in items:
        icon = item.get("icon", "")
        title = item.get("title", "")
        body = item.get("body", "")
        icon_html = f'<i data-lucide="{icon}"></i>' if icon else ""
        items_html += f"""<div class="dz-feature-item card bg-base-100 shadow-sm">
    <div class="card-body">
        {icon_html}
        <h3 class="card-title">{title}</h3>
        <p>{body}</p>
    </div>
</div>"""

    return f"""<section{_ssr_section_id(section)} class="dz-section dz-section-features">
    <div class="dz-section-content">
        {_ssr_section_header(section)}
        <div class="dz-features-grid">{items_html}</div>
    </div>
</section>"""


def _ssr_cta(section: dict[str, Any]) -> str:
    headline = section.get("headline", "")
    subhead = section.get("subhead", "")
    primary_cta = section.get("primary_cta")
    secondary_cta = section.get("secondary_cta")

    cta_html = ""
    if primary_cta:
        href = primary_cta.get("href", "#")
        label = primary_cta.get("label", "Get Started")
        cta_html += f'<a href="{href}" class="btn btn-primary">{label}</a>'
    if secondary_cta:
        href = secondary_cta.get("href", "#")
        label = secondary_cta.get("label", "Learn More")
        cta_html += f'<a href="{href}" class="btn btn-secondary btn-outline">{label}</a>'

    return f"""<section{_ssr_section_id(section)} class="dz-section dz-section-cta">
    <div class="dz-section-content">
        {"<h2>" + headline + "</h2>" if headline else ""}
        {'<p class="dz-subhead">' + subhead + "</p>" if subhead else ""}
        {'<div class="dz-cta-group">' + cta_html + "</div>" if cta_html else ""}
    </div>
</section>"""


def _ssr_faq(section: dict[str, Any]) -> str:
    items = section.get("items", [])
    items_html = ""
    for item in items:
        q = item.get("question", "")
        a = item.get("answer", "")
        items_html += f"""<div class="collapse collapse-arrow bg-base-200">
    <input type="radio" name="faq">
    <div class="collapse-title font-medium">{q}</div>
    <div class="collapse-content"><p>{a}</p></div>
</div>"""

    return f"""<section{_ssr_section_id(section)} class="dz-section dz-section-faq">
    <div class="dz-section-content">
        {_ssr_section_header(section)}
        <div class="dz-faq-list">{items_html}</div>
    </div>
</section>"""


def _ssr_stats(section: dict[str, Any]) -> str:
    items = section.get("items", [])
    items_html = ""
    for item in items:
        value = item.get("value", "")
        label = item.get("label", "")
        items_html += f"""<div class="stat">
    <div class="stat-value">{value}</div>
    <div class="stat-title">{label}</div>
</div>"""

    return f"""<section{_ssr_section_id(section)} class="dz-section dz-section-stats">
    <div class="dz-section-content">
        {_ssr_section_header(section)}
        <div class="stats stats-vertical lg:stats-horizontal shadow">{items_html}</div>
    </div>
</section>"""


def _ssr_steps(section: dict[str, Any]) -> str:
    items = section.get("items", [])
    items_html = ""
    for i, item in enumerate(items, 1):
        title = item.get("title", "")
        body = item.get("body", "")
        items_html += f"""<li class="step step-primary">
    <div class="dz-step-item">
        <span class="dz-step-number">{i}</span>
        <h3>{title}</h3>
        <p>{body}</p>
    </div>
</li>"""

    return f"""<section{_ssr_section_id(section)} class="dz-section dz-section-steps">
    <div class="dz-section-content">
        {_ssr_section_header(section)}
        <ul class="steps steps-vertical lg:steps-horizontal">{items_html}</ul>
    </div>
</section>"""


def _ssr_testimonials(section: dict[str, Any]) -> str:
    items = section.get("items", [])
    items_html = ""
    for item in items:
        quote = item.get("quote", "")
        name = item.get("name", "")
        role = item.get("role", "")
        items_html += f"""<div class="card bg-base-200">
    <div class="card-body">
        <p class="italic">"{quote}"</p>
        <p class="font-medium mt-2">{name}</p>
        {'<p class="text-sm opacity-70">' + role + "</p>" if role else ""}
    </div>
</div>"""

    return f"""<section{_ssr_section_id(section)} class="dz-section dz-section-testimonials">
    <div class="dz-section-content">
        {_ssr_section_header(section)}
        <div class="dz-testimonials-grid">{items_html}</div>
    </div>
</section>"""


def _ssr_pricing(section: dict[str, Any]) -> str:
    tiers = section.get("tiers", [])
    tiers_html = ""
    for tier in tiers:
        name = tier.get("name", "")
        price = tier.get("price", "")
        period = tier.get("period", "/month")
        features = tier.get("features", [])
        cta = tier.get("cta")
        highlighted = "border-primary" if tier.get("highlighted") else "border-base-300"

        features_html = "".join(f"<li>{f}</li>" for f in features)
        cta_html = ""
        if cta:
            href = cta.get("href", "#")
            label = cta.get("label", "Choose Plan")
            cta_html = f'<a href="{href}" class="btn btn-primary w-full">{label}</a>'

        tiers_html += f"""<div class="card bg-base-100 border-2 {highlighted}">
    <div class="card-body text-center">
        <h3 class="card-title justify-center">{name}</h3>
        <p class="text-3xl font-bold">{price}<span class="text-sm font-normal opacity-70">{period}</span></p>
        <ul class="dz-pricing-features text-left">{features_html}</ul>
        {cta_html}
    </div>
</div>"""

    return f"""<section{_ssr_section_id(section)} class="dz-section dz-section-pricing">
    <div class="dz-section-content">
        {_ssr_section_header(section)}
        <div class="dz-pricing-grid">{tiers_html}</div>
    </div>
</section>"""


def _ssr_markdown(section: dict[str, Any]) -> str:
    content = section.get("content", "")
    return f"""<section{_ssr_section_id(section)} class="dz-section dz-section-markdown">
    <div class="dz-section-content prose max-w-none">{content}</div>
</section>"""


def _ssr_card_grid(section: dict[str, Any]) -> str:
    items = section.get("items", [])
    cards_html = ""
    for item in items:
        icon = item.get("icon", "")
        title = item.get("title", "")
        body = item.get("body", "")
        cta = item.get("cta")

        icon_html = f'<div class="dz-card-icon"><i data-lucide="{icon}"></i></div>' if icon else ""
        cta_html = ""
        if cta:
            href = cta.get("href", "#")
            label = cta.get("label", "Learn More")
            cta_html = f'<a href="{href}" class="btn btn-primary btn-sm">{label}</a>'

        cards_html += f"""<div class="dz-card-item">
    {icon_html}
    <h3>{title}</h3>
    <p>{body}</p>
    {cta_html}
</div>"""

    return f"""<section{_ssr_section_id(section)} class="dz-section dz-section-card-grid">
    <div class="dz-section-content">
        {_ssr_section_header(section)}
        <div class="dz-card-grid">{cards_html}</div>
    </div>
</section>"""


def _ssr_split_content(section: dict[str, Any]) -> str:
    headline = section.get("headline", "")
    body = section.get("body", "")
    media = section.get("media")
    primary_cta = section.get("primary_cta")
    alignment = section.get("alignment", "left")

    cta_html = ""
    if primary_cta:
        href = primary_cta.get("href", "#")
        label = primary_cta.get("label", "Learn More")
        cta_html = f'<div class="dz-cta-group dz-cta-group--left"><a href="{href}" class="btn btn-primary">{label}</a></div>'

    media_html = ""
    if media and media.get("kind") == "image" and media.get("src"):
        alt = media.get("alt", "")
        media_html = f'<div class="dz-split-media"><img src="{media["src"]}" alt="{alt}" /></div>'

    order_cls = " dz-split--reversed" if alignment == "right" else ""

    return f"""<section{_ssr_section_id(section)} class="dz-section dz-section-split-content{order_cls}">
    <div class="dz-section-content dz-split-grid">
        <div class="dz-split-text">
            <h2>{headline}</h2>
            {f"<p>{body}</p>" if body else ""}
            {cta_html}
        </div>
        {media_html}
    </div>
</section>"""


def _ssr_trust_bar(section: dict[str, Any]) -> str:
    items = section.get("items", [])
    items_html = ""
    for item in items:
        icon = item.get("icon", "")
        text = item.get("text", "")
        icon_html = f'<i data-lucide="{icon}"></i>' if icon else ""
        items_html += f"""<div class="dz-trust-item">
    {icon_html}
    <span>{text}</span>
</div>"""

    return f"""<section{_ssr_section_id(section)} class="dz-section dz-section-trust-bar">
    <div class="dz-section-content">
        {_ssr_section_header(section)}
        <div class="dz-trust-strip">{items_html}</div>
    </div>
</section>"""


def _ssr_value_highlight(section: dict[str, Any]) -> str:
    headline = section.get("headline", "")
    subhead = section.get("subhead", "")
    body = section.get("body", "")
    primary_cta = section.get("primary_cta")

    cta_html = ""
    if primary_cta:
        href = primary_cta.get("href", "#")
        label = primary_cta.get("label", "Get Started")
        cta_html = (
            f'<div class="dz-cta-group"><a href="{href}" class="btn btn-primary">{label}</a></div>'
        )

    return f"""<section{_ssr_section_id(section)} class="dz-section dz-section-value-highlight">
    <div class="dz-section-content">
        <h2 class="dz-value-headline">{headline}</h2>
        {f'<p class="dz-subhead">{subhead}</p>' if subhead else ""}
        {f'<p class="dz-value-body">{body}</p>' if body else ""}
        {cta_html}
    </div>
</section>"""


def _ssr_logo_cloud(section: dict[str, Any]) -> str:
    items = section.get("items", [])
    items_html = ""
    for item in items:
        name = item.get("name", "")
        src = item.get("src", "")
        href = item.get("href", "#")
        items_html += f'<a href="{href}" class="dz-logo-item" title="{name}"><img src="{src}" alt="{name}"></a>'

    return f"""<section{_ssr_section_id(section)} class="dz-section dz-section-logo-cloud">
    <div class="dz-section-content">
        {_ssr_section_header(section)}
        <div class="dz-logos-grid">{items_html}</div>
    </div>
</section>"""


def _ssr_comparison(section: dict[str, Any]) -> str:
    columns = section.get("columns", [])
    items = section.get("items", [])

    th_html = ""
    for col in columns:
        cls = ' class="dz-comparison-highlighted"' if col.get("highlighted") else ""
        th_html += f"<th{cls}>{col.get('label', '')}</th>"

    rows_html = ""
    for row in items:
        cells_html = ""
        for i, cell in enumerate(row.get("cells", [])):
            col = columns[i] if i < len(columns) else {}
            cls = ' class="dz-comparison-highlighted"' if col.get("highlighted") else ""
            cells_html += f"<td{cls}>{cell}</td>"
        rows_html += (
            f'<tr><td class="dz-comparison-feature">{row.get("feature", "")}</td>{cells_html}</tr>'
        )

    return f"""<section{_ssr_section_id(section)} class="dz-section dz-section-comparison">
    <div class="dz-section-content">
        {_ssr_section_header(section)}
        <div class="dz-comparison-wrapper">
            <table class="dz-comparison-table">
                <thead><tr><th></th>{th_html}</tr></thead>
                <tbody>{rows_html}</tbody>
            </table>
        </div>
    </div>
</section>"""


def _ssr_generic(section: dict[str, Any]) -> str:
    """Fallback renderer for unknown section types."""
    content = section.get("content", "")
    sec_type = section.get("type", "unknown")

    return f"""<section{_ssr_section_id(section)} class="dz-section dz-section-{sec_type.replace("_", "-")}">
    <div class="dz-section-content">
        {_ssr_section_header(section)}
        {f'<div class="prose max-w-none">{content}</div>' if content else ""}
    </div>
</section>"""


_SSR_RENDERERS: dict[str, Any] = {
    "hero": _ssr_hero,
    "features": _ssr_features,
    "feature_grid": _ssr_features,
    "cta": _ssr_cta,
    "faq": _ssr_faq,
    "stats": _ssr_stats,
    "steps": _ssr_steps,
    "testimonials": _ssr_testimonials,
    "pricing": _ssr_pricing,
    "markdown": _ssr_markdown,
    "card_grid": _ssr_card_grid,
    "split_content": _ssr_split_content,
    "trust_bar": _ssr_trust_bar,
    "value_highlight": _ssr_value_highlight,
    "logo_cloud": _ssr_logo_cloud,
    "comparison": _ssr_comparison,
}


def render_auth_page_html(
    sitespec_data: dict[str, Any],
    page_type: str,
) -> str:
    """
    Render an authentication page (login/signup).

    Args:
        sitespec_data: Site specification data
        page_type: Either "login" or "signup"

    Returns:
        Complete HTML page string
    """
    brand = sitespec_data.get("brand", {})
    product_name = brand.get("product_name", "My App")

    is_login = page_type == "login"
    title = "Sign In" if is_login else "Create Account"
    other_page = "/signup" if is_login else "/login"
    other_link_text = "Create an account" if is_login else "Sign in instead"
    button_text = "Sign In" if is_login else "Sign Up"
    action_url = "/auth/login" if is_login else "/auth/register"

    # Build form fields
    fields_html = _build_auth_fields(is_login)

    return f"""<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
    {get_shared_head_html(f"{title} - {product_name}")}
</head>
<body class="dz-site dz-auth-page bg-base-200">
    <div class="dz-auth-container">
        <div class="card bg-base-100 shadow-xl dz-auth-card">
            <div class="card-body">
                <a href="/" class="dz-auth-logo text-primary font-bold text-xl">{product_name}</a>
                <h1 class="card-title text-2xl justify-center">{title}</h1>

                <div id="dz-auth-error" class="alert alert-error hidden" role="alert"></div>

                <form id="dz-auth-form" method="POST" action="{action_url}">
                    {fields_html}

                    <button type="submit" class="btn btn-primary w-full mt-4">
                        {button_text}
                    </button>
                </form>

                {'<p class="text-right text-sm mt-2"><a href="/forgot-password" class="link link-secondary">Forgot password?</a></p>' if is_login else ""}

                <p class="dz-auth-switch text-center text-sm mt-4">
                    <a href="{other_page}" class="link link-primary">{other_link_text}</a>
                </p>
            </div>
        </div>
    </div>

    <script>
    {_get_auth_form_script()}
    </script>
</body>
</html>"""


def _build_auth_fields(is_login: bool) -> str:
    """Build authentication form fields HTML using DaisyUI form-control."""
    fields_html = ""

    if not is_login:
        fields_html += """
            <div class="form-control w-full">
                <label class="label" for="name">
                    <span class="label-text">Full Name</span>
                </label>
                <input type="text" id="name" name="name" required autocomplete="name" class="input input-bordered w-full">
            </div>"""

    fields_html += """
            <div class="form-control w-full">
                <label class="label" for="email">
                    <span class="label-text">Email</span>
                </label>
                <input type="email" id="email" name="email" required autocomplete="email" class="input input-bordered w-full">
            </div>
            <div class="form-control w-full">
                <label class="label" for="password">
                    <span class="label-text">Password</span>
                </label>
                <input type="password" id="password" name="password" required autocomplete="current-password" class="input input-bordered w-full">
            </div>"""

    if not is_login:
        fields_html += """
            <div class="form-control w-full">
                <label class="label" for="confirm_password">
                    <span class="label-text">Confirm Password</span>
                </label>
                <input type="password" id="confirm_password" name="confirm_password" required class="input input-bordered w-full">
            </div>"""

    return fields_html


def _get_auth_form_script() -> str:
    """Return the authentication form submission script."""
    return """(function() {
        const form = document.getElementById('dz-auth-form');
        const errorDiv = document.getElementById('dz-auth-error');

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            errorDiv.classList.add('hidden');
            errorDiv.textContent = '';

            const formData = new FormData(form);
            const data = Object.fromEntries(formData.entries());

            try {
                const response = await fetch(form.action, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data),
                });

                if (response.ok) {
                    const result = await response.json();
                    if (result.token) {
                        localStorage.setItem('auth_token', result.token);
                    }
                    window.location.href = '/app';
                } else {
                    const error = await response.json();
                    errorDiv.textContent = error.detail || 'Authentication failed';
                    errorDiv.classList.remove('hidden');
                }
            } catch (err) {
                errorDiv.textContent = 'Network error. Please try again.';
                errorDiv.classList.remove('hidden');
            }
        });
    })();"""


def render_forgot_password_page_html(sitespec_data: dict[str, Any]) -> str:
    """Render the forgot-password page.

    Args:
        sitespec_data: Site specification data.

    Returns:
        Complete HTML page string.
    """
    brand = sitespec_data.get("brand", {})
    product_name = brand.get("product_name", "My App")

    return f"""<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
    {get_shared_head_html(f"Reset Password - {product_name}")}
</head>
<body class="dz-site dz-auth-page bg-base-200">
    <div class="dz-auth-container">
        <div class="card bg-base-100 shadow-xl dz-auth-card">
            <div class="card-body">
                <a href="/" class="dz-auth-logo text-primary font-bold text-xl">{product_name}</a>
                <h1 class="card-title text-2xl justify-center">Reset Password</h1>
                <p class="text-center text-sm opacity-70">
                    Enter your email and we'll send you a link to reset your password.
                </p>

                <div id="dz-auth-error" class="alert alert-error hidden" role="alert"></div>
                <div id="dz-auth-success" class="alert alert-success hidden" role="alert"></div>

                <form id="dz-auth-form" method="POST" action="/auth/forgot-password">
                    <div class="form-control w-full">
                        <label class="label" for="email">
                            <span class="label-text">Email</span>
                        </label>
                        <input type="email" id="email" name="email" required
                               autocomplete="email"
                               class="input input-bordered w-full">
                    </div>

                    <button type="submit" class="btn btn-primary w-full mt-4">
                        Send Reset Link
                    </button>
                </form>

                <p class="dz-auth-switch text-center text-sm mt-4">
                    <a href="/login" class="link link-primary">Back to sign in</a>
                </p>
            </div>
        </div>
    </div>

    <script>
    {_get_forgot_password_script()}
    </script>
</body>
</html>"""


def render_reset_password_page_html(sitespec_data: dict[str, Any]) -> str:
    """Render the reset-password page (with token from query string).

    Args:
        sitespec_data: Site specification data.

    Returns:
        Complete HTML page string.
    """
    brand = sitespec_data.get("brand", {})
    product_name = brand.get("product_name", "My App")

    return f"""<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
    {get_shared_head_html(f"Set New Password - {product_name}")}
</head>
<body class="dz-site dz-auth-page bg-base-200">
    <div class="dz-auth-container">
        <div class="card bg-base-100 shadow-xl dz-auth-card">
            <div class="card-body">
                <a href="/" class="dz-auth-logo text-primary font-bold text-xl">{product_name}</a>
                <h1 class="card-title text-2xl justify-center">Set New Password</h1>

                <div id="dz-auth-error" class="alert alert-error hidden" role="alert"></div>

                <form id="dz-auth-form" method="POST" action="/auth/reset-password">
                    <input type="hidden" id="token" name="token" value="">

                    <div class="form-control w-full">
                        <label class="label" for="new_password">
                            <span class="label-text">New Password</span>
                        </label>
                        <input type="password" id="new_password" name="new_password"
                               required minlength="8" autocomplete="new-password"
                               class="input input-bordered w-full">
                    </div>

                    <div class="form-control w-full">
                        <label class="label" for="confirm_password">
                            <span class="label-text">Confirm Password</span>
                        </label>
                        <input type="password" id="confirm_password" name="confirm_password"
                               required minlength="8" autocomplete="new-password"
                               class="input input-bordered w-full">
                    </div>

                    <button type="submit" class="btn btn-primary w-full mt-4">
                        Reset Password
                    </button>
                </form>

                <p class="dz-auth-switch text-center text-sm mt-4">
                    <a href="/login" class="link link-primary">Back to sign in</a>
                </p>
            </div>
        </div>
    </div>

    <script>
    {_get_reset_password_script()}
    </script>
</body>
</html>"""


def _get_forgot_password_script() -> str:
    """Return the forgot-password form submission script."""
    return """(function() {
        const form = document.getElementById('dz-auth-form');
        const errorDiv = document.getElementById('dz-auth-error');
        const successDiv = document.getElementById('dz-auth-success');

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            errorDiv.classList.add('hidden');
            successDiv.classList.add('hidden');

            const formData = new FormData(form);
            const data = Object.fromEntries(formData.entries());

            try {
                const response = await fetch(form.action, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data),
                });

                const result = await response.json();
                if (response.ok) {
                    successDiv.textContent = result.message || 'Check your email for a reset link.';
                    successDiv.classList.remove('hidden');
                    form.querySelector('button[type="submit"]').disabled = true;
                } else {
                    errorDiv.textContent = result.detail || 'Something went wrong.';
                    errorDiv.classList.remove('hidden');
                }
            } catch (err) {
                errorDiv.textContent = 'Network error. Please try again.';
                errorDiv.classList.remove('hidden');
            }
        });
    })();"""


def _get_reset_password_script() -> str:
    """Return the reset-password form submission script."""
    return """(function() {
        const form = document.getElementById('dz-auth-form');
        const errorDiv = document.getElementById('dz-auth-error');
        const tokenInput = document.getElementById('token');

        // Extract token from query string
        const params = new URLSearchParams(window.location.search);
        const token = params.get('token');
        if (!token) {
            errorDiv.textContent = 'Missing reset token. Please use the link from your email.';
            errorDiv.classList.remove('hidden');
            form.querySelector('button[type="submit"]').disabled = true;
            return;
        }
        tokenInput.value = token;

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            errorDiv.classList.add('hidden');

            const password = document.getElementById('new_password').value;
            const confirm = document.getElementById('confirm_password').value;

            if (password !== confirm) {
                errorDiv.textContent = 'Passwords do not match.';
                errorDiv.classList.remove('hidden');
                return;
            }

            try {
                const response = await fetch(form.action, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ token: tokenInput.value, new_password: password }),
                });

                if (response.ok) {
                    window.location.href = '/app';
                } else {
                    const error = await response.json();
                    errorDiv.textContent = error.detail || 'Reset failed. The link may have expired.';
                    errorDiv.classList.remove('hidden');
                }
            } catch (err) {
                errorDiv.textContent = 'Network error. Please try again.';
                errorDiv.classList.remove('hidden');
            }
        });
    })();"""


# Task Context Injection Functions


def render_task_context_script(task_context: TaskContext | None) -> str:
    """
    Render a script tag containing task context data.

    This script tag is injected into pages that are rendered as part
    of a human task workflow, enabling the task-header.js component
    to display task information and outcome buttons.

    Args:
        task_context: TaskContext instance or None

    Returns:
        HTML script tag with task context JSON, or empty string
    """
    if not task_context:
        return ""

    context_json = json.dumps(task_context.to_dict())

    return f"""<script type="application/json" id="task-context">
{context_json}
</script>
<script src="/js/components/task-header.js" type="module"></script>"""


def render_task_surface_page(
    surface_name: str,
    entity_id: str,
    task_context: TaskContext,
    surface_html: str,
    product_name: str = "My App",
) -> str:
    """
    Render a surface page with task context for human task workflow.

    This wraps a surface's HTML content with task header/footer components
    and injects the TaskContext for JavaScript to use.

    Args:
        surface_name: Name of the surface being rendered
        entity_id: ID of the entity being displayed
        task_context: TaskContext with task information and outcomes
        surface_html: The rendered surface HTML content
        product_name: Application name for title

    Returns:
        Complete HTML page with task context injection
    """
    task_script = render_task_context_script(task_context)
    title = f"Task: {task_context.step_name} - {product_name}"

    return f"""<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
    {get_shared_head_html(title)}
</head>
<body class="dz-site bg-base-100">
    <header class="dz-site-header">
        <nav class="dz-site-nav">
            <a href="/workspaces/tasks" class="dz-site-logo">{product_name}</a>
            <div class="dz-nav-items">
                <a href="/workspaces/tasks" class="dz-nav-link">My Tasks</a>
            </div>
        </nav>
    </header>

    <main class="dz-task-surface-container">
        <div class="surface-container" data-surface="{surface_name}" data-entity-id="{entity_id}">
            {surface_html}
        </div>
    </main>

    {task_script}
</body>
</html>"""


def get_task_header_script_tag() -> str:
    """
    Get script tag for task header component.

    Include this in pages that may render with task context.
    """
    return '<script src="/js/components/task-header.js" type="module" defer></script>'


def get_site_js() -> str:
    """
    Get the site page JavaScript content.

    This JS handles theme toggling and fetches page data from the /_site/page API
    to render marketing page sections client-side.

    Returns:
        JavaScript content for /site.js route
    """
    return """/**
 * Dazzle Site Page Renderer
 * Fetches page data from /_site/page/{route} and renders sections.
 */
(function() {
    'use strict';

    // ==========================================================================
    // Theme System (v0.16.0 - Issue #26)
    // ==========================================================================

    const STORAGE_KEY = 'dz-theme-variant';
    const THEME_LIGHT = 'light';
    const THEME_DARK = 'dark';

    function getSystemPreference() {
        if (typeof window === 'undefined') return THEME_LIGHT;
        const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
        return mediaQuery.matches ? THEME_DARK : THEME_LIGHT;
    }

    function getStoredPreference() {
        if (typeof localStorage === 'undefined') return null;
        return localStorage.getItem(STORAGE_KEY);
    }

    function storePreference(variant) {
        if (typeof localStorage === 'undefined') return;
        localStorage.setItem(STORAGE_KEY, variant);
    }

    function applyTheme(variant) {
        const root = document.documentElement;
        root.setAttribute('data-theme', variant);
        root.style.colorScheme = variant;
        root.classList.remove('dz-theme-light', 'dz-theme-dark');
        root.classList.add('dz-theme-' + variant);
    }

    function initTheme() {
        const stored = getStoredPreference();
        const system = getSystemPreference();
        const variant = stored || system || THEME_LIGHT;
        applyTheme(variant);

        // Listen for system preference changes
        const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
        mediaQuery.addEventListener('change', function(e) {
            if (!getStoredPreference()) {
                applyTheme(e.matches ? THEME_DARK : THEME_LIGHT);
            }
        });

        return variant;
    }

    function toggleTheme() {
        const current = document.documentElement.getAttribute('data-theme') || THEME_LIGHT;
        const newVariant = current === THEME_LIGHT ? THEME_DARK : THEME_LIGHT;
        applyTheme(newVariant);
        storePreference(newVariant);
        return newVariant;
    }

    // Initialize theme immediately (before DOMContentLoaded)
    initTheme();

    // Set up toggle button
    document.addEventListener('DOMContentLoaded', function() {
        const toggleBtn = document.getElementById('dz-theme-toggle');
        if (toggleBtn) {
            toggleBtn.addEventListener('click', toggleTheme);
        }
    });

    // ==========================================================================
    // Page Rendering
    // ==========================================================================

    const main = document.getElementById('dz-site-main');
    const route = main?.dataset.route || '/';

    // Slugify helper for auto-generating anchor IDs from headlines
    function slugify(text) {
        if (!text) return null;
        return text
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, '-')
            .replace(/^-+|-+$/g, '');
    }

    // Get section ID: explicit id > auto-generated from headline > null
    function getSectionId(section) {
        if (section.id) return section.id;
        if (section.headline) return slugify(section.headline);
        return null;
    }

    // Generate id attribute string for section element
    function idAttr(section) {
        return section._computedId ? `id="${section._computedId}"` : '';
    }

    // Section renderers
    const renderers = {
        hero: renderHero,
        features: renderFeatures,
        feature_grid: renderFeatureGrid,
        cta: renderCTA,
        faq: renderFAQ,
        testimonials: renderTestimonials,
        stats: renderStats,
        steps: renderSteps,
        logo_cloud: renderLogoCloud,
        pricing: renderPricing,
        markdown: renderMarkdown,
        comparison: renderComparison,
        value_highlight: renderValueHighlight,
        split_content: renderSplitContent,
        card_grid: renderCardGrid,
        trust_bar: renderTrustBar,
    };

    function renderSectionHeader(section) {
        const headline = section.headline || '';
        const subhead = section.subhead || '';
        if (!headline && !subhead) return '';
        return `
            <div class="dz-section-header">
                ${headline ? `<h2>${headline}</h2>` : ''}
                ${subhead ? `<p class="dz-subhead">${subhead}</p>` : ''}
            </div>
        `;
    }

    function renderHero(section) {
        const headline = section.headline || '';
        const subhead = section.subhead || '';
        const primaryCta = section.primary_cta;
        const secondaryCta = section.secondary_cta;
        const media = section.media;

        let ctaHtml = '';
        if (primaryCta) {
            ctaHtml += `<a href="${primaryCta.href || '#'}" class="btn btn-primary">${primaryCta.label || 'Get Started'}</a>`;
        }
        if (secondaryCta) {
            ctaHtml += `<a href="${secondaryCta.href || '#'}" class="btn btn-secondary btn-outline">${secondaryCta.label || 'Learn More'}</a>`;
        }

        let mediaHtml = '';
        if (media && media.kind === 'image' && media.src) {
            mediaHtml = `<div class="dz-hero-media"><img src="${media.src}" alt="${media.alt || ''}" class="dz-hero-image" /></div>`;
        }

        const hasMedia = mediaHtml ? 'dz-hero-with-media' : '';

        return `
            <section ${idAttr(section)} class="dz-section dz-section-hero ${hasMedia}">
                <div class="dz-section-content">
                    <div class="dz-hero-text">
                        <h1>${headline}</h1>
                        ${subhead ? `<p class="dz-subhead">${subhead}</p>` : ''}
                        ${ctaHtml ? `<div class="dz-cta-group">${ctaHtml}</div>` : ''}
                    </div>
                    ${mediaHtml}
                </div>
            </section>
        `;
    }

    function renderFeatures(section) {
        const items = section.items || [];
        const headerHtml = renderSectionHeader(section);
        const itemsHtml = items.map(item => `
            <div class="dz-feature-item">
                ${item.icon ? `<div class="dz-feature-icon"><i data-lucide="${item.icon}"></i></div>` : ''}
                <h3>${item.title || ''}</h3>
                <p>${item.body || ''}</p>
            </div>
        `).join('');

        return `
            <section ${idAttr(section)} class="dz-section dz-section-features">
                <div class="dz-section-content">
                    ${headerHtml}
                    <div class="dz-features-grid">${itemsHtml}</div>
                </div>
            </section>
        `;
    }

    function renderFeatureGrid(section) {
        return renderFeatures(section);  // Same layout
    }

    function renderCTA(section) {
        const headline = section.headline || '';
        const body = section.body || section.subhead || '';
        const primaryCta = section.primary_cta;
        const secondaryCta = section.secondary_cta;

        let ctaHtml = '';
        if (primaryCta) {
            ctaHtml += `<a href="${primaryCta.href || '#'}" class="btn btn-primary">${primaryCta.label || 'Get Started'}</a>`;
        }
        if (secondaryCta) {
            ctaHtml += `<a href="${secondaryCta.href || '#'}" class="btn btn-secondary btn-outline">${secondaryCta.label || 'Learn More'}</a>`;
        }

        return `
            <section ${idAttr(section)} class="dz-section dz-section-cta">
                <div class="dz-section-content">
                    <h2>${headline}</h2>
                    ${body ? `<p class="dz-subhead">${body}</p>` : ''}
                    ${ctaHtml ? `<div class="dz-cta-group">${ctaHtml}</div>` : ''}
                </div>
            </section>
        `;
    }

    function renderFAQ(section) {
        const headline = section.headline || 'Frequently Asked Questions';
        const items = section.items || [];
        const itemsHtml = items.map(item => `
            <details class="dz-faq-item">
                <summary>${item.question || ''}</summary>
                <p>${item.answer || ''}</p>
            </details>
        `).join('');

        return `
            <section ${idAttr(section)} class="dz-section dz-section-faq">
                <div class="dz-section-content">
                    <h2>${headline}</h2>
                    <div class="dz-faq-list">${itemsHtml}</div>
                </div>
            </section>
        `;
    }

    function renderTestimonials(section) {
        const items = section.items || [];
        const headerHtml = renderSectionHeader(section);
        const itemsHtml = items.map(item => `
            <div class="dz-testimonial-item">
                <blockquote>"${item.quote || ''}"</blockquote>
                <div class="dz-testimonial-author">
                    ${item.avatar ? `<img src="${item.avatar}" alt="${item.author}" class="dz-avatar">` : ''}
                    <div>
                        <strong>${item.author || ''}</strong>
                        ${item.role ? `<span>${item.role}${item.company ? `, ${item.company}` : ''}</span>` : ''}
                    </div>
                </div>
            </div>
        `).join('');

        return `
            <section ${idAttr(section)} class="dz-section dz-section-testimonials">
                <div class="dz-section-content">
                    ${headerHtml}
                    <div class="dz-testimonials-grid">${itemsHtml}</div>
                </div>
            </section>
        `;
    }

    function renderStats(section) {
        const items = section.items || [];
        const headerHtml = renderSectionHeader(section);
        const itemsHtml = items.map(item => `
            <div class="dz-stat-item">
                <span class="dz-stat-value">${item.value || ''}</span>
                <span class="dz-stat-label">${item.label || ''}</span>
            </div>
        `).join('');

        return `
            <section ${idAttr(section)} class="dz-section dz-section-stats">
                <div class="dz-section-content">
                    ${headerHtml}
                    <div class="dz-stats-grid">${itemsHtml}</div>
                </div>
            </section>
        `;
    }

    function renderSteps(section) {
        const items = section.items || [];
        const headerHtml = renderSectionHeader(section);
        const itemsHtml = items.map(item => `
            <div class="dz-step-item">
                <span class="dz-step-number">${item.step || ''}</span>
                <div>
                    <h3>${item.title || ''}</h3>
                    <p>${item.body || ''}</p>
                </div>
            </div>
        `).join('');

        return `
            <section ${idAttr(section)} class="dz-section dz-section-steps">
                <div class="dz-section-content">
                    ${headerHtml}
                    <div class="dz-steps-list">${itemsHtml}</div>
                </div>
            </section>
        `;
    }

    function renderLogoCloud(section) {
        const items = section.items || [];
        const headerHtml = renderSectionHeader(section);
        const itemsHtml = items.map(item => `
            <a href="${item.href || '#'}" class="dz-logo-item" title="${item.name || ''}">
                <img src="${item.src || ''}" alt="${item.name || ''}">
            </a>
        `).join('');

        return `
            <section ${idAttr(section)} class="dz-section dz-section-logo-cloud">
                <div class="dz-section-content">
                    ${headerHtml}
                    <div class="dz-logos-grid">${itemsHtml}</div>
                </div>
            </section>
        `;
    }

    function renderPricing(section) {
        const tiers = section.tiers || [];
        const headerHtml = renderSectionHeader(section);
        const tiersHtml = tiers.map(tier => {
            const features = (tier.features || []).map(f => `<li>${f}</li>`).join('');
            const highlighted = tier.highlighted ? ' dz-pricing-highlighted' : '';
            const btnClass = tier.highlighted ? 'btn btn-secondary' : 'btn btn-primary';
            return `
                <div class="dz-pricing-tier${highlighted}">
                    <h3>${tier.name || ''}</h3>
                    <div class="dz-pricing-price">
                        <span class="dz-price">${tier.price || ''}</span>
                        ${tier.period ? `<span class="dz-period">/${tier.period}</span>` : ''}
                    </div>
                    ${tier.description ? `<p class="dz-pricing-description">${tier.description}</p>` : ''}
                    <ul class="dz-pricing-features">${features}</ul>
                    ${tier.cta ? `<a href="${tier.cta.href || '#'}" class="${btnClass}">${tier.cta.label || 'Get Started'}</a>` : ''}
                </div>
            `;
        }).join('');

        return `
            <section ${idAttr(section)} class="dz-section dz-section-pricing">
                <div class="dz-section-content">
                    ${headerHtml}
                    <div class="dz-pricing-grid">${tiersHtml}</div>
                </div>
            </section>
        `;
    }

    function renderMarkdown(section) {
        const content = section.content || '';
        return `
            <section ${idAttr(section)} class="dz-section dz-section-markdown">
                <div class="dz-section-content dz-prose">
                    ${content}
                </div>
            </section>
        `;
    }

    function renderComparison(section) {
        const columns = section.columns || [];
        const items = section.items || [];
        const headerHtml = renderSectionHeader(section);

        const thHtml = columns.map(col => {
            const cls = col.highlighted ? ' class="dz-comparison-highlighted"' : '';
            return `<th${cls}>${col.label || ''}</th>`;
        }).join('');

        const rowsHtml = items.map(row => {
            const cellsHtml = (row.cells || []).map((cell, i) => {
                const col = columns[i] || {};
                const cls = col.highlighted ? ' class="dz-comparison-highlighted"' : '';
                return `<td${cls}>${cell}</td>`;
            }).join('');
            return `<tr><td class="dz-comparison-feature">${row.feature || ''}</td>${cellsHtml}</tr>`;
        }).join('');

        return `
            <section ${idAttr(section)} class="dz-section dz-section-comparison">
                <div class="dz-section-content">
                    ${headerHtml}
                    <div class="dz-comparison-wrapper">
                        <table class="dz-comparison-table">
                            <thead><tr><th></th>${thHtml}</tr></thead>
                            <tbody>${rowsHtml}</tbody>
                        </table>
                    </div>
                </div>
            </section>
        `;
    }

    function renderValueHighlight(section) {
        const headline = section.headline || '';
        const subhead = section.subhead || '';
        const body = section.body || '';
        const primaryCta = section.primary_cta;

        let ctaHtml = '';
        if (primaryCta) {
            ctaHtml = `<div class="dz-cta-group"><a href="${primaryCta.href || '#'}" class="btn btn-primary">${primaryCta.label || 'Get Started'}</a></div>`;
        }

        return `
            <section ${idAttr(section)} class="dz-section dz-section-value-highlight">
                <div class="dz-section-content">
                    <h2 class="dz-value-headline">${headline}</h2>
                    ${subhead ? `<p class="dz-subhead">${subhead}</p>` : ''}
                    ${body ? `<p class="dz-value-body">${body}</p>` : ''}
                    ${ctaHtml}
                </div>
            </section>
        `;
    }

    function renderSplitContent(section) {
        const headline = section.headline || '';
        const body = section.body || '';
        const media = section.media;
        const primaryCta = section.primary_cta;
        const alignment = section.alignment || 'left';

        let ctaHtml = '';
        if (primaryCta) {
            ctaHtml = `<div class="dz-cta-group dz-cta-group--left"><a href="${primaryCta.href || '#'}" class="btn btn-primary">${primaryCta.label || 'Learn More'}</a></div>`;
        }

        let mediaHtml = '';
        if (media && media.kind === 'image' && media.src) {
            mediaHtml = `<div class="dz-split-media"><img src="${media.src}" alt="${media.alt || ''}" /></div>`;
        }

        const orderCls = alignment === 'right' ? ' dz-split--reversed' : '';

        return `
            <section ${idAttr(section)} class="dz-section dz-section-split-content${orderCls}">
                <div class="dz-section-content dz-split-grid">
                    <div class="dz-split-text">
                        <h2>${headline}</h2>
                        ${body ? `<p>${body}</p>` : ''}
                        ${ctaHtml}
                    </div>
                    ${mediaHtml}
                </div>
            </section>
        `;
    }

    function renderCardGrid(section) {
        const items = section.items || [];
        const headerHtml = renderSectionHeader(section);

        const cardsHtml = items.map(item => {
            let ctaHtml = '';
            if (item.cta) {
                ctaHtml = `<a href="${item.cta.href || '#'}" class="btn btn-primary btn-sm">${item.cta.label || 'Learn More'}</a>`;
            }
            return `
                <div class="dz-card-item">
                    ${item.icon ? `<div class="dz-card-icon"><i data-lucide="${item.icon}"></i></div>` : ''}
                    <h3>${item.title || ''}</h3>
                    <p>${item.body || ''}</p>
                    ${ctaHtml}
                </div>
            `;
        }).join('');

        return `
            <section ${idAttr(section)} class="dz-section dz-section-card-grid">
                <div class="dz-section-content">
                    ${headerHtml}
                    <div class="dz-card-grid">${cardsHtml}</div>
                </div>
            </section>
        `;
    }

    function renderTrustBar(section) {
        const items = section.items || [];
        const headerHtml = renderSectionHeader(section);

        const itemsHtml = items.map(item => `
            <div class="dz-trust-item">
                ${item.icon ? `<i data-lucide="${item.icon}"></i>` : ''}
                <span>${item.text || ''}</span>
            </div>
        `).join('');

        return `
            <section ${idAttr(section)} class="dz-section dz-section-trust-bar">
                <div class="dz-section-content">
                    ${headerHtml}
                    <div class="dz-trust-strip">${itemsHtml}</div>
                </div>
            </section>
        `;
    }

    function renderPage(pageData) {
        if (!main) return;

        const sections = pageData.sections || [];

        // Backward compat: if no sections but content exists,
        // synthesize a markdown section
        if (!sections.length && pageData.content) {
            sections.push({ type: 'markdown', content: pageData.content });
        }

        // Track used IDs to handle duplicates
        const usedIds = new Set();

        let html = '';

        for (const section of sections) {
            // Compute section ID (explicit > headline-based > null)
            let sectionId = getSectionId(section);

            // Handle duplicate IDs by appending a suffix
            if (sectionId && usedIds.has(sectionId)) {
                let suffix = 2;
                while (usedIds.has(`${sectionId}-${suffix}`)) {
                    suffix++;
                }
                sectionId = `${sectionId}-${suffix}`;
            }
            if (sectionId) {
                usedIds.add(sectionId);
            }

            // Inject computed ID into section for renderers to use
            section._computedId = sectionId;

            const renderer = renderers[section.type];
            if (renderer) {
                html += renderer(section);
            } else {
                console.warn(`Unknown section type: ${section.type}`);
            }
        }

        main.innerHTML = html || '<p>No content</p>';

        // Initialize Lucide icons after DOM update
        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }

        // Scroll to fragment if present
        if (window.location.hash) {
            const target = document.getElementById(window.location.hash.slice(1));
            if (target) {
                target.scrollIntoView({ behavior: 'smooth' });
            }
        }
    }

    // Fetch and render page (skip if SSR content is already present)
    async function init() {
        // If the page was server-side rendered, content is already in the DOM.
        // Just initialize Lucide icons and handle hash scrolling.
        if (main && main.querySelector('.dz-section')) {
            if (typeof lucide !== 'undefined') { lucide.createIcons(); }
            if (window.location.hash) {
                const target = document.getElementById(window.location.hash.slice(1));
                if (target) { target.scrollIntoView({ behavior: 'smooth' }); }
            }
            return;
        }

        try {
            const apiRoute = route === '/' ? '' : route;
            const response = await fetch(`/_site/page${apiRoute}`);
            if (response.status === 404) {
                if (main) {
                    main.innerHTML = `
                        <section class="dz-section dz-section-hero">
                            <div class="dz-section-content dz-404-section">
                                <h1 class="dz-404-headline">404</h1>
                                <p class="dz-subhead">The page you&rsquo;re looking for doesn&rsquo;t exist.</p>
                                <div class="dz-cta-group dz-404-cta">
                                    <a href="/" class="btn btn-primary">Go Home</a>
                                </div>
                            </div>
                        </section>`;
                }
                return;
            }
            if (!response.ok) {
                throw new Error(`Failed to load page: ${response.status}`);
            }
            const pageData = await response.json();
            renderPage(pageData);
        } catch (error) {
            console.error('Error loading page:', error);
            if (main) {
                main.innerHTML = '<p class="dz-error">Failed to load page content.</p>';
            }
        }
    }

    init();
})();
"""
