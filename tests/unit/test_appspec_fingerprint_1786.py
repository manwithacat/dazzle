"""`/health` `dsl_hash` is the same under every hash seed (#1786).

The IR carries sets (``FKGraph._fields``), pydantic serialises them in iteration order,
and each uvicorn worker has its own ``PYTHONHASHSEED``, so ``sha256(model_dump_json())``
gave one hash per worker. The fingerprint canonicalises the dump first; this gate loads
one example under two seeds in separate interpreters and expects one hash.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from dazzle.core.ir.fingerprint import canonical_value

REPO = Path(__file__).resolve().parents[2]
EXAMPLE = REPO / "examples" / "simple_task"

_SCRIPT = """
import pathlib, sys
from dazzle.core.appspec_loader import load_project_appspec
from dazzle.core.ir.fingerprint import appspec_fingerprint
spec = load_project_appspec(pathlib.Path(sys.argv[1]))
print(appspec_fingerprint(spec))
"""


def _fingerprint_under_seed(seed: str) -> str:
    proc = subprocess.run(
        [sys.executable, "-c", _SCRIPT, str(EXAMPLE)],
        capture_output=True,
        text=True,
        check=True,
        env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin:/bin"},
        cwd=REPO,
        timeout=120,
    )
    return proc.stdout.strip()


@pytest.mark.xdist_group("examples_simple_task")
def test_fingerprint_is_hash_seed_independent() -> None:
    a, b = _fingerprint_under_seed("1"), _fingerprint_under_seed("2")
    assert len(a) == 8
    assert a == b, f"dsl_hash drifted with the hash seed: {a} != {b}"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ({"b", "a", "c"}, ["a", "b", "c"]),
        (frozenset({3, 1, 2}), [1, 2, 3]),
        ({"k": {"y", "x"}}, {"k": ["x", "y"]}),
        ([{"z", "a"}, ("t", {"q"})], [["a", "z"], ["t", ["q"]]]),
        ({1, "1"}, ["1", 1]),
    ],
    ids=["str-set", "frozenset", "nested-dict", "nested-list-tuple", "mixed-types"],
)
def test_canonical_value_orders_unordered_containers(value: object, expected: object) -> None:
    assert canonical_value(value) == expected
