"""Deterministic fingerprint of an AppSpec (#1786).

``/health`` reports a ``dsl_hash`` so deploy tooling can tell which DSL a process is
running. Hashing ``model_dump_json()`` directly is hash-seed dependent: the IR carries
``set`` values (``FKGraph._fields`` is ``{entity: {field}}``), pydantic serialises a set
in iteration order, and every uvicorn worker has its own ``PYTHONHASHSEED``, so three
workers reported three hashes for one build. This module canonicalises the dump first:
sets become sorted lists, dict keys are sorted, and anything JSON cannot carry is
rendered through ``repr`` of a canonical form.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from dazzle.core.ir.appspec import AppSpec


def canonical_value(value: Any) -> Any:
    """Return ``value`` with every unordered container made ordered.

    Sets and frozensets become sorted lists (sorted on the canonical JSON text of each
    member, so mixed-type members still order deterministically); dicts keep their keys
    but are emitted with ``sort_keys`` at dump time; tuples and lists keep their order;
    scalars pass through; anything else is reduced to ``repr``.
    """
    if isinstance(value, dict):
        return {str(k): canonical_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [canonical_value(v) for v in value]
    if isinstance(value, (set, frozenset)):
        members = [canonical_value(v) for v in value]
        return sorted(members, key=lambda m: json.dumps(m, sort_keys=True, default=repr))
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return repr(value)


def appspec_fingerprint(appspec: AppSpec, *, length: int = 8) -> str:
    """The first ``length`` hex digits of the SHA-256 of the canonical AppSpec dump.

    Stable across processes, hash seeds and workers for the same IR; changes whenever
    any serialised IR field changes.
    """
    dumped = appspec.model_dump(mode="python")
    text = json.dumps(canonical_value(dumped), sort_keys=True, default=repr)
    return hashlib.sha256(text.encode()).hexdigest()[:length]
