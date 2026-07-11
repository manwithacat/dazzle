# Dazzle Contract-Boundary Expansion — Design

**Date**: 2026-07-11
**Status**: Approved
**Driver**: Contract-module follow-on after HM `PENDING_CONTRACTS` drain (v0.101.34). The HM package now has DOM contracts for every controller; Dazzle dual locks remain pilot-only (`GridEditCell` / grid-edit).
**Prior art**: `docs/superpowers/specs/2026-07-10-hyperpart-contract-modules-design.md` (pilot + ratchet); `contracts/AUTHORING.md` step 4 (Dazzle emitter against typed model).

## Goal

Make the Dazzle↔HM cross-boundary locks **extensible**: any HM contract module that defines a Pydantic ingestion model can register into schema-parity and DOM-conformance gates without new one-off gate files. Ship the three model-bearing modules that already exist on the HM side — **combobox**, **tags**, **money** — through that machinery.

## Non-goals

- Enriching thin root-only HM modules (command, tabs, dialog, …) with models.
- Unifying Dazzle form primitives (`primitives/forms.py` `MoneyField` / `TagsField`) into a single type with HM (approach B — deferred product refactor).
- Prose `Contract:` header ↔ `DOM_CONTRACT` name drift gate (AUTHORING integrity track).
- Runtime import of `packages/hatchi-maxchi` from the installed wheel (still forbidden).

## Context

| Side | State today |
|------|-------------|
| HM | 19 contract modules; `PENDING_CONTRACTS` empty; models+EXEMPLARS on `grid_edit`, `combobox`, `tags`, `money` |
| Dazzle schema parity | Only `GridEditCell` ↔ `contracts/grid_edit.py` |
| Dazzle DOM conformance | Only hydrated grid-edit rows via `build_data_table` → `render_data_table_rows` |
| Dazzle typed ingest | `src/dazzle/render/fragment/ingest.py` — `GridEditCell` + `edit_span_attrs` only |
| Sole-emitter | Only `data-dz-edit-*` must be assembled in `ingest.py` |

Dazzle already emits combobox / tags / money HTML via form fragment primitives (`_render_forms.py`, `form_field.py`). Those primitives are **not** schema-identical to the HM contract models (different field sets / roles). The pilot pattern for grid-edit introduced a **seam model** in `ingest.py` rather than forcing the whole form primitive to match HM.

## Decisions

1. **Programme**: Dazzle typed-boundary expansion (not HM enrichment-first, not AUTHORING-only).
2. **Approach A**: Registry-driven dual locks + ingest seam copies for model-bearing modules.
3. **Name isolation**: HM-shaped copies live on `dazzle.render.fragment.ingest` only. They are **not** re-exported from `dazzle.render.fragment` until a later rewire. Existing form primitives (`MoneyField`, `TagsField` in `primitives/forms.py`) keep their names and roles.
4. **Root-only modules**: stay out of schema parity until they grow models. Optional future DOM-only gates are out of this design.
5. **Phasing**: combobox first (cleanest sole-emitter path), then tags + money; optional later primitive-unification is a separate issue.

## Architecture

```
packages/hatchi-maxchi/contracts/<part>.py     Dazzle monorepo
─────────────────────────────────────────     ──────────────────────────────
Pydantic model (source of truth)         ──►  ingest.py seam copy
DOM_CONTRACT                             ──►  validate_dom in gate tests
EXEMPLARS + render() (HM CI)             ──►  optional fixture reference

Emission (today)                              Emission (after typed path)
───────────────                               ────────────────────────────
_render_forms / form_field               ──►  construct seam model → attr helper
                                              (combobox in phase 1; tags/money
                                               when sole-emitter lands)
```

Cross-boundary locks remain **test-time** `importlib` reads of `packages/hatchi-maxchi/` — same pattern as the pilot. No runtime wheel dependency.

## Components

### 1. Shared registry (new)

`tests/unit/hm_contract_registry.py` (or equivalent single module imported by both gates):

```python
# Each row is one model-bearing contract.
# dazzle_model may equal hm_model; both are loaded from dazzle_module via getattr.
CONTRACT_MODELS: list[tuple[str, str, str, str]] = [
    # (hm_rel_path, hm_model_name, dazzle_module, dazzle_model_name)
    ("contracts/grid_edit.py", "GridEditCell", "dazzle.render.fragment.ingest", "GridEditCell"),
    ("contracts/combobox.py", "ComboboxField", "dazzle.render.fragment.ingest", "ComboboxField"),
    ("contracts/tags.py", "TagsField", "dazzle.render.fragment.ingest", "TagsField"),
    ("contracts/money.py", "MoneyField", "dazzle.render.fragment.ingest", "MoneyField"),
]
```

Helper: `_load_hm_module(rel)` — lift from existing parity test (fastapi importorskip, path insert, exec_module).

Adding the next model-bearing contract = one registry row + ingest copy + one DOM fixture — not a new test file.

### 2. Schema parity gate (generalise)

`tests/unit/test_hm_contract_schema_parity.py`:

- Parametrize over `CONTRACT_MODELS`.
- Canonicaliser stays as today (strip titles/descriptions; sort `required` / properties).
- Failure message names HM path + model and prints both schemas.

### 3. Ingest seam copies

`src/dazzle/render/fragment/ingest.py` grows:

