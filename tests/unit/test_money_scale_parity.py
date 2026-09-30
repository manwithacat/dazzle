"""Currency minor-unit rendering must honour the ISO-4217 scale table.

Why this exists
---------------
``format_cell`` used to hardcode ``Decimal(minor) / 100`` and format with
``,.2f`` while ignoring its own ``code`` argument. The canonical scale lives in
:data:`dazzle.core.ir.money.CURRENCY_SCALES` (JPY=0, BHD=3), and
``render/filters.py`` honoured it. The result was that the same record rendered
correctly in one surface and 100x wrong in another: a JPY amount of 1500 minor
units showed as "15.00 JPY" in tables and CSV export while the edit form
showed the true value.

What this catches
-----------------
Any formatter that divides minor units by a literal instead of consulting
``get_currency_scale()``, or that formats with a fixed decimal precision. The
assertion is numeric, so it does not care which symbol/layout convention a
given surface uses — only that the magnitude agrees with the canonical value
object.

How to satisfy it
-----------------
Use ``get_currency_scale(code)`` for both the divisor and the format
precision, as ``_currency_str``/``_currency`` in ``format_cell.py`` and
``_currency_filter`` in ``render/filters.py`` now do.

What this does NOT catch
------------------------
Symbol-table membership/layout divergence between renderers (a cosmetic
inconsistency) — see ``test_currency_symbol_table_ratchet.py`` for that.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

import pytest

from dazzle.core.ir.money import CURRENCY_SCALES, Money, from_money, get_currency_scale
from dazzle.render.filters import _currency_filter
from dazzle.render.fragment.format_cell import _currency, _currency_major

pytestmark = pytest.mark.gate

# Every currency the canonical scale table declares, so all three scale shapes
# are covered: 2-decimal majors, 0-decimal (JPY/KRW/VND/CLP/ISK), 3-decimal
# dinars. Derived from the table itself, so adding a currency here is automatic.
_ALL_CODES = sorted(CURRENCY_SCALES)
_SCALES_COVERED = sorted({get_currency_scale(c) for c in _ALL_CODES})
_AMOUNTS = [0, 1, 7, 100, 999, 1500, 1999, 123456]

_NUMERIC = re.compile(r"[^0-9.]")


def _magnitude(rendered: str) -> Decimal:
    """Extract the numeric magnitude from a formatted currency string.

    Tolerant of symbol prefixes/suffixes and thousands separators, so this
    asserts the *amount*, not the presentation. That is deliberate: two
    surfaces may legitimately disagree on where the symbol sits, but they must
    never disagree on the number of units.
    """
    stripped = _NUMERIC.sub("", rendered)
    if not stripped:
        raise AssertionError(f"no numeric content in {rendered!r}")
    try:
        return Decimal(stripped)
    except InvalidOperation as exc:  # pragma: no cover - defensive
        raise AssertionError(f"unparsable numeric {rendered!r}") from exc


def test_canonical_scale_table_covers_all_three_scale_shapes() -> None:
    """The parametrised cases are only meaningful if the table actually declares
    0-, 2- and 3-decimal currencies. If someone trims CURRENCY_SCALES, fail here
    rather than silently losing the JPY/dinar coverage."""
    assert _SCALES_COVERED == [0, 2, 3], (
        f"expected ISO-4217 scales 0/2/3 to be present, found {_SCALES_COVERED}"
    )


@pytest.mark.parametrize("code", _ALL_CODES)
@pytest.mark.parametrize("minor", _AMOUNTS)
def test_format_cell_minor_units_match_canonical_scale(code: str, minor: int) -> None:
    """`format_cell`'s money inference path divides by the right power of ten."""
    expected = from_money(Money(currency=code, amount_minor=minor))
    assert _magnitude(_currency(minor, code)) == expected, (
        f"format_cell rendered {_currency(minor, code)!r} for {code} minor={minor}; "
        f"canonical major is {expected} (scale {get_currency_scale(code)})"
    )


@pytest.mark.parametrize("code", _ALL_CODES)
@pytest.mark.parametrize("minor", _AMOUNTS)
def test_filters_minor_units_match_canonical_scale(code: str, minor: int) -> None:
    """`_currency_filter` is the reference implementation; pin it so the two
    implementations cannot drift apart again."""
    expected = from_money(Money(currency=code, amount_minor=minor))
    assert _magnitude(_currency_filter(minor, code)) == expected


@pytest.mark.parametrize("code", _ALL_CODES)
def test_format_cell_uses_currency_own_decimal_precision(code: str) -> None:
    """Guard the second, subtler half: a scale-aware division rendered with a
    fixed ``,.2f`` still misstates JPY as "1,500.00" and dinars as "1.500" ->
    "1.50". The rendered number must carry exactly ``get_currency_scale``
    decimal places."""
    scale = get_currency_scale(code)
    rendered = _currency(10**scale, code)
    # Strip the symbol / code decoration first: the suffix layout renders
    # "1.00 AUD", whose ".split('.')[1]" is "00 AUD", not the decimal digits.
    numeric = _NUMERIC.sub("", rendered)
    digits = numeric.split(".")[1] if "." in numeric else ""
    assert len(digits) == scale, (
        f"{code} (scale {scale}) rendered {rendered!r} with {len(digits)} decimal places; "
        "the format precision must come from get_currency_scale()"
    )


@pytest.mark.parametrize("code", _ALL_CODES)
def test_format_cell_major_units_are_not_rescaled(code: str) -> None:
    """The explicit ``format: currency`` path takes MAJOR units. It must render
    the value as-is — never apply a second minor-unit division."""
    scale = get_currency_scale(code)
    major = Decimal(10) ** scale
    assert _magnitude(_currency_major(major, code)) == major
