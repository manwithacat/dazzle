"""Tests for _resolve_display_name — FK dict → display string resolution."""

import pytest

from dazzle.http.runtime.workspace_card_data import (
    _inject_display_names,
    _resolve_display_name,
)


class TestResolveDisplayName:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("Alice", "Alice"),  # scalar passthrough
            (42, "42"),  # int → str
            (None, ""),  # None → empty
            ({}, ""),  # empty dict → empty
            ({"id": "abc-123"}, "abc-123"),  # only id → use id
            # Well-known field resolution
            ({"id": "abc-123", "name": "Alice Smith"}, "Alice Smith"),
            ({"id": "abc-123", "title": "Assessment Objective 1"}, "Assessment Objective 1"),
            ({"id": "abc-123", "code": "AO1"}, "AO1"),
            ({"id": "abc-123", "label": "Priority High"}, "Priority High"),
            # __display__ injection — used first
            ({"__display__": "Alice Smith", "id": "abc-123", "name": "alice"}, "Alice Smith"),
            # Priority chain — __display__ > name > code > id
            ({"__display__": "Display", "name": "Name", "code": "Code", "id": "ID"}, "Display"),
            # Non-standard fields — first string value wins
            ({"some_field": "value", "number": 42}, "value"),
        ],
        ids=[
            "string_passthrough",
            "int_passthrough",
            "none_returns_empty",
            "empty_dict",
            "fallback_to_id",
            "name",
            "title",
            "code",
            "label",
            "display_key",
            "priority_order",
            "non_standard_string",
        ],
    )
    def test_resolve(self, value, expected) -> None:
        assert _resolve_display_name(value) == expected


class TestInjectDisplayNames:
    def test_injects_display_for_fk_dicts(self) -> None:
        item = {
            "id": "abc",
            "title": "My Task",
            "assignee": {"id": "u1", "name": "Alice Smith"},
        }
        result = _inject_display_names(item)
        assert result["assignee_display"] == "Alice Smith"
        assert result["assignee"] == {"id": "u1", "name": "Alice Smith"}

    def test_skips_scalar_fields(self) -> None:
        item = {"id": "abc", "title": "Test", "count": 42}
        result = _inject_display_names(item)
        assert "title_display" not in result
        assert "count_display" not in result

    def test_skips_attention_field(self) -> None:
        item = {"id": "abc", "_attention": {"level": "warning"}}
        result = _inject_display_names(item)
        assert "_attention_display" not in result

    def test_multiple_fk_fields(self) -> None:
        item = {
            "id": "abc",
            "student": {"id": "s1", "__display__": "Ben Jones"},
            "subject": {"id": "sub1", "code": "MATH"},
        }
        result = _inject_display_names(item)
        assert result["student_display"] == "Ben Jones"
        assert result["subject_display"] == "MATH"

    def test_empty_dict_fk(self) -> None:
        item = {"id": "abc", "category": {}}
        result = _inject_display_names(item)
        assert result["category_display"] == ""
