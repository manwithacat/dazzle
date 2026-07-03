"""Typed in-app error views (Phase 2.B full, v0.67.40; HaTchi-MaXchi Phase 3+).

Replaces the legacy `app/403.html` and `app/404.html` Jinja templates
and adds a typed in-app 500 (which had no template before — it fell
through to Starlette's plain-text default).

Architecturally these are "app-shell-lite" — they render the error
inside a typed Page WITHOUT the full authenticated app shell
(sidebar, persona dropdown, full navbar). Since #1536 the views use
the designed error shape (TASTE-8): a centered card carrying a
registry-icon EmptyState + primary CTA, instead of a bare text stack
— the raw stack scored 1.3/10 with the blind taste judges when it
rendered at all (most apps served raw JSON before #1536).
"""

from __future__ import annotations

from typing import Any

from dazzle.render.fragment import (
    URL,
    Card,
    EmptyState,
    Link,
    Page,
    Stack,
    Text,
)


def _common_assets() -> tuple[tuple[str, ...], tuple[str, ...]]:
    return (
        ("/static/dist/dazzle.min.css",),
        ("/static/dist/dazzle.min.js",),
    )


def _error_page(
    *,
    page_title: str,
    icon: str,
    headline: str,
    description: str,
    extra_children: tuple[Any, ...] = (),
    back_url: str = "",
    back_label: str = "",
    css_links: tuple[str, ...],
    js_scripts: tuple[str, ...],
) -> Page:
    """Shared error-page shell: one centered card, icon + copy + CTAs.

    The centering CSS keys on the `.dz-page > .dz-stack > .dz-card`
    error shape (see components/fragment-primitives.css) — all six
    error views (app + marketing) share it.
    """
    if not css_links or not js_scripts:
        default_css, default_js = _common_assets()
        css_links = css_links or default_css
        js_scripts = js_scripts or default_js

    card_children: list[Any] = [
        EmptyState(
            icon=icon,
            title=headline,
            description=description,
            action=Link(label="Go to Dashboard", href=URL("/app")),
        ),
        *extra_children,
    ]
    if back_url:
        card_children.append(Link(label=back_label or "Back", href=URL(back_url)))

    return Page(
        title=page_title,
        body=Stack(children=(Card(body=Stack(children=tuple(card_children))),)),
        css_links=css_links,
        js_scripts=js_scripts,
    )


def build_app_403_view(
    *,
    app_name: str,
    message: str = "",
    forbidden_detail: dict[str, Any] | None = None,
    back_url: str = "",
    back_label: str = "",
    css_links: tuple[str, ...] = (),
    js_scripts: tuple[str, ...] = (),
) -> Page:
    """Render the in-app 403 page.

    `forbidden_detail` carries the structured disclosure from
    `_forbidden_detail` (issue #808): `entity`, `operation`,
    `permitted_personas`, `current_roles`. When present, the view
    renders a "Signed in as X; requires Y" panel so the user can
    self-diagnose rather than seeing a bare "Forbidden".

    `back_url` + `back_label` are computed by `_compute_back_affordance`
    at the call site and rendered as a "Back" link when present.
    """
    default_message = "You don't have permission to access this page."

    extra: list[Any] = []
    if forbidden_detail:
        if forbidden_detail.get("entity"):
            extra.append(Text(body=f"Entity: {forbidden_detail['entity']}", tone="muted"))
        if forbidden_detail.get("operation"):
            extra.append(Text(body=f"Operation: {forbidden_detail['operation']}", tone="muted"))
        permitted = forbidden_detail.get("permitted_personas") or []
        if permitted:
            extra.append(Text(body=f"Allowed for: {', '.join(permitted)}", tone="muted"))
        current = forbidden_detail.get("current_roles") or []
        if current:
            extra.append(Text(body=f"Your roles: {', '.join(current)}", tone="muted"))
        else:
            extra.append(Text(body="Your roles: (none)", tone="muted"))

    return _error_page(
        page_title=f"Access Denied — {app_name}",
        icon="lock",
        headline="403 — Access denied",
        description=message or default_message,
        extra_children=tuple(extra),
        back_url=back_url,
        back_label=back_label,
        css_links=css_links,
        js_scripts=js_scripts,
    )


def build_app_404_view(
    *,
    app_name: str,
    message: str = "",
    suggestions: list[dict[str, str]] | None = None,
    back_url: str = "",
    back_label: str = "",
    css_links: tuple[str, ...] = (),
    js_scripts: tuple[str, ...] = (),
) -> Page:
    """Render the in-app 404 page.

    `suggestions` is the list of `{url, label}` plausible alternative
    paths computed by `_compute_404_suggestions` (issue #811). When
    present, the view renders them as a "Did you mean..." block so a
    typo doesn't leave the user stranded.
    """
    default_message = "The page you're looking for doesn't exist."

    extra: list[Any] = []
    if suggestions:
        extra.append(Text(body="Did you mean:", tone="muted"))
        for sug in suggestions:
            url = sug.get("url", "")
            label = sug.get("label", "")
            if url and label:
                extra.append(Link(label=f"{url} — {label}", href=URL(url)))

    return _error_page(
        page_title=f"Page Not Found — {app_name}",
        icon="compass",
        headline="404 — Page not found",
        description=message or default_message,
        extra_children=tuple(extra),
        back_url=back_url,
        back_label=back_label,
        css_links=css_links,
        js_scripts=js_scripts,
    )


def build_app_500_view(
    *,
    app_name: str,
    back_url: str = "",
    back_label: str = "",
    css_links: tuple[str, ...] = (),
    js_scripts: tuple[str, ...] = (),
) -> Page:
    """Render the in-app 500 page.

    Same CWE-209 discipline as the marketing 500: no exception
    details ever surface in the body. The user gets a generic apology
    + a back-to-dashboard CTA. The traceback is logged via
    `dazzle.errors` by the handler that calls this view.
    """
    return _error_page(
        page_title=f"Something went wrong — {app_name}",
        icon="triangle-alert",
        headline="500 — Something went wrong",
        description=(
            "Something went wrong on our end. We've been notified — please try again in a moment."
        ),
        back_url=back_url,
        back_label=back_label,
        css_links=css_links,
        js_scripts=js_scripts,
    )
