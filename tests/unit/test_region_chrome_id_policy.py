"""Region chrome policy: HTMX fragments must not nest bare region wrappers.

Dashboard cards own ``id="region-{name}-{card_id}"`` and poll with
``hx-swap=innerHTML``. Returning a full chrome wrapper
(``id="region-{name}"``) on every poll nests wrappers and multiplies
duplicate region ids (smoke structure oracle, ownership=framework).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from dazzle.http.runtime.workspace_region_render import RegionRenderInputs, render_region_html


@pytest.mark.asyncio
async def test_htmx_request_returns_body_without_chrome() -> None:
    request = MagicMock()
    request.headers = {"hx-request": "true", "hx-target": "region-device_attention-card-0"}
    ctx_region = SimpleNamespace(name="device_attention", display="NOT_TYPED", endpoint="/api/x")
    ctx = SimpleNamespace(ctx_region=ctx_region, ir_region=None)
    html = await render_region_html(
        request, ctx, SimpleNamespace(), RegionRenderInputs(), None, "asc"
    )
    assert "data-dz-region" not in html
    assert 'id="region-device_attention"' not in html


@pytest.mark.asyncio
async def test_non_htmx_keeps_chrome_with_region_id() -> None:
    request = MagicMock()
    request.headers = {}
    ctx_region = SimpleNamespace(name="device_attention", display="NOT_TYPED", endpoint="/api/x")
    ctx = SimpleNamespace(ctx_region=ctx_region, ir_region=None)
    html = await render_region_html(
        request, ctx, SimpleNamespace(), RegionRenderInputs(), None, "asc"
    )
    assert 'data-dz-region-name="device_attention"' in html
    assert 'id="region-device_attention"' in html


@pytest.mark.asyncio
async def test_htmx_true_case_insensitive() -> None:
    request = MagicMock()
    request.headers = {"HX-Request": "true"}
    ctx_region = SimpleNamespace(name="device_attention", display="NOT_TYPED", endpoint="/api/x")
    ctx = SimpleNamespace(ctx_region=ctx_region, ir_region=None)
    html = await render_region_html(
        request, ctx, SimpleNamespace(), RegionRenderInputs(), None, "asc"
    )
    assert 'id="region-device_attention"' not in html
