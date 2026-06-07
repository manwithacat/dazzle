"""Distillation clusterer (`scripts/distill/cluster.py`) — fuzz-target recommendation.

#1342 fuzz-leverage follow-up 1b: each redundancy cluster gets a `recommended_form`
(parametrise / property / fuzz) so the redundancy backlog reads as a ranked fuzz-target
worklist. Loads the script by path (scripts/ is not a package)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_PATH = Path(__file__).resolve().parents[2] / "scripts" / "distill" / "cluster.py"
_spec = importlib.util.spec_from_file_location("distill_cluster", _PATH)
assert _spec and _spec.loader
cluster = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = cluster
_spec.loader.exec_module(cluster)


def test_dsl_parser_file_recommends_fuzz() -> None:
    form, why = cluster.recommend_form("tests/unit/test_parser.py", "('eq',)")
    assert form == "fuzz" and why


def test_input_boundary_file_recommends_property() -> None:
    for f in (
        "tests/unit/test_saml_metadata.py",
        "tests/unit/test_secret_rotation.py",
        "tests/unit/test_connection_crypto.py",
        "tests/unit/test_jwt_security.py",
    ):
        form, _why = cluster.recommend_form(f, "('eq',)")
        assert form == "property", f


def test_plain_file_recommends_parametrise() -> None:
    form, _why = cluster.recommend_form("tests/unit/test_workspace_routes.py", "('eq',)")
    assert form == "parametrise"
