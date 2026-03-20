"""Tests for _resolve_display_name — FK dict → display string resolution."""

from __future__ import annotations

from dazzle_back.runtime.workspace_rendering import (
    _inject_display_names,
    _resolve_display_name,
)


class TestResolveDisplayName:
    def test_string_passthrough(self) -> None:
        assert _resolve_display_name("Alice") == "Alice"

    def test_int_passthrough(self) -> None:
        assert _resolve_display_name(42) == "42"

    def test_none_returns_empty(self) -> None:
        assert _resolve_display_name(None) == ""

    def test_dict_with_display_key(self) -> None:
        val = {"__display__": "Alice Smith", "id": "abc-123", "name": "alice"}
        assert _resolve_display_name(val) == "Alice Smith"

    def test_dict_with_name(self) -> None:
        val = {"id": "abc-123", "name": "Alice Smith"}
        assert _resolve_display_name(val) == "Alice Smith"

    def test_dict_with_title(self) -> None:
        val = {"id": "abc-123", "title": "Assessment Objective 1"}
        assert _resolve_display_name(val) == "Assessment Objective 1"

    def test_dict_with_code(self) -> None:
        val = {"id": "abc-123", "code": "AO1"}
        assert _resolve_display_name(val) == "AO1"

    def test_dict_with_label(self) -> None:
        val = {"id": "abc-123", "label": "Priority High"}
        assert _resolve_display_name(val) == "Priority High"

    def test_dict_fallback_to_id(self) -> None:
        val = {"id": "abc-123"}
        assert _resolve_display_name(val) == "abc-123"

    def test_dict_priority_order(self) -> None:
        """__display__ takes priority over name, which takes priority over code."""
        val = {"__display__": "Display", "name": "Name", "code": "Code", "id": "ID"}
        assert _resolve_display_name(val) == "Display"

    def test_empty_dict(self) -> None:
        assert _resolve_display_name({}) == ""

    def test_dict_with_only_non_standard_string(self) -> None:
        val = {"some_field": "value", "number": 42}
        assert _resolve_display_name(val) == "value"


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
