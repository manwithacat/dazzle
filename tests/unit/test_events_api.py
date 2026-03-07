"""Tests for the dazzle_back.events.api public boundary module."""

from dazzle_back.events import api


def test_events_available_true_in_dev():
    """In test/dev env (aiosqlite installed), EVENTS_AVAILABLE should be True."""
    assert api.EVENTS_AVAILABLE is True


def test_core_types_importable():
    """Core zero-dep types are always importable from api module."""
    assert api.EventBus is not None
    assert api.EventEnvelope is not None
    assert api.EventHandler is not None
    assert api.EventBusError is not None
    assert api.SubscriptionInfo is not None
    assert api.ConsumerStatus is not None
    assert api.NackReason is not None


def test_null_types_importable():
    """Null implementations are always importable from api module."""
    assert api.NullBus is not None
    assert api.NullEventFramework is not None


def test_api_all_exports():
    """api.__all__ contains expected symbols."""
    expected = {
        "EventBus",
        "EventHandler",
        "EventEnvelope",
        "SubscriptionInfo",
        "ConsumerStatus",
        "NackReason",
        "EventBusError",
        "NullBus",
        "NullEventFramework",
        "EVENTS_AVAILABLE",
    }
    assert expected.issubset(set(api.__all__))


def test_init_exports_null_types():
    """The main events __init__ also exports null types."""
    from dazzle_back import events

    assert hasattr(events, "NullBus")
    assert hasattr(events, "NullEventFramework")
    assert hasattr(events, "EVENTS_AVAILABLE")
