"""Framework default 404 / 410 pages for tenant_host: (#1289 slice 3).

Projects override per-block via the dotted-path `not_found_template:` and
`expired_template:` sub-fields. These defaults exist so the framework
always ships a sensible response without per-project work.
"""

from __future__ import annotations

from html import escape


def render_default_404(*, app_name: str, host: str) -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{escape(app_name)} — Not Found</title>"
        "<style>body{font-family:system-ui,sans-serif;max-width:40rem;margin:4rem auto;padding:0 1rem;color:#222}h1{font-size:1.5rem}</style>"
        "</head><body>"
        f"<h1>{escape(app_name)} — Tenant not found</h1>"
        f"<p>No tenant matches <code>{escape(host)}</code>.</p>"
        "<p>Status: 404</p>"
        "</body></html>"
    )


def render_default_410(*, app_name: str, old_slug: str, new_slug: str, domain: str) -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{escape(app_name)} — Moved</title>"
        "<style>body{font-family:system-ui,sans-serif;max-width:40rem;margin:4rem auto;padding:0 1rem;color:#222}h1{font-size:1.5rem}</style>"
        "</head><body>"
        f"<h1>{escape(app_name)} — Tenant moved</h1>"
        f"<p><code>{escape(old_slug)}</code> moved to "
        f"<a href='https://{escape(new_slug)}.{escape(domain)}/'>"
        f"<code>{escape(new_slug)}.{escape(domain)}</code></a>.</p>"
        "<p>This redirect link has expired (status: 410).</p>"
        "</body></html>"
    )
