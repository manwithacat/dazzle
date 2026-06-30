"""Tests for the 2d column-economy default-flip resolver (#1491).

`resolve_column_economy` keeps the top-N most salient auto-derived columns and
sheds the low-signal tail (timestamps, long text), recovered via the default
row drill / peek. A within-budget table is a no-op (byte-stable).
"""

from __future__ import annotations

from dazzle.page.runtime.column_economy_resolver import resolve_column_economy


def _cols(*specs: tuple[str, str]) -> list[dict[str, str]]:
    return [{"key": k, "type": t} for k, t in specs]


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
