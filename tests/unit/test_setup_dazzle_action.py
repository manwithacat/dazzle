"""Pin setup-dazzle to setup-uv v10.0.1 (retries uv.ndjson fetch flake)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

_REPO = Path(__file__).resolve().parents[2]
_ACTION = _REPO / ".github" / "actions" / "setup-dazzle" / "action.yml"

# v10.0.1 — Tolerate transient manifest timeouts (astral-sh/setup-uv#1016).
# Cycle 2171: v8.2.0 still fetched uv.ndjson and `fetch failed` on one
# GUIDE_WALK cell (run 31953872726) while every other job was green.
_SETUP_UV_V10_0_1 = "20cfd1bf945f4377ade1205e4dbc17946fc9a30d"
_PINNED_UV = 'version: "0.11.19"'


def test_setup_dazzle_uses_setup_uv_v10_0_1_with_pinned_uv() -> None:
    text = _ACTION.read_text(encoding="utf-8")
    assert _SETUP_UV_V10_0_1 in text, (
        "setup-dazzle must pin astral-sh/setup-uv@v10.0.1 "
        f"({_SETUP_UV_V10_0_1}) so uv.ndjson fetch failures retry"
    )
    assert "fac544c07dec837d0ccb6301d7b5580bf5edae39" not in text
    assert _PINNED_UV in text, "keep an explicit uv version (do not resolve latest)"
    assert "v10.0.1" in text
