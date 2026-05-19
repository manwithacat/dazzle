"""Flatten Pydantic models into OTel-compatible span attribute dicts.

OTel span attributes must be primitives (str / int / float / bool) or
sequences of primitives. This module recursively walks a Pydantic
model and produces a flat ``dict[str, scalar]`` keyed by dotted paths.

Lists/tuples that contain only primitives are JSON-encoded into one
string attribute (preserving structure while staying within OTel's
type rules). Lists of nested models are similarly JSON-encoded — they
shouldn't be common in span attrs, but the fallback prevents crashes.

``None`` values are omitted — OTel discourages explicit nulls and our
findings extractor treats missing keys as absent.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

_Scalar = str | int | float | bool


def pydantic_attrs(model: BaseModel, *, prefix: str) -> dict[str, _Scalar]:
    """Return a flat ``dict[str, scalar]`` for ``model``.

    Args:
        model: A Pydantic model instance.
        prefix: Dotted-path prefix prepended to every key. Pass ``""``
            to emit unprefixed keys.

    Raises:
        TypeError: when ``model`` is not a Pydantic model instance.
    """
    if not isinstance(model, BaseModel):
        raise TypeError(f"pydantic_attrs() requires a Pydantic model, got {type(model).__name__}")
    out: dict[str, _Scalar] = {}
    _walk(model.model_dump(mode="python"), prefix, out)
    return out


def _walk(value: Any, key: str, out: dict[str, _Scalar]) -> None:
    if value is None:
        return
    if isinstance(value, bool | int | float | str):
        out[key] = value
        return
    if isinstance(value, dict):
        for k, v in value.items():
            sub_key = f"{key}.{k}" if key else str(k)
            _walk(v, sub_key, out)
        return
    if isinstance(value, list | tuple):
        # Lists are JSON-encoded into a single string attribute so the
        # full structure is preserved without splitting into N keys.
        out[key] = json.dumps(list(value), default=str)
        return
    # Fallback for unexpected types — stringify so the span attr still
    # captures something useful.
    out[key] = str(value)
