"""Gate: path packs for recurrent CI-red classes stay wired in ci_changed.

After the 2026-07-28 CI autopsy, HM / render / http touches must select the
packs that would have blocked those reds locally.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "ci_changed.py"


def _load_ci_changed():
    # Register before exec so @dataclass can resolve the module namespace.
    name = "dazzle_scripts_ci_changed"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_hm_paths_select_hm_surface() -> None:
    mod = _load_ci_changed()
    packs = mod.select_packs(
        [
            "packages/hatchi-maxchi/controllers/dz-kanban.js",
            "packages/hatchi-maxchi/components/kanban.css",
        ]
    )
    names = {p.name for p in packs}
    assert "hm-surface" in names
    hm = next(p for p in packs if p.name == "hm-surface")
    joined = " ".join(hm.pytest)
    assert "test_contract_surface_tool" in joined
    assert "test_ux_catalogue" in joined
    assert "test_hm_package_suite_gate" in joined


def test_render_paths_select_catalogue() -> None:
    mod = _load_ci_changed()
    packs = mod.select_packs(["src/dazzle/render/fragment/region/_builders_kanban.py"])
    names = {p.name for p in packs}
    assert "render-catalogue" in names


def test_http_paths_select_ratchets() -> None:
    mod = _load_ci_changed()
    packs = mod.select_packs(["src/dazzle/http/runtime/workspace_route_builder.py"])
    names = {p.name for p in packs}
    assert "http-ratchets" in names
    http = next(p for p in packs if p.name == "http-ratchets")
    joined = " ".join(http.pytest)
    assert "test_clone_ratchet" in joined
    assert "test_deferred_imports_ratchet" in joined
    assert "test_byte_route_proof" in joined


def test_unrelated_docs_alone_selects_nothing_mapped() -> None:
    mod = _load_ci_changed()
    packs = mod.select_packs(["docs/contributing/local-ci-concordance.md"])
    # docs-only may select nothing — ok
    names = {p.name for p in packs}
    assert "hm-surface" not in names
    assert "http-ratchets" not in names


def test_ci_runner_changes_select_the_gate_suite() -> None:
    """A CI-infra diff used to select no pack at all, making it unverifiable.

    Found while consolidating the pip-audit copies (#1745): the entire diff was
    `.github/`, `Makefile`, `scripts/ci_local.sh` and a new `scripts/*.py`, and
    `make ci-changed` reported "no path packs selected". The `-m gate` suite is
    where CI invariants live, so it has to be reachable from a runner change.
    """
    mod = _load_ci_changed()
    for path in (
        ".github/workflows/ci.yml",
        ".github/workflows/main-hygiene.yml",
        ".github/actions/setup-dazzle/action.yml",
        "Makefile",
        "scripts/ci_local.sh",
        "scripts/pip_audit.py",
    ):
        names = {p.name for p in mod.select_packs([path])}
        assert "ci-infra" in names, f"{path} selected nothing"


def test_ci_infra_pack_runs_the_gate_marker() -> None:
    mod = _load_ci_changed()
    pack = next(p for p in mod.select_packs(["Makefile"]) if p.name == "ci-infra")
    assert pack.pytest == ["tests/unit", "-m", "gate"]


def test_docs_only_diff_still_selects_no_ci_infra_pack() -> None:
    """Guard against the new pack swallowing every markdown edit."""
    mod = _load_ci_changed()
    assert "ci-infra" not in {p.name for p in mod.select_packs(["docs/reference/taste.md"])}
