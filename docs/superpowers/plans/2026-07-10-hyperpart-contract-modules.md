# Hyperpart Contract Modules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pilot the triple-derived Hyperpart contract module (typed ingestion model + structured DOM contract + executable FastAPI exemplar) for grid/grid-edit, with HM CI validation, gallery/docs derivation, and Dazzle-side typed-boundary + cross-boundary lock gates.

**Architecture:** One contract module per data-bearing Hyperpart in `packages/hatchi-maxchi/contracts/`; HM CI executes exemplars against the DOM contract; Dazzle keeps runtime model copies locked by a test-time schema-parity gate and validates its emitted DOM against the HM contract. Spec: `docs/superpowers/specs/2026-07-10-hyperpart-contract-modules-design.md`.

**Tech Stack:** Pydantic v2, FastAPI (HM dev-dep only), html.parser, pytest.

## Global Constraints

- HM edits: run `python build.py` from `packages/hatchi-maxchi/` after site/CSS changes and `python -m pytest tests/ -q` (gallery content changes may require `HM_UPDATE_BASELINES=1` visual-baseline regen — only if `test_visual.py` fails). The **dist must not change** (contracts are dev-only; verify with `git diff dist/`).
- NEVER subtree-push to the standalone HM repo — `sync-hatchi-maxchi.yml` mirrors automatically, including `.github/workflows/ci.yml` (verified: CI config is in the synced tree).
- Dazzle gates carry `pytestmark = pytest.mark.gate`, DB-free.
- Two ships: Ship A after Task 6 (HM side), Ship B after Task 10 (Dazzle side). Each: `/bump patch` + CHANGELOG (+ HM `package.json` version bump in Ship A), commit in its own command, verify HEAD moved, THEN tag+push.
- The registry `exchanges` mechanism is untouched (complementary, per spec Out of scope).
- `src/dazzle/services/agent_commands/` untouched.

## File map

| File | Role |
|---|---|
| `packages/hatchi-maxchi/contracts/__init__.py` | package marker (empty) |
| `packages/hatchi-maxchi/contracts/_kit.py` | DomContract/Node/validators + validate_dom |
| `packages/hatchi-maxchi/contracts/grid.py` | base grid root contract (thin) |
| `packages/hatchi-maxchi/contracts/grid_edit.py` | pilot: model + DOM contract + exemplars + FastAPI app |
| `packages/hatchi-maxchi/contracts/AUTHORING.md` | new-Hyperpart authoring checklist |
| `packages/hatchi-maxchi/tests/test_contracts.py` | HM CI: exemplars → render → validate_dom |
| `packages/hatchi-maxchi/site/registry.py` | `contracts:` field on Hyperpart + grid entry |
| `packages/hatchi-maxchi/tests/test_hyperpart_cohesion.py` | contract-pointer + PENDING ratchet gates |
| `packages/hatchi-maxchi/site/build_site.py` | gallery contract section + llms.txt entries |
| `packages/hatchi-maxchi/.github/workflows/ci.yml` | contracts test job |
| `packages/hatchi-maxchi/AGENTS.md` | AUTHORING.md link |
| `src/dazzle/render/fragment/ingest.py` | Dazzle runtime GridEditCell + edit_span_attrs |
| `src/dazzle/render/fragment/renderer/_data_row.py:440-483` | emit via typed path; delete 3-branch comprehension |
| `tests/unit/test_hm_contract_schema_parity.py` | cross-boundary lock 1 |
| `tests/unit/test_hm_contract_dom_conformance.py` | cross-boundary lock 2 + typed-path emission gate |

---

## Phase A — HM side

### Task 1: Contracts kit

**Files:**
- Create: `packages/hatchi-maxchi/contracts/__init__.py` (empty), `packages/hatchi-maxchi/contracts/_kit.py`
- Test: `packages/hatchi-maxchi/tests/test_contracts.py` (kit tests only in this task)

**Interfaces:**
- Produces: `DomContract(part, root, nodes)`, `Node(selector, attrs)`, validators `OneOf(*values)`, `Present()`, `JsonPairs(required_when: dict[str,str]|None)`, and `validate_dom(html: str, contract: DomContract, require_root: bool = True) -> list[str]` (violation strings; empty = conforming). Selector syntax supported: `[attr]`, `[attr="v"]` conjunctions like `[data-dz-grid][data-dz-grid-edit-url]` — attribute-presence/equality only, no CSS engine.

- [ ] **Step 1: Write the failing kit tests** (append to a new `tests/test_contracts.py`):

```python
"""Contract-module gates: every exemplar renders DOM conforming to its
own DOM_CONTRACT (spec 2026-07-10-hyperpart-contract-modules-design)."""

import sys
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PKG))

from contracts._kit import DomContract, JsonPairs, Node, OneOf, Present, validate_dom  # noqa: E402

_CONTRACT = DomContract(
    part="t",
    root="[data-x]",
    nodes=(
        Node(
            "[data-cell]",
            attrs={
                "data-kind": OneOf("a", "b"),
                "data-val": Present(),
                "data-opts": JsonPairs(required_when={"data-kind": "b"}),
            },
        ),
    ),
)


def test_validate_dom_accepts_conforming_fragment() -> None:
    html = (
        '<div data-x="1"><span data-cell data-kind="b" data-val="v" '
        "data-opts='[[\"x\",\"X\"]]'>v</span></div>"
    )
    assert validate_dom(html, _CONTRACT) == []


def test_validate_dom_flags_bad_enum_missing_attr_and_bad_json() -> None:
    html = (
        '<div data-x="1">'
        '<span data-cell data-kind="z" data-val="v">v</span>'          # bad enum
        '<span data-cell data-kind="a">v</span>'                        # missing data-val
        '<span data-cell data-kind="b" data-val="v" data-opts="nope">v</span>'  # bad JSON pairs
        "</div>"
    )
    violations = validate_dom(html, _CONTRACT)
    assert len(violations) == 3
    assert any("data-kind" in v for v in violations)
    assert any("data-val" in v for v in violations)
    assert any("data-opts" in v for v in violations)


def test_validate_dom_missing_root_and_fragment_mode() -> None:
    html = '<span data-cell data-kind="a" data-val="v">v</span>'
    assert any("root" in v for v in validate_dom(html, _CONTRACT))
    assert validate_dom(html, _CONTRACT, require_root=False) == []
```

