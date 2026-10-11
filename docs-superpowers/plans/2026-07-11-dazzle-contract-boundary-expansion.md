# Dazzle Contract-Boundary Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend Dazzle↔HM dual locks (schema parity + DOM conformance) from pilot-only `GridEditCell` to registry-driven coverage of combobox, tags, and money via ingest seam model copies.

**Architecture:** A shared `CONTRACT_MODELS` registry drives parametrized schema-parity tests. Runtime Pydantic copies of HM models live only in `dazzle.render.fragment.ingest` (name-isolated from form primitives). DOM conformance fixtures emit real Dazzle HTML via `FragmentRenderer` and call HM `validate_dom(..., require_root=False)`. No runtime import of `packages/hatchi-maxchi`.

**Tech Stack:** Pydantic v2, pytest (`pytest.mark.gate`), `FragmentRenderer`, HM `contracts._kit.validate_dom` (test-time importlib load).

**Spec:** `docs/superpowers/specs/2026-07-11-dazzle-contract-boundary-expansion-design.md`

## Global Constraints

- Dazzle gates: `pytestmark = pytest.mark.gate`, DB-free.
- Ingest seam models stay in `ingest.py` only — **do not** re-export `ComboboxField` / `TagsField` / `MoneyField` from `dazzle.render.fragment` (those names are form primitives).
- HM contracts are source of truth; if Dazzle HTML is missing a required DOM attr, **fix emission** in the same change set — do not weaken the HM contract.
- No e2e. Local verify: `pytest tests/unit/test_hm_contract_schema_parity.py tests/unit/test_hm_contract_dom_conformance.py -q`.
- Ship as sequential commits on `main` (equivalent to PR plan 1→2→3). Optional `/bump patch` + CHANGELOG after each green phase if behaviour shipped; pure test/registry can land under `test:` without bump until Phase 2 green dual locks.
- Co-Authored-By trailer: `Grok Build <noreply@x.ai>`.

## File map

| File | Action | Responsibility |
|------|--------|----------------|
| `tests/unit/hm_contract_registry.py` | Create | Shared `CONTRACT_MODELS` + `_load_hm_module` + `_canonical` helpers |
| `tests/unit/test_hm_contract_schema_parity.py` | Rewrite | Parametrize over registry; thin test body |
| `src/dazzle/render/fragment/ingest.py` | Modify | Add `ComboboxOption`, `ComboboxField`, `TagsField`, `MoneyField` seam copies |
| `tests/unit/test_hm_contract_dom_conformance.py` | Modify | Combobox / tags / money DOM fixtures via `FragmentRenderer` |
| `src/dazzle/render/fragment/renderer/_render_forms.py` | Modify (if needed) | Fix money selector-mode missing `data-dz-currency` if fixture covers it |

---

### Task 1: Shared registry + generalised schema parity

**Files:**
- Create: `tests/unit/hm_contract_registry.py`
- Modify: `tests/unit/test_hm_contract_schema_parity.py`
- Modify: `src/dazzle/render/fragment/ingest.py` (add three model copies so parity can pass)

**Interfaces:**
- Produces: `CONTRACT_MODELS: list[tuple[str, str, str, str]]` = `(hm_rel, hm_model, dazzle_module, dazzle_model)`; `_load_hm_module(rel: str)`; `_canonical(schema: dict) -> object`
- Consumes: existing HM modules under `packages/hatchi-maxchi/contracts/{grid_edit,combobox,tags,money}.py`

- [ ] **Step 1: Create registry module**

Create `tests/unit/hm_contract_registry.py`:

