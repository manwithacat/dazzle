"""
Combined DNR Server - runs both backend and frontend.

Provides a unified development server that:
1. Runs FastAPI backend on port 8000
2. Runs UI dev server on port 3000 with API proxy
3. Handles hot reload for both (when enabled with --watch)
"""

from __future__ import annotations

import http.server
import os
import socketserver
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dazzle.core.strings import to_api_plural
from dazzle_dnr_ui.runtime.js_generator import JSGenerator
from dazzle_dnr_ui.specs import UISpec

if TYPE_CHECKING:
    from dazzle_dnr_back.specs import BackendSpec
    from dazzle_dnr_ui.runtime.hot_reload import HotReloadManager


# =============================================================================
# Terminal Utilities
# =============================================================================


def _supports_hyperlinks() -> bool:
    """
    Check if the terminal likely supports OSC 8 hyperlinks.

    We check for:
    1. NO_COLOR not set (respect user preference)
    2. TERM is set (indicates a terminal environment)
    3. Not running in dumb terminal
    """
    if os.environ.get("NO_COLOR"):
        return False

    term = os.environ.get("TERM", "")
    if not term or term == "dumb":
        return False

    # Most modern terminals support OSC 8: iTerm2, Terminal.app, VS Code, etc.
    return True


def _clickable_url(url: str, label: str | None = None) -> str:
    """
    Create a clickable hyperlink for terminal emulators that support OSC 8.

    Uses the OSC 8 escape sequence format:
    \\e]8;;URL\\e\\\\LABEL\\e]8;;\\e\\\\

    Falls back to plain text if NO_COLOR is set or TERM is not set.
    """
    if not _supports_hyperlinks():
        return label or url

    # OSC 8 hyperlink format
    # \x1b]8;; starts the hyperlink, \x1b\\ (or \x07) ends parameters
    # Then the visible text, then \x1b]8;;\x1b\\ to close
    display = label or url
    return f"\x1b]8;;{url}\x1b\\{display}\x1b]8;;\x1b\\"


# =============================================================================
# Proxy Handler
# =============================================================================


