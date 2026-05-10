"""Typed-Fragment error views.

Phase 2.A (v0.67.34): replaced the marketing-site Jinja error
templates (`site/403.html` and `site/404.html`) with typed-Fragment
Page composition.

Phase 2.B partial (v0.67.36): added `build_site_500_view` to
cover unhandled-exception responses (the pre-2.B path was Starlette's
plain-text "Internal Server Error", which leaked nothing about
branding and skipped the framework's CSS chrome entirely).

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


def build_site_500_view(
    *,
    product_name: str,
    message: str = "",
    css_links: tuple[str, ...] = ("/static/dist/dazzle.min.css",),
    js_scripts: tuple[str, ...] = ("/static/dist/dazzle.min.js",),
) -> Page:
    """Render the marketing-site 500 page (Phase 2.B partial, v0.67.36).

    Shown when an unhandled exception bubbles up to the framework's
    exception layer. The page deliberately offers two CTAs — "Go
    Home" and "Try again" (which reloads `/` rather than the
    failing route, since retrying the failure isn't usually
    productive). `message` is accepted for forward symmetry but is
    NOT rendered into the page body — surfacing exception details
    to the user leaks internals (CWE-209) and the message string
    at the call site is usually a raw exception ``str()``.
    """
    description = (
        "Something went wrong on our end. We've been notified — please try again in a moment."
    )
    body_children: list[Any] = [
        Link(label=product_name, href=URL("/")),
        Heading(body="500", level=1),
        Text(body=description),
        Link(label="Try again", href=URL("/")),
        Link(label="Go Home", href=URL("/")),
    ]
    _ = message  # see docstring — intentionally not rendered (CWE-209 guard)
    return Page(
        title=f"Something went wrong — {product_name}",
        body=Stack(children=tuple(body_children)),
        css_links=css_links,
        js_scripts=js_scripts,
    )
