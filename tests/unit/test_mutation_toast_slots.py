"""Structured showToast slots on entity mutation + validation paths.

The toast Hyperpart host accepts title / message / actions. Mutation
responses and validation errors must emit those slots via HX-Trigger so
product surfaces (support tickets create/save, etc.) get titled toasts
without each app wiring with_toast by hand.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from dazzle.http.runtime.htmx import (
    htmx_error_response,
    htmx_toast_error_response,
    htmx_trigger_headers,
    json_or_htmx_error,
)
from dazzle.http.runtime.htmx_render import _with_htmx_triggers


def _trigger_payload(headers: dict[str, str]) -> dict:
    raw = headers.get("HX-Trigger") or headers.get("hx-trigger")
    assert raw, f"missing HX-Trigger in {headers!r}"
    return json.loads(raw)


class TestHtmxTriggerHeadersSlots:
    def test_created_has_title_and_body(self) -> None:
        headers = htmx_trigger_headers("Ticket", "created")
        toast = _trigger_payload(headers)["showToast"]
        assert toast["title"] == "Created"
        assert toast["type"] == "success"
        assert "Ticket" in toast["message"]
        assert "created" in toast["message"].lower()
        assert "actions" not in toast

    def test_updated_title_is_saved(self) -> None:
        toast = _trigger_payload(htmx_trigger_headers("Ticket", "updated"))["showToast"]
        assert toast["title"] == "Saved"

    def test_deleted_title(self) -> None:
        toast = _trigger_payload(htmx_trigger_headers("Ticket", "deleted"))["showToast"]
        assert toast["title"] == "Deleted"

    def test_view_action_when_view_url_set(self) -> None:
        toast = _trigger_payload(
            htmx_trigger_headers("Ticket", "created", view_url="/app/ticket/abc")
        )["showToast"]
        assert toast["actions"] == [{"label": "View", "href": "/app/ticket/abc"}]

    def test_entity_event_still_fires(self) -> None:
        payload = _trigger_payload(htmx_trigger_headers("Ticket", "updated"))
        assert payload["entityUpdated"] == {"entity": "Ticket"}


class TestWithHtmxTriggersViewAction:
    def _htmx_request(self) -> MagicMock:
        request = MagicMock()
        request.headers = {"HX-Request": "true"}
        return request

    def test_view_suppressed_when_redirect_matches(self) -> None:
        """Create-with-redirect: toast is titled, but no redundant View action."""
        detail = "/app/ticket/abc-123"
        resp = _with_htmx_triggers(
            self._htmx_request(),
            {"id": "abc-123"},
            "Ticket",
            "created",
            redirect_url=detail,
            view_url=detail,
        )
        toast = _trigger_payload(dict(resp.headers))["showToast"]
        assert toast["title"] == "Created"
        assert "actions" not in toast
        assert resp.headers.get("HX-Redirect") == detail

    def test_view_kept_when_no_redirect(self) -> None:
        """Peek save-and-stay: titled toast + View full page."""
        detail = "/app/ticket/abc-123"
        resp = _with_htmx_triggers(
            self._htmx_request(),
            {"id": "abc-123"},
            "Ticket",
            "updated",
            redirect_url=None,
            view_url=detail,
        )
        toast = _trigger_payload(dict(resp.headers))["showToast"]
        assert toast["title"] == "Saved"
        assert toast["actions"] == [{"label": "View", "href": detail}]
        assert "HX-Redirect" not in resp.headers


class TestErrorToastTitles:
    def test_form_error_toast_has_title(self) -> None:
        resp = htmx_error_response(["title is required"])
        toast = _trigger_payload(dict(resp.headers))["showToast"]
        assert toast["title"] == "Validation error"
        assert toast["type"] == "error"

    def test_toast_only_error_has_title(self) -> None:
        resp = htmx_toast_error_response(["permission denied"])
        toast = _trigger_payload(dict(resp.headers))["showToast"]
        assert toast["title"] == "Couldn't complete"
        assert "permission denied" in toast["message"]

    def test_json_or_htmx_get_error_includes_title(self) -> None:
        request = SimpleNamespace(
            method="GET",
            headers={"HX-Request": "true"},
            query_params={},
        )
        resp = json_or_htmx_error(request, [{"loc": ["sort"], "msg": "invalid sort field"}])
        toast = _trigger_payload(dict(resp.headers))["showToast"]
        assert toast["title"] == "Couldn't complete"
        assert "invalid sort field" in toast["message"]


class TestUuidSerializeUnchanged:
    def test_dict_with_uuid_still_serializes(self) -> None:
        request = MagicMock()
        request.headers = {"HX-Request": "true"}
        uid = uuid4()
        resp = _with_htmx_triggers(request, {"id": uid, "title": "x"}, "Task", "updated")
        body = json.loads(resp.body)
        assert body["id"] == str(uid)
        toast = _trigger_payload(dict(resp.headers))["showToast"]
        assert toast["title"] == "Saved"
