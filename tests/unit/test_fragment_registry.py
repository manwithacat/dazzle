"""Unit tests for the fragment registry."""

from __future__ import annotations

from dazzle_ui.runtime.fragment_registry import get_fragment_info, get_fragment_registry

EXPECTED_FRAGMENTS = [
    "search_select",
    "search_results",
    "search_input",
    "table_rows",
    "table_pagination",
    "inline_edit",
    "bulk_actions",
    "status_badge",
    "form_errors",
]


class TestFragmentRegistry:
    def test_registry_has_all_fragments(self) -> None:
        registry = get_fragment_registry()
        for name in EXPECTED_FRAGMENTS:
            assert name in registry, f"Missing fragment: {name}"

    def test_registry_entry_structure(self) -> None:
        registry = get_fragment_registry()
        for name, info in registry.items():
            assert "template" in info, f"{name}: missing template"
            assert "params" in info, f"{name}: missing params"
            assert "description" in info, f"{name}: missing description"
            assert isinstance(info["params"], list), f"{name}: params not a list"

    def test_get_fragment_info_found(self) -> None:
        info = get_fragment_info("search_select")
        assert info is not None
        assert "emits" in info
        assert "itemSelected" in info["emits"]

    def test_get_fragment_info_not_found(self) -> None:
        assert get_fragment_info("nonexistent") is None

    def test_fragment_count(self) -> None:
        registry = get_fragment_registry()
        assert len(registry) == len(EXPECTED_FRAGMENTS)
