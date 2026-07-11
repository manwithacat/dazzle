"""Shared HM↔Dazzle contract-model registry for dual-lock gates.

Adding a model-bearing contract = one row here + an ingest seam copy +
a DOM fixture — not a new gate file.
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
