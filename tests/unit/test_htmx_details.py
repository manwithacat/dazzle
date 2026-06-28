"""Unit tests for HtmxDetails dataclass."""

from types import SimpleNamespace

import pytest

from dazzle.http.runtime.htmx import is_peek_request
from dazzle.http.runtime.htmx_response import HtmxDetails


def _fake_request(**headers: str) -> SimpleNamespace:
    """Build a minimal request-like object with the given headers."""
    return SimpleNamespace(headers=headers)


class TestIsPeekRequest:
    """is_peek_request() — #1494 row-peek detail-body fetch detection."""

    def test_htmx_get_with_peek_param(self) -> None:
        req = SimpleNamespace(headers={"HX-Request": "true"}, query_params={"peek": "1"})
        assert is_peek_request(req) is True

    def test_htmx_without_peek_param(self) -> None:
        req = SimpleNamespace(headers={"HX-Request": "true"}, query_params={})
        assert is_peek_request(req) is False

    def test_peek_param_without_htmx(self) -> None:
        # A direct browser GET of the peek URL is a full-page detail view,
        # not a row-peek fragment.
        req = SimpleNamespace(headers={}, query_params={"peek": "1"})
        assert is_peek_request(req) is False

    def test_missing_query_params(self) -> None:
        req = SimpleNamespace(headers={"HX-Request": "true"})
        assert is_peek_request(req) is False


class TestFromRequest:
    """HtmxDetails.from_request() parsing."""

    def test_non_htmx_request(self) -> None:
        req = _fake_request()
        d = HtmxDetails.from_request(req)
        assert d.is_htmx is False
        assert d.is_boosted is False
        assert d.wants_partial is False

    def test_plain_htmx_request(self) -> None:
        req = _fake_request(**{"HX-Request": "true"})
        d = HtmxDetails.from_request(req)
        assert d.is_htmx is True
        assert d.is_boosted is False
        assert d.wants_partial is False

    def test_boosted_request(self) -> None:
        req = _fake_request(**{"HX-Request": "true", "HX-Boosted": "true"})
        d = HtmxDetails.from_request(req)
        assert d.is_htmx is True
        assert d.is_boosted is True
        assert d.wants_partial is True

    def test_history_restore_overrides_boosted(self) -> None:
        req = _fake_request(
            **{
                "HX-Request": "true",
                "HX-Boosted": "true",
                "HX-History-Restore-Request": "true",
            }
        )
        d = HtmxDetails.from_request(req)
        assert d.is_boosted is True
        assert d.is_history_restore is True
        assert d.wants_partial is False

    def test_current_url_parsed(self) -> None:
        req = _fake_request(
            **{"HX-Request": "true", "HX-Current-URL": "http://localhost:3000/app/tasks"}
        )
        d = HtmxDetails.from_request(req)
        assert d.current_url == "http://localhost:3000/app/tasks"

    def test_prompt_parsed(self) -> None:
        req = _fake_request(**{"HX-Request": "true", "HX-Prompt": "confirm delete"})
        d = HtmxDetails.from_request(req)
        assert d.prompt == "confirm delete"

    def test_target_parsed(self) -> None:
        req = _fake_request(**{"HX-Request": "true", "HX-Target": "task-table-body"})
        d = HtmxDetails.from_request(req)
        assert d.target == "task-table-body"

    def test_trigger_parsed(self) -> None:
        req = _fake_request(
            **{
                "HX-Request": "true",
                "HX-Trigger": "delete-btn",
                "HX-Trigger-Name": "delete",
            }
        )
        d = HtmxDetails.from_request(req)
        assert d.trigger_id == "delete-btn"
        assert d.trigger_name == "delete"

    def test_no_headers_attr(self) -> None:
        """Object without .headers should return empty defaults."""
        d = HtmxDetails.from_request(object())
        assert d.is_htmx is False
        assert d.target == ""

    def test_frozen(self) -> None:
        d = HtmxDetails(is_htmx=True)
        with pytest.raises(AttributeError):
            d.is_htmx = False  # type: ignore[misc]


