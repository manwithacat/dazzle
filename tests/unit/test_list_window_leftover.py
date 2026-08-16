"""List leftover page / page_size must not invent a window (cycle 2162).

Leftover URL junk (``2abc``, ``zzz``, ``1e2``) used to raise in ``int()``
and ``_handle_table``'s bare ``except Exception`` invented an empty table
(loading/empty theater). Empty / invalid restores the server default;
valid whole numbers still window. Not a JS parseInt sibling (2157) —
the invent here is an empty collection, not a silent page 2.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.http.runtime.page_routes import _parse_list_window

_PAGE_ROUTES = (
    Path(__file__).resolve().parents[2] / "src" / "dazzle" / "http" / "runtime" / "page_routes.py"
)


@pytest.mark.parametrize(
    ("raw", "default", "hi", "expected"),
    [
        ("2abc", 1, None, 1),
        ("zzz", 1, None, 1),
        ("1e2", 1, None, 1),
        ("", 1, None, 1),
        (None, 1, None, 1),
        ("  ", 1, None, 1),
        ("0", 1, None, 1),
        ("-1", 1, None, 1),
        ("2", 1, None, 2),
        ("12", 1, None, 12),
        ("2abc", 20, 100, 20),
        ("1e2", 20, 100, 20),
        ("101", 20, 100, 20),
        ("20", 20, 100, 20),
        ("100", 20, 100, 100),
    ],
    ids=[
        "page-leftover-suffix",
        "page-leftover-named",
        "page-leftover-scientific",
        "page-empty",
        "page-none",
        "page-whitespace",
        "page-zero",
        "page-negative",
        "page-valid-2",
        "page-valid-12",
        "size-leftover-suffix",
        "size-leftover-scientific",
        "size-out-of-range",
        "size-valid-default",
        "size-valid-max",
    ],
)
def test_parse_list_window_leftover_does_not_invent(
    raw: object, default: int, hi: int | None, expected: int
) -> None:
    assert _parse_list_window(raw, default=default, hi=hi) == expected


def test_handle_table_uses_leftover_honest_window() -> None:
    """``_handle_table`` must not raw-int leftover page into the fetch."""
    src = _PAGE_ROUTES.read_text(encoding="utf-8")
    assert 'page=_parse_list_window(api_params.get("page"), default=1)' in src
    assert "page_size=_parse_list_window(" in src
    assert 'page=int(api_params.get("page"' not in src
    assert 'page_size=int(api_params.get("page_size"' not in src
    assert "invented an empty table" in src