class DNRCombinedHandler(http.server.SimpleHTTPRequestHandler):
    """
    HTTP handler that serves UI and proxies API requests to backend.
    """

    ui_spec: UISpec | None = None
    generator: JSGenerator | None = None
    backend_url: str = "http://127.0.0.1:8000"
    test_mode: bool = False  # Disable hot-reload in test mode for Playwright compatibility
    hot_reload_manager: HotReloadManager | None = None  # For hot reload support
    dev_mode: bool = True  # Enable Dazzle Bar in dev mode (v0.8.5)
    api_route_prefixes: set[str] = set()  # Entity route prefixes (e.g., "/tasks", "/users")
    theme_css: str | None = None  # Generated theme CSS (v0.16.0)
    sitespec_data: dict[str, Any] | None = None  # SiteSpec for public site pages (v0.16.0)
    site_page_routes: set[str] = set()  # Routes that are site pages (/, /about, /pricing, etc.)

    def _is_api_path(self, path: str) -> bool:
        """Check if a path should be proxied to the backend API."""
        # Known system routes
        if path.startswith(("/auth/", "/files/", "/pages/", "/__test__/", "/_site/")):
            return True
        if path in ("/ui-spec", "/health"):
            return True
        # Entity CRUD routes (dynamically registered)
        for prefix in self.api_route_prefixes:
            if path == prefix or path.startswith(prefix + "/"):
                return True
        return False

    def _is_site_page_path(self, path: str) -> bool:
        """Check if a path is a site page route (/, /about, /pricing, etc.)."""
        if not self.site_page_routes:
            return False
        return path in self.site_page_routes

    def handle(self) -> None:
        """Handle request, suppressing connection reset errors from browser."""
        try:
            super().handle()
        except ConnectionResetError:
            # Browser closed connection early - common with prefetch/cancelled requests
            pass

    def do_GET(self) -> None:
        """Handle GET requests."""
        path = self.path.split("?")[0]

        # Proxy API requests to backend
        if self._is_api_path(path):
            self._proxy_request("GET")
        elif path.startswith("/dazzle/dev/"):
            # Proxy Dazzle Bar control plane requests (v0.8.5)
            self._proxy_request("GET")
        elif path == "/dazzle-bar.js":
            # Serve Dazzle Bar JavaScript (v0.8.5)
            self._serve_dazzle_bar()
        elif path == "/styles/dnr.css":
            # Serve bundled CSS (v0.8.11)
            self._serve_css()
        elif path.startswith("/assets/"):
            # Serve static assets (favicon, etc.) (v0.14.2)
            self._serve_asset(path)
        elif path == "/dnr-runtime.js":
            self._serve_runtime()
        elif path == "/app.js":
            self._serve_app()
        elif path == "/site.js":
            # Serve site page JavaScript (v0.16.0)
            self._serve_site_js()
        elif path == "/ui-spec.json":
            self._serve_spec()
        elif path == "/__hot-reload__":
            self._serve_hot_reload()
        elif path == "/docs" or path.startswith("/docs"):
            self._proxy_request("GET")
        elif path == "/openapi.json":
            self._proxy_request("GET")
        elif self._is_site_page_path(path):
            # Serve public site pages (v0.16.0)
            self._serve_site_page(path)
        else:
            # For SPA: serve HTML for all non-static routes
            # This enables path-based routing (e.g., /task/create, /task/123)
            self._serve_html()

    def do_POST(self) -> None:
        """Handle POST requests."""
        path = self.path.split("?")[0]
        if self._is_api_path(path):
            self._proxy_request("POST")
        elif path.startswith("/dazzle/dev/"):
            # Proxy Dazzle Bar control plane requests (v0.8.5)
            self._proxy_request("POST")
        else:
            self.send_error(405, "Method Not Allowed")

    def do_PUT(self) -> None:
        """Handle PUT requests."""
        path = self.path.split("?")[0]
        if self._is_api_path(path):
            self._proxy_request("PUT")
        else:
            self.send_error(405, "Method Not Allowed")

    def do_DELETE(self) -> None:
        """Handle DELETE requests."""
        path = self.path.split("?")[0]
        if self._is_api_path(path):
            self._proxy_request("DELETE")
        else:
            self.send_error(405, "Method Not Allowed")

    def do_PATCH(self) -> None:
        """Handle PATCH requests."""
        path = self.path.split("?")[0]
        if self._is_api_path(path):
            self._proxy_request("PATCH")
        else:
            self.send_error(405, "Method Not Allowed")

    def do_HEAD(self) -> None:
        """Handle HEAD requests (used by Dazzle Bar to check control plane availability)."""
        if self.path.startswith("/dazzle/dev/"):
            self._proxy_request("HEAD")
        else:
            # Default HEAD behavior for other paths
            super().do_HEAD()

    def _proxy_request(self, method: str) -> None:
        """Proxy request to backend server."""
        try:
            # Build backend URL
            url = f"{self.backend_url}{self.path}"

            # Read request body for non-GET requests
            body = None
            if method in ("POST", "PUT", "PATCH"):
                content_length = int(self.headers.get("Content-Length", 0))
                if content_length > 0:
                    body = self.rfile.read(content_length)

            # Build request
            req = urllib.request.Request(url, data=body, method=method)

            # Copy relevant headers
            for header in ["Content-Type", "Authorization", "Accept"]:
                if self.headers.get(header):
                    req.add_header(header, self.headers[header])

            # Make request
            with urllib.request.urlopen(req, timeout=30) as response:
                self.send_response(response.status)
                for key, value in response.getheaders():
                    if key.lower() not in ("transfer-encoding", "connection"):
                        self.send_header(key, value)
                self.end_headers()
                self.wfile.write(response.read())

        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            error_body = e.read() if e.fp else b"{}"
            self.wfile.write(error_body)

        except urllib.error.URLError as e:
            self.send_error(502, f"Backend unavailable: {e.reason}")

        except Exception as e:
            self.send_error(500, f"Proxy error: {str(e)}")

    def _serve_html(self) -> None:
        """Serve the main HTML page."""
        if not self.generator:
            self.send_error(500, "No UISpec loaded")
            return

        html = self.generator.generate_html(include_runtime=False)

        # Inject Dazzle Bar script in dev mode (v0.8.5)
        if self.dev_mode:
            dazzle_bar_script = '<script type="module" src="/dazzle-bar.js"></script>\n</body>'
            html = html.replace("</body>", dazzle_bar_script)

        # Inject hot reload script (disabled in test mode for Playwright compatibility)
        if not self.test_mode:
            hot_reload_script = """
<script>
(function() {
  const eventSource = new EventSource('/__hot-reload__');
  eventSource.onmessage = function(e) {
    if (e.data === 'reload') {
      window.location.reload();
    }
  };
})();
</script>
</body>
"""
            html = html.replace("</body>", hot_reload_script)
        # Fix script references - replace inline script placeholders with external references
        html = html.replace(
            "<script>\n\n  </script>\n  <script>",
            '<script src="/dnr-runtime.js"></script>\n  <script src="/app.js"></script>\n  <script>',
        )
        # Remove the now-empty inline app script that follows
        html = html.replace(
            '<script src="/app.js"></script>\n  <script>\n\n  </script>',
            '<script src="/app.js"></script>',
        )

        self._send_response(html, "text/html")

    def _get_generator(self) -> JSGenerator | None:
        """Get the current generator, checking hot reload manager for updates."""
        if self.hot_reload_manager:
            _, ui_spec = self.hot_reload_manager.get_specs()
            if ui_spec:
                return JSGenerator(ui_spec)
        return self.generator

    def _serve_runtime(self) -> None:
        """Serve the runtime JavaScript."""
        generator = self._get_generator()
        if not generator:
            self.send_error(500, "No UISpec loaded")
            return
        self._send_response(generator.generate_runtime(), "application/javascript")

    def _serve_app(self) -> None:
        """Serve the application JavaScript."""
        generator = self._get_generator()
        if not generator:
            self.send_error(500, "No UISpec loaded")
            return
        self._send_response(generator.generate_app_js(), "application/javascript")

    def _serve_spec(self) -> None:
        """Serve the UISpec as JSON."""
        generator = self._get_generator()
        if not generator:
            self.send_error(500, "No UISpec loaded")
            return
        self._send_response(generator.generate_spec_json(), "application/json")

    def _serve_dazzle_bar(self) -> None:
        """Serve the Dazzle Bar JavaScript bundle (v0.8.5)."""
        if not self.dev_mode:
            self.send_error(404, "Dazzle Bar not available in production mode")
            return

        try:
            from dazzle_dnr_ui.runtime.js_loader import get_dazzle_bar_js

            js_content = get_dazzle_bar_js()
            self._send_response(js_content, "application/javascript")
        except Exception as e:
            self.send_error(500, f"Failed to load Dazzle Bar: {e}")

    def _serve_css(self) -> None:
        """Serve the bundled CSS (v0.8.11, v0.16.0 theme support)."""
        try:
            from dazzle_dnr_ui.runtime.vite_generator import _get_bundled_css

            css_content = _get_bundled_css(theme_css=self.theme_css)
            self._send_response(css_content, "text/css")
        except Exception as e:
            self.send_error(500, f"Failed to load CSS: {e}")

    def _serve_site_page(self, path: str) -> None:
        """Serve a public site page (v0.16.0)."""
        from .site_renderer import render_site_page_html

        if not self.sitespec_data:
            self.send_error(404, "No site configuration")
            return

        # Check if this is an auth page
        auth_pages = self.sitespec_data.get("auth_pages", {})
        login_page = auth_pages.get("login", {})
        signup_page = auth_pages.get("signup", {})

        if path == login_page.get("route", "/login"):
            self._serve_auth_page("login")
            return
        if path == signup_page.get("route", "/signup"):
            self._serve_auth_page("signup")
            return

        html = render_site_page_html(self.sitespec_data, path)

        # Inject Dazzle Bar script in dev mode (v0.23.0 - site pages too)
        if self.dev_mode:
            dazzle_bar_script = '<script type="module" src="/dazzle-bar.js"></script>\n</body>'
            html = html.replace("</body>", dazzle_bar_script)

        self._send_response(html, "text/html")

    def _serve_site_js(self) -> None:
        """Serve the site page JavaScript (v0.16.0)."""
        js = """
/**
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

        let ctaHtml = '';
        if (primaryCta) {
            // Use DaisyUI btn classes for consistency with workspace
            ctaHtml += `<a href="${primaryCta.href || '#'}" class="btn btn-primary">${primaryCta.label || 'Get Started'}</a>`;
        }
        if (secondaryCta) {
            ctaHtml += `<a href="${secondaryCta.href || '#'}" class="btn btn-secondary btn-outline">${secondaryCta.label || 'Learn More'}</a>`;
        }

        return `
            <section class="dz-section dz-section-hero">
                <div class="dz-section-content">
                    <h1>${headline}</h1>
                    ${subhead ? `<p class="dz-subhead">${subhead}</p>` : ''}
                    ${ctaHtml ? `<div class="dz-cta-group">${ctaHtml}</div>` : ''}
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
            // Use DaisyUI btn classes - use btn-secondary for highlighted tiers (white on colored bg)
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
        // For markdown content, we'll render it as-is (assuming pre-rendered HTML)
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

        // Handle markdown page content
        if (pageData.content && pageData.type === 'markdown') {
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
        self._send_response(js, "application/javascript")

    def _serve_auth_page(self, page_type: str) -> None:
        """Serve a login or signup page (v0.16.0)."""
        from .site_renderer import render_auth_page_html

        if not self.sitespec_data:
            self.send_error(404, "No site configuration")
            return

        html = render_auth_page_html(self.sitespec_data, page_type)

        # Inject Dazzle Bar script in dev mode (v0.23.0 - auth pages too)
        if self.dev_mode:
            dazzle_bar_script = '<script type="module" src="/dazzle-bar.js"></script>\n</body>'
            html = html.replace("</body>", dazzle_bar_script)

        self._send_response(html, "text/html")

    def _serve_asset(self, path: str) -> None:
        """Serve static assets from static/assets/ directory (v0.14.2)."""
        try:
            # Get filename from path (e.g., /assets/dazzle-favicon.svg -> dazzle-favicon.svg)
            filename = path.removeprefix("/assets/")
            if not filename or ".." in filename or filename.startswith("/"):
                self.send_error(404, "Asset not found")
                return

            # Load from static/assets directory
            static_dir = Path(__file__).parent / "static" / "assets"
            asset_path = static_dir / filename

            if not asset_path.exists() or not asset_path.is_file():
                self.send_error(404, f"Asset not found: {filename}")
                return

            # Determine content type based on extension
            content_types = {
                ".svg": "image/svg+xml",
                ".png": "image/png",
                ".ico": "image/x-icon",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".gif": "image/gif",
                ".webp": "image/webp",
            }
            ext = asset_path.suffix.lower()
            content_type = content_types.get(ext, "application/octet-stream")

            # Read and send the asset
            data = asset_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "public, max-age=86400")  # Cache for 1 day
            self.end_headers()
            self.wfile.write(data)

        except Exception as e:
            self.send_error(500, f"Failed to load asset: {e}")

    def _serve_hot_reload(self) -> None:
        """Serve hot reload SSE endpoint."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        # Register with hot reload manager if available
        reload_event = None
        if self.hot_reload_manager:
            reload_event = self.hot_reload_manager.register_sse_client()

        try:
            while True:
                # Check if reload was triggered
                if reload_event and reload_event.is_set():
                    self.wfile.write(b"data: reload\n\n")
                    self.wfile.flush()
                    reload_event.clear()
                else:
                    # Send keepalive
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()

                time.sleep(0.5)
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            # Unregister from hot reload manager
            if self.hot_reload_manager and reload_event:
                self.hot_reload_manager.unregister_sse_client(reload_event)

    def _send_response(self, content: str, content_type: str) -> None:
        """Send HTTP response."""
        data = content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: Any) -> None:
        """Log HTTP requests."""
        path = args[0] if args else ""
        status = args[1] if len(args) > 1 else ""
        clean_path = path.split("?")[0]
        if self._is_api_path(clean_path) or clean_path.startswith("/dazzle/dev/"):
            print(f"[DNR API] {path} -> {status}")
        elif path != "/__hot-reload__":
            print(f"[DNR UI] {path} -> {status}")


