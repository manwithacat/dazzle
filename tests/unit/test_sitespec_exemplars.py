"""Structural gate for the sitespec vision-score exemplar manifest (Goal-2 2A-ii).

The reference exemplars (`scripts/taste/capture_sitespec_references.py::TARGETS`)
anchor the per-family vision score AND double as the visual target an agent studies
when customising HM for a new property (north star). The actual capture needs a
browser + outbound network (CI/workstation), but the MANIFEST is deterministic — so
we gate its coherence here: every aesthetic family stays covered, names are unique,
URLs are well-formed. Keeps the exemplar set honest as families/refs evolve.
"""

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

_SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts" / "taste" / "capture_sitespec_references.py"
)

# The aesthetic families the exemplars must cover (Goal 2). `expressive` is the
# pending 4th; the others are the promoted app themes.
_EXPECTED_FAMILIES = {"linear-dark", "stripe", "paper", "expressive"}
_MIN_EXEMPLARS_PER_FAMILY = 2


def _load_targets() -> list[tuple[str, str, str, list[str]]]:
    spec = importlib.util.spec_from_file_location("_sitespec_refs", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.TARGETS


def test_every_family_has_enough_exemplars() -> None:
    targets = _load_targets()
    per_family: dict[str, int] = {}
    for family, *_ in targets:
        per_family[family] = per_family.get(family, 0) + 1
    assert set(per_family) == _EXPECTED_FAMILIES, (
        f"exemplar families {set(per_family)} != expected {_EXPECTED_FAMILIES}"
    )
    thin = {f: n for f, n in per_family.items() if n < _MIN_EXEMPLARS_PER_FAMILY}
    assert not thin, (
        f"families with too few exemplars (< {_MIN_EXEMPLARS_PER_FAMILY}): {thin}. "
        "A single reference over-fits the judge — add ≥2 best-in-class pages per family."
    )


def test_exemplar_rows_are_well_formed() -> None:
    targets = _load_targets()
    names = [name for _f, name, _u, _t in targets]
    assert len(names) == len(set(names)), f"duplicate exemplar names: {names}"
    for family, name, url, themes in targets:
        assert url.startswith("https://"), f"{family}/{name}: url must be https ({url})"
        assert themes, f"{family}/{name}: at least one theme required"
        assert set(themes) <= {"light", "dark"}, f"{family}/{name}: bad theme in {themes}"
