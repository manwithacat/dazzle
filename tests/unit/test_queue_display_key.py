"""QUEUE regions must wire display_key so cards are not bare UUIDs.

Regression for qa-trial friction on llm_ticket_classifier: Ticket has
``display_field: subject`` but queue cards labeled only by id.
"""

from __future__ import annotations

from types import SimpleNamespace

from dazzle.http.runtime.workspace_region_render import (
    _entity_display_field,
    _entity_text_identity_key,
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


def test_pick_display_key_skips_duration_prefers_notes() -> None:
    """Duration minutes are measurement chrome, not identity (oral #137)."""
    from dazzle.http.runtime.workspace_region_render import _is_measurement_title_key

    columns = [
        {"key": "device", "type": "ref"},
        {"key": "tester", "type": "ref"},
        {"key": "duration_minutes", "type": "text"},
        {"key": "environment", "type": "badge"},
        {"key": "temperature", "type": "text"},
        {"key": "notes", "type": "text"},
        {"key": "logged_at", "type": "datetime"},
    ]
    assert _is_measurement_title_key("duration_minutes")
    assert _is_measurement_title_key("temperature")
    assert not _is_measurement_title_key("notes")
    assert not _is_measurement_title_key("zzz")
    assert _pick_display_key(columns) == "notes"
    assert _pick_display_key(columns, preferred="notes") == "notes"
    # Author display_field still wins even when it is measurement chrome.
    assert _pick_display_key(columns, preferred="duration_minutes") == "duration_minutes"


def test_pick_display_key_skips_attempt_prefers_failure_reason() -> None:
    """Attempt numbers are sequence chrome, not identity (oral #140)."""
    from dazzle.render.cell_chrome import is_sequence_title_key

    columns = [
        {"key": "invoice", "type": "ref"},
        {"key": "attempt_number", "type": "text"},
        {"key": "status", "type": "badge"},
        {"key": "failure_reason", "type": "text"},
        {"key": "created_at", "type": "datetime"},
    ]
    assert is_sequence_title_key("attempt_number")
    assert not is_sequence_title_key("failure_reason")
    assert _pick_display_key(columns) == "failure_reason"
    assert _pick_display_key(columns, preferred="failure_reason") == "failure_reason"


def test_pick_display_key_does_not_fallback_to_badge() -> None:
    """Fitness repr that sheds notes must not title the enum token (oral #138)."""
    columns = [
        {"key": "type", "type": "badge"},
        {"key": "status", "type": "badge"},
        {"key": "assigned_to", "type": "ref"},
        {"key": "created_by", "type": "ref"},
    ]
    assert _pick_display_key(columns) == ""
    assert _pick_display_key(columns, preferred="notes") == "notes"


def test_entity_text_identity_key_notes_on_task() -> None:
    from pathlib import Path

    from dazzle.core.project import load_project
    from dazzle.http.converters.entity_converter import convert_entity

    spec = load_project(Path("examples/fieldtest_hub"))
    runtime = convert_entity(spec.get_entity("Task"))
    ctx = SimpleNamespace(entity_spec=runtime)
    assert _entity_display_field(ctx) == ""
    assert _entity_text_identity_key(ctx) == "notes"
    assert _entity_text_identity_key(SimpleNamespace(entity_spec=None)) == ""
    assert _entity_text_identity_key(SimpleNamespace()) == ""


def test_entity_display_field_from_ctx() -> None:
    ctx = SimpleNamespace(entity_spec=SimpleNamespace(display_field="subject"))
    assert _entity_display_field(ctx) == "subject"
    assert _entity_display_field(SimpleNamespace(entity_spec=None)) == ""
    assert _entity_display_field(SimpleNamespace()) == ""
