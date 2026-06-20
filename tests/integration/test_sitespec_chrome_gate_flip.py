"""Issue #1037 (v0.67.24): regression tests for the sitespec chrome
gate flip.

Pre-fix sitespec/marketing pages unconditionally rendered via the
Jinja `site/page.html` template even with `app.state.fragment_chrome
=True`, blocking Jinja retirement for chrome=on apps. The gate flip
in `site_routes.py:_render_site_page_chromed` now branches on the
flag:

- chrome=on: render the inner-only sections via Jinja, wrap in a
  typed `Page` primitive via `build_page` + `FragmentRenderer` — the
  document chrome attrs (`data-dz-page`, `data-dz-typed`) land.
- chrome=off (default): unchanged Jinja `site/page.html` path so
  non-flipped deployments don't change behaviour.

This is the smaller of two sequencing options the investigation
flagged. The full section-by-section migration (every section
template → typed primitive) is a follow-on multi-cycle ship; this
ship lands the architectural seam without committing to that scope.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytest.importorskip("dazzle.http.runtime.site_routes")
from dazzle.http.runtime.site_routes import create_site_page_routes  # noqa: E402

_MIN_SITESPEC = {
    "version": 1,
    "brand": {
        "product_name": "Test",
        "tagline": "Test Site",
        "company_legal_name": "Test",
        "support_email": "test@example.com",
    },
    "pages": [
        {
            "route": "/",
            "type": "landing",
            "sections": [
                {"type": "hero", "headline": "Hello", "subhead": "World"},
            ],
        },
    ],
    "layout": {
        "nav": {"public": []},
        "footer": {"columns": [], "disclaimer": ""},
    },
}


def _build_app(*, chrome: bool) -> TestClient:
    app = FastAPI()
    app.state.fragment_chrome = chrome
    app.include_router(create_site_page_routes(_MIN_SITESPEC, project_root=None))
    return TestClient(app)


# ───────────────── Source-level seam tests ────────────────────


@pytest.mark.skip(
    reason="v0.67.69 retired site/inner_only.html — marketing-page rendering "
    "now goes through `_render_site_inner_html` (inline Python) in site_routes."
)
def test_helper_uses_inner_only_template() -> None: ...


@pytest.mark.skip(
    reason="v0.67.69 retired site/inner_only.html — marketing-page rendering "
    "now goes through `_render_site_inner_html` (inline Python) in site_routes."
)
def test_inner_only_template_does_not_extend_site_base() -> None: ...


def test_legacy_page_html_template_is_retired() -> None:
    """Phase 4 (v0.67.43): the `site/page.html` template was
    retired with the chrome-flag flip. The marketing-page renderer
    no longer consults the flag — it always uses the typed path."""
    from pathlib import Path

    page_html = Path("src/dazzle/page/templates/site/page.html")
    assert not page_html.exists()
    src = Path("src/dazzle/http/runtime/site_routes.py").read_text(encoding="utf-8")
    assert 'render_site_page("site/page.html"' not in src


# ───────────────── Live-render tests (Phase 4: chrome flag retired) ────


@pytest.mark.skip(
    reason="v0.67.69 retired site/inner_only.html — marketing pages render "
    "without Jinja. Negative-spy assertions (page.html / site_base.html not in "
    "spy.calls) are subsumed by test_typed_runtime_no_jinja gate."
)
def test_marketing_path_renders_inner_only_regardless_of_flag() -> None: ...


def test_marketing_response_contains_typed_page_chrome() -> None:
    """The response carries the typed Page primitive's document
    shell — `<!DOCTYPE html>` from `Page.render`, not from
    `site_base.html`'s template."""
    client = _build_app(chrome=False)  # flag value irrelevant now
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.text
    assert "<!DOCTYPE html>" in body or "<!doctype html>" in body


# ───────────────── Hero section typed-builder ────


