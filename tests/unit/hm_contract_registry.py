"""Shared HM↔Dazzle contract registries for dual-lock gates.

**Model-bearing** (schema parity + DOM): one ``CONTRACT_MODELS`` row +
ingest seam copy + DOM fixture.

**Root-only** (DOM only, #1578): one ``DOM_ONLY_CONTRACTS`` row + a fixture
callable in ``test_hm_contract_dom_conformance`` — no fake Pydantic model,
no schema parity. Root-only modules without a stable Dazzle emission path
are listed in ``DOM_ONLY_DEFERRED`` (inventory only).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HM = REPO_ROOT / "packages" / "hatchi-maxchi"

# (hm_rel_path, hm_model_name, dazzle_module, dazzle_model_name)
CONTRACT_MODELS: list[tuple[str, str, str, str]] = [
    ("contracts/grid_edit.py", "GridEditCell", "dazzle.render.fragment.ingest", "GridEditCell"),
    ("contracts/combobox.py", "ComboboxField", "dazzle.render.fragment.ingest", "ComboboxField"),
    ("contracts/tags.py", "TagsField", "dazzle.render.fragment.ingest", "TagsField"),
    ("contracts/money.py", "MoneyField", "dazzle.render.fragment.ingest", "MoneyField"),
]

# Root-only Hyperparts with a stable Dazzle emission path.
# (hm_rel_path, part_id, require_root)
# Fixture builders live in test_hm_contract_dom_conformance (keyed by part_id).
DOM_ONLY_CONTRACTS: list[tuple[str, str, bool]] = [
    ("contracts/slider.py", "slider", True),
    ("contracts/color.py", "color", True),
    ("contracts/search_select.py", "search_select", True),
    ("contracts/app_shell.py", "app_shell", True),
    ("contracts/command.py", "command", True),
    ("contracts/confirm_panel.py", "confirm_panel", True),
    ("contracts/tabs.py", "tabs", True),
    ("contracts/dialog.py", "dialog", True),
]

# Root-only modules without a simple FragmentRenderer / page fixture yet.
# Keep as inventory so the drain is greppable; add a DOM_ONLY_CONTRACTS row
# when a stable emission site exists.
DOM_ONLY_DEFERRED: list[tuple[str, str]] = [
    ("contracts/wizard.py", "page-layer experience_renderer only"),
    ("contracts/pdf.py", "page-layer pdf_viewer_renderer (not Fragment)"),
    ("contracts/grid.py", "root-only thin; covered by grid_edit dual lock"),
    ("contracts/grid_cols.py", "needs full data-table chrome fixture"),
    ("contracts/grid_resize.py", "needs full data-table chrome fixture"),
    ("contracts/master_detail.py", "no stable Dazzle emission site yet"),
    ("contracts/confirm.py", "hx-confirm attribute path, not data-dz root"),
]


def load_hm_module(rel: str):
    """Load an HM contract module by path relative to packages/hatchi-maxchi."""
    pytest.importorskip("fastapi")
    if str(HM) not in sys.path:
        sys.path.insert(0, str(HM))
    spec = importlib.util.spec_from_file_location(f"hm_{Path(rel).stem}", HM / rel)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def canonical_schema(schema: dict) -> object:
    """Structural fields only — strip titles/descriptions/default-ordering noise."""
    keep = {
        "type",
        "required",
        "enum",
        "items",
        "properties",
        "anyOf",
        "prefixItems",
        "additionalProperties",
        "minItems",
        "maxItems",
        "const",
        "$defs",
        "$ref",
    }

    def walk(node: object) -> object:
        if isinstance(node, dict):
            out: dict = {}
            for k, v in sorted(node.items()):
                if k not in keep:
                    continue
                if k == "required":
                    out[k] = sorted(v)
                elif k in ("properties", "$defs"):
                    out[k] = {name: walk(sub) for name, sub in sorted(v.items())}
                else:
                    out[k] = walk(v)
            return out
        if isinstance(node, list):
            return [walk(x) for x in node]
        return node

    return walk(schema)