```python
"""Shared HM↔Dazzle contract-model registry for dual-lock gates.

Adding a model-bearing contract = one row here + an ingest seam copy +
a DOM fixture — not a new gate file.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HM = REPO_ROOT / "packages" / "hatchi-maxchi"

# (hm_rel_path, hm_model_name, dazzle_module, dazzle_model_name)
CONTRACT_MODELS: list[tuple[str, str, str, str]] = [
    ("contracts/grid_edit.py", "GridEditCell", "dazzle.render.fragment.ingest", "GridEditCell"),
    ("contracts/combobox.py", "ComboboxField", "dazzle.render.fragment.ingest", "ComboboxField"),
    ("contracts/tags.py", "TagsField", "dazzle.render.fragment.ingest", "TagsField"),
    ("contracts/money.py", "MoneyField", "dazzle.render.fragment.ingest", "MoneyField"),
]


def load_hm_module(rel: str):
    """Load an HM contract module by path relative to packages/hatchi-maxchi."""
    pytest.importorskip("fastapi")
    if str(HM) not in sys.path:
        sys.path.insert(0, str(HM))
    spec = importlib.util.spec_from_file_location(f"hm_{Path(rel).stem}", HM / rel)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def canonical_schema(schema: dict) -> object:
    """Structural fields only — strip titles/descriptions/default-ordering noise."""
    keep = {
        "type",
        "required",
        "enum",
        "items",
        "properties",
        "anyOf",
        "prefixItems",
        "additionalProperties",
        "minItems",
        "maxItems",
        "const",
        "$defs",
        "$ref",
    }

    def walk(node: object) -> object:
        if isinstance(node, dict):
            out: dict = {}
            for k, v in sorted(node.items()):
                if k not in keep:
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
```

- [ ] **Step 2: Rewrite schema-parity test to use the registry**

Replace `tests/unit/test_hm_contract_schema_parity.py` with:

```python
"""Cross-boundary lock: Dazzle's runtime contract models must match the HM
contract modules field-for-field (schema-level). The wheel can't ship
packages/, so Dazzle keeps copies; THIS gate is what makes them copies
rather than forks. On failure: fix whichever side changed unilaterally —
the HM contract module is the source of truth."""

import importlib

import pytest

from tests.unit.hm_contract_registry import (
    CONTRACT_MODELS,
    canonical_schema,
    load_hm_module,
)

pytestmark = pytest.mark.gate


@pytest.mark.parametrize(
    ("hm_path", "hm_model", "dz_module", "dz_model"),
    CONTRACT_MODELS,
)
def test_schema_parity(hm_path: str, hm_model: str, dz_module: str, dz_model: str) -> None:
    hm_cls = getattr(load_hm_module(hm_path), hm_model)
    dz_cls = getattr(importlib.import_module(dz_module), dz_model)
    hm_schema = canonical_schema(hm_cls.model_json_schema())
    dz_schema = canonical_schema(dz_cls.model_json_schema())
    assert hm_schema == dz_schema, (
        f"{hm_model}↔{dz_model}: Dazzle runtime model diverged from HM {hm_path}.\n"
        f"HM:     {hm_schema}\nDazzle: {dz_schema}"
    )
```

- [ ] **Step 3: Run parity — expect FAIL for missing ingest models**

Run: `pytest tests/unit/test_hm_contract_schema_parity.py -q`
Expected: FAIL — `AttributeError` / missing `ComboboxField` (and tags/money) on ingest module. GridEditCell row may still pass.

- [ ] **Step 4: Add ingest seam copies**

Append to `src/dazzle/render/fragment/ingest.py` (after `edit_span_attrs`, keep existing `GridEditCell` unchanged). Update module docstring to list all four models.

