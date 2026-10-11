"""Mutation toast / fallback detail must not dump IssueReport (oral #192)."""

from __future__ import annotations

from types import SimpleNamespace

from dazzle.http.runtime.htmx_render import _render_detail_html


def test_fallback_detail_heading_not_issuereport() -> None:
    request = SimpleNamespace(headers={"HX-Request": "true"}, method="GET")
    html = _render_detail_html(
        request,
        {"id": "c3000000-0000-4000-8000-000000000001", "title": "Login loop"},
        "IssueReport",
    )
    body = html.body.decode() if hasattr(html.body, "decode") else str(html.body)
    assert ">Issue Report</h2>" in body
    assert ">IssueReport</h2>" not in body
    assert "Login loop" in body
