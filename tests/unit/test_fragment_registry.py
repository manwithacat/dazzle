"""Unit tests for the fragment registry."""

from dazzle.page.runtime.fragment_registry import (
    PARKING_LOT_FRAGMENTS,
    get_fragment_info,
    get_fragment_registry,
)

EXPECTED_FRAGMENTS = [
    "table_rows",
    "table_pagination",
    "inline_edit",
    "form_errors",
    "detail_fields",
    "table_sentinel",
]


class TestFragmentRegistry:
    def test_registry_has_all_fragments(self) -> None:
        registry = get_fragment_registry()
        for name in EXPECTED_FRAGMENTS:
            assert name in registry, f"Missing fragment: {name}"

    def test_registry_entry_structure(self) -> None:
        registry = get_fragment_registry()
        for name, info in registry.items():
            assert "module" in info, f"{name}: missing module"
            assert "params" in info, f"{name}: missing params"
            assert "description" in info, f"{name}: missing description"
            assert isinstance(info["params"], list), f"{name}: params not a list"

    def test_get_fragment_info_found(self) -> None:
        info = get_fragment_info("table_rows")
        assert info is not None
        assert "params" in info

    def test_get_fragment_info_not_found(self) -> None:
        assert get_fragment_info("nonexistent") is None

    def test_fragment_count(self) -> None:
        registry = get_fragment_registry()
        assert len(registry) == len(EXPECTED_FRAGMENTS)

    def test_parking_lot_is_empty_post_1044(self) -> None:
        """Post-#1044: the parking-lot tier is retired. Adding a new
        parking-lot fragment requires re-introducing Jinja2 — gate it
        explicitly so the regression is visible."""
        assert PARKING_LOT_FRAGMENTS == frozenset()