# =============================================================================
# Combined Server
# =============================================================================


class DNRCombinedServer:
    """
    Combined development server for DNR applications.

    Runs both backend and frontend in a single process with API proxying.
    """

    def __init__(
        self,
        backend_spec: BackendSpec,
        ui_spec: UISpec,
        backend_host: str = "127.0.0.1",
        backend_port: int = 8000,
        frontend_host: str = "127.0.0.1",
        frontend_port: int = 3000,
        db_path: str | Path | None = None,
        enable_test_mode: bool = False,
        enable_dev_mode: bool = True,  # Enable Dazzle Bar (v0.24.0 - env-aware)
        enable_auth: bool = True,  # Enable authentication by default
        auth_config: Any = None,  # AuthConfig from manifest (for OAuth providers)
        enable_watch: bool = False,
        watch_source: bool = False,
        project_root: Path | None = None,
        personas: list[dict[str, Any]] | None = None,
        scenarios: list[dict[str, Any]] | None = None,
        sitespec_data: dict[str, Any] | None = None,
        theme_preset: str = "saas-default",
        theme_overrides: dict[str, Any] | None = None,
    ):
        """
        Initialize the combined server.

        Args:
            backend_spec: Backend specification
            ui_spec: UI specification
            backend_host: Backend server host
            backend_port: Backend server port
            frontend_host: Frontend server host
            frontend_port: Frontend server port
            db_path: Path to SQLite database
            enable_test_mode: Enable test endpoints (/__test__/*)
            enable_dev_mode: Enable Dazzle Bar (v0.24.0 - controlled by DAZZLE_ENV)
            enable_auth: Enable authentication endpoints (/auth/*)
            auth_config: Full auth configuration from manifest (for OAuth providers)
            enable_watch: Enable hot reload file watching
            watch_source: Also watch framework source files (Python, CSS, JS)
            project_root: Project root directory (required for hot reload)
            personas: List of persona configurations for Dazzle Bar (v0.8.5)
            scenarios: List of scenario configurations for Dazzle Bar (v0.8.5)
            sitespec_data: SiteSpec data as dict for public site shell (v0.16.0)
            theme_preset: Theme preset name (v0.16.0)
            theme_overrides: Custom theme token overrides (v0.16.0)
        """
        self.backend_spec = backend_spec
        self.ui_spec = ui_spec
        self.backend_host = backend_host
        self.backend_port = backend_port
        self.frontend_host = frontend_host
        self.frontend_port = frontend_port
        self.db_path = Path(db_path) if db_path else Path(".dazzle/data.db")
        self.enable_test_mode = enable_test_mode
        self.enable_dev_mode = enable_dev_mode
        self.enable_auth = enable_auth
        self.auth_config = auth_config
        self.enable_watch = enable_watch
        self.watch_source = watch_source
        self.project_root = project_root or Path.cwd()
        self.personas = personas or []
        self.scenarios = scenarios or []
        self.sitespec_data = sitespec_data
        self.theme_preset = theme_preset
        self.theme_overrides = theme_overrides or {}

        self._backend_thread: threading.Thread | None = None
        self._frontend_server: socketserver.TCPServer | None = None
        self._hot_reload_manager: HotReloadManager | None = None

    def start(self) -> None:
        """
        Start both backend and frontend servers.

        The backend runs in a background thread, frontend blocks.
        """
        # Initialize logging (JSONL format for LLM agents)
        try:
            from dazzle_dnr_back.runtime.logging import setup_logging

            log_dir = self.db_path.parent / "logs"
            setup_logging(log_dir=log_dir)
        except ImportError:
            pass  # Logging module not available

        print("\n" + "=" * 60)
        print("  DAZZLE NATIVE RUNTIME (DNR)")
        print("=" * 60)
        print()

        # Initialize hot reload if enabled
        if self.enable_watch:
            self._start_hot_reload()

        # Start backend in background thread
        self._start_backend()

        # Start frontend (blocking)
        self._start_frontend()

    def _start_hot_reload(self) -> None:
        """Initialize and start hot reload file watching."""
        from dazzle_dnr_ui.runtime.hot_reload import (
            HotReloadManager,
            create_reload_callback,
        )

        reload_callback = create_reload_callback(self.project_root)
        self._hot_reload_manager = HotReloadManager(
            project_root=self.project_root,
            on_reload=reload_callback,
            watch_source=self.watch_source,
        )

        # Set initial specs
        self._hot_reload_manager.set_specs(self.backend_spec, self.ui_spec)

        # Start watching
        self._hot_reload_manager.start()
        msg = "DSL files"
        if self.watch_source:
            msg += " + source files"
        print(f"[DNR] Hot reload: ENABLED (watching {msg})")

    def _start_backend(self) -> None:
        """Start the FastAPI backend in a background thread."""
        try:
            from dazzle_dnr_back.runtime.server import DNRBackendApp
        except ImportError:
            print("[DNR] Warning: dazzle_dnr_back not available, skipping backend")
            return

        # Capture flags for closure
        enable_test_mode = self.enable_test_mode
        enable_auth = self.enable_auth
        auth_config = self.auth_config
        personas = self.personas
        scenarios = self.scenarios
        sitespec_data = self.sitespec_data
        project_root = self.project_root

        def run_backend() -> None:
            try:
                import uvicorn

                app_builder = DNRBackendApp(
                    self.backend_spec,
                    db_path=self.db_path,
                    use_database=True,
                    enable_test_mode=enable_test_mode,
                    enable_auth=enable_auth,
                    auth_config=auth_config,
                    enable_dev_mode=self.enable_dev_mode,  # v0.24.0: env-aware
                    personas=personas,
                    scenarios=scenarios,
                    sitespec_data=sitespec_data,
                    project_root=project_root,
                )
                app = app_builder.build()

                config = uvicorn.Config(
                    app,
                    host=self.backend_host,
                    port=self.backend_port,
                    log_level="warning",
                )
                server = uvicorn.Server(config)
                server.run()
            except ImportError:
                print("[DNR] Warning: uvicorn not available, backend disabled")
            except OSError as e:
                if e.errno == 48 or "address already in use" in str(e).lower():
                    print(f"\n[DNR] ERROR: Backend port {self.backend_port} is already in use.")
                    print(
                        "[DNR] Stop the other process or use --api-port to specify a different port."
                    )
                    print(f"[DNR] Hint: lsof -i :{self.backend_port} | grep LISTEN")
                else:
                    print(f"[DNR] Backend error: {e}")
            except Exception as e:
                print(f"[DNR] Backend error: {e}")

        self._backend_thread = threading.Thread(target=run_backend, daemon=True)
        self._backend_thread.start()

        backend_url = f"http://{self.backend_host}:{self.backend_port}"
        docs_url = f"{backend_url}/docs"
        print(f"[DNR] Backend:  {_clickable_url(backend_url)}")
        print(f"[DNR] API Docs: {_clickable_url(docs_url)}")
        print(f"[DNR] Database: {self.db_path}")
        if self.enable_test_mode:
            print("[DNR] Test endpoints: /__test__/* (enabled)")
        if self.enable_auth:
            print("[DNR] Authentication: ENABLED (/auth/* endpoints available)")
        print()

    def _start_frontend(self) -> None:
        """Start the frontend dev server (blocking)."""
        # Configure handler
        DNRCombinedHandler.ui_spec = self.ui_spec
        DNRCombinedHandler.generator = JSGenerator(self.ui_spec)
        DNRCombinedHandler.backend_url = f"http://{self.backend_host}:{self.backend_port}"
        DNRCombinedHandler.test_mode = self.enable_test_mode
        DNRCombinedHandler.dev_mode = self.enable_dev_mode  # v0.24.0: env-aware
        DNRCombinedHandler.hot_reload_manager = self._hot_reload_manager

        # Build API route prefixes from backend spec entities
        api_prefixes: set[str] = set()
        for entity in self.backend_spec.entities:
            api_prefixes.add(f"/{to_api_plural(entity.name)}")
        DNRCombinedHandler.api_route_prefixes = api_prefixes

        # Generate theme CSS (v0.16.0)
        try:
            from dazzle_dnr_ui.themes import generate_theme_css, resolve_theme

            theme = resolve_theme(
                preset_name=self.theme_preset,
                manifest_overrides=self.theme_overrides,
            )
            DNRCombinedHandler.theme_css = generate_theme_css(theme)
        except ImportError:
            DNRCombinedHandler.theme_css = None

        # Configure site pages (v0.16.0)
        DNRCombinedHandler.sitespec_data = self.sitespec_data
        if self.sitespec_data:
            # Build set of site page routes
            site_routes: set[str] = set()
            for page in self.sitespec_data.get("pages", []):
                route = page.get("route")
                if route:
                    site_routes.add(route)
            # Add legal page routes
            legal = self.sitespec_data.get("legal", {})
            if legal.get("terms"):
                site_routes.add(legal["terms"].get("route", "/terms"))
            if legal.get("privacy"):
                site_routes.add(legal["privacy"].get("route", "/privacy"))
            # Add auth page routes (login/signup)
            auth_pages = self.sitespec_data.get("auth_pages", {})
            login_page = auth_pages.get("login", {})
            signup_page = auth_pages.get("signup", {})
            if login_page.get("enabled", True) and login_page.get("mode") == "generated":
                site_routes.add(login_page.get("route", "/login"))
            if signup_page.get("enabled", True) and signup_page.get("mode") == "generated":
                site_routes.add(signup_page.get("route", "/signup"))
            DNRCombinedHandler.site_page_routes = site_routes
            if site_routes:
                print(f"[DNR] Site pages: {', '.join(sorted(site_routes))}")
        else:
            DNRCombinedHandler.site_page_routes = set()

        # Create server with threading for concurrent SSE connections
        socketserver.TCPServer.allow_reuse_address = True

        # Use ThreadingTCPServer for concurrent hot reload connections
        class ThreadingTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
            daemon_threads = True

        try:
            self._frontend_server = ThreadingTCPServer(
                (self.frontend_host, self.frontend_port),
                DNRCombinedHandler,
            )
        except OSError as e:
            if e.errno == 48 or "address already in use" in str(e).lower():
                print(f"\n[DNR] ERROR: Port {self.frontend_port} is already in use.")
                print("[DNR] Stop the other process or use --port to specify a different port.")
                print(f"[DNR] Hint: lsof -i :{self.frontend_port} | grep LISTEN")
                raise SystemExit(1)
            raise

        frontend_url = f"http://{self.frontend_host}:{self.frontend_port}"
        print(f"[DNR] Frontend: {_clickable_url(frontend_url)}")
        print()
        print("Press Ctrl+C to stop")
        print("-" * 60)
        print()

        try:
            self._frontend_server.serve_forever()
        except KeyboardInterrupt:
            print("\n[DNR] Shutting down...")
        finally:
            if self._hot_reload_manager:
                self._hot_reload_manager.stop()
            self._frontend_server.shutdown()

    def stop(self) -> None:
        """Stop both servers."""
        if self._frontend_server:
            self._frontend_server.shutdown()


