"""Distillation classifier (`scripts/distill/classify.py`) — archetype detection.

Focus: the `property_based` archetype (#1342 fuzz-leverage follow-up 1a) so the
distillation pass can MEASURE the property-vs-example ratio. Loads the script by path
(scripts/ is not a package)."""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

_CLASSIFY_PATH = Path(__file__).resolve().parents[2] / "scripts" / "distill" / "classify.py"
_spec = importlib.util.spec_from_file_location("distill_classify", _CLASSIFY_PATH)
assert _spec and _spec.loader
classify = importlib.util.module_from_spec(_spec)
# Register before exec so @dataclass can resolve the module via sys.modules.
sys.modules[_spec.name] = classify
_spec.loader.exec_module(classify)


def _archetypes(src: str) -> dict[str, str]:
    """Classify each top-level test function in `src` → {test_name: archetype}.

    Drives the classifier's lower-level functions directly (classify_file requires the
    file to live under the repo root, which a tmp file does not)."""
    tree = ast.parse(src)
    priv, pub = classify._gather_imports(tree)
    out: dict[str, str] = {}
    for top in tree.body:
        if isinstance(top, ast.FunctionDef | ast.AsyncFunctionDef) and top.name.startswith("test_"):
            rec = classify._process_test_function(
                top, top.name, "test_sample.py", top.lineno, priv, pub
            )
            out[top.name] = rec.archetype
    return out


def test_given_test_is_property_based() -> None:
    src = """\
from hypothesis import given, strategies as st


@given(st.text())
def test_prop(s):
    assert isinstance(s, str)
"""
    assert _archetypes(src)["test_prop"] == "property_based"


def test_given_outranks_parametrize() -> None:
    # A test carrying BOTH @given and @parametrize is property_based (the stronger signal).
    src = """\
import pytest
from hypothesis import given, strategies as st


@pytest.mark.parametrize("k", [1, 2, 3])
@given(s=st.text())
def test_both(k, s):
    assert k > 0
"""
    assert _archetypes(src)["test_both"] == "property_based"


def test_parametrize_still_parametric_cluster() -> None:
    src = """\
import pytest


@pytest.mark.parametrize("k", [1, 2, 3])
def test_param(k):
    assert k > 0
"""
    assert _archetypes(src)["test_param"] == "parametric_cluster"


def test_plain_test_not_property_based() -> None:
    src = """\
def test_plain():
    x = 2 + 2
    assert x == 4
    assert x != 5
"""
    assert _archetypes(src)["test_plain"] != "property_based"