class TestWantsPartial:
    """Property logic for wants_partial."""

    def test_not_boosted(self) -> None:
        assert HtmxDetails(is_htmx=True, is_boosted=False).wants_partial is False

    def test_boosted_no_restore(self) -> None:
        assert HtmxDetails(is_boosted=True).wants_partial is True

    def test_boosted_with_restore(self) -> None:
        assert HtmxDetails(is_boosted=True, is_history_restore=True).wants_partial is False


class TestWantsFragment:
    """Property logic for wants_fragment (navigation targeting #main-content)."""

    @pytest.mark.parametrize(
        "kwargs,expected",
        [
            ({"is_htmx": True, "target": "main-content"}, True),
            ({"is_htmx": True, "target": "body"}, False),
            ({"is_htmx": True, "target": "main-content", "is_history_restore": True}, False),
            ({"is_htmx": False, "target": "main-content"}, False),
            ({"is_htmx": True, "target": ""}, False),
        ],
        ids=[
            "test_targeting_main_content",
            "test_targeting_body",
            "test_targeting_main_content_with_history_restore",
            "test_non_htmx_with_main_content_target",
            "test_no_target",
        ],
    )
    def test_wants_fragment(self, kwargs: dict, expected: bool) -> None:
        d = HtmxDetails(**kwargs)
        assert d.wants_fragment is expected


class TestWantsDrawer:
    """Property logic for wants_drawer (workspace detail drawer targeting)."""

    def test_targeting_drawer_content(self) -> None:
        d = HtmxDetails(is_htmx=True, target="dz-detail-drawer-content")
        assert d.wants_drawer is True

    def test_targeting_body(self) -> None:
        d = HtmxDetails(is_htmx=True, target="body")
        assert d.wants_drawer is False

    def test_non_htmx_with_drawer_target(self) -> None:
        d = HtmxDetails(is_htmx=False, target="dz-detail-drawer-content")
        assert d.wants_drawer is False

    def test_no_target(self) -> None:
        d = HtmxDetails(is_htmx=True, target="")
        assert d.wants_drawer is False


class TestPartialRendering:
    """Broader partial rendering logic used by page handlers.

    Page handlers use ``htmx.is_htmx and not htmx.is_history_restore``
    which is broader than ``wants_partial`` — any HTMX request (not just
    boosted) benefits from skipping the <head> wrapper when targeting a
    page route that always renders a full document.
    """

    def test_plain_htmx_gets_partial(self) -> None:
        """hx-get to a page route (e.g. row click) should get partial."""
        d = HtmxDetails(is_htmx=True, is_boosted=False)
        assert d.is_htmx and not d.is_history_restore

    def test_boosted_gets_partial(self) -> None:
        d = HtmxDetails(is_htmx=True, is_boosted=True)
        assert d.is_htmx and not d.is_history_restore

    def test_history_restore_gets_full(self) -> None:
        d = HtmxDetails(is_htmx=True, is_boosted=True, is_history_restore=True)
        assert not (d.is_htmx and not d.is_history_restore)

    def test_non_htmx_gets_full(self) -> None:
        d = HtmxDetails(is_htmx=False)
        assert not (d.is_htmx and not d.is_history_restore)

    def test_target_body_gets_partial(self) -> None:
        """Row click targets body — still gets partial."""
        d = HtmxDetails(is_htmx=True, target="body")
        assert d.is_htmx and not d.is_history_restore


class TestTargetDerivedTableId:
    """HX-Target can be used to derive table_id for OOB pagination."""

    def test_strip_body_suffix(self) -> None:
        d = HtmxDetails(is_htmx=True, target="dt-tasks-body")
        table_id = d.target.removesuffix("-body")
        assert table_id == "dt-tasks"

    def test_default_table_id(self) -> None:
        d = HtmxDetails(is_htmx=True, target="dt-table-body")
        table_id = d.target.removesuffix("-body")
        assert table_id == "dt-table"

    def test_no_body_suffix(self) -> None:
        d = HtmxDetails(is_htmx=True, target="some-other-target")
        # Falls back — no suffix to strip
        assert not d.target.endswith("-body")


class TestBackwardCompat:
    """is_htmx_request() still works as before."""

    def test_delegates_to_htmx_details(self) -> None:
        from dazzle.http.runtime.htmx_response import is_htmx_request

        assert is_htmx_request(_fake_request(**{"HX-Request": "true"})) is True
        assert is_htmx_request(_fake_request()) is False
        assert is_htmx_request(object()) is False
