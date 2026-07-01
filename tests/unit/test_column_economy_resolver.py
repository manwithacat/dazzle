"""Tests for the 2d column-economy default-flip resolver (#1491).

`resolve_column_economy` keeps the top-N most salient auto-derived columns and
sheds the low-signal tail (timestamps, long text), recovered via the default
row drill / peek. A within-budget table is a no-op (byte-stable).
"""

from __future__ import annotations

from dazzle.page.runtime.column_economy_resolver import (
    resolve_column_economy,
    resolve_column_economy_by_usage,
)


def _cols(*specs: tuple[str, str]) -> list[dict[str, str]]:
    return [{"key": k, "type": t} for k, t in specs]


def _key(c: dict[str, str]) -> str:
    return c["key"]


def test_within_budget_is_a_noop() -> None:
    cols = _cols(("title", "text"), ("status", "badge"), ("owner", "ref"))
    assert resolve_column_economy(cols) == cols


def test_over_budget_trims_to_six_in_declaration_order() -> None:
    cols = _cols(
        ("title", "text"),
        ("status", "badge"),
        ("owner", "ref"),
        ("amount", "currency"),
        ("active", "bool"),
        ("due", "date"),
        ("notes", "text"),
        ("created_at", "date"),
    )
    kept = resolve_column_economy(cols)
    assert len(kept) == 6
    # Survivors keep their original relative order (truncation, not reorder).
    keys = [c["key"] for c in kept]
    assert keys == sorted(keys, key=lambda k: [c["key"] for c in cols].index(k))


def test_identifying_field_always_survives() -> None:
    # 'title' declared LAST but is identifying — must beat low-signal columns.
    cols = _cols(*[(f"f{i}", "text") for i in range(7)]) + _cols(("title", "text"))
    kept = {c["key"] for c in resolve_column_economy(cols)}
    assert "title" in kept


def test_auto_timestamp_is_demoted() -> None:
    cols = _cols(
        ("title", "text"),
        ("status", "badge"),
        ("owner", "ref"),
        ("amount", "currency"),
        ("active", "bool"),
        ("priority", "badge"),
        ("created_at", "date"),  # lowest salience — should drop
    )
    kept = {c["key"] for c in resolve_column_economy(cols)}
    assert "created_at" not in kept
    assert {"title", "status", "owner"} <= kept


def test_custom_budget_and_does_not_mutate_input() -> None:
    cols = _cols(*[(f"f{i}", "text") for i in range(10)])
    kept = resolve_column_economy(cols, budget=3)
    assert len(kept) == 3
    assert len(cols) == 10  # input untouched


# --- usage-boosted column economy (ADR-0050 2d → L4) -------------------------


def test_by_usage_below_floor_is_byte_identical() -> None:
    """Cold start / thin signal: below min_samples → the declared-salience truncation."""
    cols = _cols(*[(f"f{i}", "text") for i in range(8)])
    usage = {"f7": 3, "f6": 2}  # total 5 < floor 10
    got = resolve_column_economy_by_usage(cols, usage, key_of=_key, min_samples=10)
    assert got == resolve_column_economy(cols, budget=6)


def test_by_usage_zero_usage_is_byte_identical() -> None:
    cols = _cols(*[(f"f{i}", "text") for i in range(8)])
    assert resolve_column_economy_by_usage(cols, {}, key_of=_key) == resolve_column_economy(cols)


def test_by_usage_rescues_a_heavily_engaged_low_salience_field() -> None:
    """A plain-text field that salience would drop survives when heavily engaged."""
    cols = _cols(
        ("title", "text"),  # identifying → salience 100, always kept
        ("status", "badge"),
        ("owner", "ref"),
        ("amount", "currency"),
        ("active", "bool"),
        ("category", "badge"),
        ("notes", "text"),  # low salience, would drop past budget 6 …
    )
    # …but 'notes' is by far the most engaged (floor met, total 30 >= 10).
    usage = {"notes": 25, "title": 5}
    kept = {c["key"] for c in resolve_column_economy_by_usage(cols, usage, key_of=_key)}
    assert "notes" in kept  # rescued by usage
    assert "title" in kept  # identifying field never displaced


def test_by_usage_never_displaces_identifying_field() -> None:
    """Even a maxed-out usage boost can't outrank the identifying column's floor."""
    cols = _cols(
        ("title", "text"),  # identifying = 100
        ("a", "text"),
        ("b", "text"),
        ("c", "text"),
        ("d", "text"),
        ("e", "text"),
        ("f", "text"),
    )
    usage = {"a": 100, "b": 90, "c": 80, "d": 70, "e": 60, "f": 50}  # title never focused
    kept = {c["key"] for c in resolve_column_economy_by_usage(cols, usage, key_of=_key, budget=6)}
    assert "title" in kept  # salience 100 > any text (30) + boost (≤40) = 70
