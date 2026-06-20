"""SSO button-row typed view (Phase 1.C, v0.67.39).

Renders the "Continue with Google / Microsoft" buttons that auth
views append above the email/password form when SSO providers are
configured. The buttons are plain `<a>` links — clicking one
navigates to `/auth/sso/<provider>` which kicks off the OAuth dance
handled in `sso_routes.py`.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from dazzle.http.runtime.auth.sso_config import SsoProviderConfig
from dazzle.render.fragment import URL, Link, Stack, Text


def _safe_next(next_url: str) -> str:
    """Render the `?next=` query suffix for the initiation URL.

    Same shape as the auth views' next-URL threading — empty / "/"
    means no override, anything else gets a single `?next=...`
    fragment. The route handler is responsible for validating
    same-origin before consuming.
    """
    return f"?next={next_url}" if next_url and next_url != "/" else ""


def build_sso_button_row(
    *,
    providers: Iterable[SsoProviderConfig],
    next_url: str = "/",
    divider_label: str = "or continue with",
) -> tuple[Any, ...]:
    """Return a tuple of Fragment children rendering the SSO buttons.

    The return shape is a tuple — callers splice it into their
    existing `Stack(children=...)` body. When ``providers`` is empty,
    returns an empty tuple so the caller's layout doesn't change.

    The divider label sits above the buttons and reads "or continue
    with" by default — this prefixes the existing form so the user
    understands SSO is the alternative path.
    """
    provider_list = tuple(providers)
    if not provider_list:
        return ()

    children: list[Any] = [Text(body=divider_label, tone="muted")]
    suffix = _safe_next(next_url)
    for provider in provider_list:
        children.append(
            Link(
                label=f"Continue with {provider.display_name}",
                href=URL(f"/auth/sso/{provider.name}{suffix}"),
            )
        )
    return tuple(children)


def render_sso_section(
    *,
    providers: Iterable[SsoProviderConfig],
    next_url: str = "/",
) -> Stack | None:
    """Convenience wrapper for callers that want a single Fragment.

    Returns a `Stack` of the button row children, or `None` when no
    providers are configured (so the caller can skip including it).
    """
    children = build_sso_button_row(providers=providers, next_url=next_url)
    if not children:
        return None
    return Stack(children=children)
