"""Tests for HTMX OOB response helpers."""

from starlette.responses import HTMLResponse

from dazzle.http.runtime.response_helpers import with_oob, with_toast


class TestWithToast:
    def test_appends_toast_html_to_response(self):
        resp = HTMLResponse("<p>OK</p>")
        result = with_toast(resp, "Saved successfully", "success")
        body = result.body.decode()
        assert "<p>OK</p>" in body
        # the OOB target must be the shell's REAL toast stack (`#dz-toast`,
        # rendered by _render_shell) — `#dz-toast-container` never existed
        # in any layout, so every with_toast OOB silently missed.
        assert 'hx-swap-oob="afterbegin:#dz-toast"' in body
        assert 'id="dz-toast-container"' not in body
        assert "Saved successfully" in body
        # #1113 — tone driven by data attribute instead of DaisyUI
        # `alert-{level}` class.
        assert 'class="dz-toast"' in body
        assert 'data-dz-toast-level="success"' in body

    def test_default_level_is_info(self):
        resp = HTMLResponse("<p>OK</p>")
        result = with_toast(resp, "Hello")
        body = result.body.decode()
        assert 'data-dz-toast-level="info"' in body

    def test_includes_remove_me_attribute(self):
        resp = HTMLResponse("<p>OK</p>")
        result = with_toast(resp, "Gone soon", "warning")
        body = result.body.decode()
        # htmx 4: dz-toast.js bridge dismisses via data-dz-remove-after
        # (was the remove-me htmx-2 extension).
        assert 'data-dz-remove-after="8s"' in body

    def test_escapes_html_in_message(self):
        resp = HTMLResponse("<p>OK</p>")
        result = with_toast(resp, "<script>alert('xss')</script>", "error")
        body = result.body.decode()
        assert "<script>" not in body
        assert "&lt;script&gt;" in body

    def test_preserves_response_status_code(self):
        resp = HTMLResponse("<p>Created</p>", status_code=201)
        result = with_toast(resp, "Created", "success")
        assert result.status_code == 201

    def test_preserves_existing_headers(self):
        resp = HTMLResponse("<p>OK</p>")
        resp.headers["X-Custom"] = "test"
        result = with_toast(resp, "Done")
        assert result.headers.get("X-Custom") == "test"

    def test_title_and_actions_slots(self):
        resp = HTMLResponse("<p>OK</p>")
        result = with_toast(
            resp,
            "Your changes are live.",
            "success",
            title="Saved",
            actions=(("View record", "/tickets/1"), ("Dismiss", "")),
        )
        body = result.body.decode()
        assert 'class="dz-toast__title"' in body
        assert "Saved" in body
        assert 'class="dz-toast__message"' in body
        assert 'href="/tickets/1"' in body
        assert "View record" in body
        assert "data-dz-toast-dismiss" in body
        assert 'class="dz-toast__close"' in body
        assert 'role="status"' in body

    def test_error_level_uses_alert_role(self):
        resp = HTMLResponse("<p>OK</p>")
        result = with_toast(resp, "Nope", "error")
        assert 'role="alert"' in result.body.decode()


class TestWithOob:
    def test_appends_oob_swap_to_response(self):
        resp = HTMLResponse("<p>Main</p>")
        result = with_oob(resp, "sidebar", "<ul><li>New item</li></ul>")
        body = result.body.decode()
        assert "<p>Main</p>" in body
        assert 'id="sidebar"' in body
        assert 'hx-swap-oob="innerHTML"' in body
        assert "<ul><li>New item</li></ul>" in body

    def test_custom_swap_strategy(self):
        resp = HTMLResponse("<p>Main</p>")
        result = with_oob(resp, "nav", "<nav>Updated</nav>", swap="outerHTML")
        body = result.body.decode()
        assert 'hx-swap-oob="outerHTML"' in body

    def test_multiple_oob_swaps(self):
        resp = HTMLResponse("<p>Main</p>")
        result = with_oob(resp, "a", "<div>A</div>")
        result = with_oob(result, "b", "<div>B</div>")
        body = result.body.decode()
        assert 'id="a"' in body
        assert 'id="b"' in body
