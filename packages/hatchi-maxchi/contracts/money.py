"""HYPERPART: money — major display + hidden minor-unit carrier."""

import html

from pydantic import BaseModel

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="money",
    root="[data-dz-money]",
    nodes=(
        Node(
            "[data-dz-money]",
            attrs={"data-dz-scale": Present(), "data-dz-currency": Present()},
        ),
    ),
)


class MoneyField(BaseModel):
    name: str
    currency: str = "GBP"
    scale: int = 2
    major_display: str = "0.00"
    minor_value: int = 0
    field_id: str = "money-field"


EXEMPLARS: list[MoneyField] = [
    MoneyField(name="amount", currency="GBP", scale=2, major_display="12.50", minor_value=1250),
    MoneyField(name="fee", currency="USD", scale=2, major_display="0.99", minor_value=99),
]


def render(field: MoneyField) -> str:
    fid = html.escape(field.field_id, quote=True)
    name = html.escape(field.name, quote=True)
    return (
        f'<div class="dz-money" data-dz-money '
        f'data-dz-currency="{html.escape(field.currency, quote=True)}" '
        f'data-dz-scale="{field.scale}">'
        f'<input id="{fid}" name="{name}" inputmode="decimal" '
        f'value="{html.escape(field.major_display, quote=True)}" class="dz-form-input">'
        f'<input type="hidden" name="{name}_minor" value="{field.minor_value}">'
        f"</div>"
    )


__all__ = ["DOM_CONTRACT", "MoneyField", "EXEMPLARS", "render"]
