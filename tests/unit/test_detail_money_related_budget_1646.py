"""#1646 — detail money expanded keys + related-tab finger-scale budget.

Pilot (CyFuture): VIEW detail money fields ignored ``{name}_minor`` /
``{name}_currency``; related tabs hard-coded ``page_size=50``.
"""

from __future__ import annotations

from types import SimpleNamespace

from dazzle.http.runtime.dispatch_ctx import _one_detail_field_dict


def _money_field(name: str = "box5_net_vat", *, currency: str = "GBP") -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        key=name,
        label=name.replace("_", " ").title(),
        type="money",
        widget=None,
        extra={"currency_code": currency},
        enum_semantics={},
        ref_entity="",
        ref_route="",
    )


def test_detail_money_prefers_minor_when_bare_empty() -> None:
    """Bare field empty → read ``{name}_minor`` (list/detail parity)."""
    item = {
        "id": "inv-1",
        "box5_net_vat_minor": 1250,
        "box5_net_vat_currency": "GBP",
    }
    out = _one_detail_field_dict(_money_field(), item)
    assert out["kind"] == "money"
    assert out["value"] == 1250
    assert out["currency_code"] == "GBP"


def test_detail_money_uses_item_currency_when_extra_missing() -> None:
    item = {
        "fee_minor": 9900,
        "fee_currency": "EUR",
    }
    f = SimpleNamespace(
        name="fee",
        key="fee",
        label="Fee",
        type="money",
        widget=None,
        extra={},
        enum_semantics={},
        ref_entity="",
        ref_route="",
    )
    out = _one_detail_field_dict(f, item)
    assert out["value"] == 9900
    assert out["currency_code"] == "EUR"


def test_detail_money_bare_value_wins_when_present() -> None:
    item = {
        "box5_net_vat": 500,
        "box5_net_vat_minor": 99999,
        "box5_net_vat_currency": "GBP",
    }
    out = _one_detail_field_dict(_money_field(), item)
    assert out["value"] == 500


def test_detail_money_defaults_currency_gbp() -> None:
    f = SimpleNamespace(
        name="amount",
        key="amount",
        label="Amount",
        type="money",
        widget=None,
        extra={},
        enum_semantics={},
        ref_entity="",
        ref_route="",
    )
    item = {"amount_minor": 100}
    out = _one_detail_field_dict(f, item)
    assert out["value"] == 100
    assert out["currency_code"] == "GBP"


def test_related_tab_page_size_default_is_finger_scale() -> None:
    """Source pins the related-tab budget (no warehouse 50 default)."""
    from pathlib import Path

    src = Path("src/dazzle/http/runtime/page_routes.py").read_text(encoding="utf-8")
    assert "page_size=50" not in src or "_related_page_size" in src
    assert "_related_page_size" in src
    assert "max(1, min(_related_page_size, 50))" in src
    # default 8 appears as budget when tab has no page_size/limit
    assert "if _tab_budget else 8" in src


def test_detail_money_non_money_unchanged() -> None:
    f = SimpleNamespace(
        name="title",
        key="title",
        label="Title",
        type="text",
        widget=None,
        extra={},
        enum_semantics={},
        ref_entity="",
        ref_route="",
    )
    item = {"title": "Hello", "title_minor": 1}
    out = _one_detail_field_dict(f, item)
    assert out["value"] == "Hello"
    assert out["currency_code"] == ""
