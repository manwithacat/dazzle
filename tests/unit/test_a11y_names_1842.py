"""#1842 (CyFuture WCAG 2.2 audit, second batch) — server-rendered names,
labels and structure.

One parametrized table per seam: each row renders through the real emitter
and pins what the markup must (and must not) carry.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from dazzle.http.runtime.auth.product_name import product_name
from dazzle.http.runtime.auth.two_factor_views import (
    build_2fa_setup_view,
    build_code_entry_view,
)
from dazzle.http.runtime.site_routes import _format_page_response
from dazzle.render.filters import _bool_icon_filter
from dazzle.render.fragment import URL, FragmentRenderer, MoneyField, RefPicker
from dazzle.render.fragment.primitives import RowCapabilities
from dazzle.render.fragment.renderer._data_row import render_data_row

_R = FragmentRenderer()
_UUID = "3f2b8c1e-9a4d-4e7b-8c2a-1d5e6f7a8b9c"


# ── 1.1.1: bool cells carry text, the glyph is decorative ──────────────


@pytest.mark.parametrize(("value", "text"), [(True, "Yes"), (False, "No")])
def test_bool_icon_has_text_alternative(value: bool, text: str) -> None:
    html = str(_bool_icon_filter(value))
    assert '<span aria-hidden="true">' in html
    assert f'<span class="visually-hidden">{text}</span>' in html


# ── 1.1.1: row controls are named by the row, not its UUID ─────────────


@pytest.mark.parametrize(
    ("columns", "item", "label"),
    [
        pytest.param(
            [{"key": "ref_code", "type": "text"}, {"key": "name", "type": "text"}],
            {"id": _UUID, "ref_code": _UUID, "name": "Ada"},
            "Ada",
            id="skips-uuid-valued-column",
        ),
        pytest.param(
            [{"key": "owner_id", "type": "text"}, {"key": "title", "type": "text"}],
            {"id": "r1", "owner_id": "o1", "title": "Quarterly"},
            "Quarterly",
            id="skips-id-keyed-column",
        ),
        pytest.param(
            [{"key": "ssn", "type": "sensitive"}, {"key": "name", "type": "text"}],
            {"id": "r1", "ssn": "123456789", "name": "Grace"},
            "Grace",
            id="never-names-by-sensitive-column",
        ),
        pytest.param(
            [{"key": "contact", "type": "ref"}, {"key": "notes", "type": "text"}],
            {"id": "r1", "__display__": "Acme Ltd", "contact": {"id": "c1"}, "notes": "x"},
            "Acme Ltd",
            id="prefers-injected-display-field",
        ),
        pytest.param(
            [{"key": "nickname", "type": "text"}, {"key": "name", "type": "text"}],
            {"id": "r1", "nickname": "", "name": "Lin"},
            "Lin",
            id="skips-empty-text-column",
        ),
        pytest.param(
            [{"key": "contact", "type": "ref"}],
            {"id": "r1", "contact": {"id": "c1"}},
            "r1",
            id="id-is-last-resort",
        ),
    ],
)
def test_row_controls_named_by_display_text(columns: list, item: dict, label: str) -> None:
    html = render_data_row(
        tuple(columns),
        item,
        RowCapabilities(bulk_select=True),
        entity_name="Task",
        api_endpoint="/api/tasks",
    )
    assert f'aria-label="Select {label}"' in html
    assert f'aria-label="Delete {label}"' in html


# ── 3.3.2: money has a visible label; required pickers mark + no preselect ──


@pytest.mark.parametrize(
    ("field", "present", "absent"),
    [
        pytest.param(
            MoneyField(
                name="fee", label="Fee", currency_code="GBP", symbol="£", scale="2", required=True
            ),
            (
                '<label class="dz-field" for="field-fee">',
                '<span class="dz-field__label">Fee',
                '<span class="dz-form-required" aria-hidden="true">*</span>',
                '<span class="visually-hidden"> (GBP)</span>',
                'id="field-fee"',
            ),
            ('aria-label="Fee',),
            id="money-fixed-currency",
        ),
        pytest.param(
            MoneyField(
                name="fee",
                label="Fee",
                currency_code="GBP",
                symbol="£",
                scale="2",
                currency_fixed=False,
                currency_options=(("GBP", "2", "£"), ("EUR", "2", "€")),
            ),
            (
                '<label class="dz-field" for="field-fee">',
                'aria-label="Currency for Fee"',
            ),
            ('aria-label="Fee"', "dz-form-required"),
            id="money-currency-selector",
        ),
        pytest.param(
            RefPicker(name="owner", label="Owner", ref_api=URL("/api/users"), required=True),
            (
                '<span class="dz-form-required" aria-hidden="true">*</span>',
                'required aria-required="true"',
                '<option value="">Select…</option></select>',
            ),
            (" selected>",),
            id="ref-picker-required-no-preselect",
        ),
        pytest.param(
            RefPicker(
                name="owner",
                label="Owner",
                ref_api=URL("/api/users"),
                initial_value="u1",
                initial_label="Ada",
            ),
            ('<option value="">Select…</option><option value="u1" selected>Ada</option>',),
            ("dz-form-required", "aria-required"),
            id="ref-picker-edit-keeps-current",
        ),
    ],
)
def test_form_widget_labels(field: object, present: tuple, absent: tuple) -> None:
    html = _R.render(field)  # type: ignore[arg-type]
    for frag in present:
        assert frag in html
    for frag in absent:
        assert frag not in html


# ── 3.3.8: one-time-code inputs ────────────────────────────────────────


def _code_entry(mode: str) -> str:
    return _R.render(
        build_code_entry_view(
            product_name="Acme",
            heading="Verify",
            mode=mode,
            methods=(mode,),
            verify_action="/auth/2fa/verify",
            send_action="/auth/2fa/send",
            page_path="/2fa/challenge",
            code_sent=True,
        )
    )


def _setup(email_code_sent: bool) -> str:
    return _R.render(
        build_2fa_setup_view(
            product_name="Acme",
            qr_data_uri="data:image/png;base64,AA",
            secret="ABC",
            email_otp_allowed=True,
            totp_allowed=True,
            email_code_sent=email_code_sent,
        )
    )


@pytest.mark.parametrize(
    ("html_fn", "hinted"),
    [
        pytest.param(lambda: _code_entry("totp"), True, id="challenge-totp"),
        pytest.param(lambda: _code_entry("email_otp"), True, id="challenge-email"),
        pytest.param(lambda: _code_entry("recovery"), False, id="challenge-recovery"),
        pytest.param(lambda: _setup(True), True, id="setup-app-and-email"),
    ],
)
def test_two_factor_code_inputs(html_fn: object, hinted: bool) -> None:
    html = html_fn()  # type: ignore[operator]
    hints = ('autocomplete="one-time-code"', 'inputmode="numeric"')
    for hint in hints:
        assert (hint in html) is hinted


# ── 3.2.4: auth chrome names the product ───────────────────────────────


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        pytest.param({"sitespec": {"brand": {"product_name": "CyFuture"}}}, "CyFuture", id="brand"),
        pytest.param({"sitespec": {}, "app_title": "Tax Desk"}, "Tax Desk", id="app-title"),
        pytest.param(
            {"sitespec": {"brand": {"product_name": "B"}}, "app_title": "T"}, "B", id="brand-wins"
        ),
        pytest.param({}, "Dazzle", id="framework-default"),
    ],
)
def test_product_name_resolution(state: dict, expected: str) -> None:
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(**state)))
    assert product_name(request) == expected


# ── split_content `source:` is rendered once, not escaped again ────────


def test_split_content_source_renders_as_body_html(tmp_path: Path) -> None:
    content = tmp_path / "site" / "content"
    content.mkdir(parents=True)
    (content / "why.md").write_text("- **Fast**\n- Safe\n", encoding="utf-8")
    page = {
        "route": "/",
        "sections": [{"type": "split_content", "source": {"path": "why.md"}}],
    }
    section = _format_page_response(page, tmp_path)["sections"][0]
    assert "<strong>Fast</strong>" in section["body_html"]
    assert "body" not in section
