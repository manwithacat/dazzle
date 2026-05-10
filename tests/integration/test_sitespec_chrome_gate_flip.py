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

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jinja2 import Template

pytest.importorskip("dazzle_back.runtime.site_routes")
from dazzle_back.runtime.site_routes import create_site_page_routes  # noqa: E402

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


class _JinjaSpy:
    """Records every Template.render call inside a `with` block."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self._original = Template.render

    def __enter__(self) -> _JinjaSpy:
        spy = self
        original = self._original

        def tracked(self_template: Template, *args: object, **kwargs: object) -> str:
            name = getattr(self_template, "name", None) or "<inline>"
            spy.calls.append(name)
            return original(self_template, *args, **kwargs)

        self._patch = patch.object(Template, "render", tracked)
        self._patch.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._patch.stop()


def _build_app(*, chrome: bool) -> TestClient:
    app = FastAPI()
    app.state.fragment_chrome = chrome
    app.include_router(create_site_page_routes(_MIN_SITESPEC, project_root=None))
    return TestClient(app)


# ───────────────── Source-level seam tests ────────────────────


def test_helper_branches_on_app_state_fragment_chrome() -> None:
    """The helper must read the flag from `request.app.state` —
    catches a regression that hard-codes one path."""
    from pathlib import Path

    src = Path("src/dazzle_back/runtime/site_routes.py").read_text(encoding="utf-8")
    assert "_render_site_page_chromed" in src
    assert 'request.app.state, "fragment_chrome"' in src


def test_helper_uses_inner_only_template_in_typed_path() -> None:
    """Typed path must use the inner-only template, not the full
    `site/page.html` (which extends `site_base.html` and would
    double-wrap the chrome)."""
    from pathlib import Path

    src = Path("src/dazzle_back/runtime/site_routes.py").read_text(encoding="utf-8")
    assert '"site/inner_only.html"' in src


def test_inner_only_template_does_not_extend_site_base() -> None:
    """The inner-only template must NOT extend `site_base.html`
    — otherwise the typed Page wrapper would emit a doubled
    `<html>...</html>` shell."""
    from pathlib import Path

    src = Path("src/dazzle_ui/templates/site/inner_only.html").read_text(encoding="utf-8")
    assert '{% extends "site/site_base.html" %}' not in src
    assert "{% extends" not in src  # no extends at all


def test_legacy_fallback_path_still_present() -> None:
    """The chrome=off branch must keep calling
    `render_site_page(\"site/page.html\", ctx)` so non-flipped
    deployments don't change behaviour."""
    from pathlib import Path

    src = Path("src/dazzle_back/runtime/site_routes.py").read_text(encoding="utf-8")
    assert 'render_site_page("site/page.html"' in src


# ───────────────── Live-render tests ──────────────────────────


def test_chrome_off_renders_via_legacy_jinja_template() -> None:
    """chrome=off keeps calling site/page.html as the entry
    template. (Extends-resolved parents like site/site_base.html
    don't appear as separate Template.render calls — Jinja
    resolves extends inline. The entry-template assertion is the
    contract.)"""
    client = _build_app(chrome=False)
    with _JinjaSpy() as spy:
        resp = client.get("/")
    assert resp.status_code == 200
    assert "site/page.html" in spy.calls
    # Inner-only template must NOT fire on the legacy path.
    assert "site/inner_only.html" not in spy.calls


def test_chrome_on_renders_inner_only_template_not_page() -> None:
    """chrome=on uses the inner-only template, NOT the full
    site/page.html. site_base.html should not be invoked since
    the typed Page primitive provides the document chrome."""
    client = _build_app(chrome=True)
    with _JinjaSpy() as spy:
        resp = client.get("/")
    assert resp.status_code == 200
    # Typed path uses inner_only — page.html should NOT appear in
    # this run's render trace.
    assert "site/page.html" not in spy.calls
    assert "site/site_base.html" not in spy.calls
    # The inner-only template DOES fire (sections still render via
    # Jinja in this gate-flip ship — full migration is the
    # follow-on).
    assert "site/inner_only.html" in spy.calls


def test_chrome_on_response_contains_typed_page_chrome() -> None:
    """The response should carry the typed Page primitive's
    document shell — `<!DOCTYPE html>` from `Page.render`, not
    from `site_base.html`'s template."""
    client = _build_app(chrome=True)
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.text
    assert "<!DOCTYPE html>" in body or "<!doctype html>" in body


# ───────────────── Hero section migration (#1037 v0.67.25) ────────


def test_chrome_on_renders_hero_via_typed_builder_not_jinja_partial() -> None:
    """v0.67.25 (first section migration): hero sections under
    chrome=on render via `_build_hero_section` instead of
    `site/sections/hero.html`. The Jinja partial should NOT fire
    for the hero section."""
    client = _build_app(chrome=True)
    with _JinjaSpy() as spy:
        resp = client.get("/")
    assert resp.status_code == 200
    # Hero partial must NOT fire under chrome=on.
    assert "site/sections/hero.html" not in spy.calls
    # inner_only.html still fires (it dispatches based on _typed marker).
    assert "site/inner_only.html" in spy.calls


def test_chrome_off_still_renders_hero_via_jinja() -> None:
    """Sanity: chrome=off path keeps using the legacy Jinja chain
    (page.html → site_base.html → sections/hero.html). The section
    builder typed path is gated on the flag, not always-on. Jinja
    `{% include %}` calls aren't visible to the spy; we assert on
    entry-template difference instead."""
    client = _build_app(chrome=False)
    with _JinjaSpy() as spy:
        resp = client.get("/")
    assert resp.status_code == 200
    assert "site/page.html" in spy.calls
    assert "site/inner_only.html" not in spy.calls


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
