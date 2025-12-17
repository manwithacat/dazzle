"""
Site page renderer for DNR runtime.

Extracts HTML/JS template generation from combined_server.py for better maintainability.
"""

from __future__ import annotations

from typing import Any


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
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{product_name}</title>
    <link rel="icon" href="/assets/dazzle-favicon.svg" type="image/svg+xml">
    <link rel="stylesheet" href="/styles/dnr.css">
</head>
<body class="dz-site">
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
        nav_items_html += f'<a href="{href}" class="dz-nav-link">{label}</a>\n'

    # Add CTA button if present
    cta = nav.get("cta")
    if cta:
        cta_label = cta.get("label", "Get Started")
        cta_href = cta.get("href", "/app")
        nav_items_html += f'<a href="{cta_href}" class="dz-nav-cta">{cta_label}</a>\n'

    # Add theme toggle button
    nav_items_html += """<button class="dz-theme-toggle" id="dz-theme-toggle" aria-label="Toggle dark mode" title="Toggle dark mode">
                <svg class="dz-theme-toggle__icon dz-theme-toggle__sun" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
                </svg>
                <svg class="dz-theme-toggle__icon dz-theme-toggle__moon" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
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
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - {product_name}</title>
    <link rel="icon" href="/assets/dazzle-favicon.svg" type="image/svg+xml">
    <link rel="stylesheet" href="/styles/dnr.css">
</head>
<body class="dz-site dz-auth-page">
    <div class="dz-auth-container">
        <div class="dz-auth-card">
            <a href="/" class="dz-auth-logo">{product_name}</a>
            <h1>{title}</h1>

            <div id="dz-auth-error" class="dz-auth-error hidden"></div>

            <form id="dz-auth-form" method="POST" action="{action_url}">
                {fields_html}

                <button type="submit" class="dz-btn dz-btn-primary dz-btn-full">
                    {button_text}
                </button>
            </form>

            <p class="dz-auth-switch">
                <a href="{other_page}">{other_link_text}</a>
            </p>
        </div>
    </div>

    <script>
    {_get_auth_form_script()}
    </script>
</body>
</html>"""


def _build_auth_fields(is_login: bool) -> str:
    """Build authentication form fields HTML."""
    fields_html = ""

    if not is_login:
        fields_html += """
            <div class="dz-auth-field">
                <label for="name">Full Name</label>
                <input type="text" id="name" name="name" required autocomplete="name">
            </div>"""

    fields_html += """
            <div class="dz-auth-field">
                <label for="email">Email</label>
                <input type="email" id="email" name="email" required autocomplete="email">
            </div>
            <div class="dz-auth-field">
                <label for="password">Password</label>
                <input type="password" id="password" name="password" required autocomplete="current-password">
            </div>"""

    if not is_login:
        fields_html += """
            <div class="dz-auth-field">
                <label for="confirm_password">Confirm Password</label>
                <input type="password" id="confirm_password" name="confirm_password" required>
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
