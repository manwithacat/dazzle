"""Unit tests for the fragment registry."""

from __future__ import annotations

from dazzle_dnr_ui.runtime.fragment_registry import get_fragment_info, get_fragment_registry


class TestFragmentRegistry:
    def test_registry_has_search_select(self) -> None:
        registry = get_fragment_registry()
        assert "search_select" in registry
        assert "template" in registry["search_select"]
        assert "params" in registry["search_select"]

    def test_registry_has_search_results(self) -> None:
        registry = get_fragment_registry()
        assert "search_results" in registry

    def test_get_fragment_info_found(self) -> None:
        info = get_fragment_info("search_select")
        assert info is not None
        assert "emits" in info
        assert "itemSelected" in info["emits"]

    def test_get_fragment_info_not_found(self) -> None:
        assert get_fragment_info("nonexistent") is None