- [ ] **Step 2: Run to verify failure**

Run: `cd packages/hatchi-maxchi && python -m pytest tests/test_contracts.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'contracts'`.

- [ ] **Step 3: Implement the kit** (`contracts/_kit.py`):

```python
"""Contract kit — structured DOM contracts for Hyperparts.

A DomContract is the machine-readable half of a controller's prose
`Contract:` header: root selector + per-node required attributes with
value validators. validate_dom() is used by HM CI (exemplar output) and,
test-time, by Dazzle's conformance gate. Selector support is deliberately
tiny: conjunctions of [attr] / [attr="value"] — enough for data-dz-*
contracts, no CSS engine.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser


class Present:
    def check(self, value: str) -> str | None:
        return None  # presence is checked by the caller


@dataclass(frozen=True)
class OneOf:
    values: tuple[str, ...]

    def __init__(self, *values: str) -> None:
        object.__setattr__(self, "values", values)

    def check(self, value: str) -> str | None:
        return None if value in self.values else f"expected one of {self.values}, got {value!r}"


@dataclass(frozen=True)
class JsonPairs:
    """Attribute must be JSON of shape [[str, str], ...]. If required_when
    is set, the attribute is required only on nodes whose OTHER attributes
    match; on non-matching nodes it must be absent."""

    required_when: dict[str, str] | None = None

    def check(self, value: str) -> str | None:
        try:
            data = json.loads(value)
        except ValueError:
            return f"not valid JSON: {value!r}"
        if not isinstance(data, list) or not all(
            isinstance(p, list) and len(p) == 2 and all(isinstance(s, str) for s in p)
            for p in data
        ):
            return f"not a list of [value, label] string pairs: {value!r}"
        return None


@dataclass(frozen=True)
class Node:
    selector: str
    attrs: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class DomContract:
    part: str
    root: str
    nodes: tuple[Node, ...] = ()


_SEL = re.compile(r"\[([a-zA-Z0-9_-]+)(?:=\"([^\"]*)\")?\]")


def _sel_conditions(selector: str) -> list[tuple[str, str | None]]:
    return [(m.group(1), m.group(2)) for m in _SEL.finditer(selector)]


class _Collector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.elements: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.elements.append({k: (v if v is not None else "") for k, v in attrs})


def _matches(el: dict[str, str], selector: str) -> bool:
    return all(
        (name in el) and (want is None or el[name] == want)
        for name, want in _sel_conditions(selector)
    )


def validate_dom(html: str, contract: DomContract, require_root: bool = True) -> list[str]:
    parser = _Collector()
    parser.feed(html)
    els = parser.elements
    out: list[str] = []
    if require_root and not any(_matches(e, contract.root) for e in els):
        out.append(f"{contract.part}: no element matches root {contract.root!r}")
    for node in contract.nodes:
        matched = [e for e in els if _matches(e, node.selector)]
        for el in matched:
            for attr, validator in node.attrs.items():
                required = True
                if isinstance(validator, JsonPairs) and validator.required_when:
                    required = all(el.get(k) == v for k, v in validator.required_when.items())
                    if not required and attr in el:
                        out.append(
                            f"{contract.part}: {node.selector} has {attr} but "
                            f"required_when {validator.required_when} does not match"
                        )
                if attr not in el:
                    if required:
                        out.append(f"{contract.part}: {node.selector} missing {attr}")
                    continue
                err = validator.check(el[attr]) if hasattr(validator, "check") else None
                if err:
                    out.append(f"{contract.part}: {node.selector}[{attr}] {err}")
    return out
```

- [ ] **Step 4: Run to verify pass**

Run: `cd packages/hatchi-maxchi && python -m pytest tests/test_contracts.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add packages/hatchi-maxchi/contracts packages/hatchi-maxchi/tests/test_contracts.py
git commit -m "feat(hm): contract kit — structured DOM contracts + validate_dom"
```

### Task 2: grid_edit + grid contract modules with exemplars

**Files:**
- Create: `packages/hatchi-maxchi/contracts/grid_edit.py`, `packages/hatchi-maxchi/contracts/grid.py`
- Modify: `packages/hatchi-maxchi/tests/test_contracts.py` (add the exemplar sweep)

**Interfaces:**
- Consumes: Task 1 kit.
- Produces: `GridEditCell` (pydantic BaseModel: `col: str`, `kind: Literal["text","date","bool","select"]`, `value: str`, `label: str`, `options: list[tuple[str,str]] | None = None`), `DOM_CONTRACT: DomContract`, `EXEMPLARS: list[GridEditCell]`, `render(cell) -> str`, `app: FastAPI`. `grid.py` exports `DOM_CONTRACT` only. Dazzle Tasks 7–10 rely on these exact names.

- [ ] **Step 1: Add the failing exemplar sweep** (append to `tests/test_contracts.py`):

```python
import importlib
import pkgutil

import contracts  # noqa: E402


def _contract_modules():
    for m in pkgutil.iter_modules(contracts.__path__):
        if not m.name.startswith("_"):
            yield importlib.import_module(f"contracts.{m.name}")


def test_every_contract_module_has_the_required_surface() -> None:
    mods = list(_contract_modules())
    assert mods, "no contract modules found"
    for mod in mods:
        assert hasattr(mod, "DOM_CONTRACT"), f"{mod.__name__}: missing DOM_CONTRACT"


def test_exemplars_render_conforming_dom() -> None:
    """The core loop: every exemplar payload, rendered by the module's own
    render(), must satisfy the module's own DOM_CONTRACT."""
    checked = 0
    for mod in _contract_modules():
        exemplars = getattr(mod, "EXEMPLARS", None)
        render = getattr(mod, "render", None)
        if exemplars is None or render is None:
            continue  # root-only contracts (grid.py) have no ingestion side
        for ex in exemplars:
            html = render(ex)
            violations = validate_dom(html, mod.DOM_CONTRACT, require_root=False)
            assert not violations, f"{mod.__name__}: {violations}"
            checked += 1
    assert checked >= 3, "exemplar sweep is not exercising the #1573 shapes"


def test_grid_edit_normalises_the_1573_producer_shapes() -> None:
    from contracts.grid_edit import GridEditCell

    for raw in (
        [{"value": "open", "label": "Open"}, {"value": "closed", "label": "Closed"}],
        [("open", "Open"), ("closed", "Closed")],
        ["open", "closed"],  # the #1573 bare-string shape
    ):
        cell = GridEditCell(col="status", kind="select", value="open", label="Status", options=raw)
        assert cell.options is not None and all(
            isinstance(p, tuple) and len(p) == 2 for p in cell.options
        )
    import pytest as _pytest

    with _pytest.raises(ValueError):
        GridEditCell(col="status", kind="select", value="x", label="S")  # select without options
    with _pytest.raises(ValueError):
        GridEditCell(col="t", kind="text", value="x", label="T", options=[("a", "A")])
```

