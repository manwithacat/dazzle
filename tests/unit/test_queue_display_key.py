"""QUEUE regions must wire display_key so cards are not bare UUIDs.

Regression for qa-trial friction on llm_ticket_classifier: Ticket has
``display_field: subject`` but queue cards labeled only by id.
"""

from __future__ import annotations

from types import SimpleNamespace

from dazzle.http.runtime.workspace_region_render import (
    _entity_display_field,
    _pick_display_key,
)


def test_pick_display_key_prefers_entity_display_field() -> None:
    columns = [
        {"key": "status", "type": "badge"},
        {"key": "created_at", "type": "date"},
        {"key": "subject", "type": "text"},
    ]
    assert _pick_display_key(columns, preferred="subject") == "subject"


def test_pick_display_key_without_preferred_skips_badge() -> None:
    columns = [
        {"key": "status", "type": "badge"},
        {"key": "subject", "type": "text"},
    ]
    assert _pick_display_key(columns) == "subject"


def test_pick_display_key_skips_date_prefers_currency() -> None:
    """ISO dates are chrome, not identity — salary queues titled pay (oral #136)."""
    columns = [
        {"key": "person", "type": "ref"},
        {"key": "amount_minor", "type": "currency", "currency_code": "GBP"},
        {"key": "effective_from", "type": "date"},
        {"key": "reason", "type": "badge"},
    ]
    assert _pick_display_key(columns) == "amount_minor"
    no_money = [
        {"key": "person", "type": "ref"},
        {"key": "effective_from", "type": "date"},
        {"key": "reason", "type": "badge"},
        {"key": "note", "type": "text"},
    ]
    assert _pick_display_key(no_money) == "note"


def test_entity_display_field_from_ctx() -> None:
    ctx = SimpleNamespace(entity_spec=SimpleNamespace(display_field="subject"))
    assert _entity_display_field(ctx) == "subject"
    assert _entity_display_field(SimpleNamespace(entity_spec=None)) == ""
    assert _entity_display_field(SimpleNamespace()) == ""
