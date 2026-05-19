"""Pydantic-attrs flattener tests."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from dazzle.perf.serializer import pydantic_attrs


class Inner(BaseModel):
    name: str
    count: int


class Outer(BaseModel):
    label: str
    inner: Inner
    flags: list[str]


def test_flattens_pydantic_model_with_dotted_keys() -> None:
    m = Outer(label="x", inner=Inner(name="y", count=3), flags=["a", "b"])
    attrs = pydantic_attrs(m, prefix="op")
    assert attrs == {
        "op.label": "x",
        "op.inner.name": "y",
        "op.inner.count": 3,
        "op.flags": '["a", "b"]',
    }


def test_handles_none_values_by_omission() -> None:
    class WithNone(BaseModel):
        a: str
        b: int | None = None

    attrs = pydantic_attrs(WithNone(a="x"), prefix="op")
    assert attrs == {"op.a": "x"}


def test_lists_of_models_render_as_json() -> None:
    m = Outer(label="x", inner=Inner(name="y", count=1), flags=[])
    attrs = pydantic_attrs(m, prefix="op")
    assert attrs["op.flags"] == "[]"


def test_non_pydantic_input_raises_typeerror() -> None:
    with pytest.raises(TypeError):
        pydantic_attrs({"x": 1}, prefix="op")  # type: ignore[arg-type]


def test_empty_prefix_emits_unprefixed_keys() -> None:
    m = Inner(name="y", count=3)
    attrs = pydantic_attrs(m, prefix="")
    assert attrs == {"name": "y", "count": 3}
