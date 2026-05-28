"""Tests for the tenant middleware + default templates (#1289 slice 3)."""

from __future__ import annotations

from dazzle.back.runtime.tenant.templates import (
    render_default_404,
    render_default_410,
)


def test_default_404_includes_host():
    body = render_default_404(app_name="acme", host="missing.acme.com")
    assert "missing.acme.com" in body
    assert "404" in body or "not found" in body.lower()


def test_default_410_includes_new_slug():
    body = render_default_410(
        app_name="acme", old_slug="oldco", new_slug="newco", domain="acme.com"
    )
    assert "newco" in body
    assert "oldco" in body


def test_default_templates_escape_html():
    body = render_default_404(app_name="<script>", host="evil<.com")
    assert "<script>" not in body
    assert "&lt;script&gt;" in body