- [ ] **Step 2: Run to verify failure**

Run: `cd packages/hatchi-maxchi && python -m pytest tests/test_contracts.py -q`
Expected: FAIL — `ModuleNotFoundError: contracts.grid_edit` (via the sweep) / import error.

- [ ] **Step 3: Implement `contracts/grid_edit.py`** (contract facts from `controllers/dz-grid-edit.js` header + registry lines 225-227):

```python
"""HYPERPART: grid (extension: dz-grid-edit) — contract module.

Single source of truth for the inline-edit seam: the typed ingestion
model (what the server-side producer must supply), the DOM contract (what
controllers/dz-grid-edit.js requires — mirrors its prose header), and an
executable FastAPI exemplar mirroring how Dazzle feeds it. The exemplar
payloads deliberately include the #1573 producer shapes (dict / tuple /
bare-string options) as permanent regression documentation.
"""

from __future__ import annotations

import html
import json
from typing import Literal

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, field_validator, model_validator

from contracts._kit import DomContract, JsonPairs, Node, OneOf, Present

Kind = Literal["text", "date", "bool", "select"]


class GridEditCell(BaseModel):
    """One editable cell's seam data — the single canonical ingestion shape."""

    col: str
    kind: Kind
    value: str
    label: str  # a11y label for the editor
    options: list[tuple[str, str]] | None = None  # [(value, label), …] — select only

    @field_validator("options", mode="before")
    @classmethod
    def _normalise_options(cls, v: object) -> object:
        # THE one normalisation boundary (#1573): producers may hold dicts
        # ({"value","label"}), pairs, or bare strings; all become pairs here.
        if v is None:
            return v
        out: list[tuple[str, str]] = []
        for o in v:  # type: ignore[union-attr]
            if isinstance(o, dict):
                out.append((str(o.get("value", "")), str(o.get("label", ""))))
            elif isinstance(o, (tuple, list)) and len(o) >= 2:
                out.append((str(o[0]), str(o[1])))
            else:
                out.append((str(o), str(o)))
        return out

    @model_validator(mode="after")
    def _select_requires_options(self) -> "GridEditCell":
        if self.kind == "select" and not self.options:
            raise ValueError("kind='select' requires options")
        if self.kind != "select" and self.options:
            raise ValueError(f"kind={self.kind!r} must not carry options")
        return self


DOM_CONTRACT = DomContract(
    part="grid-edit",
    root='[data-dz-grid][data-dz-grid-edit-url]',
    nodes=(
        Node(
            "[data-dz-grid-edit]",
            attrs={
                "data-dz-edit-kind": OneOf("text", "date", "bool", "select"),
                "data-dz-edit-value": Present(),
                "data-dz-edit-label": Present(),
                "data-dz-edit-options": JsonPairs(
                    required_when={"data-dz-edit-kind": "select"}
                ),
            },
        ),
    ),
)

EXEMPLARS: list[GridEditCell] = [
    GridEditCell(col="title", kind="text", value="Fix the door", label="Title"),
    GridEditCell(col="due", kind="date", value="2026-07-10", label="Due date"),
    GridEditCell(col="done", kind="bool", value="false", label="Done"),
    # The #1573 producer shapes — permanent, executable regression docs:
    GridEditCell(col="status", kind="select", value="open", label="Status",
                 options=[{"value": "open", "label": "Open"}]),          # dict producer
    GridEditCell(col="severity", kind="select", value="p1", label="Severity",
                 options=[("p1", "P1"), ("p2", "P2")]),                   # tuple producer
    GridEditCell(col="lane", kind="select", value="triage", label="Lane",
                 options=["triage", "active", "done"]),                   # bare-string producer
]


def render(cell: GridEditCell) -> str:
    """Model → conforming display-span fragment (the seam the controller reads)."""
    opts = ""
    if cell.kind == "select" and cell.options is not None:
        pairs = json.dumps([[v, label] for v, label in cell.options])
        opts = f" data-dz-edit-options=\"{html.escape(pairs, quote=True)}\""
    return (
        f'<span class="dz-tr-cell-display" '
        f'data-dz-grid-edit="{html.escape(cell.col, quote=True)}" '
        f'data-dz-edit-kind="{cell.kind}" '
        f'data-dz-edit-value="{html.escape(cell.value, quote=True)}" '
        f'data-dz-edit-label="{html.escape(cell.label, quote=True)}"{opts}>'
        f"{html.escape(cell.value)}</span>"
    )


app = FastAPI(title="grid-edit exemplar — how a server feeds the inline-edit seam")


@app.get("/rows", response_class=HTMLResponse)
def rows() -> str:
    """A tbody fragment: what a real endpoint returns to fill the grid.
    Mirrors Dazzle's shape: the grid ROOT (with data-dz-grid-edit-url)
    is page furniture; this endpoint returns rows whose editable cells
    carry the seam spans."""
    cells = "".join(f"<td>{render(c)}</td>" for c in EXEMPLARS[:3])
    return f'<tr id="row-1">{cells}</tr>'
```

And `contracts/grid.py`:

```python
"""HYPERPART: grid — root contract (thin). The base grid's structural
root attributes; the data-bearing seams live in extension contracts
(grid_edit). Root-only: no ingestion model, no exemplars."""

from __future__ import annotations

from contracts._kit import DomContract, Present

DOM_CONTRACT = DomContract(
    part="grid",
    root="[data-dz-grid]",
    nodes=(),
)

__all__ = ["DOM_CONTRACT", "Present"]
```

