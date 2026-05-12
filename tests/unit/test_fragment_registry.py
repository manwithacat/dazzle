"""Unit tests for the fragment registry."""

from pathlib import Path

from dazzle_ui.runtime.fragment_registry import (
    FRAGMENT_REGISTRY,
    PARKING_LOT_FRAGMENTS,
    get_fragment_info,
    get_fragment_registry,
)

TEMPLATES_ROOT = Path(__file__).resolve().parents[2] / "src" / "dazzle_ui" / "templates"

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
            assert "template" in info, f"{name}: missing template"
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

    def test_every_template_resolves_to_disk(self) -> None:
        """Every registry entry's ``template`` path must exist on disk.

        Prevents the v0.67.62–v0.67.76 regression where parking-lot
        entries kept pointing at templates the typed-renderer sweep
        deleted (closed #1043).
        """
        missing = []
        for name, info in FRAGMENT_REGISTRY.items():
            template_path = TEMPLATES_ROOT / info["template"]
            if not template_path.is_file():
                missing.append(f"{name} -> {info['template']}")
        assert not missing, (
            "Fragment registry entries point to deleted templates:\n  " + "\n  ".join(missing)
        )
