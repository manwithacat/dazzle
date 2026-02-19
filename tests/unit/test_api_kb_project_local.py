"""Tests for project-local API pack resolution."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from dazzle.api_kb.loader import (
    list_packs,
    load_pack,
    set_project_root,
)


@pytest.fixture(autouse=True)
def _reset_pack_cache():
    """Reset pack cache between tests."""
    set_project_root(None)
    yield
    set_project_root(None)


def _write_pack_toml(path: Path, name: str, provider: str = "TestVendor") -> None:
    """Write a minimal pack TOML file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        textwrap.dedent(f"""\
            [pack]
            name = "{name}"
            provider = "{provider}"
            category = "testing"
            version = "1.0"
            description = "Test pack"
            base_url = "https://test.example.com"
        """)
    )


def test_project_local_pack_discovered(tmp_path: Path) -> None:
    """Project-local packs in .dazzle/api_packs/ are discovered."""
    pack_dir = tmp_path / ".dazzle" / "api_packs" / "myvendor"
    _write_pack_toml(pack_dir / "my_pack.toml", "my_pack", "MyVendor")

    set_project_root(tmp_path)
    pack = load_pack("my_pack")

    assert pack is not None
    assert pack.name == "my_pack"
    assert pack.provider == "MyVendor"


def test_project_local_overrides_builtin(tmp_path: Path) -> None:
    """Project-local pack overrides built-in pack with same name."""
    # Create a project-local pack with the same name as a built-in
    pack_dir = tmp_path / ".dazzle" / "api_packs" / "sumsub"
    _write_pack_toml(pack_dir / "sumsub_kyc.toml", "sumsub_kyc", "OverriddenSumSub")

    set_project_root(tmp_path)
    pack = load_pack("sumsub_kyc")

    assert pack is not None
    assert pack.provider == "OverriddenSumSub"


def test_builtin_packs_still_available(tmp_path: Path) -> None:
    """Built-in packs remain accessible when project root is set."""
    # Empty project dir (no .dazzle/api_packs/)
    set_project_root(tmp_path)

    # Built-in packs should still load
    packs = list_packs()
    names = {p.name for p in packs}
    assert "sumsub_kyc" in names
    assert "stripe_payments" in names


def test_missing_project_dir_is_fine(tmp_path: Path) -> None:
    """Setting a project root without .dazzle/api_packs/ doesn't error."""
    set_project_root(tmp_path)
    packs = list_packs()
    # Should still have built-in packs
    assert len(packs) > 0


def test_set_project_root_clears_cache(tmp_path: Path) -> None:
    """Changing project root clears the cache for re-discovery."""
    set_project_root(tmp_path)
    packs_before = list_packs()

    # Create a new pack after initial discovery
    pack_dir = tmp_path / ".dazzle" / "api_packs" / "newvendor"
    _write_pack_toml(pack_dir / "new_pack.toml", "new_pack")

    # Reset to force re-discovery
    set_project_root(tmp_path)
    packs_after = list_packs()

    names_before = {p.name for p in packs_before}
    names_after = {p.name for p in packs_after}

    assert "new_pack" not in names_before
    assert "new_pack" in names_after


def test_project_and_builtin_merge(tmp_path: Path) -> None:
    """Project-local and built-in packs are merged in list_packs."""
    pack_dir = tmp_path / ".dazzle" / "api_packs" / "custom"
    _write_pack_toml(pack_dir / "custom_api.toml", "custom_api", "Custom")

    set_project_root(tmp_path)
    packs = list_packs()
    names = {p.name for p in packs}

    assert "custom_api" in names
    assert "sumsub_kyc" in names  # built-in still present
