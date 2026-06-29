"""ADR-0049 Phase 3a — substrate `MoneyField` parity with the legacy
`form_renderer._render_money` (first-class `: money` field, widget 2/9).

`money` is a first-class lexer type (used by the `pra` fixture). The legacy
widget emits the `x-data="dzMoney"` controller contract — a major-unit text
input backed by a hidden `{name}_minor` integer carrier — in two modes
(fixed-currency vs currency-selector). This pins the substrate `MoneyField`
to the same mount attributes so the dzMoney Alpine controller keeps working
after the 3b forms flip (and money doesn't degrade to a plain number input).
"""

from __future__ import annotations

from dazzle.http.runtime.renderers.fragment_adapter import _field_to_primitive
from dazzle.render.fragment import FragmentRenderer, MoneyField


def _render(field_dict: dict) -> str:
    prim = _field_to_primitive(field_dict)
    assert isinstance(prim, MoneyField), f"expected MoneyField, got {type(prim).__name__}"
    return FragmentRenderer().render(prim)


_FIXED = {
    "name": "amount",
    "label": "Amount",
    "kind": "money",
    "required": True,
    "minor_initial": "1500",
    "extra": {"currency_code": "GBP", "scale": "2", "symbol": "£", "currency_fixed": True},
}

_SELECTOR = {
    "name": "price",
    "label": "Price",
    "kind": "money",
    "extra": {
        "currency_code": "USD",
        "scale": "2",
        "currency_fixed": False,
        "currency_options": [
            {"code": "USD", "scale": "2", "symbol": "$"},
            {"code": "EUR", "scale": "2", "symbol": "€"},
        ],
    },
}


def test_money_field_maps_from_kind() -> None:
    prim = _field_to_primitive(_FIXED)
    assert isinstance(prim, MoneyField)
    assert prim.currency_code == "GBP"
    assert prim.currency_fixed is True
    assert prim.minor_initial == "1500"


def test_money_does_not_degrade_to_number() -> None:
    # The regression Phase-2's review flagged: money → plain number loses the
    # minor/major split + currency. The mapper must route money → MoneyField.
    from dazzle.render.fragment import Field

    prim = _field_to_primitive(_FIXED)
    assert not isinstance(prim, Field)


def test_fixed_mode_controller_contract() -> None:
    html = _render(_FIXED)
    assert 'x-data="dzMoney"' in html
    assert 'data-dz-currency="GBP"' in html
    assert 'data-dz-scale="2"' in html
    # Major-unit visible input bound to the controller.
    assert 'inputmode="decimal"' in html
    assert 'id="field-amount"' in html
    assert 'x-model="displayValue"' in html
    assert '@input="onInput()"' in html
    # Hidden minor + currency carriers.
    assert 'name="amount_minor"' in html
    assert "minorValue = '1500'" in html
    assert 'name="amount_currency"' in html
    assert 'value="GBP"' in html
    # Symbol prefix.
    assert 'class="dz-form-money-prefix"' in html


def test_fixed_mode_required_aria() -> None:
    html = _render(_FIXED)
    assert 'required aria-required="true"' in html


def test_selector_mode_currency_options() -> None:
    html = _render(_SELECTOR)
    assert 'name="price_currency"' in html
    assert '@change="onCurrencyChange($event)"' in html
    assert '<option value="USD"' in html
    assert 'data-symbol="$"' in html
    assert '<option value="EUR"' in html
    # Selector mode has no fixed data-dz-currency on the controller.
    assert "data-dz-currency=" not in html
    # Still carries the hidden minor input.
    assert 'name="price_minor"' in html


# NOTE: the `def test_parity_with_legacy_money` legacy-vs-substrate parity test was removed in ADR-0049
# Phase 3b — `form_renderer` is deleted, so there is no legacy renderer left to
# compare against; the substrate is now the source of truth (parity is recorded
# in git history + the CHANGELOG). The substrate-only assertions above stand.
