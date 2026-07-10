"""Cross-boundary lock: Dazzle's runtime contract models must match the HM
contract modules field-for-field (schema-level). The wheel can't ship
packages/, so Dazzle keeps copies; THIS gate is what makes them copies
rather than forks. On failure: fix whichever side changed unilaterally —
the HM contract module is the source of truth."""

import importlib
import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

REPO_ROOT = Path(__file__).resolve().parents[2]
HM = REPO_ROOT / "packages" / "hatchi-maxchi"

# (hm_module_path, hm_model_name, dazzle_import_path)
PAIRS = [
    ("contracts/grid_edit.py", "GridEditCell", "dazzle.render.fragment.ingest"),
]


def _load_hm_module(rel: str):
    pytest.importorskip("fastapi")
    if str(HM) not in sys.path:
        sys.path.insert(0, str(HM))
    spec = importlib.util.spec_from_file_location(f"hm_{Path(rel).stem}", HM / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclass/pydantic need the module registered
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _canonical(schema: dict) -> object:
    """Structural fields only — strips titles/descriptions/default-ordering
    noise so pydantic-version skew between envs can't fail the gate."""
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


@pytest.mark.parametrize(("hm_path", "model_name", "dz_module"), PAIRS)
def test_schema_parity(hm_path: str, model_name: str, dz_module: str) -> None:
    hm_model = getattr(_load_hm_module(hm_path), model_name)
    dz_model = getattr(importlib.import_module(dz_module), model_name)
    hm_schema = _canonical(hm_model.model_json_schema())
    dz_schema = _canonical(dz_model.model_json_schema())
    assert hm_schema == dz_schema, (
        f"{model_name}: Dazzle runtime model diverged from HM {hm_path}.\n"
        f"HM:     {hm_schema}\nDazzle: {dz_schema}"
    )
