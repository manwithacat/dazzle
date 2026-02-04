"""
Site page renderer for DNR runtime.

Extracts HTML/JS template generation from combined_server.py for better maintainability.
Includes support for TaskContext injection when rendering surfaces as human tasks.
"""

from __future__ import annotations

import json
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
    <link rel="icon" href="/assets/dazzle-favicon.svg" type="image/svg+xml">
    <!-- Inter font -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <!-- DaisyUI - semantic component classes (same as workspace) -->
    <link href="https://cdn.jsdelivr.net/npm/daisyui@5/daisyui.css" rel="stylesheet" type="text/css" />
    <!-- Tailwind Browser - minimal utilities for layout -->
    <script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
    <!-- DAZZLE design system layer -->
    <link rel="stylesheet" href="/styles/dazzle.css">"""


def render_site_page_html(
    sitespec_data: dict[str, Any],
    path: str,
) -> str:
    """
    Render the site page HTML shell.

    Args:
        sitespec_data: Site specification data
        path: Current page route

    Returns:
        Complete HTML page string
    """
    brand = sitespec_data.get("brand", {})
    product_name = brand.get("product_name", "My App")
    layout = sitespec_data.get("layout", {})
    nav = layout.get("nav", {})
    footer = layout.get("footer", {})

    # Build nav HTML
    nav_items_html = _build_nav_items(nav)

    # Build footer HTML
    footer_html = _build_footer(footer)
    copyright_text = footer.get("copyright", f"© 2025 {product_name}")

    return f"""<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
    {get_shared_head_html(product_name)}
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
        <!-- Page sections will be rendered by site.js -->
        <div class="dz-loading">Loading...</div>
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


def _build_nav_items(nav: dict[str, Any]) -> str:
    """Build navigation items HTML."""
    nav_items_html = ""
    for item in nav.get("items", []):
        label = item.get("label", "")
        href = item.get("href", "#")
        # Use DaisyUI-compatible link styling
        nav_items_html += f'<a href="{href}" class="dz-nav-link">{label}</a>\n'

    # Add CTA button if present - use DaisyUI btn classes
    cta = nav.get("cta")
    if cta:
        cta_label = cta.get("label", "Get Started")
        cta_href = cta.get("href", "/app")
        nav_items_html += f'<a href="{cta_href}" class="btn btn-primary btn-sm">{cta_label}</a>\n'

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

                <div id="dz-auth-error" class="alert alert-error hidden"></div>

                <form id="dz-auth-form" method="POST" action="{action_url}">
                    {fields_html}

                    <button type="submit" class="btn btn-primary w-full mt-4">
                        {button_text}
                    </button>
                </form>

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
    <style>
        .task-surface-container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }}
    </style>
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

    <main class="task-surface-container">
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
    };

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
            <section class="dz-section dz-section-hero ${hasMedia}">
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
        const itemsHtml = items.map(item => `
            <div class="dz-feature-item">
                ${item.icon ? `<div class="dz-feature-icon">${item.icon}</div>` : ''}
                <h3>${item.title || ''}</h3>
                <p>${item.body || ''}</p>
            </div>
        `).join('');

        return `
            <section class="dz-section dz-section-features">
                <div class="dz-section-content">
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
        const body = section.body || '';
        const primaryCta = section.primary_cta;

        return `
            <section class="dz-section dz-section-cta">
                <div class="dz-section-content">
                    <h2>${headline}</h2>
                    ${body ? `<p>${body}</p>` : ''}
                    ${primaryCta ? `<a href="${primaryCta.href || '#'}" class="btn btn-primary">${primaryCta.label || 'Get Started'}</a>` : ''}
                </div>
            </section>
        `;
    }

    function renderFAQ(section) {
        const items = section.items || [];
        const itemsHtml = items.map(item => `
            <details class="dz-faq-item">
                <summary>${item.question || ''}</summary>
                <p>${item.answer || ''}</p>
            </details>
        `).join('');

        return `
            <section class="dz-section dz-section-faq">
                <div class="dz-section-content">
                    <h2>Frequently Asked Questions</h2>
                    <div class="dz-faq-list">${itemsHtml}</div>
                </div>
            </section>
        `;
    }

    function renderTestimonials(section) {
        const items = section.items || [];
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
            <section class="dz-section dz-section-testimonials">
                <div class="dz-section-content">
                    <div class="dz-testimonials-grid">${itemsHtml}</div>
                </div>
            </section>
        `;
    }

    function renderStats(section) {
        const items = section.items || [];
        const itemsHtml = items.map(item => `
            <div class="dz-stat-item">
                <span class="dz-stat-value">${item.value || ''}</span>
                <span class="dz-stat-label">${item.label || ''}</span>
            </div>
        `).join('');

        return `
            <section class="dz-section dz-section-stats">
                <div class="dz-section-content">
                    <div class="dz-stats-grid">${itemsHtml}</div>
                </div>
            </section>
        `;
    }

    function renderSteps(section) {
        const items = section.items || [];
        const itemsHtml = items.map(item => `
            <div class="dz-step-item">
                <span class="dz-step-number">${item.step || ''}</span>
                <h3>${item.title || ''}</h3>
                <p>${item.body || ''}</p>
            </div>
        `).join('');

        return `
            <section class="dz-section dz-section-steps">
                <div class="dz-section-content">
                    <div class="dz-steps-list">${itemsHtml}</div>
                </div>
            </section>
        `;
    }

    function renderLogoCloud(section) {
        const items = section.items || [];
        const itemsHtml = items.map(item => `
            <a href="${item.href || '#'}" class="dz-logo-item" title="${item.name || ''}">
                <img src="${item.src || ''}" alt="${item.name || ''}">
            </a>
        `).join('');

        return `
            <section class="dz-section dz-section-logo-cloud">
                <div class="dz-section-content">
                    <div class="dz-logos-grid">${itemsHtml}</div>
                </div>
            </section>
        `;
    }

    function renderPricing(section) {
        const tiers = section.tiers || [];
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
                    <ul class="dz-pricing-features">${features}</ul>
                    ${tier.cta ? `<a href="${tier.cta.href || '#'}" class="${btnClass}">${tier.cta.label || 'Get Started'}</a>` : ''}
                </div>
            `;
        }).join('');

        return `
            <section class="dz-section dz-section-pricing">
                <div class="dz-section-content">
                    <div class="dz-pricing-grid">${tiersHtml}</div>
                </div>
            </section>
        `;
    }

    function renderMarkdown(section) {
        const content = section.content || '';
        return `
            <section class="dz-section dz-section-markdown">
                <div class="dz-section-content dz-prose">
                    ${content}
                </div>
            </section>
        `;
    }

    function renderPage(pageData) {
        if (!main) return;

        const sections = pageData.sections || [];
        let html = '';

        for (const section of sections) {
            const renderer = renderers[section.type];
            if (renderer) {
                html += renderer(section);
            } else {
                console.warn(`Unknown section type: ${section.type}`);
            }
        }

        // Handle markdown and legal page content
        if (pageData.content && (pageData.type === 'markdown' || pageData.type === 'legal')) {
            html = renderMarkdown({ content: pageData.content });
        }

        main.innerHTML = html || '<p>No content</p>';
    }

    // Fetch and render page
    async function init() {
        try {
            const apiRoute = route === '/' ? '' : route;
            const response = await fetch(`/_site/page${apiRoute}`);
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
