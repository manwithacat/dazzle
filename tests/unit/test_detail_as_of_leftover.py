"""Page DETAIL leftover as_of must not invent current / 404 (cycle 2166).

``_read_entity_in_process`` used to ignore ``?as_of=`` and
``CRUDService.read`` dropped the kwarg, so HTML detail invented the
*current* row (or 404 if leftover were wired like REST
``date.fromisoformat``). Leftover junk (``2abc``, ``zzz``,
``not-a-date``) restores *no as_of*. Valid YYYY-MM-DD still
time-travels. Not leftover list as_of (2165) and not leftover
sort/page.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from dazzle.http.runtime.page_routes import _detail_as_of, _parse_list_as_of

_PAGE_ROUTES = (
    Path(__file__).resolve().parents[2] / "src" / "dazzle" / "http" / "runtime" / "page_routes.py"
)
_SERVICE = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "service_generator.py"
)
_GATED = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "access"
    / "gated.py"
)
_SCOPE = (
    Path(__file__).resolve().parents[2] / "src" / "dazzle" / "http" / "runtime" / "scope_filters.py"
)


def _prc(
    as_of_raw: object | None,
    *,
    temporal: bool = True,
    param: str = "as_of",
    entity: str = "Employment",
) -> SimpleNamespace:
    spec = SimpleNamespace(temporal=SimpleNamespace(as_of_param=param) if temporal else None)
    svc = SimpleNamespace(entity_spec=spec)
    q: dict[str, object] = {}
    if as_of_raw is not None:
        q[param] = as_of_raw
    return SimpleNamespace(
        deps=SimpleNamespace(entity_services={entity: svc}),
        request=SimpleNamespace(query_params=q),
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
        ("2026-06-20", date(2026, 6, 20)),
        (" 2026-01-01 ", date(2026, 1, 1)),
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
def test_detail_as_of_leftover_does_not_invent(raw: object, expected: date | None) -> None:
    assert _detail_as_of(_prc(raw), "Employment") == expected


def test_detail_as_of_absent_when_entity_is_not_temporal() -> None:
    assert _detail_as_of(_prc("2026-06-20", temporal=False), "Employment") is None


def test_detail_as_of_honours_custom_param() -> None:
    prc = _prc("2026-06-20", param="snapshot_date")
    assert _detail_as_of(prc, "Employment") == date(2026, 6, 20)


def test_detail_as_of_reuses_leftover_honest_parse() -> None:
    """DETAIL leftover shares the ISO parse; does not clone list fetch theater."""
    assert _parse_list_as_of("zzz") is None
    assert _parse_list_as_of("2026-06-20") == "2026-06-20"


def test_handle_detail_uses_leftover_honest_as_of() -> None:
    """``_handle_detail`` must parse leftover-honest as_of into the read."""
    src = _PAGE_ROUTES.read_text(encoding="utf-8")
    assert "as_of=_detail_as_of(" in src
    assert "def _detail_as_of(" in src
    assert "invented the *current* row" in src or "invented the current row" in src


def test_edit_form_does_not_time_travel() -> None:
    """Edit stays current — do not clone DETAIL as_of onto the form."""
    src = _PAGE_ROUTES.read_text(encoding="utf-8")
    # The only as_of=_detail_as_of call is the detail handler.
    assert src.count("as_of=_detail_as_of(") == 1
    assert "Failed to fetch initial form values" in src


def test_read_entity_forwards_as_of() -> None:
    src = _PAGE_ROUTES.read_text(encoding="utf-8")
    assert '_read_kw["as_of"] = as_of' in src
    assert "as_of: Any = None" in src


def test_crud_service_read_forwards_as_of() -> None:
    src = _SERVICE.read_text(encoding="utf-8")
    assert "as_of: Any = None" in src
    assert "as_of=as_of" in src
    assert "invented the *current*" in src or "invented the current" in src


def test_gated_read_and_scoped_pre_read_thread_as_of() -> None:
    gated = _GATED.read_text(encoding="utf-8")
    scope = _SCOPE.read_text(encoding="utf-8")
    assert "as_of: Any = None" in gated
    assert "as_of=as_of" in gated
    assert '_read_kw["as_of"] = as_of' in gated
    assert "as_of: Any = None" in scope
    assert 'filters["__as_of"] = as_of' in scope
    assert "_execute_read_as_of(" in scope
    assert "_scoped_list_filters(" in scope


@pytest.mark.asyncio
async def test_crud_service_read_passes_as_of_to_repository() -> None:
    from pydantic import BaseModel, ConfigDict

    from dazzle.http.runtime.service_generator import CRUDService

    class _Row(BaseModel):
        model_config = ConfigDict(extra="allow")
        id: object

    repo = MagicMock()
    repo.read = AsyncMock(return_value=None)
    svc: CRUDService[Any, Any, Any] = CRUDService(
        entity_name="Employment",
        model_class=_Row,
        create_schema=_Row,
        update_schema=_Row,
        repository=repo,
    )
    eid = uuid4()
    when = date(2025, 6, 1)
    await svc.read(eid, as_of=when)
    repo.read.assert_awaited_once_with(eid, include=None, as_of=when)
