"""Diagram must not dump empty ER while entities exist (oral #166)."""

from __future__ import annotations

from types import SimpleNamespace

from dazzle.http.runtime.workspace_region_computes import compute_diagram_data
from dazzle.http.runtime.workspace_region_render import (
    RegionRenderInputs,
    RenderEnv,
    _build_specialty_adapter_ctx,
)


def test_empty_spec_does_not_invent_leftover_entities() -> None:
    assert compute_diagram_data(None) == ""
    empty = SimpleNamespace(domain=SimpleNamespace(entities=[]))
    mermaid = compute_diagram_data(empty)
    assert mermaid == "erDiagram"
    assert "zzz" not in mermaid


def test_specialty_ctx_forwards_precomputed_mermaid() -> None:
    mermaid = "erDiagram\n    Device {\n        str name\n    }"
    ctx = SimpleNamespace(
        ctx_region=SimpleNamespace(display="DIAGRAM", nodes=[], edges=[]),
        diagram_data=mermaid,
    )
    env = RenderEnv(
        ctx=ctx,  # type: ignore[arg-type]
        ir_region=None,
        inputs=RegionRenderInputs(),
        request=None,
        user_ctx=None,  # type: ignore[arg-type]
        sort=None,
        sort_dir="asc",
    )
    out = _build_specialty_adapter_ctx("DIAGRAM", env, {})
    assert out["diagram_data"] == mermaid
    assert out["nodes"] == []
