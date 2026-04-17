"""HTMX request simulation for contract verification.

Two fetch modes are exposed:

- :meth:`HtmxClient.get_full_page` returns the **initial** HTML
  server-rendered at request time. For workspace pages this contains
  the Alpine ``x-for`` template, the embedded ``#dz-workspace-layout``
  JSON, and a skeleton placeholder where each region's content will
  later land. Regions themselves are NOT in this HTML — they are
  fetched post-hydration via HTMX.

- :meth:`HtmxClient.get_workspace_composite` follows the HTMX boot
  sequence: fetches the initial page, parses out the card/region list
  from the ``#dz-workspace-layout`` JSON, issues an HTMX GET for each
  ``/api/workspaces/{ws}/regions/{region}`` endpoint, and stitches the
  region HTML back into the initial page. The result is the full DOM
  a user actually sees once the page settles — the right input for the
  shape-nesting and duplicate-title gates in ``contract_checker.py``.

Before v0.57.42 the contract checker only saw the initial HTML, which
is why the #794 card-in-card shipped undetected across three fixes:
the scanner was staring at a dashboard slot with a skeleton inside,
not a dashboard slot with a region inside.
"""

from __future__ import annotations

import json
import os
import re
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

    async def get_workspace_composite(self, path: str) -> HtmxResponse:
        """Fetch a workspace page and assemble the post-HTMX composite.

        Returns an :class:`HtmxResponse` whose ``html`` field is the
        initial page with each region's HTMX content substituted into
        its card body slot. Any region fetch that fails (non-200) is
        left as the original skeleton so the composite is always well-
        formed and scanner-ready.

        The workspace name and card/region list come from the embedded
        ``#dz-workspace-layout`` JSON (see ``workspace/_content.html``).
        """
        page_resp = await self.get_full_page(path)
        if page_resp.status != 200:
            return page_resp
        layout = _extract_workspace_layout(page_resp.html)
        if not layout:
            return page_resp
        workspace_name = layout.get("workspace_name", "")
        cards = layout.get("cards") or []
        if not workspace_name or not cards:
            return page_resp

        region_htmls: dict[tuple[str, str], str] = {}
        for card in cards:
            if not isinstance(card, dict):
                continue
            region = card.get("region")
            card_id = card.get("id")
            if not region or card_id is None:
                continue
            region_path = f"/api/workspaces/{workspace_name}/regions/{region}"
            region_resp = await self.get(region_path, hx_target=f"region-{region}-{card_id}")
            if region_resp.status == 200:
                region_htmls[(str(card_id), str(region))] = region_resp.html

        composite = assemble_workspace_composite(page_resp.html, region_htmls)
        return HtmxResponse(
            status=page_resp.status,
            html=composite,
            headers=page_resp.headers,
        )

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


# ---------------------------------------------------------------------------
# Workspace composite helpers (pure functions — unit-testable)
# ---------------------------------------------------------------------------


_WORKSPACE_LAYOUT_RE = re.compile(
    r'<script[^>]+id="dz-workspace-layout"[^>]*>(.*?)</script>',
    re.DOTALL,
)


def _extract_workspace_layout(initial_html: str) -> dict | None:
    """Pull the embedded layout JSON from a workspace page.

    Returns the parsed dict (with ``cards``, ``catalog``,
    ``workspace_name`` keys), or ``None`` if the page isn't a
    workspace page or the JSON is malformed.
    """
    match = _WORKSPACE_LAYOUT_RE.search(initial_html)
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def assemble_workspace_composite(
    initial_html: str, region_htmls: dict[tuple[str, str], str]
) -> str:
    """Substitute each ``region_htmls[(card_id, region)]`` into the
    initial workspace page at its card body slot, producing the
    composite DOM a user sees post-hydration.

    Card body slots are identified by ``id="region-{region}-{card_id}"``
    — the same id the Alpine template assigns on hydration. A card
    whose region is not present in ``region_htmls`` is left with its
    original skeleton so the composite remains well-formed.

    Intentionally string-substitution rather than full DOM manipulation:
    we want to preserve the surrounding markup byte-for-byte so the
    shape-nesting scanner gets the exact chrome shape the user sees.
    """
    composite = initial_html
    for (card_id, region), region_html in region_htmls.items():
        # Match <div ... id="region-{region}-{card_id}" ...>...</div>.
        # The template's outer slot div wraps the skeleton; we replace
        # that inner content but keep the outer wrapper so any
        # surrounding attributes (hx-get, hx-trigger) remain intact.
        pattern = re.compile(
            r'(<div[^>]*\bid="region-'
            + re.escape(region)
            + r"-"
            + re.escape(card_id)
            + r'"[^>]*>)(.*?)(</div>)',
            re.DOTALL,
        )
        composite = pattern.sub(
            lambda m, html=region_html: m.group(1) + html + m.group(3),
            composite,
            count=1,
        )
    return composite
