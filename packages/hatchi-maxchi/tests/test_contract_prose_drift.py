"""#1579 — prose ``Contract:`` header ↔ ``DOM_CONTRACT`` attr-name drift gate.

The structured ``DOM_CONTRACT`` in ``contracts/<part>.py`` is the machine-
checkable source of truth. Controllers carry a prose ``Contract:`` header
(or at least mention the same ``data-dz-*`` names) so agents reading the
JS file see the same seam. This gate keeps the two from drifting.

Pairing: each contract module maps to a controller file via stem convention
(``contracts/grid_edit.py`` → ``controllers/dz-grid-edit.js``) with a small
special-case table. Hyperpart ``contracts=`` from the registry is the set
of modules under test.

Checks:
1. Every ``data-dz-*`` / ``data-hm-*`` / ``hx-confirm`` name in a
   ``DOM_CONTRACT`` appears in the paired controller source (code or comment).
2. When a formal ``Contract:`` block exists, those same required names appear
   *inside the block* (header documents the structured contract).
3. When a ``Contract:`` block exists, prose ``data-dz-*`` names are a subset
   of the paired ``DOM_CONTRACT`` plus ``TRANSIENT_STATE_ATTRS`` (runtime-only
   flags like ``data-dz-open``). Thin-root contracts whose prose documents a
   larger controller surface (base ``grid``) skip the reverse subset check —
   expand the DOM_CONTRACT before re-enabling reverse for those.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PKG))
sys.path.insert(0, str(PKG / "site"))

from registry import HYPERPARTS  # noqa: E402

# Contract stem → controller path when convention dz-<stem-with-dashes> fails.
_CONTROLLER_SPECIAL: dict[str, str] = {
    "confirm_panel": "controllers/dz-confirm-gate.js",
    "color": "controllers/dz-color.js",
}

# Runtime / progressive-enhancement flags controllers set that are intentionally
# outside the static DOM_CONTRACT (server-emitted seed attrs only).
TRANSIENT_STATE_ATTRS: frozenset[str] = frozenset(
    {
        "data-dz-open",
        "data-dz-enhanced",
        "data-dz-resizing",
        "data-dz-pdf-state",
        "data-dz-pdf-status",
        "data-dz-pdf-page",
        "data-dz-pdf-page-count",
        "data-dz-pdf-prev",
        "data-dz-pdf-next",
        "data-dz-pdf-zoom-in",
        "data-dz-pdf-zoom-out",
        "data-dz-pdf-fit-width",
        "data-dz-pdf-worker",
        "data-dz-pdf-initial-page",
        "data-dz-confirm-href",  # confirm-panel action chrome, not gate root
        "data-dz-native-confirm",  # confirm controller opt-out
        "data-dz-widget",  # progressive mount marker; contract may use value form
        "data-dz-bulk-count",
        "data-dz-bulk-count-target",
        "data-dz-grid-all-matching",
        "data-dz-grid-announce",
        "data-dz-grid-body",
        "data-dz-grid-bulk-action",
        "data-dz-grid-bulk-refresh",
        "data-dz-grid-clear",
        "data-dz-grid-debounce",
        "data-dz-grid-excluded",
        "data-dz-grid-filter",
        "data-dz-grid-goto",
        "data-dz-grid-matching-total",
        "data-dz-grid-page",
        "data-dz-grid-page-next",
        "data-dz-grid-page-prev",
        "data-dz-grid-page-size",
        "data-dz-grid-row-id",
        "data-dz-grid-scope",
        "data-dz-grid-search",
        "data-dz-grid-select",
        "data-dz-grid-select-all",
        "data-dz-grid-select-all-matching",
        "data-dz-grid-sort",
        "data-dz-grid-sort-cycle",
        "data-dz-grid-src",
        "data-dz-grid-total",
        "data-dz-grid-url",
        "hx-confirm",  # confirm extension on bulk, not grid root contract
    }
)

# Thin DOM_CONTRACT roots whose controller prose documents a larger surface —
# reverse (prose ⊆ contract) is skipped until the structured contract grows.
_THIN_ROOT_SKIP_REVERSE: frozenset[str] = frozenset({"grid"})

_ATTR_RE = re.compile(r"data-dz-[\w-]+|data-hm-[\w-]+|hx-confirm\b")
_CONTRACT_BLOCK_RE = re.compile(r"\*\s*Contract:\s*\n(.*?)(?:\*/)", re.S)


def _load_contract(rel: str):
    path = PKG / rel
    name = f"prose_drift_{path.stem}"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _dom_data_attrs(mod) -> set[str]:
    """data-dz-* / data-hm-* / hx-confirm names from DOM_CONTRACT only."""
    dc = getattr(mod, "DOM_CONTRACT", None)
    if dc is None:
        return set()
    out: set[str] = set()
    for sel in (dc.root, *(n.selector for n in dc.nodes)):
        out |= set(_ATTR_RE.findall(sel))
    for n in dc.nodes:
        for k in n.attrs:
            if _ATTR_RE.fullmatch(k) or k.startswith("data-dz-") or k.startswith("data-hm-"):
                out.add(k)
            elif k == "hx-confirm":
                out.add(k)
    return out


def _contract_block(text: str) -> str | None:
    m = _CONTRACT_BLOCK_RE.search(text)
    return m.group(1) if m else None


def _controller_for_contract(stem: str, hyperpart) -> str | None:
    if stem in _CONTROLLER_SPECIAL:
        return _CONTROLLER_SPECIAL[stem]
    cand = f"controllers/dz-{stem.replace('_', '-')}.js"
    files = ((hyperpart.controller,) if hyperpart.controller else ()) + tuple(hyperpart.extensions)
    if cand in files:
        return cand
    if len(hyperpart.contracts) == 1 and hyperpart.controller:
        return hyperpart.controller
    return None


def _pairs() -> list[tuple[str, str, str, object]]:
    """(hyperpart_id, contract_rel, controller_rel, contract_module)."""
    out: list[tuple[str, str, str, object]] = []
    for h in HYPERPARTS:
        if not h.contracts:
            continue
        for rel in h.contracts:
            stem = Path(rel).stem
            ctrl = _controller_for_contract(stem, h)
            if not ctrl:
                continue
            mod = _load_contract(rel)
            out.append((h.id, rel, ctrl, mod))
    return out


def test_every_contract_pairs_to_a_controller() -> None:
    """Registry contracts must resolve to a controller path (convention table)."""
    unpaired: list[str] = []
    for h in HYPERPARTS:
        for rel in h.contracts:
            stem = Path(rel).stem
            if _controller_for_contract(stem, h) is None:
                unpaired.append(f"{h.id}:{rel}")
    assert not unpaired, f"no controller pairing for contracts: {unpaired}"


def test_dom_contract_attrs_appear_in_controller_source() -> None:
    """Direction B: structured required data-* must be greppable in the controller."""
    missing: list[str] = []
    for hid, rel, ctrl, mod in _pairs():
        need = _dom_data_attrs(mod)
        if not need:
            continue
        text = (PKG / ctrl).read_text(encoding="utf-8")
        absent = sorted(a for a in need if a not in text)
        if absent:
            missing.append(f"{hid} {rel} ← {ctrl}: missing {absent}")
    assert not missing, (
        "DOM_CONTRACT data-* attrs not mentioned in paired controller "
        "(add to Contract: header or use the attr in code):\n  " + "\n  ".join(missing)
    )


def test_contract_header_documents_dom_contract_attrs() -> None:
    """When a Contract: block exists, it must name every DOM_CONTRACT data-* attr."""
    missing: list[str] = []
    for hid, rel, ctrl, mod in _pairs():
        text = (PKG / ctrl).read_text(encoding="utf-8")
        block = _contract_block(text)
        if block is None:
            continue  # no formal block — covered by source-wide Direction B
        need = _dom_data_attrs(mod)
        absent = sorted(a for a in need if a not in block)
        if absent:
            missing.append(f"{hid} {ctrl}: Contract: block missing {absent} (from {rel})")
    assert not missing, "Contract: header incomplete vs DOM_CONTRACT:\n  " + "\n  ".join(missing)


def test_contract_header_attrs_subset_of_dom_or_transient() -> None:
    """Direction A: Contract: prose data-dz-* ⊆ DOM_CONTRACT ∪ transient state.

    Skips thin-root modules listed in _THIN_ROOT_SKIP_REVERSE (prose is a
    fuller API surface than the structured root-only contract).
    """
    extras: list[str] = []
    for hid, rel, ctrl, mod in _pairs():
        stem = Path(rel).stem
        if stem in _THIN_ROOT_SKIP_REVERSE:
            continue
        text = (PKG / ctrl).read_text(encoding="utf-8")
        block = _contract_block(text)
        if block is None:
            continue
        prose = set(_ATTR_RE.findall(block))
        allowed = _dom_data_attrs(mod) | TRANSIENT_STATE_ATTRS
        # Multi-contract hyperparts: union sibling contracts on the same part
        # so an extension Contract: can mention the shared root marker.
        h = next(x for x in HYPERPARTS if x.id == hid)
        for sib in h.contracts:
            allowed |= _dom_data_attrs(_load_contract(sib))
        unknown = sorted(prose - allowed)
        if unknown:
            extras.append(f"{hid} {ctrl}: prose-only attrs {unknown}")
    assert not extras, (
        "Contract: header names attrs not in DOM_CONTRACT (expand the contract "
        "or add to TRANSIENT_STATE_ATTRS if truly runtime-only):\n  " + "\n  ".join(extras)
    )