# =============================================================================
# Convenience Functions
# =============================================================================


def run_combined_server(
    backend_spec: BackendSpec,
    ui_spec: UISpec,
    backend_port: int = 8000,
    frontend_port: int = 3000,
    db_path: str | Path | None = None,
    enable_test_mode: bool = False,
    enable_dev_mode: bool = True,  # v0.24.0: Enable Dazzle Bar (env-aware)
    enable_auth: bool = True,  # Enable authentication by default
    auth_config: Any = None,  # AuthConfig from manifest (for OAuth providers)
    host: str = "127.0.0.1",
    enable_watch: bool = False,
    watch_source: bool = False,
    project_root: Path | None = None,
    personas: list[dict[str, Any]] | None = None,
    scenarios: list[dict[str, Any]] | None = None,
    sitespec_data: dict[str, Any] | None = None,
    theme_preset: str = "saas-default",
    theme_overrides: dict[str, Any] | None = None,
) -> None:
    """
    Run a combined DNR development server.

    Args:
        backend_spec: Backend specification
        ui_spec: UI specification
        backend_port: Backend server port
        frontend_port: Frontend server port
        db_path: Path to SQLite database
        enable_test_mode: Enable test endpoints (/__test__/*)
        enable_dev_mode: Enable Dazzle Bar (v0.24.0 - controlled by DAZZLE_ENV)
        enable_auth: Enable authentication endpoints (/auth/*)
        auth_config: Full auth configuration from manifest (for OAuth providers)
        host: Host to bind both servers to
        enable_watch: Enable hot reload file watching
        watch_source: Also watch framework source files (Python, CSS, JS)
        project_root: Project root directory (for hot reload)
        personas: List of persona configurations for Dazzle Bar (v0.8.5)
        scenarios: List of scenario configurations for Dazzle Bar (v0.8.5)
        sitespec_data: SiteSpec data as dict for public site shell (v0.16.0)
        theme_preset: Theme preset name (v0.16.0)
        theme_overrides: Custom theme token overrides (v0.16.0)
    """
    server = DNRCombinedServer(
        backend_spec=backend_spec,
        ui_spec=ui_spec,
        backend_host=host,
        backend_port=backend_port,
        frontend_host=host,
        frontend_port=frontend_port,
        db_path=db_path,
        enable_test_mode=enable_test_mode,
        enable_dev_mode=enable_dev_mode,
        enable_auth=enable_auth,
        auth_config=auth_config,
        enable_watch=enable_watch,
        watch_source=watch_source,
        project_root=project_root,
        personas=personas,
        scenarios=scenarios,
        sitespec_data=sitespec_data,
        theme_preset=theme_preset,
        theme_overrides=theme_overrides,
    )
    server.start()