- [ ] **Step 4: Run to verify pass**

Run: `cd packages/hatchi-maxchi && python -m pytest tests/test_contracts.py -q` (needs `pip install fastapi` in the venv if absent — Dazzle's venv already has both).
Expected: PASS (6 tests). Also sanity-run the exemplar app: `cd packages/hatchi-maxchi && python -c "from contracts.grid_edit import app, rows; print(rows()[:80])"` — expected: a `<tr id="row-1">…` fragment.

- [ ] **Step 5: Commit**

```bash
git add packages/hatchi-maxchi/contracts packages/hatchi-maxchi/tests/test_contracts.py
git commit -m "feat(hm): grid/grid-edit contract modules — #1573 shapes as permanent exemplars"
```

### Task 3: Registry pointers + cohesion ratchet

**Files:**
- Modify: `packages/hatchi-maxchi/site/registry.py` (Hyperpart dataclass ~line 63; grid entry ~line 527)
- Modify: `packages/hatchi-maxchi/tests/test_hyperpart_cohesion.py`

**Interfaces:**
- Produces: `Hyperpart.contracts: tuple[str, ...]` (paths like `"contracts/grid_edit.py"`), `PENDING_CONTRACTS` frozenset in the cohesion test. Task 4 (gallery) reads `h.contracts`.

- [ ] **Step 1: Write the failing gates** (append to `test_hyperpart_cohesion.py`):

```python
# Controller/extension files whose Hyperpart does not yet declare a contract
# module. SHRINK-ONLY: remove entries as contracts land; never add to it.
PENDING_CONTRACTS = frozenset({
    "controllers/dz-app-shell.js",
    "controllers/dz-color.js",
    "controllers/dz-combobox.js",
    "controllers/dz-command.js",
    "controllers/dz-confirm-gate.js",
    "controllers/dz-confirm.js",
    "controllers/dz-dialog.js",
    "controllers/dz-grid-cols.js",
    "controllers/dz-grid-resize.js",
    "controllers/dz-master-detail.js",
    "controllers/dz-money.js",
    "controllers/dz-pdf.js",
    "controllers/dz-search-select.js",
    "controllers/dz-slider.js",
    "controllers/dz-tabs.js",
    "controllers/dz-tags.js",
    "controllers/dz-wizard.js",
})


def test_declared_contracts_exist() -> None:
    for h in HYPERPARTS:
        for ref in h.contracts:
            assert (PKG / ref).is_file(), f"{h.id}: declared contract {ref} does not exist"


def test_controller_bearing_hyperparts_have_contracts_or_pending() -> None:
    """The rollout ratchet: every controller/extension file is either covered
    by its Hyperpart's contract modules or explicitly PENDING. New controllers
    without contracts fail here (spec: allowlist only shrinks)."""
    for h in HYPERPARTS:
        files = ((h.controller,) if h.controller else ()) + tuple(h.extensions)
        for ref in files:
            if ref in PENDING_CONTRACTS:
                continue
            assert h.contracts, (
                f"{h.id}: controller {ref} has no contract module and is not in "
                f"PENDING_CONTRACTS — write contracts/<part>.py (see contracts/AUTHORING.md)"
            )


def test_pending_contracts_entries_are_real_and_uncovered() -> None:
    """Stale-allowlist guard: every PENDING entry must name a controller file
    that is actually declared by some Hyperpart (existence check — coverage
    semantics stay with the previous gate)."""
    all_files = {(h, ref) for h in HYPERPARTS
                 for ref in ((h.controller,) if h.controller else ()) + tuple(h.extensions)}
    known = {ref for _, ref in all_files}
    ghosts = sorted(PENDING_CONTRACTS - known)
    assert not ghosts, f"PENDING_CONTRACTS names unknown controllers: {ghosts}"
```

- [ ] **Step 2: Run to verify failure**

Run: `cd packages/hatchi-maxchi && python -m pytest tests/test_hyperpart_cohesion.py -q`
Expected: FAIL — `AttributeError: 'Hyperpart' object has no attribute 'contracts'`.

- [ ] **Step 3: Add the field and the grid pointers.** In `site/registry.py`, add to the `Hyperpart` dataclass (after `mock`):

```python
    # Contract modules (contracts/<part>.py): typed ingestion model + DOM
    # contract + executable exemplar. One Hyperpart may carry several (the
    # base part + each data-bearing extension). Cohesion-gated: every
    # controller-bearing entry needs contracts or a PENDING_CONTRACTS entry.
    contracts: tuple[str, ...] = field(default_factory=tuple)
```

In the grid entry (after `mock="/mock/grid",`):

```python
        contracts=("contracts/grid.py", "contracts/grid_edit.py"),
```

- [ ] **Step 4: Run to verify pass**

Run: `cd packages/hatchi-maxchi && python -m pytest tests/test_hyperpart_cohesion.py tests/test_contracts.py -q`
Expected: PASS. Note: `dz-grid.js` is NOT in PENDING (covered by the grid entry's contracts); the 17 listed files are.

- [ ] **Step 5: Commit**

```bash
git add packages/hatchi-maxchi/site/registry.py packages/hatchi-maxchi/tests/test_hyperpart_cohesion.py
git commit -m "feat(hm): registry contract pointers + shrink-only PENDING_CONTRACTS ratchet"
```

### Task 4: Gallery contract section + llms.txt

**Files:**
- Modify: `packages/hatchi-maxchi/site/build_site.py` (new `_contracts_html(hyperpart)` next to `_exchanges_html` ~line 48; call it where `_exchanges_html` is composed into the part page; llms.txt block ~line 1089)

- [ ] **Step 1: Implement `_contracts_html`** (pattern-match `_exchanges_html`'s structure — read it first and mirror its disclosure markup):

```python
def _contracts_html(hyperpart) -> str:  # type: ignore[no-untyped-def]
    """Contract-module section: ingestion model schema table + exemplar
    source (inspect.getsource — the page IS the snippet) + live output."""
    if not hyperpart.contracts:
        return ""
    import importlib
    import inspect

    blocks: list[str] = []
    for ref in hyperpart.contracts:
        mod = importlib.import_module(ref.removesuffix(".py").replace("/", "."))
        title = ref.rsplit("/", 1)[-1]
        rows = ""
        model = next(
            (v for v in vars(mod).values()
             if isinstance(v, type) and hasattr(v, "model_json_schema")
             and v.__module__ == mod.__name__),
            None,
        )
        if model is not None:
            schema = model.model_json_schema()
            req = set(schema.get("required", ()))
            for name, prop in schema.get("properties", {}).items():
                typ = prop.get("type") or " | ".join(
                    a.get("type", "?") for a in prop.get("anyOf", ())
                ) or "object"
                if "enum" in prop.get("items", {}) or "enum" in prop:
                    typ += f" ∈ {prop.get('enum', prop.get('items', {}).get('enum'))}"
                rows += (
                    f"<tr><td><code>{name}</code></td><td><code>{typ}</code></td>"
                    f"<td>{'required' if name in req else 'optional'}</td></tr>"
                )
        exemplar_html = ""
        render_fn = getattr(mod, "render", None)
        exemplars = getattr(mod, "EXEMPLARS", ())
        if render_fn and exemplars:
            src = _escape(inspect.getsource(render_fn))
            live = render_fn(exemplars[0])
            exemplar_html = (
                f"<details class='hm-disclosure'><summary>Exemplar (executable — "
                f"runs in CI)</summary><pre><code>{src}</code></pre>"
                f"<div class='hm-contract-live'>{live}</div></details>"
            )
        blocks.append(
            f"<h4>{title}</h4>"
            + (f"<table class='hm-contract-schema'>{rows}</table>" if rows else "")
            + exemplar_html
        )
    return (
        "<details class='hm-disclosure'><summary>Contract module</summary>"
        + "".join(blocks)
        + "</details>"
    )
```

(`_escape` = whatever HTML-escaping helper `build_site.py` already uses — check imports at the top of the file and reuse it; if none, use `html.escape`.)

- [ ] **Step 2: Wire it** into the per-part page assembly immediately after the `_exchanges_html(...)` call site (grep `_exchanges_html(` inside `build()`), and add one line per contract-bearing part to the llms.txt block (~1089): locate the section listing per-part URLs and append `contracts/<ref>` lines for `h.contracts`.

- [ ] **Step 3: Rebuild + full HM suite**

Run: `cd packages/hatchi-maxchi && python build.py && python -m pytest tests/ -q`
Expected: PASS. If `test_visual.py` fails on gallery pages (the new disclosure changed layout): regenerate with `HM_UPDATE_BASELINES=1 python -m pytest tests/test_visual.py -q`, eyeball the diff, re-run. Verify `git diff dist/` is EMPTY (contracts are dev-only).

- [ ] **Step 4: Commit**

```bash
git add packages/hatchi-maxchi/site packages/hatchi-maxchi/tests
git commit -m "feat(hm): gallery contract sections + llms.txt entries"
```

### Task 5: AUTHORING.md + AGENTS.md link + CI job

**Files:**
- Create: `packages/hatchi-maxchi/contracts/AUTHORING.md`
- Modify: `packages/hatchi-maxchi/AGENTS.md` (contributing section), `packages/hatchi-maxchi/.github/workflows/ci.yml`

- [ ] **Step 1: Write `contracts/AUTHORING.md`** (exact content):

```markdown
# Authoring a new Hyperpart — the ordered path

## 0. Should this be a new Hyperpart at all?

- **Compose first**: if existing parts + Layout primitives express it, write a
  Blueprint, not a part.
- **Build-to-replace**: an HM part must REPLACE a Dazzle-native equivalent (or fill a
  hole no Dazzle layer covers). A part that ships alongside an unconverted Dazzle
  equivalent is decoration — it will be shadowed by unlayered Dazzle CSS.
- **Controller only where the platform lacks a primitive** (registry.py doctrine).

## 1. Contract module FIRST — `contracts/<part>.py`

Write, in one module: the **ingestion model** (Pydantic — the single canonical data
shape; put producer-shape normalisation in a field_validator so there is exactly one
normalisation boundary), the **DOM_CONTRACT** (root selector + per-node required
`data-*` attributes with validators from `contracts/_kit.py`), **EXEMPLARS** (including
every producer shape you expect — they are permanent, executable regression docs), a
**render()** turning the model into conforming markup, and a minimal **FastAPI app**
showing how a server feeds it. `tests/test_contracts.py` sweeps all of this in CI: an
exemplar that violates its own contract cannot ship. Green here = your interface is real.

## 2. Controller against the DOM contract

Idiom rules (the gates can't fully see these — follow them):

- **Document-level delegation**, Pointer-Events, vanilla JS. One controller file,
  `HYPERPART: <id>` marker (cohesion-gated).
- **State lives in the DOM** (attributes, `.checked`, `aria-*`) — never in JS objects
  that a morph would orphan.
- **Morph-path survival**: transient interaction state that must outlive a tbody swap
  goes on a stable root property with before/after-swap hooks. Canonical example:
  `controllers/dz-grid-edit.js` — the typed edit buffer lives at `root._dzEdit`, the
  before-swap hook captures the live input value, the after-swap hook re-opens the
  editor on the morph-keyed row.
- **No hover-only affordances**; touch accommodations get tested (README › Touch input).
- Keep the prose `Contract:` header in the controller and point it at the contract
  module — the module is the source of truth; the prose explains.

## 3. Registry entry

Add the Hyperpart to `site/registry.py` with `partial`, `exchanges` (every hx-*
affordance needs one — gated), `controller`/`extensions`, `mock`, and
`contracts=("contracts/<part>.py",)`. A controller-bearing entry without contracts
fails `test_hyperpart_cohesion.py` unless it is in `PENDING_CONTRACTS` — and that
list only shrinks; new parts never enter it.

## 4. Dazzle emitter against the typed model

In the Dazzle monorepo: add the runtime model copy (`dazzle/render/fragment/ingest.py`),
emit the part's `data-*` attributes FROM the model, and watch two gates go green:
`test_hm_contract_schema_parity` (your model matches this module's, field for field)
and `test_hm_contract_dom_conformance` (the real pipeline's DOM satisfies
DOM_CONTRACT). Red gates here are the loop working, not noise.
```

- [ ] **Step 2: Link from AGENTS.md** — in the "Changing the system (contributing)" section, add as the first bullet:

```markdown
- **Authoring a new Hyperpart?** Follow `contracts/AUTHORING.md` — the ordered
  contract-first path (decision test → contract module → controller → registry →
  Dazzle emitter). Contract modules in `contracts/` are the typed source of truth
  for each part's ingestion shape and DOM contract.
```

- [ ] **Step 3: CI job** — in `.github/workflows/ci.yml`, alongside the existing contract job (the one running `test_contract.py tests/test_boundary.py`, ~line 31-35), extend its pytest line and install:

```yaml
      - run: pip install pytest fastapi pydantic
      - run: python -m pytest tests/test_contract.py tests/test_boundary.py tests/test_contracts.py tests/test_hyperpart_cohesion.py -q
```

(Check first whether `test_hyperpart_cohesion.py` is already in another job's list — if so, only add `tests/test_contracts.py`. Keep the change minimal.)

- [ ] **Step 4: Run the HM suite once more**

Run: `cd packages/hatchi-maxchi && python -m pytest tests/ -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/hatchi-maxchi/contracts/AUTHORING.md packages/hatchi-maxchi/AGENTS.md packages/hatchi-maxchi/.github/workflows/ci.yml
git commit -m "docs(hm): contract-first authoring path + contracts CI job"
```

### Task 6: Ship A (HM side)

- [ ] **Step 1:** Bump HM `package.json` version (patch, e.g. 0.1.64 → 0.1.65) and run `python build.py` (version stamps in dist banner if applicable — follow build output). Verify `git status` shows only intended files.
- [ ] **Step 2:** Dazzle `/bump patch`; CHANGELOG Added entry: "Hyperpart contract modules (pilot: grid/grid-edit) — typed ingestion model + structured DOM contract + executable FastAPI exemplars in `packages/hatchi-maxchi/contracts/`, validated in HM CI; registry contract pointers with a shrink-only PENDING_CONTRACTS ratchet; contract-first authoring path in `contracts/AUTHORING.md`. The #1573 producer shapes ship as permanent exemplars. Spec: docs/superpowers/specs/2026-07-10-hyperpart-contract-modules-design.md." + `### Agent Guidance`: "New Hyperparts start with a contract module — see `packages/hatchi-maxchi/contracts/AUTHORING.md`."
- [ ] **Step 3:** `/ship` (gate suite, mkdocs, commit alone → verify HEAD → tag → push tag → signal). After the mirror sync fires, verify the standalone repo's CI run includes the contracts job.

---

## Phase B — Dazzle side

### Task 7: Runtime model + typed emission (`ingest.py`)

**Files:**
- Create: `src/dazzle/render/fragment/ingest.py`
- Test: `tests/unit/test_grid_edit_ingest.py`

**Interfaces:**
- Produces: `GridEditCell` (field-for-field identical to the HM contract model) and `edit_span_attrs(cell: GridEditCell) -> str` returning the attribute string `data-dz-grid-edit="…" data-dz-edit-kind="…" data-dz-edit-value="…" data-dz-edit-label="…"[ data-dz-edit-options="…"]`. Task 8 consumes both.

- [ ] **Step 1: Write the failing test**:

```python
"""#1573 class closure: the ONE ingestion boundary for grid-edit seams."""

import pytest

from dazzle.render.fragment.ingest import GridEditCell, edit_span_attrs

pytestmark = pytest.mark.gate


@pytest.mark.parametrize(
    "raw",
    [
        [{"value": "open", "label": "Open"}],
        [("open", "Open")],
        ["open"],  # the #1573 bare-string producer
    ],
)
def test_producer_shapes_normalise_to_pairs(raw) -> None:
    cell = GridEditCell(col="status", kind="select", value="open", label="Status", options=raw)
    assert cell.options == [("open", "Open")] or cell.options == [("open", "open")]


def test_select_requires_options_and_others_forbid_them() -> None:
    with pytest.raises(ValueError):
        GridEditCell(col="s", kind="select", value="x", label="S")
    with pytest.raises(ValueError):
        GridEditCell(col="t", kind="text", value="x", label="T", options=[("a", "A")])


def test_edit_span_attrs_emits_the_contract_attributes() -> None:
    cell = GridEditCell(col="status", kind="select", value="o<p", label='S"x',
                        options=["open"])
    attrs = edit_span_attrs(cell)
    assert 'data-dz-grid-edit="status"' in attrs
    assert 'data-dz-edit-kind="select"' in attrs
    assert "o&lt;p" in attrs and "&quot;" in attrs  # escaping holds
    assert "data-dz-edit-options=" in attrs


def test_non_select_omits_options_attr() -> None:
    attrs = edit_span_attrs(GridEditCell(col="t", kind="text", value="v", label="T"))
    assert "data-dz-edit-options" not in attrs
```

- [ ] **Step 2:** Run: `pytest tests/unit/test_grid_edit_ingest.py -q` — expected FAIL (module not found).

- [ ] **Step 3: Implement `src/dazzle/render/fragment/ingest.py`** — the model body is IDENTICAL to the HM module's `GridEditCell` (copy the class from `packages/hatchi-maxchi/contracts/grid_edit.py` including validators and docstrings; the schema-parity gate in Task 9 enforces the match), plus:

```python
import html as _html
import json


def edit_span_attrs(cell: GridEditCell) -> str:
    """The ONLY place in src/dazzle that assembles data-dz-edit-* attributes
    (gated by test_hm_contract_dom_conformance.py::test_typed_path_is_sole_emitter)."""
    opts = ""
    if cell.kind == "select" and cell.options is not None:
        pairs = json.dumps([[v, label] for v, label in cell.options])
        opts = f' data-dz-edit-options="{_html.escape(pairs, quote=True)}"'
    return (
        f'data-dz-grid-edit="{_html.escape(cell.col, quote=True)}" '
        f'data-dz-edit-kind="{cell.kind}" '
        f'data-dz-edit-value="{_html.escape(cell.value, quote=True)}" '
        f'data-dz-edit-label="{_html.escape(cell.label, quote=True)}"{opts}'
    )
```

- [ ] **Step 4:** Run: `pytest tests/unit/test_grid_edit_ingest.py -q` — expected PASS.
- [ ] **Step 5:** Commit: `git add src/dazzle/render/fragment/ingest.py tests/unit/test_grid_edit_ingest.py && git commit -m "feat: GridEditCell typed ingestion boundary (dazzle-side contract copy)"`

### Task 8: Repoint `_data_row.py` — delete the #1573 comprehension

**Files:**
- Modify: `src/dazzle/render/fragment/renderer/_data_row.py:440-483`

**Interfaces:**
- Consumes: `GridEditCell`, `edit_span_attrs` from Task 7.

- [ ] **Step 1:** Replace the inline-edit block (lines 447-483: from `kind = {...}` through the `cell_inner = (...)` for the edit span) with:

```python
            kind = {"bool": "bool", "badge": "select", "date": "date"}.get(col_type, "text")
            if col_type == "bool":
                raw = "true" if cell_value else "false"
            else:
                raw = "" if cell_value is None else str(cell_value)
            # #1573 closure: ONE ingestion boundary — the model's validator
            # normalises the three producer shapes; emission is derived from
            # the model (see contracts/grid_edit.py in HaTchi-MaXchi).
            cell_model = GridEditCell(
                col=col_key,
                kind=kind,  # type: ignore[arg-type]
                value=raw,
                label=str(col.get("label", col_key)),
                options=(col.get("filter_options") or None) if kind == "select" else None,
            )
            title_attr = ""
            if cell_value is not None:
                title_attr = f' title="{_html_mod.escape(str(cell_value), quote=True)}"'
            cell_inner = (
                f'<span class="dz-tr-cell-display" '
                f"{edit_span_attrs(cell_model)}{title_attr}>{display_html}</span>"
            )
```

Add the import at the top of the file with the other `dazzle.render` imports: `from dazzle.render.fragment.ingest import GridEditCell, edit_span_attrs`. Delete the now-unused `json` usage if this was its last call site (check `grep -n "json\." src/dazzle/render/fragment/renderer/_data_row.py`).

Edge case to preserve: the old code emitted `data-dz-edit-options="[]"` for a select column whose `filter_options` was empty; the model forbids optionless selects. Guard: if `kind == "select"` and there are no filter_options, fall back to `kind = "text"` BEFORE constructing the model (a select editor with zero options was never usable — record this behaviour change in the commit message).

```python
            if kind == "select" and not col.get("filter_options"):
                kind = "text"
```

- [ ] **Step 2: Regression + characterization tests**

Run: `pytest tests/unit/test_data_row_characterization_1505.py tests/unit/test_list_fragment_rows_present_gate.py tests/unit/test_grid_edit_ingest.py -q`
Expected: PASS — the `TestInlineEditOptionShapes1573` shape tests must pass unchanged (byte-compatible attribute output). If attribute ORDER differs from the old emission, fix `edit_span_attrs` ordering to match (contract attrs in the original order: grid-edit, kind, value, label, options).

- [ ] **Step 3:** Full gate sweep: `pytest tests/unit -m gate -q` — expected PASS.
- [ ] **Step 4:** Commit: `git commit -am "refactor: grid-edit emission via typed GridEditCell — #1573 3-branch comprehension deleted"`

### Task 9: Cross-boundary lock 1 — schema parity

**Files:**
- Create: `tests/unit/test_hm_contract_schema_parity.py`

- [ ] **Step 1: Write the gate** (it should pass immediately if Task 7 copied faithfully — then liveness-check it):

```python
"""Cross-boundary lock: Dazzle's runtime contract models must match the HM
contract modules field-for-field (schema-level). The wheel can't ship
packages/, so Dazzle keeps copies; THIS gate is what makes them copies
rather than forks. On failure: fix whichever side changed unilaterally —
the HM contract module is the source of truth."""

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

REPO_ROOT = Path(__file__).resolve().parents[2]
HM = REPO_ROOT / "packages" / "hatchi-maxchi"

# (hm_module_path, hm_model_name, dazzle_import_path)
PAIRS = [
    ("contracts/grid_edit.py", "GridEditCell", "dazzle.render.fragment.ingest"),
]


def _load_hm_module(rel: str):
    if str(HM) not in sys.path:
        sys.path.insert(0, str(HM))
    spec = importlib.util.spec_from_file_location(
        f"hm_{Path(rel).stem}", HM / rel, submodule_search_locations=[]
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _canonical(schema: dict) -> object:
    """Structural fields only — strips titles/descriptions/default-ordering
    noise so pydantic-version skew between envs can't fail the gate."""
    KEEP = {"type", "required", "enum", "items", "properties", "anyOf", "prefixItems",
            "additionalProperties", "minItems", "maxItems", "const", "$defs", "$ref"}

    def walk(node: object) -> object:
        if isinstance(node, dict):
            out: dict = {}
            for k, v in sorted(node.items()):
                if k not in KEEP:
                    continue
                if k == "required":
                    out[k] = sorted(v)
                elif k in ("properties", "$defs"):
                    out[k] = {name: walk(sub) for name, sub in sorted(v.items())}
                else:
                    out[k] = walk(v)
            return out
        if isinstance(node, list):
            return [walk(x) for x in node]
        return node

    return walk(schema)


@pytest.mark.parametrize(("hm_path", "model_name", "dz_module"), PAIRS)
def test_schema_parity(hm_path: str, model_name: str, dz_module: str) -> None:
    hm_model = getattr(_load_hm_module(hm_path), model_name)
    dz_model = getattr(importlib.import_module(dz_module), model_name)
    hm_schema = _canonical(hm_model.model_json_schema())
    dz_schema = _canonical(dz_model.model_json_schema())
    assert hm_schema == dz_schema, (
        f"{model_name}: Dazzle runtime model diverged from HM {hm_path}.\n"
        f"HM:     {hm_schema}\nDazzle: {dz_schema}"
    )
```

Note: loading `contracts/grid_edit.py` imports FastAPI — if the exemplar import is too heavy for the gate env, split the HM module so the model lives above the FastAPI section and the loader tolerates it (FastAPI IS in Dazzle's dev env, so plain import should work; if it ever isn't, `pytest.importorskip("fastapi")`).

- [ ] **Step 2:** Run: `pytest tests/unit/test_hm_contract_schema_parity.py -v` — expected PASS.
- [ ] **Step 3: Liveness check** — temporarily add a field `extra: str = ""` to the Dazzle `GridEditCell`, re-run, expected FAIL with a field-level diff; revert; re-run PASS.
- [ ] **Step 4:** Commit: `git add tests/unit/test_hm_contract_schema_parity.py && git commit -m "test: HM↔Dazzle contract schema-parity lock (grid-edit pilot)"`

### Task 10: Cross-boundary lock 2 — DOM conformance + sole-emitter gate

**Files:**
- Create: `tests/unit/test_hm_contract_dom_conformance.py`

- [ ] **Step 1: Write the gate** (reuses the #1574 hydrated-row approach; kit loaded from packages/ test-time — the delegation-proof precedent):

```python
"""Cross-boundary lock: the REAL Dazzle pipeline's emitted DOM must satisfy
the HM DOM contract. This is the gate that would have caught #1573 at the
contract layer: a hydrated badge row with producer-shaped filter_options is
rendered through build_data_table → render_data_table_rows and validated
against contracts/grid_edit.py's DOM_CONTRACT (fragment mode — the grid
root is page furniture, validated in HM's own exemplar tests)."""

import importlib.util
import sys
import uuid
from pathlib import Path

import pytest

from dazzle.http.runtime.handlers.list_handlers import build_data_table
from dazzle.render.fragment.renderer._data_row import render_data_table_rows

pytestmark = pytest.mark.gate

REPO_ROOT = Path(__file__).resolve().parents[2]
HM = REPO_ROOT / "packages" / "hatchi-maxchi"


def _load(rel: str):
    if str(HM) not in sys.path:
        sys.path.insert(0, str(HM))
    spec = importlib.util.spec_from_file_location(f"hm_{Path(rel).stem}", HM / rel)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


_KIT = _load("contracts/_kit.py")
_GRID_EDIT = _load("contracts/grid_edit.py")

PRODUCER_SHAPES = [
    [{"value": "open", "label": "Open"}, {"value": "closed", "label": "Closed"}],
    [("open", "Open"), ("closed", "Closed")],
    ["open", "closed"],  # the #1573 crash shape
]


@pytest.mark.parametrize("options", PRODUCER_SHAPES)
def test_hydrated_badge_row_conforms_to_grid_edit_contract(options) -> None:
    table = {
        "columns": [
            {"key": "title", "label": "Title", "type": "text"},
            {"key": "status", "label": "Status", "type": "badge", "filter_options": options},
        ],
        "entity_name": "Ticket",
        "api_endpoint": "/tickets",
        "table_id": "t-conformance",
        "detail_url_template": "/app/ticket/{id}",
        "inline_editable": ["title", "status"],
    }
    row = {"id": str(uuid.uuid4()), "title": "x", "status": "open"}
    html = render_data_table_rows(build_data_table(table, [row]))
    violations = _KIT.validate_dom(html, _GRID_EDIT.DOM_CONTRACT, require_root=False)
    assert not violations, violations
    assert "data-dz-grid-edit=" in html  # the seam actually rendered


def test_typed_path_is_sole_emitter() -> None:
    """data-dz-edit-* attribute assembly is allowed ONLY in the typed
    ingestion boundary (dazzle/render/fragment/ingest.py). A second
    emission site would reopen the #1573 normalise-at-every-consumer hole."""
    offenders = []
    for p in (REPO_ROOT / "src" / "dazzle").rglob("*.py"):
        if p.name == "ingest.py" and p.parent.name == "fragment":
            continue
        if "data-dz-edit-" in p.read_text(encoding="utf-8"):
            offenders.append(str(p.relative_to(REPO_ROOT)))
    assert not offenders, (
        f"data-dz-edit-* assembled outside the typed boundary: {offenders} — "
        f"construct a GridEditCell and use edit_span_attrs() instead."
    )
```

- [ ] **Step 2:** Run: `pytest tests/unit/test_hm_contract_dom_conformance.py -v` — expected PASS (4 tests).
- [ ] **Step 3: Liveness check** — in `ingest.py`, temporarily rename the emitted attribute `data-dz-edit-kind` to `data-dz-edit-knd`; expected: conformance test FAILS naming the missing attr; revert; PASS.
- [ ] **Step 4:** Full sweep: `pytest tests/unit -m gate -q` and `mypy src/dazzle` — expected PASS/clean.
- [ ] **Step 5:** Commit: `git add tests/unit/test_hm_contract_dom_conformance.py && git commit -m "test: DOM-conformance lock + sole-emitter gate (grid-edit pilot)"`

### Task 11: Ship B (Dazzle side)

- [ ] **Step 1:** `/bump patch`; CHANGELOG Changed: "Grid inline-edit emission goes through the typed `GridEditCell` ingestion boundary (`dazzle/render/fragment/ingest.py`) — the #1573 3-branch normalisation comprehension is deleted; producer-shape normalisation happens once, in the model validator. Two cross-boundary locks land: HM↔Dazzle schema parity and DOM conformance against `contracts/grid_edit.py`. Behaviour note: a select-kind editable column with zero filter_options now degrades to a text editor (previously emitted an unusable empty-options select)." + `### Agent Guidance`: "Never assemble `data-dz-edit-*` attributes by hand — construct `GridEditCell` and use `edit_span_attrs()` (sole-emitter gated). New Hyperpart contracts follow `packages/hatchi-maxchi/contracts/AUTHORING.md`."
- [ ] **Step 2:** `/ship`; watch CI (final HEAD run is the arbiter).
- [ ] **Step 3:** Post a wrap-up comment on #1573 noting the class closure (typed boundary + conformance gates, exemplar shapes permanent) with the `🔖 Claude-lens: dazzle` trailer. Do not reopen/close anything — #1573 is already closed; this is the paper trail.