```python
# ── Combobox / tags / money seam copies ──────────────────────────────
# Mirrors packages/hatchi-maxchi/contracts/{combobox,tags,money}.py.
# Name collision note: dazzle.render.fragment.TagsField / MoneyField are
# form *primitives* (dataclasses). These Pydantic seam models are only
# importable as dazzle.render.fragment.ingest.TagsField / MoneyField.


class ComboboxOption(BaseModel):
    value: str
    label: str


class ComboboxField(BaseModel):
    """Server-rendered seed for a combobox (pre-enhancement markup)."""

    name: str
    field_id: str
    label: str
    options: list[ComboboxOption]
    selected: str = ""
    placeholder: str = ""

    @field_validator("options", mode="before")
    @classmethod
    def _pairs(cls, v: object) -> object:
        if not isinstance(v, list):
            return v
        out = []
        for o in v:
            if isinstance(o, dict):
                out.append({"value": str(o.get("value", "")), "label": str(o.get("label", ""))})
            elif isinstance(o, (tuple, list)) and len(o) >= 2:
                out.append({"value": str(o[0]), "label": str(o[1])})
            else:
                out.append({"value": str(o), "label": str(o)})
        return out


class TagsField(BaseModel):
    name: str
    field_id: str
    label: str
    tags: list[str] = []
    placeholder: str = ""

    @field_validator("tags", mode="before")
    @classmethod
    def _split(cls, v: object) -> object:
        if isinstance(v, str):
            return [t.strip() for t in v.split(",") if t.strip()]
        return v


class MoneyField(BaseModel):
    name: str
    currency: str = "GBP"
    scale: int = 2
    major_display: str = "0.00"
    minor_value: int = 0
    field_id: str = "money-field"
```

Also extend the top-of-file docstring so it names all four models (not only GridEditCell).

- [ ] **Step 5: Run parity — expect PASS**

Run: `pytest tests/unit/test_hm_contract_schema_parity.py -q`
Expected: 4 passed.

- [ ] **Step 6: Confirm form primitive imports unchanged**

Run:
```bash
python -c "
from dazzle.render.fragment import TagsField, MoneyField, WidgetCombobox
from dazzle.render.fragment.ingest import TagsField as IngestTags, MoneyField as IngestMoney, ComboboxField
assert TagsField is not IngestTags
assert MoneyField is not IngestMoney
print('ok', TagsField.__module__, IngestTags.__module__)
"
```
Expected: `ok dazzle.render.fragment.primitives.forms dazzle.render.fragment.ingest` (or similar primitive path).

- [ ] **Step 7: Commit**

```bash
git add tests/unit/hm_contract_registry.py \
  tests/unit/test_hm_contract_schema_parity.py \
  src/dazzle/render/fragment/ingest.py
git commit -m "$(cat <<'EOF'
test: generalise HM contract registry + schema parity for combobox/tags/money

Shared CONTRACT_MODELS registry; ingest seam copies for the three
model-bearing HM modules. Form primitives keep their public names.

Co-Authored-By: Grok Build <noreply@x.ai>
EOF
)"
```

---

### Task 2: Combobox DOM conformance

**Files:**
- Modify: `tests/unit/test_hm_contract_dom_conformance.py`
- Optional: no emission change if `WidgetCombobox` already emits `name` + `data-dz-combobox`

**Interfaces:**
- Consumes: `load_hm_module` from registry (or local `_load` if still present — prefer migrating `_load` to `load_hm_module` from registry to avoid duplication)
- Produces: green `test_widget_combobox_conforms_to_combobox_contract`

- [ ] **Step 1: Prefer shared loader in DOM gate**

In `test_hm_contract_dom_conformance.py`, replace the local `_load` / path setup with:

```python
from tests.unit.hm_contract_registry import HM, REPO_ROOT, load_hm_module
```

Update call sites: `_load("contracts/grid_edit.py")` → `load_hm_module("contracts/grid_edit.py")`, and `_load("contracts/_kit.py")` → `load_hm_module("contracts/_kit.py")`. Keep `REPO_ROOT` usage for the sole-emitter walk.

- [ ] **Step 2: Write combobox DOM fixture test**

Append:

```python
def test_widget_combobox_conforms_to_combobox_contract() -> None:
    """Real Dazzle WidgetCombobox emission must satisfy contracts/combobox.py."""
    pytest.importorskip("fastapi")
    from dazzle.render.fragment.primitives.forms import WidgetCombobox
    from dazzle.render.fragment.renderer import FragmentRenderer

    combobox = load_hm_module("contracts/combobox.py")
    kit = load_hm_module("contracts/_kit.py")
    frag = WidgetCombobox(
        name="priority",
        label="Priority",
        options=(("low", "Low"), ("medium", "Medium"), ("high", "High")),
        placeholder="Select…",
        initial_value="medium",
    )
    html = FragmentRenderer().render(frag)
    violations = kit.validate_dom(html, combobox.DOM_CONTRACT, require_root=False)
    assert not violations, violations
    assert 'data-dz-combobox' in html
    assert 'name="priority"' in html
```

