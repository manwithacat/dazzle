"""HTMX request simulation for contract verification."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from html.parser import HTMLParser


@dataclass
class HtmxResponse:
    status: int
    html: str
    headers: dict[str, str] = field(default_factory=dict)
    hx_trigger: str = ""
    hx_redirect: str = ""


class _TagCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, dict(attrs)))


def parse_html(html: str) -> list[tuple[str, dict[str, str | None]]]:
    collector = _TagCollector()
    collector.feed(html)
    return collector.tags


@dataclass
class HtmxClient:
    base_url: str
    _session_token: str = ""
    _csrf_token: str = ""

    def set_session(self, session_token: str, csrf_token: str = "") -> None:
        self._session_token = session_token
        self._csrf_token = csrf_token

    def _cookies(self) -> dict[str, str]:
        cookies: dict[str, str] = {}
        if self._session_token:
            cookies["dazzle_session"] = self._session_token
        if self._csrf_token:
            cookies["dazzle_csrf"] = self._csrf_token
        return cookies

    def _htmx_headers(
        self, target: str = "body", method: str = "GET", trigger: str = ""
    ) -> dict[str, str]:
        headers: dict[str, str] = {"HX-Request": "true", "HX-Target": target}
        if trigger:
            headers["HX-Trigger"] = trigger
        if method != "GET" and self._csrf_token:
            headers["X-CSRF-Token"] = self._csrf_token
        secret = os.environ.get("DAZZLE_TEST_SECRET", "")
        if secret:
            headers["X-Test-Secret"] = secret
        return headers

    async def get(self, path: str, hx_target: str = "body") -> HtmxResponse:
        import httpx

        url = f"{self.base_url}{path}"
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                url,
                headers=self._htmx_headers(target=hx_target),
                cookies=self._cookies(),
                follow_redirects=False,
                timeout=10,
            )
        return HtmxResponse(
            status=resp.status_code,
            html=resp.text,
            headers=dict(resp.headers),
            hx_trigger=resp.headers.get("hx-trigger", ""),
            hx_redirect=resp.headers.get("hx-redirect", ""),
        )

    async def get_full_page(self, path: str) -> HtmxResponse:
        import httpx

        url = f"{self.base_url}{path}"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, cookies=self._cookies(), follow_redirects=True, timeout=10)
        return HtmxResponse(status=resp.status_code, html=resp.text, headers=dict(resp.headers))

    async def authenticate(self, persona: str) -> bool:
        import httpx

        headers: dict[str, str] = {}
        secret = os.environ.get("DAZZLE_TEST_SECRET", "")
        if secret:
            headers["X-Test-Secret"] = secret
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/__test__/authenticate",
                json={"role": persona, "username": persona},
                headers=headers,
                timeout=10,
            )
        if resp.status_code != 200:
            return False
        data = resp.json()
        token = data.get("session_token", "") or data.get("token", "")
        if not token:
            return False
        # Get CSRF token
        async with httpx.AsyncClient() as client:
            csrf_resp = await client.get(f"{self.base_url}/health", timeout=5)
        csrf = ""
        for cookie_header in csrf_resp.headers.get_list("set-cookie"):
            if "dazzle_csrf=" in cookie_header:
                csrf = cookie_header.split("dazzle_csrf=")[1].split(";")[0]
                break
        self.set_session(token, csrf)
        return True