def run_frontend_only(
    ui_spec: UISpec,
    host: str = "127.0.0.1",
    port: int = 3000,
    backend_url: str = "http://127.0.0.1:8000",
) -> None:
    """
    Run only the frontend dev server with API proxy.

    Args:
        ui_spec: UI specification
        host: Host to bind to
        port: Port to bind to
        backend_url: URL of the backend to proxy to
    """
    # Configure handler
    DNRCombinedHandler.ui_spec = ui_spec
    DNRCombinedHandler.generator = JSGenerator(ui_spec)
    DNRCombinedHandler.backend_url = backend_url

    socketserver.TCPServer.allow_reuse_address = True
    try:
        server = socketserver.TCPServer((host, port), DNRCombinedHandler)
    except OSError as e:
        if e.errno == 48 or "address already in use" in str(e).lower():
            print(f"\n[DNR-UI] ERROR: Port {port} is already in use.")
            print("[DNR-UI] Stop the other process or use --port to specify a different port.")
            print(f"[DNR-UI] Hint: lsof -i :{port} | grep LISTEN")
            raise SystemExit(1)
        raise

    frontend_url = f"http://{host}:{port}"
    print(f"[DNR-UI] Frontend server: {_clickable_url(frontend_url)}")
    print(f"[DNR-UI] Backend proxy:   {_clickable_url(backend_url)}")
    print("[DNR-UI] Press Ctrl+C to stop")
    print()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[DNR-UI] Shutting down...")
    finally:
        server.shutdown()