- [ ] **Step 3: Run DOM tests**

Run: `pytest tests/unit/test_hm_contract_dom_conformance.py -q`
Expected: PASS (existing grid-edit + sole-emitter + new combobox). If FAIL with missing `name`, fix `_emit_widget_combobox` in `_render_forms.py` to always emit `name` on the select (today it already does).

- [ ] **Step 4: Optional sole-emitter for combobox — DEFER unless a helper lands**

Do **not** add a sole-emitter grep for `data-dz-combobox` in this task: emission still lives in `_render_forms.py`, not ingest. Document deferral: sole-emitter for combobox attrs lands only when a `combobox_select_attrs` (or similar) helper is extracted into `ingest.py` and rewired. Spec allows Phase 1 parity+DOM without rewire.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_hm_contract_dom_conformance.py
git commit -m "$(cat <<'EOF'
test: combobox DOM conformance against HM contract

FragmentRenderer WidgetCombobox emission validated with require_root=False
against contracts/combobox.py DOM_CONTRACT.

Co-Authored-By: Grok Build <noreply@x.ai>
EOF
)"
```

---

### Task 3: Tags + money DOM conformance

**Files:**
- Modify: `tests/unit/test_hm_contract_dom_conformance.py`
- Modify (conditional): `src/dazzle/render/fragment/renderer/_render_forms.py` — only if money emission fails DOM

**Interfaces:**
- Money fixed-currency path must emit `data-dz-money`, `data-dz-scale`, `data-dz-currency` on the root div (HM `DOM_CONTRACT`).
- Selector path currently may omit `data-dz-currency` — fix if testing selector, or document fixed-only fixture + separate bugfix for selector.

- [ ] **Step 1: Write tags DOM fixture**

```python
def test_tags_field_conforms_to_tags_contract() -> None:
    """Real Dazzle TagsField form primitive emission must satisfy contracts/tags.py."""
    pytest.importorskip("fastapi")
    from dazzle.render.fragment.primitives.forms import TagsField as FormTagsField
    from dazzle.render.fragment.renderer import FragmentRenderer

    tags_mod = load_hm_module("contracts/tags.py")
    kit = load_hm_module("contracts/_kit.py")
    frag = FormTagsField(
        name="labels",
        label="Labels",
        placeholder="Add a label…",
        initial_value="urgent,backend",
    )
    html = FragmentRenderer().render(frag)
    violations = kit.validate_dom(html, tags_mod.DOM_CONTRACT, require_root=False)
    assert not violations, violations
    assert "data-dz-tags" in html
    assert 'name="labels"' in html
```

- [ ] **Step 2: Write money DOM fixture (fixed currency)**

```python
def test_money_field_fixed_conforms_to_money_contract() -> None:
    """Fixed-currency MoneyField emission must satisfy contracts/money.py."""
    pytest.importorskip("fastapi")
    from dazzle.render.fragment.primitives.forms import MoneyField as FormMoneyField
    from dazzle.render.fragment.renderer import FragmentRenderer

    money_mod = load_hm_module("contracts/money.py")
    kit = load_hm_module("contracts/_kit.py")
    frag = FormMoneyField(
        name="amount",
        label="Amount",
        currency_code="GBP",
        scale="2",
        symbol="£",
        currency_fixed=True,
        minor_initial="1250",
    )
    html = FragmentRenderer().render(frag)
    violations = kit.validate_dom(html, money_mod.DOM_CONTRACT, require_root=False)
    assert not violations, violations
    assert "data-dz-money" in html
    assert 'data-dz-currency="GBP"' in html
    assert 'data-dz-scale="2"' in html
