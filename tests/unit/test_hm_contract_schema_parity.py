"""Cross-boundary lock: Dazzle's runtime contract models must match the HM
contract modules field-for-field (schema-level). The wheel can't ship
packages/, so Dazzle keeps copies; THIS gate is what makes them copies
rather than forks. On failure: fix whichever side changed unilaterally —
the HM contract module is the source of truth."""

import importlib

import pytest

from tests.unit.hm_contract_registry import (
    CONTRACT_MODELS,
    canonical_schema,
    load_hm_module,
)

pytestmark = pytest.mark.gate


@pytest.mark.parametrize(
    ("hm_path", "hm_model", "dz_module", "dz_model"),
    CONTRACT_MODELS,
)
def test_schema_parity(hm_path: str, hm_model: str, dz_module: str, dz_model: str) -> None:
    hm_cls = getattr(load_hm_module(hm_path), hm_model)
    dz_cls = getattr(importlib.import_module(dz_module), dz_model)
    hm_schema = canonical_schema(hm_cls.model_json_schema())
    dz_schema = canonical_schema(dz_cls.model_json_schema())
    assert hm_schema == dz_schema, (
        f"{hm_model}↔{dz_model}: Dazzle runtime model diverged from HM {hm_path}.\n"
        f"HM:     {hm_schema}\nDazzle: {dz_schema}"
    )
