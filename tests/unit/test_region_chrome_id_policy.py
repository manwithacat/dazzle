"""Region chrome id policy: omit bare id when HTMX targets a card body.

Card SSR owns ``id="region-{name}-{card_id}"``. HTMX fragments swapped as
innerHTML must not re-emit ``id="region-{name}"`` or multi-card pages fail
the smoke structure oracle (duplicate region ids).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def _chrome(request_headers: dict[str, str], region_name: str = "device_attention") -> str:
    """Call the wrap tail of render_region_html with typed path skipped."""
    import asyncio

    from dazzle.http.runtime.workspace_region_render import render_region_html

    request = MagicMock()
    request.headers = request_headers
    ctx_region = SimpleNamespace(name=region_name, display="QUEUE", endpoint="/api/x")
    ctx = SimpleNamespace(ctx_region=ctx_region, ir_region=None)
    user_ctx = SimpleNamespace()
    from dazzle.http.runtime.workspace_region_render import RegionRenderInputs

    inputs = RegionRenderInputs()

    async def _run() -> str:
        return await render_region_html(request, ctx, user_ctx, inputs, None, "asc")

    return asyncio.get_event_loop().run_until_complete(_run())


@pytest.mark.asyncio
async def test_card_body_hx_target_omits_bare_region_id() -> None:
    from dazzle.http.runtime.workspace_region_render import RegionRenderInputs, render_region_html

    request = MagicMock()
    request.headers = {"hx-target": "region-device_attention-card-0"}
    ctx_region = SimpleNamespace(name="device_attention", display="NOT_TYPED", endpoint="/api/x")
    # display not in typed set → empty body, but chrome still wraps
    ctx = SimpleNamespace(ctx_region=ctx_region, ir_region=None)
    html = await render_region_html(
        request, ctx, SimpleNamespace(), RegionRenderInputs(), None, "asc"
    )
    assert 'data-dz-region-name="device_attention"' in html
    assert "data-dz-region" in html
    assert 'id="region-device_attention"' not in html


@pytest.mark.asyncio
async def test_bare_region_target_keeps_region_id() -> None:
    from dazzle.http.runtime.workspace_region_render import RegionRenderInputs, render_region_html

    request = MagicMock()
    request.headers = {"hx-target": "region-device_attention"}
    ctx_region = SimpleNamespace(name="device_attention", display="NOT_TYPED", endpoint="/api/x")
    ctx = SimpleNamespace(ctx_region=ctx_region, ir_region=None)
    html = await render_region_html(
        request, ctx, SimpleNamespace(), RegionRenderInputs(), None, "asc"
    )
    assert 'id="region-device_attention"' in html


@pytest.mark.asyncio
async def test_no_hx_target_keeps_region_id() -> None:
    from dazzle.http.runtime.workspace_region_render import RegionRenderInputs, render_region_html

    request = MagicMock()
    request.headers = {}
    ctx_region = SimpleNamespace(name="device_attention", display="NOT_TYPED", endpoint="/api/x")
    ctx = SimpleNamespace(ctx_region=ctx_region, ir_region=None)
    html = await render_region_html(
        request, ctx, SimpleNamespace(), RegionRenderInputs(), None, "asc"
    )
    assert 'id="region-device_attention"' in html
