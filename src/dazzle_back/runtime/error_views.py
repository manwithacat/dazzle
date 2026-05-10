"""Typed-Fragment error views (Phase 2.A, v0.67.34).

Replaces the legacy marketing-site Jinja error templates
(`site/403.html` and `site/404.html`) with typed-Fragment Page
composition. Same shape as the Phase 1 auth views in
`runtime/auth/auth_views.py`: explicit primitives, no template
inheritance.

In-app 403/404 (`app/403.html`, `app/404.html`) still render via
the existing Jinja path because they're embedded in the
authenticated app shell. Migrating those is part of the broader
app-shell typed-Fragment work, not this ship.
"""

from __future__ import annotations

from typing import Any

from dazzle.render.fragment import (
    URL,
    EmptyState,
    Heading,
    Link,
    Page,
    Stack,
    Text,
)


def build_site_404_view(
    *,
    product_name: str,
    message: str = "",
    css_links: tuple[str, ...] = ("/static/dist/dazzle.min.css",),
    js_scripts: tuple[str, ...] = ("/static/dist/dazzle.min.js",),
) -> Page:
    """Render the marketing-site 404 page.

    Replaces `site/404.html` byte-for-message equivalence: the
    legacy template renders an `<h1>404</h1>` + "The page you're
    looking for doesn't exist." + a "Go Home" CTA. The typed view
    uses the same copy with an EmptyState for the headline +
    description and a single "Go Home" Link below.
    """
    title = "404"
    description = message or "The page you're looking for doesn't exist."
    return Page(
        title=f"Page Not Found — {product_name}",
        body=Stack(
            children=(
                Link(label=product_name, href=URL("/")),
                EmptyState(title=title, description=description),
                Link(label="Go Home", href=URL("/")),
            )
        ),
        css_links=css_links,
        js_scripts=js_scripts,
    )


def build_site_403_view(
    *,
    product_name: str,
    message: str = "",
    forbidden_detail: dict[str, Any] | None = None,
    css_links: tuple[str, ...] = ("/static/dist/dazzle.min.css",),
    js_scripts: tuple[str, ...] = ("/static/dist/dazzle.min.js",),
) -> Page:
    """Render the marketing-site 403 page.

    The legacy `site/403.html` template doesn't render
    `forbidden_detail` — only `app/403.html` does (the app-shell
    variant deeper in the system, kept on Jinja for now). The
    typed marketing variant matches the legacy behavior:
    headline + message + two CTAs ("Go to Dashboard" and "Go
    Home"). ``forbidden_detail`` is accepted as a no-op for
    handler-call symmetry with the app-shell renderer; the
    marketing context can't usefully render persona disclosure.
    """
    title = "403"
    description = message or "You don't have permission to access this page."
    body_children: list[Any] = [
        Link(label=product_name, href=URL("/")),
        Heading(body=title, level=1),
        Text(body=description),
        Link(label="Go to Dashboard", href=URL("/app")),
        Link(label="Go Home", href=URL("/")),
    ]
    if forbidden_detail:
        # No-op: marketing-site context doesn't render persona
        # disclosure. Accepting the kwarg keeps the call site
        # symmetric with the app-shell renderer so future migration
        # doesn't need handler-signature surgery.
        pass
    return Page(
        title=f"Access Denied — {product_name}",
        body=Stack(children=tuple(body_children)),
        css_links=css_links,
        js_scripts=js_scripts,
    )
