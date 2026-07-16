"""#1616 — api_kb packs load without mcp extra; built-in TOMLs discoverable."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate


def test_load_pack_without_mcp_import() -> None:
    """Dual-lock pins without mcp must resolve packs (#1616)."""
    mod = importlib.import_module("dazzle.api_kb.loader")
    src = Path(mod.__file__).read_text(encoding="utf-8")
    assert "from dazzle.mcp" not in src
    assert "import dazzle.mcp" not in src

    import dazzle.api_kb.loader as loader
    from dazzle.api_kb import load_pack, set_pack_project_root

    set_pack_project_root(None)
    loader._packs_loaded = False
    loader._pack_cache = {}

    pack = load_pack("companies_house_lookup")
    assert pack is not None, "built-in companies_house_lookup pack missing"
    assert any(o.name == "search_companies" for o in pack.operations)
    frag = pack.generate_fragment_source("search_companies")
    assert frag.get("display_key") or frag.get("value_key")


def test_builtin_pack_tomls_exist_on_disk() -> None:
    packs_dir = Path(__file__).resolve().parents[2] / "src" / "dazzle" / "api_kb"
    assert (packs_dir / "companies_house" / "lookup.toml").is_file()
    # package-data declaration documents wheel inclusion
    pyproject = (Path(__file__).resolve().parents[2] / "pyproject.toml").read_text(encoding="utf-8")
    assert "dazzle.api_kb" in pyproject
    assert "**/*.toml" in pyproject
