"""Icon registry drift gate — registry ↔ generator manifest ↔ shape (TASTE-6)."""

import importlib.util
import re
from pathlib import Path

import pytest

from dazzle.render.fragment.icon_registry import ICONS, LUCIDE_VERSION

pytestmark = pytest.mark.gate

REPO = Path(__file__).parents[2]
GENERATOR = REPO / "packages" / "hatchi-maxchi" / "icons" / "gen_registry.py"
HM_REGISTRY = REPO / "packages" / "hatchi-maxchi" / "icons" / "registry.py"

_ALLOWED_INNER = re.compile(
    r"^(?:\s*<(?:path|circle|rect|line|polyline|polygon|ellipse)\b[^>]*/?>\s*)+$"
)


def _load_generator_manifest() -> tuple[list[str], str]:
    spec = importlib.util.spec_from_file_location("gen_icon_registry", GENERATOR)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.CURATED_ICONS, mod.LUCIDE_VERSION


def test_registry_matches_generator_manifest() -> None:
    curated, gen_version = _load_generator_manifest()
    assert sorted(ICONS) == curated, (
        "icon_registry.py drifted from the generator manifest — "
        "re-run packages/hatchi-maxchi/icons/gen_registry.py --sync"
    )
    assert LUCIDE_VERSION == gen_version


def test_vendored_copy_matches_hm_source_of_truth() -> None:
    """Dazzle's icon_registry.py is a vendored copy of the HM package's
    registry (the upstream source of truth) — byte-identical data."""
    spec = importlib.util.spec_from_file_location("hm_registry", HM_REGISTRY)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert ICONS == mod.ICONS and LUCIDE_VERSION == mod.LUCIDE_VERSION, (
        "vendored dazzle/render/fragment/icon_registry.py drifted from "
        "packages/hatchi-maxchi/icons/registry.py — re-run "
        "packages/hatchi-maxchi/icons/gen_registry.py --sync"
    )


def test_registry_version_matches_vendored_client_bundle() -> None:
    bundle = (
        REPO / "src" / "dazzle" / "page" / "runtime" / "static" / "dist" / "dazzle-icons.min.js"
    )
    assert LUCIDE_VERSION in bundle.read_text(encoding="utf-8", errors="ignore")[:2000], (
        "registry LUCIDE_VERSION must match the vendored client UMD bundle "
        "(the data-lucide fallback path) so server and client icons agree"
    )


def test_registry_values_are_wellformed_stroke_markup() -> None:
    assert len(ICONS) >= 100
    for name, inner in ICONS.items():
        assert re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name), name
        assert _ALLOWED_INNER.match(inner), f"{name}: unexpected markup"
        assert "<script" not in inner and "javascript:" not in inner
