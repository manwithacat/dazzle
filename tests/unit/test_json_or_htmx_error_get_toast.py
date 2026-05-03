"""Test #994 fix — GET HTMX errors return toast, not form-errors retarget.

Pre-fix `json_or_htmx_error` always returned 422 with
`HX-Retarget: #form-errors`. Sort/filter requests on list pages
target a table body (e.g. `dt-users-body`), so retargeting to a
non-existent `#form-errors` triggered `htmx:targetError` in the
browser and the user saw nothing change.

The fix routes GET-method HTMX requests to `htmx_toast_error_response`
(200 + `HX-Trigger: showToast`) and keeps the form-errors retarget
for write methods (POST/PUT/PATCH/DELETE).
"""

from __future__ import annotations

from types import SimpleNamespace

from dazzle_ui.runtime.htmx import json_or_htmx_error


def _request(method: str, htmx: bool = True) -> SimpleNamespace:
    """Stub Request: only ``method`` and the HX-Request header are read.

    `HtmxDetails.from_request` looks up the header by its canonical
    "HX-Request" name, so the dict must respond to that exact key.
    """
    headers = {"HX-Request": "true"} if htmx else {}
    return SimpleNamespace(method=method, headers=headers, query_params={})


def test_get_returns_toast_not_form_errors_retarget():
    """The bug: a sort link is GET, but the response retargeted #form-errors."""
    response = json_or_htmx_error(_request("GET"), [{"loc": ["sort"], "msg": "invalid sort field"}])
    # No HX-Retarget — that's what was breaking sort/filter pages.
    assert "hx-retarget" not in {k.lower() for k in response.headers.keys()}
    # Toast carries the message instead.
    assert "hx-trigger" in {k.lower() for k in response.headers.keys()}
    trigger_header = response.headers.get("hx-trigger") or response.headers.get("HX-Trigger")
    assert "showToast" in trigger_header
    assert "invalid sort field" in trigger_header
    # 200 not 422 — htmx treats 422 as an error and the targetError fires
    # before the trigger handler runs. 200 lets the toast appear cleanly.
    assert response.status_code == 200


def test_post_keeps_form_errors_retarget():
    """Form submissions still get the in-place form-errors render."""
    response = json_or_htmx_error(_request("POST"), [{"loc": ["title"], "msg": "field required"}])
    headers_lower = {k.lower(): v for k, v in response.headers.items()}
    assert headers_lower.get("hx-retarget") == "#form-errors"
    assert response.status_code == 422


def test_put_keeps_form_errors_retarget():
    response = json_or_htmx_error(_request("PUT"), [{"loc": ["title"], "msg": "field required"}])
    headers_lower = {k.lower(): v for k, v in response.headers.items()}
    assert headers_lower.get("hx-retarget") == "#form-errors"


def test_patch_keeps_form_errors_retarget():
    response = json_or_htmx_error(_request("PATCH"), [{"loc": ["title"], "msg": "field required"}])
    headers_lower = {k.lower(): v for k, v in response.headers.items()}
    assert headers_lower.get("hx-retarget") == "#form-errors"


def test_non_htmx_get_returns_json():
    """API clients (no HX-Request header) get JSON regardless of method."""
    response = json_or_htmx_error(_request("GET", htmx=False), [{"loc": [], "msg": "bad request"}])
    # JSONResponse, not the toast-only HTMLResponse path.
    assert response.status_code == 422
    assert response.media_type == "application/json"
