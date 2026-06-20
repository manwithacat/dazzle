"""Typed in-app error views (Phase 2.B full, v0.67.40).

Replaces the legacy `app/403.html` and `app/404.html` Jinja templates
and adds a typed in-app 500 (which had no template before — it fell
through to Starlette's plain-text default).

Architecturally these are "app-shell-lite" — they render the error
inside a typed Page WITHOUT the full authenticated app shell
(sidebar, persona dropdown, full navbar). The legacy templates
embedded the app shell but the helper that built their context
(`_render_app_shell_error`) intentionally passed empty `nav_items` /
`nav_groups` / `user_email`, so the sidebar already rendered empty
in practice. Lifting the rendering layer out of the app shell is a
net improvement: the error page stops depending on the much bigger
`layouts/app_shell.html` Jinja chain.

The full app-shell typed-Fragment migration (#TBD) is the next
substrate piece — once it lands, these views can grow back into
embedded shell views if the empty-sidebar UX turns out to be too
jarring.
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


def _common_assets() -> tuple[tuple[str, ...], tuple[str, ...]]:
    return (
        ("/static/dist/dazzle.min.css",),
        ("/static/dist/dazzle.min.js",),
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
    if not css_links or not js_scripts:
        default_css, default_js = _common_assets()
        css_links = css_links or default_css
        js_scripts = js_scripts or default_js

    body_children: list[Any] = [
        Link(label=app_name, href=URL("/app")),
        Heading(body="403", level=1),
        Text(body=message or default_message),
    ]

    if forbidden_detail:
        if forbidden_detail.get("entity"):
            body_children.append(Text(body=f"Entity: {forbidden_detail['entity']}", tone="muted"))
        if forbidden_detail.get("operation"):
            body_children.append(
                Text(
                    body=f"Operation: {forbidden_detail['operation']}",
                    tone="muted",
                )
            )
        permitted = forbidden_detail.get("permitted_personas") or []
        if permitted:
            body_children.append(Text(body=f"Allowed for: {', '.join(permitted)}", tone="muted"))
        current = forbidden_detail.get("current_roles") or []
        if current:
            body_children.append(Text(body=f"Your roles: {', '.join(current)}", tone="muted"))
        else:
            body_children.append(Text(body="Your roles: (none)", tone="muted"))

    if back_url:
        body_children.append(Link(label=back_label or "Back", href=URL(back_url)))
    body_children.append(Link(label="Go to Dashboard", href=URL("/app")))

    return Page(
        title=f"Access Denied — {app_name}",
        body=Stack(children=tuple(body_children)),
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
    if not css_links or not js_scripts:
        default_css, default_js = _common_assets()
        css_links = css_links or default_css
        js_scripts = js_scripts or default_js

    body_children: list[Any] = [
        Link(label=app_name, href=URL("/app")),
        Heading(body="404", level=1),
        Text(body=message or default_message),
    ]

    if suggestions:
        body_children.append(Text(body="Did you mean:", tone="muted"))
        for sug in suggestions:
            url = sug.get("url", "")
            label = sug.get("label", "")
            if url and label:
                body_children.append(Link(label=f"{url} — {label}", href=URL(url)))

    if back_url:
        body_children.append(Link(label=back_label or "Back", href=URL(back_url)))
    body_children.append(Link(label="Go to Dashboard", href=URL("/app")))

    return Page(
        title=f"Page Not Found — {app_name}",
        body=Stack(children=tuple(body_children)),
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
    if not css_links or not js_scripts:
        default_css, default_js = _common_assets()
        css_links = css_links or default_css
        js_scripts = js_scripts or default_js

    body_children: list[Any] = [
        Link(label=app_name, href=URL("/app")),
        EmptyState(
            title="500",
            description=(
                "Something went wrong on our end. We've been notified — "
                "please try again in a moment."
            ),
        ),
    ]
    if back_url:
        body_children.append(Link(label=back_label or "Back", href=URL(back_url)))
    body_children.append(Link(label="Go to Dashboard", href=URL("/app")))

    return Page(
        title=f"Something went wrong — {app_name}",
        body=Stack(children=tuple(body_children)),
        css_links=css_links,
        js_scripts=js_scripts,
    )