def run_backend_only(
    backend_spec: BackendSpec,
    host: str = "127.0.0.1",
    port: int = 8000,
    db_path: str | Path | None = None,
    enable_test_mode: bool = False,
    enable_dev_mode: bool = True,  # v0.24.0: Enable Dazzle Bar (env-aware)
    enable_graphql: bool = False,
    sitespec_data: dict[str, Any] | None = None,
    project_root: Path | None = None,
) -> None:
    """
    Run only the FastAPI backend server.

    Args:
        backend_spec: Backend specification
        host: Host to bind to
        port: Port to bind to
        db_path: Path to SQLite database
        enable_test_mode: Enable test endpoints (/__test__/*)
        enable_dev_mode: Enable Dazzle Bar control plane (v0.24.0 - controlled by DAZZLE_ENV)
        enable_graphql: Enable GraphQL endpoint at /graphql
        sitespec_data: SiteSpec data as dict for public site shell (v0.16.0)
        project_root: Project root directory for content file loading
    """
    try:
        import uvicorn

        from dazzle_dnr_back.runtime.server import DNRBackendApp
    except ImportError as e:
        print(f"[DNR] Error: Required dependencies not available: {e}")
        print("[DNR] Install with: pip install fastapi uvicorn dazzle-dnr-back")
        return

    print("\n" + "=" * 60)
    print("  DAZZLE NATIVE RUNTIME (DNR) - Backend Only")
    print("=" * 60)
    print()

    app_builder = DNRBackendApp(
        backend_spec,
        db_path=db_path,
        use_database=True,
        enable_test_mode=enable_test_mode,
        enable_dev_mode=enable_dev_mode,
        sitespec_data=sitespec_data,
        project_root=project_root,
    )
    app = app_builder.build()

    # Mount GraphQL if enabled
    if enable_graphql:
        try:
            from dazzle_dnr_back.graphql import mount_graphql

            mount_graphql(
                app,
                backend_spec,
                services=app_builder.services,
                repositories=app_builder.repositories,
            )
            graphql_url = f"http://{host}:{port}/graphql"
            print(f"[DNR] GraphQL: {_clickable_url(graphql_url)}")
        except ImportError:
            print("[DNR] Warning: GraphQL not available (install strawberry-graphql)")

    backend_url = f"http://{host}:{port}"
    docs_url = f"{backend_url}/docs"
    print(f"[DNR] Backend:  {_clickable_url(backend_url)}")
    print(f"[DNR] API Docs: {_clickable_url(docs_url)}")
    print(f"[DNR] Database: {db_path}")
    if enable_test_mode:
        print("[DNR] Test endpoints: /__test__/* (enabled)")
    print()
    print("Press Ctrl+C to stop")
    print("-" * 60)
    print()

    try:
        uvicorn.run(app, host=host, port=port, log_level="info")
    except KeyboardInterrupt:
        print("\n[DNR] Shutting down...")
    except OSError as e:
        if e.errno == 48 or "address already in use" in str(e).lower():
            print(f"\n[DNR] ERROR: Port {port} is already in use.")
            print("[DNR] Stop the other process or use --api-port to specify a different port.")
            print(f"[DNR] Hint: lsof -i :{port} | grep LISTEN")
        else:
            raise
