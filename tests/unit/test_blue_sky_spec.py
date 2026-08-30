"""Blue Sky extractor discovers example slices without framework words."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "blue_sky_spec", ROOT / "scripts" / "blue_sky_spec.py"
)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
FIREWALL = _mod.FIREWALL
discover_slices = _mod.discover_slices
example_dir = _mod.example_dir
extract_slice = _mod.extract_slice
list_examples = _mod.list_examples
render_markdown = _mod.render_markdown

pytestmark = pytest.mark.gate


def test_list_examples_includes_invoice_ops() -> None:
    names = list_examples()
    assert "invoice_ops" in names
    assert "simple_task" in names


def test_invoice_ops_has_approver_slice() -> None:
    slices = discover_slices(example_dir("invoice_ops"))
    assert "approver" in slices
    assert slices["approver"]["stories"]


def test_approver_spec_passes_firewall() -> None:
    data = extract_slice(example_dir("invoice_ops"), "approver")
    md = render_markdown(data)
    assert FIREWALL.search(md) is None
    assert "The question this prototype must answer" in md
    assert "Lifecycle:" in md or "Jobs" in md
