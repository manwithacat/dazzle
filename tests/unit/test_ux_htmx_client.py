"""Tests for HTMX request simulation client."""

from dazzle.testing.ux.htmx_client import HtmxClient, parse_html


class TestHtmxClient:
    def test_builds_htmx_headers(self) -> None:
        client = HtmxClient(base_url="http://localhost:3392")
        headers = client._htmx_headers(target="dz-detail-drawer-content")
        assert headers["HX-Request"] == "true"
        assert headers["HX-Target"] == "dz-detail-drawer-content"

    def test_builds_auth_cookies(self) -> None:
        client = HtmxClient(base_url="http://localhost:3392")
        client.set_session("abc123", csrf_token="xyz789")
        cookies = client._cookies()
        assert cookies["dazzle_session"] == "abc123"
        assert cookies["dazzle_csrf"] == "xyz789"

    def test_csrf_header_included_for_mutating_methods(self) -> None:
        client = HtmxClient(base_url="http://localhost:3392")
        client.set_session("abc123", csrf_token="xyz789")
        headers = client._htmx_headers(target="body", method="DELETE")
        assert headers["X-CSRF-Token"] == "xyz789"

    def test_csrf_header_excluded_for_get(self) -> None:
        client = HtmxClient(base_url="http://localhost:3392")
        client.set_session("abc123", csrf_token="xyz789")
        headers = client._htmx_headers(target="body", method="GET")
        assert "X-CSRF-Token" not in headers


class TestParseHtml:
    def test_parses_tags_and_attrs(self) -> None:
        html = '<div hx-get="/test" hx-target="body"><input name="q" type="text" /></div>'
        tags = parse_html(html)
        assert len(tags) == 2
        assert tags[0] == ("div", {"hx-get": "/test", "hx-target": "body"})
        assert tags[1] == ("input", {"name": "q", "type": "text"})

    def test_handles_empty_html(self) -> None:
        assert parse_html("") == []
