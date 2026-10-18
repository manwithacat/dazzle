"""Unit tests for HtmxDetails dataclass."""

from types import SimpleNamespace
from typing import Any

import pytest

from dazzle.http.runtime.htmx import is_peek_request
from dazzle.http.runtime.htmx_response import HtmxDetails, is_htmx_request


def _fake_request(**headers: str) -> SimpleNamespace:
    """Build a minimal request-like object with the given headers."""
    return SimpleNamespace(headers=headers)


_HX = {"HX-Request": "true"}


@pytest.mark.parametrize(
    ("request_obj", "expected"),
    [
        pytest.param(
            SimpleNamespace(headers=_HX, query_params={"peek": "1"}),
            True,
            id="htmx-get-with-peek-param",
        ),
        pytest.param(
            SimpleNamespace(headers=_HX, query_params={}), False, id="htmx-without-peek-param"
        ),
        # A direct browser GET of the peek URL is a full-page detail view,
        # not a row-peek fragment.
        pytest.param(
            SimpleNamespace(headers={}, query_params={"peek": "1"}),
            False,
            id="peek-param-without-htmx",
        ),
        pytest.param(SimpleNamespace(headers=_HX), False, id="missing-query-params"),
    ],
)
def test_is_peek_request_1494(request_obj: object, expected: bool) -> None:
    """is_peek_request() — #1494 row-peek detail-body fetch detection."""
    assert is_peek_request(request_obj) is expected


@pytest.mark.parametrize(
    ("request_obj", "expected"),
    [
        pytest.param(
            _fake_request(),
            {"is_htmx": False, "is_boosted": False},
            id="non-htmx",
        ),
        pytest.param(
            _fake_request(**_HX),
            {"is_htmx": True, "is_boosted": False},
            id="plain-htmx",
        ),
        pytest.param(
            _fake_request(**_HX, **{"HX-Boosted": "true"}),
            {"is_htmx": True, "is_boosted": True},
            id="boosted",
        ),
        pytest.param(
            _fake_request(**_HX, **{"HX-Boosted": "true", "HX-History-Restore-Request": "true"}),
            {"is_htmx": True, "is_boosted": True, "is_history_restore": True},
            id="history-restore-overrides-boosted",
        ),
        pytest.param(
            _fake_request(**_HX, **{"HX-Current-URL": "http://localhost:3000/app/tasks"}),
            {"current_url": "http://localhost:3000/app/tasks"},
            id="current-url",
        ),
        pytest.param(
            _fake_request(**_HX, **{"HX-Prompt": "confirm delete"}),
            {"prompt": "confirm delete"},
            id="prompt",
        ),
        pytest.param(
            _fake_request(**_HX, **{"HX-Target": "task-table-body"}),
            {"target": "task-table-body"},
            id="target",
        ),
        # htmx 4 sends `tag#id` (id URI-encoded); `target` is the element id,
        # or the bare tag when the element has none (a boosted `body` swap).
        pytest.param(
            _fake_request(**_HX, **{"HX-Target": "main#main-content"}),
            {"target": "main-content", "wants_fragment": True},
            id="target-htmx4-tag-id",
        ),
        pytest.param(
            _fake_request(**_HX, **{"HX-Target": "div#dz-detail-drawer-content"}),
            {"target": "dz-detail-drawer-content", "wants_drawer": True},
            id="target-htmx4-drawer",
        ),
        pytest.param(
            _fake_request(**_HX, **{"HX-Target": "tbody#dt%20tasks-body"}),
            {"target": "dt tasks-body"},
            id="target-htmx4-uri-encoded-id",
        ),
        pytest.param(
            _fake_request(**_HX, **{"HX-Boosted": "true", "HX-Target": "body"}),
            {"target": "body", "wants_fragment": False, "wants_drawer": False},
            id="target-htmx4-boosted-body",
        ),
        pytest.param(
            _fake_request(**_HX, **{"HX-Trigger": "delete-btn", "HX-Trigger-Name": "delete"}),
            {"trigger_id": "delete-btn", "trigger_name": "delete"},
            id="trigger",
        ),
        # An object without .headers yields empty defaults.
        pytest.param(object(), {"is_htmx": False, "target": ""}, id="no-headers-attr"),
    ],
)
def test_from_request_parses_headers(request_obj: object, expected: dict[str, Any]) -> None:
    d = HtmxDetails.from_request(request_obj)
    assert {name: getattr(d, name) for name in expected} == expected


def test_frozen() -> None:
    d = HtmxDetails(is_htmx=True)
    with pytest.raises(AttributeError):
        d.is_htmx = False  # type: ignore[misc]


@pytest.mark.parametrize(
    ("kwargs", "prop", "expected"),
    [
        # wants_fragment — navigation targeting #main-content
        pytest.param(
            {"is_htmx": True, "target": "main-content"},
            "wants_fragment",
            True,
            id="fragment-targeting-main-content",
        ),
        pytest.param(
            {"is_htmx": True, "target": "body"},
            "wants_fragment",
            False,
            id="fragment-targeting-body",
        ),
        pytest.param(
            {"is_htmx": True, "target": "main-content", "is_history_restore": True},
            "wants_fragment",
            False,
            id="fragment-main-content-with-history-restore",
        ),
        pytest.param(
            {"is_htmx": False, "target": "main-content"},
            "wants_fragment",
            False,
            id="fragment-non-htmx-main-content-target",
        ),
        pytest.param(
            {"is_htmx": True, "target": ""}, "wants_fragment", False, id="fragment-no-target"
        ),
        # wants_drawer — workspace detail drawer targeting
        pytest.param(
            {"is_htmx": True, "target": "dz-detail-drawer-content"},
            "wants_drawer",
            True,
            id="drawer-targeting-drawer-content",
        ),
        pytest.param(
            {"is_htmx": True, "target": "body"}, "wants_drawer", False, id="drawer-targeting-body"
        ),
        pytest.param(
            {"is_htmx": False, "target": "dz-detail-drawer-content"},
            "wants_drawer",
            False,
            id="drawer-non-htmx-drawer-target",
        ),
        pytest.param({"is_htmx": True, "target": ""}, "wants_drawer", False, id="drawer-no-target"),
    ],
)
def test_derived_targeting_property(kwargs: dict[str, Any], prop: str, expected: bool) -> None:
    assert getattr(HtmxDetails(**kwargs), prop) is expected


@pytest.mark.parametrize(
    ("target", "table_id"),
    [
        pytest.param("dt-tasks-body", "dt-tasks", id="strip-body-suffix"),
        pytest.param("dt-table-body", "dt-table", id="default-table-id"),
        # Falls back — no suffix to strip.
        pytest.param("some-other-target", "some-other-target", id="no-body-suffix"),
    ],
)
def test_target_derived_table_id(target: str, table_id: str) -> None:
    """HX-Target derives table_id for OOB pagination (list_handlers)."""
    assert HtmxDetails(is_htmx=True, target=target).target.removesuffix("-body") == table_id


def test_is_htmx_request_delegates_to_htmx_details() -> None:
    assert is_htmx_request(_fake_request(**_HX)) is True
    assert is_htmx_request(_fake_request()) is False
    assert is_htmx_request(object()) is False
