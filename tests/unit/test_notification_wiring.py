"""Tests for #952 cycle 4 — entity-event → notification dispatch wiring.

Pre-cycle-4, the cycle-2 dispatcher existed but project code had to
call `dispatcher.dispatch(spec, payload)` manually for every event.
The new wiring module mirrors `job_triggers.py` and `audit_wiring.py`:
register a service callback per notification spec, then the cycle-2
dispatcher fires automatically when entity events match the trigger.

These tests cover:
- `should_fire` semantics (created/updated/deleted/field_changed/status_changed)
- The callback factory's safe-dispatch behaviour (failures don't break mutations)
- `register_notification_triggers` wiring (entity matching, missing-service warning)
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from dazzle_back.runtime.notification_wiring import (
    build_trigger_callbacks,
    register_notification_triggers,
    should_fire,
)


def _trigger(event: str, field: str | None = None, to_value: str | None = None) -> Any:
    return SimpleNamespace(entity="Invoice", event=event, field=field, to_value=to_value)


# ---------------------------------------------------------------------------
# should_fire — event matching
# ---------------------------------------------------------------------------


class TestShouldFireBasicEvents:
    def test_created_matches_created(self):
        assert should_fire(_trigger("created"), event_kind="created", old_data=None, new_data={})

    def test_created_does_not_match_updated(self):
        assert not should_fire(_trigger("created"), event_kind="updated", old_data={}, new_data={})

    def test_deleted_matches_deleted(self):
        assert should_fire(_trigger("deleted"), event_kind="deleted", old_data={}, new_data=None)

    def test_updated_matches_updated(self):
        assert should_fire(_trigger("updated"), event_kind="updated", old_data={}, new_data={})


class TestShouldFireFieldChanged:
    def test_field_changed_fires_when_value_differs(self):
        t = _trigger("field_changed", field="status")
        assert should_fire(
            t, event_kind="field_changed", old_data={"status": "draft"}, new_data={"status": "sent"}
        )

    def test_field_changed_skips_when_value_same(self):
        t = _trigger("field_changed", field="status")
        assert not should_fire(
            t,
            event_kind="field_changed",
            old_data={"status": "sent"},
            new_data={"status": "sent"},
        )

    def test_field_changed_skips_when_field_missing(self):
        # Trigger says field=status but no field declared → fail-closed.
        t = _trigger("field_changed", field=None)
        assert not should_fire(
            t, event_kind="field_changed", old_data={"status": "a"}, new_data={"status": "b"}
        )

    def test_field_changed_skips_on_create(self):
        # field_changed is meaningless on create (no `old`).
        t = _trigger("field_changed", field="status")
        assert not should_fire(
            t, event_kind="field_changed", old_data=None, new_data={"status": "draft"}
        )


class TestShouldFireStatusChanged:
    def test_status_changed_with_to_value_matches_target_only(self):
        t = _trigger("status_changed", field="status", to_value="overdue")
        # draft → overdue: matches
        assert should_fire(
            t,
            event_kind="field_changed",
            old_data={"status": "sent"},
            new_data={"status": "overdue"},
        )
        # draft → sent: skips (wrong target)
        assert not should_fire(
            t,
            event_kind="field_changed",
            old_data={"status": "draft"},
            new_data={"status": "sent"},
        )

    def test_status_changed_without_to_value_matches_any_change(self):
        t = _trigger("status_changed", field="status", to_value=None)
        assert should_fire(
            t,
            event_kind="field_changed",
            old_data={"status": "draft"},
            new_data={"status": "sent"},
        )

    def test_status_changed_defaults_to_field_named_status(self):
        # No explicit field → defaults to "status".
        t = _trigger("status_changed", field=None, to_value="overdue")
        assert should_fire(
            t,
            event_kind="field_changed",
            old_data={"status": "sent"},
            new_data={"status": "overdue"},
        )


# ---------------------------------------------------------------------------
# Callback factory
# ---------------------------------------------------------------------------


class _RecordingDispatcher:
    """Captures dispatch() calls so tests can assert on them."""

    def __init__(self, raise_on_dispatch: bool = False) -> None:
        self.calls: list[tuple[Any, dict[str, Any]]] = []
        self.raise_on_dispatch = raise_on_dispatch

    def dispatch(self, spec: Any, payload: dict[str, Any]) -> list[Any]:
        self.calls.append((spec, payload))
        if self.raise_on_dispatch:
            raise RuntimeError("simulated provider failure")
        return []


def _spec(trigger: Any) -> Any:
    return SimpleNamespace(name="welcome_email", title="Welcome", trigger=trigger)


class TestCallbackFactory:
    def test_on_created_dispatches_when_trigger_matches(self):
        dispatcher = _RecordingDispatcher()
        spec = _spec(_trigger("created"))
        cb = build_trigger_callbacks(spec=spec, dispatcher=dispatcher)
        asyncio.run(cb["on_created"]("uid-1", {"email": "a@b.com"}, None, "create"))
        assert len(dispatcher.calls) == 1
        sent_spec, sent_payload = dispatcher.calls[0]
        assert sent_spec is spec
        assert sent_payload["email"] == "a@b.com"
        # entity_id surfaced for templates that link to the row
        assert sent_payload["entity_id"] == "uid-1"

    def test_on_updated_skips_when_trigger_is_created_only(self):
        dispatcher = _RecordingDispatcher()
        spec = _spec(_trigger("created"))
        cb = build_trigger_callbacks(spec=spec, dispatcher=dispatcher)
        asyncio.run(cb["on_updated"]("uid-1", {"email": "x"}, {"email": "y"}, "update"))
        assert dispatcher.calls == []

    def test_on_updated_fires_field_changed_branch(self):
        dispatcher = _RecordingDispatcher()
        spec = _spec(_trigger("field_changed", field="status"))
        cb = build_trigger_callbacks(spec=spec, dispatcher=dispatcher)
        asyncio.run(cb["on_updated"]("uid-1", {"status": "sent"}, {"status": "draft"}, "update"))
        assert len(dispatcher.calls) == 1

    def test_dispatch_failure_does_not_propagate(self):
        # The mutation must succeed even when the notification fails.
        dispatcher = _RecordingDispatcher(raise_on_dispatch=True)
        spec = _spec(_trigger("created"))
        cb = build_trigger_callbacks(spec=spec, dispatcher=dispatcher)
        # Should not raise
        asyncio.run(cb["on_created"]("uid-1", {"email": "a@b.com"}, None, "create"))
        # Dispatch was attempted
        assert len(dispatcher.calls) == 1


# ---------------------------------------------------------------------------
# register_notification_triggers
# ---------------------------------------------------------------------------


class _RecordingService:
    """BaseService stub: records callback registrations."""

    def __init__(self) -> None:
        self.created: list[Any] = []
        self.updated: list[Any] = []
        self.deleted: list[Any] = []

    def on_created(self, fn: Any) -> None:
        self.created.append(fn)

    def on_updated(self, fn: Any) -> None:
        self.updated.append(fn)

    def on_deleted(self, fn: Any) -> None:
        self.deleted.append(fn)


class TestRegisterNotificationTriggers:
    def test_returns_zero_when_no_notifications(self):
        services = {"User": _RecordingService()}
        result = register_notification_triggers(services, [], _RecordingDispatcher())
        assert result == 0

    def test_wires_callback_against_trigger_entity(self):
        user_svc = _RecordingService()
        services = {"User": user_svc}
        spec = SimpleNamespace(
            name="welcome_email",
            trigger=SimpleNamespace(entity="User", event="created", field=None, to_value=None),
        )
        result = register_notification_triggers(services, [spec], _RecordingDispatcher())
        assert result == 1
        assert len(user_svc.created) == 1
        assert len(user_svc.updated) == 1
        assert len(user_svc.deleted) == 1

    def test_skips_when_service_missing(self, caplog):
        # Spec references entity that has no service — log warning, don't crash.
        services: dict[str, Any] = {}
        spec = SimpleNamespace(
            name="welcome_email",
            trigger=SimpleNamespace(entity="User", event="created", field=None, to_value=None),
        )
        with caplog.at_level("WARNING"):
            result = register_notification_triggers(services, [spec], _RecordingDispatcher())
        assert result == 0
        assert "User" in caplog.text or "welcome_email" in caplog.text

    def test_skips_notifications_with_no_trigger(self):
        # Manual-fire notifications (e.g. password reset) have no trigger entity.
        # They must not crash the wiring pass — they're fired explicitly elsewhere.
        services = {"User": _RecordingService()}
        spec = SimpleNamespace(name="manual_email", trigger=None)
        result = register_notification_triggers(services, [spec], _RecordingDispatcher())
        assert result == 0


# ---------------------------------------------------------------------------
# End-to-end: real dispatcher + IR types
# ---------------------------------------------------------------------------


class TestEndToEnd:
    def test_create_user_dispatches_welcome_email(self):
        """The cycle-2 dispatcher actually receives the call when a User
        is 'created' on a service the wiring registered against."""
        from dazzle.core.ir.notifications import (
            NotificationChannel,
            NotificationRecipient,
            NotificationSpec,
            NotificationTrigger,
        )
        from dazzle.notifications import LogProvider, NotificationDispatcher

        spec = NotificationSpec(
            name="welcome_email",
            title="Welcome",
            trigger=NotificationTrigger(entity="User", event="created"),
            channels=[NotificationChannel.EMAIL],
            subject="Welcome {{ name }}",
            message="Hello {{ name }}",
            recipients=NotificationRecipient(kind="field", value="email"),
        )

        sent: list[Any] = []
        provider = LogProvider()
        original_send = provider.send

        def _capturing_send(notification: Any) -> bool:
            sent.append(notification)
            return original_send(notification)

        provider.send = _capturing_send  # type: ignore[method-assign]
        dispatcher = NotificationDispatcher(provider=provider)

        user_svc = _RecordingService()
        services = {"User": user_svc}
        register_notification_triggers(services, [spec], dispatcher)

        # Fire the create callback — should reach the dispatcher → provider.
        asyncio.run(
            user_svc.created[0](
                "uid-42", {"name": "Ada", "email": "ada@example.com"}, None, "create"
            )
        )

        assert len(sent) == 1
        rendered = sent[0]
        assert rendered.notification_name == "welcome_email"
        assert rendered.subject == "Welcome Ada"
        assert rendered.body == "Hello Ada"
        assert rendered.recipient == "ada@example.com"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