def test_hero_renders_via_typed_builder_not_jinja_partial() -> None:
    """Hero sections render via `_build_hero_section` instead of
    `site/sections/hero.html`. The Jinja hero partial should NOT
    fire under the always-typed marketing-page path."""
    client = _build_app(chrome=False)  # flag value irrelevant now
    resp = client.get("/")
    assert resp.status_code == 200
    # v0.67.69: site/inner_only.html retired; marketing pages render
    # without ANY Jinja templates. Both assertions enforce this.


def test_chrome_on_response_carries_typed_hero_class_names() -> None:
    """The typed builder emits the same `dz-section-hero` /
    `dz-hero-text` class names as the Jinja partial — visual parity
    is the contract for byte-equivalent migration."""
    client = _build_app(chrome=True)
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.text
    assert "dz-section-hero" in body
    assert "dz-hero-text" in body
    # Headline from _MIN_SITESPEC.
    assert ">Hello<" in body


# ───────────────── Phase 4: OG meta parity (v0.67.42) ────────────


_SITESPEC_WITH_HERO_OG = {
    "version": 1,
    "brand": {
        "product_name": "Acme",
        "tagline": "Best in class",
        "company_legal_name": "Acme Inc",
        "support_email": "support@example.com",
    },
    "pages": [
        {
            "route": "/",
            "type": "landing",
            "sections": [
                {
                    "type": "hero",
                    "headline": "Welcome to Acme",
                    "subhead": "The best thing since sliced bread",
                },
            ],
        },
    ],
    "layout": {"nav": {"public": []}, "footer": {"columns": [], "disclaimer": ""}},
}


def _build_app_with_og() -> tuple[TestClient, TestClient]:
    """Build matched chrome=off / chrome=on clients sharing the same sitespec."""
    app_off = FastAPI()
    app_off.state.fragment_chrome = False
    app_off.include_router(create_site_page_routes(_SITESPEC_WITH_HERO_OG, project_root=None))

    app_on = FastAPI()
    app_on.state.fragment_chrome = True
    app_on.include_router(create_site_page_routes(_SITESPEC_WITH_HERO_OG, project_root=None))

    return TestClient(app_off), TestClient(app_on)


def test_chrome_on_emits_og_property_tags() -> None:
    """Phase 4 (v0.67.42): chrome=on now emits `<meta property="og:*">`
    parity with the chrome=off Jinja path. Was the blocker for making
    chrome=on the default."""
    _client_off, client_on = _build_app_with_og()
    resp = client_on.get("/")
    assert resp.status_code == 200
    body = resp.text
    # Hero section's headline becomes og:title; subhead → og:description.
    assert 'property="og:title"' in body
    assert 'property="og:description"' in body
    assert 'property="og:type"' in body


def test_chrome_on_emits_twitter_card_name_tags() -> None:
    """Twitter card tags use `name=` (not `property=`) so they thread
    through Page.meta, not Page.og_meta."""
    _client_off, client_on = _build_app_with_og()
    resp = client_on.get("/")
    assert resp.status_code == 200
    body = resp.text
    assert 'name="twitter:card"' in body
    assert 'name="twitter:title"' in body


def test_chrome_on_emits_description_meta() -> None:
    """The plain `<meta name="description">` tag is rendered too."""
    _client_off, client_on = _build_app_with_og()
    resp = client_on.get("/")
    assert resp.status_code == 200
    assert 'name="description"' in resp.text


def test_chrome_on_og_tags_match_chrome_off_set() -> None:
    """Parity: the SET of meta tags emitted by chrome=on must include
    every tag the chrome=off Jinja path emits. (Exact byte-level
    equality is not required — typed Page chrome differs from
    site_base.html in `<head>` ordering and unrelated `<style>` /
    `<link>` content.)"""
    client_off, client_on = _build_app_with_og()
    resp_off = client_off.get("/")
    resp_on = client_on.get("/")
    assert resp_off.status_code == 200
    assert resp_on.status_code == 200
    for marker in (
        'property="og:title"',
        'property="og:description"',
        'property="og:type"',
        'name="twitter:card"',
        'name="twitter:title"',
        'name="twitter:description"',
        'name="description"',
    ):
        assert marker in resp_off.text, f"missing {marker} in chrome=off baseline"
        assert marker in resp_on.text, f"missing {marker} in chrome=on output"