```

- [ ] **Step 3: Run and fix emission if needed**

Run: `pytest tests/unit/test_hm_contract_dom_conformance.py::test_money_field_fixed_conforms_to_money_contract -v`
Expected: PASS.

If selector path is also tested and fails (missing `data-dz-currency` on root), fix `_emit_money` selector branch to include:

```python
f'<div class="dz-money" data-dz-money '
f'data-dz-currency="{ctx.escape_attr(m.currency_code)}" '
f'data-dz-scale="{ctx.escape_attr(m.scale)}">'
```

Prefer fixing selector in the same commit if the failure is one line; otherwise keep fixed-only fixture and file a one-line follow-up only if you intentionally skip selector.

- [ ] **Step 4: Full dual-lock suite green**

Run:
```bash
pytest tests/unit/test_hm_contract_schema_parity.py tests/unit/test_hm_contract_dom_conformance.py -q
```
Expected: all passed (4 schema + grid-edit cases + sole-emitter + combobox + tags + money).

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_hm_contract_dom_conformance.py \
  src/dazzle/render/fragment/renderer/_render_forms.py  # if modified
git commit -m "$(cat <<'EOF'
test: tags + money DOM conformance against HM contracts

Form primitive emission validated with require_root=False. Fixes money
selector currency attr if required for green DOM lock.

Co-Authored-By: Grok Build <noreply@x.ai>
EOF
)"
```

---

### Task 4: Docs / Agent Guidance touch + verify gate suite

**Files:**
- Modify (optional, if present): `packages/hatchi-maxchi/contracts/AUTHORING.md` step 4 only if it still says "grid-edit only" — update to list combobox/tags/money dual locks.
- No CHANGELOG/bump required for pure test+ingest copies unless product docs claim the dual lock is pilot-only in user-facing docs that would mislead.

- [ ] **Step 1: Grep stale pilot-only claims**

```bash
rg -n "GridEditCell only|pilot-only|schema parity" docs/ packages/hatchi-maxchi/contracts/AUTHORING.md src/dazzle/render/fragment/ingest.py -g '*.md' -g '*.py' | head -40
```

Update any AUTHORING step that claims only grid-edit is dual-locked to list all four registry models.

- [ ] **Step 2: Run full unit gate marker**

```bash
pytest tests/unit -m gate -q
```
Expected: green (or only pre-existing unrelated failures — investigate if new).

- [ ] **Step 3: Commit docs if changed**

```bash
git add packages/hatchi-maxchi/contracts/AUTHORING.md  # if changed
git commit -m "$(cat <<'EOF'
docs: note Dazzle dual locks cover combobox/tags/money

Co-Authored-By: Grok Build <noreply@x.ai>
EOF
)"
```

---

### Task 5: Deferred tracks are GitHub issues (not this plan)

Filed (do not implement in this plan):

1. **#1577** — Unify form `MoneyField`/`TagsField` with HM ingest seam models (approach B).
2. **#1578** — Root-only Hyperpart DOM conformance from Dazzle emitters.
3. **#1579** — Prose `Contract:` header ↔ `DOM_CONTRACT` attr-name drift gate.

No implementation steps here.

---

## Self-review (plan vs spec)

| Spec requirement | Task |
|------------------|------|
| Shared registry | Task 1 |
| Schema parity parametrized for 4 models | Task 1 |
| Ingest seam copies combobox/tags/money | Task 1 |
| Name isolation (no re-export) | Task 1 step 6 |
| DOM fixtures combobox | Task 2 |
| DOM fixtures tags + money | Task 3 |
| Fix emission if DOM fails | Task 3 step 3 |
| Sole-emitter combobox/tags/money only if helper cheap | Explicitly deferred in Task 2 step 4 |
| Root-only / primitive unify / prose drift | Task 5 issues only |
| `pytest.mark.gate` | All test files retain marker |
| Phased green ships | Commits after Tasks 1, 2, 3 |

**Placeholder scan:** none intentional.
**Type consistency:** registry tuple order `(hm_path, hm_model, dz_module, dz_model)` used consistently; ingest model field names match HM contracts exactly.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-11-dazzle-contract-boundary-expansion.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks
2. **Inline Execution** — this session, executing-plans with checkpoints

Which approach?
