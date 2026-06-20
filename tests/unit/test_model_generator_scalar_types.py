"""Regression: every ScalarType maps to a non-str Python type unless str is correct.

Why this exists:
    #1012 — `ScalarType.FLOAT` fell through the silent ``str`` fallback
    in ``_scalar_type_to_python``, producing pydantic models that rejected
    real ``float`` values from the DB. The mapping must stay aligned with
    the enum.

What this catches:
    A new ``ScalarType`` member added to ``dazzle_http/specs/entity.py``
    that doesn't get an explicit mapping in
    ``dazzle_http/runtime/model_generator.py``. The fallback would silently
    type the field as ``str``; this test fails loudly instead.
"""

from __future__ import annotations

from dazzle.http.runtime.model_generator import _scalar_type_to_python
from dazzle.http.specs.entity import ScalarType

# Members that genuinely should map to ``str`` (URLs, emails, opaque tokens).
_STR_MEMBERS: frozenset[ScalarType] = frozenset(
    {
        ScalarType.STR,
        ScalarType.TEXT,
        ScalarType.EMAIL,
        ScalarType.URL,
        ScalarType.FILE,
        ScalarType.IMAGE,
        ScalarType.RICHTEXT,
        ScalarType.TIMEZONE,
    }
)


def test_every_scalar_type_has_explicit_mapping() -> None:
    """No ScalarType member should rely on the silent str fallback unless it's a string type."""
    unmapped: list[str] = []
    for member in ScalarType:
        py_type = _scalar_type_to_python(member)
        if py_type is str and member not in _STR_MEMBERS:
            unmapped.append(member.value)
    assert not unmapped, (
        "These ScalarType members fall through the `mapping.get(scalar_type, str)` "
        "fallback and would produce pydantic fields typed as str — the bug class "
        "from #1012. Add an explicit entry to `_scalar_type_to_python` (or, if str "
        "is correct, append to `_STR_MEMBERS` in this test). "
        f"Unmapped: {unmapped}"
    )


def test_float_maps_to_python_float() -> None:
    """Pinned by #1012 — float fields must produce float-typed pydantic models."""
    assert _scalar_type_to_python(ScalarType.FLOAT) is float


def test_decimal_maps_to_python_decimal() -> None:
    """Decimal fields must produce Decimal-typed pydantic models (not float)."""
    from decimal import Decimal

    assert _scalar_type_to_python(ScalarType.DECIMAL) is Decimal


def test_int_maps_to_python_int() -> None:
    assert _scalar_type_to_python(ScalarType.INT) is int


def test_bool_maps_to_python_bool() -> None:
    assert _scalar_type_to_python(ScalarType.BOOL) is bool