| Model | Mirrors | Notes |
|-------|---------|--------|
| `GridEditCell` | already present | unchanged |
| `ComboboxField` | `contracts/combobox.py` | options normaliser (dict/tuple/bare string) |
| `TagsField` | `contracts/tags.py` | tags list / comma-string normaliser |
| `MoneyField` | `contracts/money.py` | scale/currency/major/minor/field_id |

Module docstring states: source of truth is HM; these copies exist because the wheel cannot ship `packages/`.

**Collision policy:** `from dazzle.render.fragment import TagsField` continues to mean the **form primitive**. Call sites that need the seam model use `dazzle.render.fragment.ingest.TagsField` explicitly. Grep gate optional: forbid `from dazzle.render.fragment.ingest import TagsField` outside ingest tests/emitters if noise appears.

### 4. DOM conformance gate (generalise)

`tests/unit/test_hm_contract_dom_conformance.py`:

- Keep existing grid-edit hydrated-row cases + sole-emitter for `data-dz-edit-*`.
- Add parametrized (or named) cases:

| Module | Fixture strategy |
|--------|------------------|
| combobox | Build a `WidgetCombobox` / form_field with enum options → emit HTML → `validate_dom(..., require_root=False)` against `contracts/combobox.py` `DOM_CONTRACT` |
| tags | Emit `TagsField` form primitive with comma or list seed → validate |
| money | Emit form `MoneyField` (primitive) → validate root attrs against money `DOM_CONTRACT` |

If current emission is missing a required DOM attr that HM contracts demand, **fix emission** in the same change set (claim integrity: detector and proof move together) — do not weaken the HM contract to match a buggy emitter.

### 5. Sole-emitter expansion (phased)

| Attr family | When |
|-------------|------|
| `data-dz-edit-*` | already gated |
| Combobox select attrs / options assembly | Phase 1 — if a helper lands (`combobox_select_markup` or attr builder used only from one path) |
| Tags / money attr assembly | Phase 2 — only when emission is rewired through ingest models; otherwise document deferral in the plan |

### 6. Emission rewire (minimal, phase-gated)

- **Phase 1 (combobox):** Prefer routing widget-combobox emission through `ingest.ComboboxField` for option normalisation if producers can pass multi-shape options today; otherwise parity + DOM on current HTML is enough for the first green ship.
- **Phase 2 (tags, money):** Add ingest copies + DOM fixtures; rewire emission only if it is a small, local change. Full primitive merge is deferred.

## Testing

- All new/changed tests carry `pytest.mark.gate` (DB-free).
- Local: `pytest tests/unit/test_hm_contract_schema_parity.py tests/unit/test_hm_contract_dom_conformance.py -q`
- Pre-ship: `pytest tests/unit -m gate -q` (includes HM non-browser suite via existing monorepo gate).
- No e2e required for this expansion.

## Success criteria

1. Unilateral field change on HM or Dazzle model for combobox/tags/money fails schema parity with a readable diff.
2. Hydrated/emitted DOM that violates `DOM_CONTRACT` fails DOM conformance.
3. Adding a fourth model-bearing contract is a registry row + ingest copy + fixture — not a new gate file.
4. Form primitive public API unchanged; no accidental re-export of ingest `TagsField`/`MoneyField`.

## Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Dual `TagsField` / `MoneyField` confusion | ingest-only location; docs; no re-export |
| DOM fixtures couple to large form renderers | Prefer smallest public path (`form_field` / single `_emit_*` with fixed kwargs) |
| HM contract stricter than current Dazzle HTML | Fix Dazzle emission in the same PR |
| Scope creep into primitive unification | Explicit non-goal; file deferred GitHub issue |

## Rollout

1. **Phase 1** — shared registry + schema parity for all four models; combobox ingest + DOM fixture (+ sole-emitter if helper is cheap).
2. **Phase 2** — tags + money ingest + DOM fixtures; sole-emitter only if rewire is small.
3. **Deferred** — primitive unification; root-only DOM gates; prose Contract drift gate.

Each phase ships green independently (`/bump patch` + CHANGELOG + Agent Guidance).

## Key Decisions

1. **Registry over one-off tests** — extensibility is the product of this work.
2. **Seam copies, not primitive merge** — preserves form API; matches grid-edit pilot.
3. **Combobox before tags/money** — lowest collision risk; clear progressive-enhancement seam.
4. **Root-only modules stay HM-only** for this design — no fake schema parity without models.

## Open Questions

None remaining for phase 1–2. Deferred tracks are issues, not blockers.

## PR Plan

| PR | Title | Scope | Depends |
|----|-------|-------|---------|
| 1 | `test: generalise HM contract registry + schema parity` | `hm_contract_registry.py`; rewrite schema parity to parametrize; add three ingest model copies (may fail DOM until PR 2) | — |
| 2 | `feat: combobox typed boundary + DOM conformance` | Combobox DOM fixture; optional emission/sole-emitter; green dual locks for combobox | 1 |
| 3 | `feat: tags + money typed boundary + DOM conformance` | Tags/money DOM fixtures; sole-emitter only if cheap | 1, 2 |
| 4 | (optional later) `refactor: form primitives construct from ingest seam models` | Unify emission paths | 3 |

In monorepo practice these may ship as sequential commits on `main` with one bump each, equivalent to the PR plan.

## GitHub issues to file

1. **Follow-on**: Unify Dazzle form `MoneyField`/`TagsField` with HM ingest seam models (approach B).
2. **Follow-on**: Root-only Hyperpart DOM conformance from Dazzle emitters (when a stable render path exists).
3. **Follow-on**: Controller prose `Contract:` header ↔ `DOM_CONTRACT` attr-name drift gate.
