"""Framework structural-fitness — the clone (reuse) ratchet.

Layer-3 filter for the ``reinvented-capability`` counter-prior. A duplication
creep gate, same posture as the complexity ratchet: a *new* or *grown* clone
cluster (a function re-implementing a structure that already exists) is a
regression. Dedup, or — if a cluster is parallel-by-design accepted residue —
regenerate with ``dazzle fitness clones --write-baseline``.

NEVER run ``ruff format`` over the .json baseline (the v0.83.16 lesson — it
injects a trailing comma and breaks JSON parsing).
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from dazzle.fitness.clones import (
    _signature,
    build_clone_baseline,
    compare_clones,
    compute_clone_index,
    stale_baseline_clusters,
)

pytestmark = pytest.mark.gate

_BASELINE = Path("tests/unit/fixtures/clone_baseline.json")
_SRC = Path("src/dazzle")


def test_baseline_is_valid_json() -> None:
    data = json.loads(_BASELINE.read_text())
    assert isinstance(data, list) and data
    assert all(
        {"signature", "count", "names"} <= e.keys() and e["count"] == len(e["names"]) >= 2
        for e in data
    )


def test_current_tree_does_not_regress_against_baseline() -> None:
    baseline = json.loads(_BASELINE.read_text())
    current = compute_clone_index(_SRC)
    violations = compare_clones(baseline, current)
    assert violations == [], (
        f"{len(violations)} duplication regression(s) — reuse the existing function "
        f"instead of re-implementing it, or `dazzle fitness clones --write-baseline` "
        f"if the cluster is parallel-by-design accepted residue:\n  " + "\n  ".join(violations[:20])
    )


def test_baseline_has_no_stale_clusters() -> None:
    """A cluster that shrank or was deduped must be re-baselined (lock the win)."""
    baseline = json.loads(_BASELINE.read_text())
    current = compute_clone_index(_SRC)
    stale = stale_baseline_clusters(baseline, current)
    assert stale == [], (
        f"{len(stale)} baseline cluster(s) shrank or were deduped — "
        f"regenerate with `dazzle fitness clones --write-baseline` to lock the win:\n  "
        + "\n  ".join(stale[:20])
    )


# --- detector unit tests (synthetic) ---


def _write(tmp_path: Path, name: str, body: str) -> None:
    (tmp_path / name).write_text(body)


def test_detects_type2_clone(tmp_path: Path) -> None:
    """Two functions with identical structure (different names + literals) cluster."""
    _write(
        tmp_path,
        "a.py",
        "def alpha(items):\n"
        "    out = []\n"
        "    for it in items:\n"
        "        if it > 1:\n"
        "            out.append(it)\n"
        "    return out\n",
    )
    _write(
        tmp_path,
        "b.py",
        "def bravo(rows):\n"
        "    acc = []\n"
        "    for r in rows:\n"
        "        if r > 9:\n"
        "            acc.append(r)\n"
        "    return acc\n",
    )
    index = compute_clone_index(tmp_path)
    assert len(index) == 1
    members = next(iter(index.values()))
    names = {m.split("::")[1] for m in members}
    assert names == {"alpha", "bravo"}


def test_rename_and_move_do_not_trip_the_gate(tmp_path: Path) -> None:
    """The ratchet is signature-keyed, so renaming/moving a clustered function
    is NOT a violation (no new duplication) — the key fix vs name-keying."""
    body = (
        "def {name}({arg}):\n"
        "    out = []\n"
        "    for it in {arg}:\n"
        "        if it > 1:\n"
        "            out.append(it)\n"
        "    return out\n"
    )
    _write(tmp_path, "a.py", body.format(name="alpha", arg="items"))
    _write(tmp_path, "b.py", body.format(name="bravo", arg="rows"))
    baseline = build_clone_baseline(tmp_path)
    # rename both functions (and the move case is identical — the signature is
    # body-only, so relpath::name changing for both reasons leaves it unchanged)
    _write(tmp_path, "a.py", body.format(name="renamed_alpha", arg="xs"))
    _write(tmp_path, "b.py", body.format(name="renamed_bravo", arg="ys"))
    current = compute_clone_index(tmp_path)
    assert compare_clones(baseline, current) == []  # no spurious "duplication" violation
    assert stale_baseline_clusters(baseline, current) == []  # not flagged stale either


def test_distinct_structure_not_clustered(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "a.py",
        "def alpha(items):\n"
        "    out = []\n"
        "    for it in items:\n"
        "        out.append(it)\n"
        "    return out\n",
    )
    _write(
        tmp_path,
        "b.py",
        "def bravo(x):\n"
        "    if x:\n"
        "        return x * 2\n"
        "    while x:\n"
        "        x -= 1\n"
        "    return x\n",
    )
    assert compute_clone_index(tmp_path) == {}


def test_signature_blanks_names_keeps_api() -> None:
    """Same shape + same method call -> same signature; different method -> different."""
    f1 = ast.parse("def f(a):\n    return a.encode()\n    x = 1\n    y = 2\n    z = 3").body[0]
    f2 = ast.parse("def g(b):\n    return b.encode()\n    p = 9\n    q = 8\n    r = 7").body[0]
    f3 = ast.parse("def h(c):\n    return c.decode()\n    p = 9\n    q = 8\n    r = 7").body[0]
    assert _signature(f1) == _signature(f2)  # renamed locals/literals -> same
    assert _signature(f1) != _signature(f3)  # different method (.encode vs .decode)
