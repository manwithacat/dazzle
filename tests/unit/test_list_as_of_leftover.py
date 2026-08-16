"""List leftover as_of must not invent an empty collection (cycle 2165).

Leftover URL junk (``as_of=2abc``, ``zzz``, ``not-a-date``) used to raise
``InvalidTemporalParam`` in ``gated_list``; ``_list_entity_in_process``
then invented items=[] via ``except InvalidTemporalParam: return _empty``.
Empty / invalid restores *no as_of* (current collection). Valid
YYYY-MM-DD still time-travels. Not leftover sort/q (2164) and not
leftover page (2162).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.http.runtime.page_routes import _parse_list_as_of

_PAGE_ROUTES = (
    Path(__file__).resolve().parents[2] / "src" / "dazzle" / "http" / "runtime" / "page_routes.py"
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2abc", None),
        ("zzz", None),
        ("1e2", None),
        ("not-a-date", None),
        ("2026-13-01", None),
        ("2026/06/20", None),
        ("", None),
        (None, None),
        ("  ", None),
        ("2026-06-20", "2026-06-20"),
        (" 2026-01-01 ", "2026-01-01"),
    ],
    ids=[
        "as-of-leftover-suffix",
        "as-of-leftover-named",
        "as-of-leftover-scientific",
        "as-of-leftover-words",
        "as-of-leftover-month",
        "as-of-leftover-slashes",
        "as-of-empty",
        "as-of-none",
        "as-of-whitespace",
        "as-of-valid",
        "as-of-valid-padded",
    ],
)
def test_parse_list_as_of_leftover_does_not_invent(raw: object, expected: str | None) -> None:
    assert _parse_list_as_of(raw) == expected


def test_handle_table_uses_leftover_honest_as_of() -> None:
    """``_handle_table`` must not pass raw leftover as_of into the fetch."""
    src = _PAGE_ROUTES.read_text(encoding="utf-8")
    assert "as_of_raw=_list_as_of" in src
    assert "_list_as_of = _parse_list_as_of(" in src
    assert "except InvalidTemporalParam:\n        return _empty" not in src
    assert "invented items=[]" in src or "must not invent" in src


def test_list_entity_retries_leftover_as_of_instead_of_empty() -> None:
    """InvalidTemporalParam must retry without as_of, not invent ``_empty``."""
    src = _PAGE_ROUTES.read_text(encoding="utf-8")
    assert "as_of_raw = _parse_list_as_of(as_of_raw)" in src
    assert "temporal_as_of_raw=None" in src
    assert "except InvalidTemporalParam:" in src
    # The invent: leftover as_of must not short-circuit to empty.
    assert "except InvalidTemporalParam:\n        return _empty" not in src
