"""Tests for #969 — htmx-ext-preload disabled to silence speculative-fetch 403s.

Background: `htmx-ext-preload` fires raw `fetch()` calls on hover/mousedown
to warm the browser cache. Two failure modes:

1. **Persona-rejected URLs** — speculative fetches to workspaces the
   persona can't read return 403. Browser native-logs `Failed to load
   resource: 403` at the network layer (not the JS console), which is
   not suppressible from JS — only fix is to stop making the request.

2. **Racy auth state on accessible URLs** — under fast repeat-clicking,
   speculative fetches land in the gap between session updates and get
   403'd despite the persona having access.

Trade-off: the cache-warming benefit (~50-100ms perceived nav improvement
on hover→click) is small compared to htmx-boost's full-page-replace
speed. Cleaner to disable preload entirely until a per-link access gate
is in place. #967 fixed the JS-console-error variant (htmx XHR-path
prefetches); this test pins the network-layer fix.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BASE_HTML = REPO_ROOT / "src" / "dazzle_ui" / "templates" / "base.html"


def test_body_hx_ext_does_not_include_preload() -> None:
    """The `<body hx-ext="...">` list must not include `preload`."""
    html = BASE_HTML.read_text()
    body_idx = html.find("<body")
    assert body_idx >= 0, "missing <body> tag in base.html"
    body_end = html.find(">", body_idx)
    body_tag = html[body_idx : body_end + 1]
    # Match the hx-ext attribute value.
    hx_ext_idx = body_tag.find('hx-ext="')
    assert hx_ext_idx >= 0, "missing hx-ext attribute on <body>"
    val_start = hx_ext_idx + len('hx-ext="')
    val_end = body_tag.find('"', val_start)
    extensions = [e.strip() for e in body_tag[val_start:val_end].split(",")]
    assert "preload" not in extensions, (
        f"hx-ext list still contains `preload` ({extensions}). "
        "The htmx-ext-preload extension speculatively fetches links and "
        "logs network-level 403s on persona-rejected URLs — disabled by #969."
    )


def test_preload_vendor_script_not_loaded() -> None:
    """The `htmx-ext-preload.js` vendor script must not be loaded by base.html."""
    html = BASE_HTML.read_text()
    # Match a real <script> tag, not a comment that mentions the script.
    assert "<script defer src=\"{{ 'vendor/htmx-ext-preload.js'" not in html, (
        "base.html still loads `vendor/htmx-ext-preload.js` — disabled by #969 "
        "to silence persona-rejected speculative-fetch 403 noise. "
        "If re-enabling, also gate speculative fetches by per-link access."
    )
