# SOC 2 Trust Services Criteria — Compliance Taxonomy

> **Issue:** #657
> **Status:** Approved
> **Date:** 2026-03-24
> **Follow-on issues:** #666 (DSL constructs for availability/processing integrity), #667 (taxonomy format restructure)

## Goal

Add SOC 2 Trust Services Criteria (TSC) as a second compliance framework alongside ISO 27001, using the existing framework-agnostic pipeline with zero Python logic changes.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Scope | All 5 TSC categories | Small incremental cost; immediate gap visibility |
| Cross-framework comparison | Deferred (future issue #667) | Needs both taxonomies in place first |
| Points of Focus | `attributes.points_of_focus` list | Consistent with ISO's `attributes` pattern; useful for auditors |
| Approach | Pure data (YAML only) | Pipeline is already framework-agnostic |

## Architecture

No new components. The existing pipeline handles everything:

```
soc2.yaml → taxonomy.load_taxonomy() → compiler.compile_auditspec() → AuditSpec
```

All existing operations (`compile`, `evidence`, `gaps`, `summary`, `review`) work unchanged with `--framework soc2`.

## Key Implementation Notes

**Construct names in YAML:** Always use the **taxonomy-side** construct name in `dsl_evidence` entries, not the raw AppSpec alias. For example, write `construct: permit` (not `construct: grant_schema`). The compiler's `CONSTRUCT_TO_KEY` mapping normalizes evidence items from the AppSpec to these canonical names before matching.

**`points_of_focus` storage:** The `points_of_focus` list sits inside `attributes` as a normal `list[str]` value, which matches the existing `dict[str, list[str]]` type declared in `models.py`. No model change is needed.

**Construct name spelling:** Check the existing ISO 27001 YAML for canonical construct name spelling (e.g. `processes` vs `process`). The compiler does exact string matching — use the same spelling as appears in the evidence extractor output.

## Deliverables

### 1. SOC 2 Taxonomy — `src/dazzle/compliance/frameworks/soc2.yaml`

~250–350 lines of YAML covering all five Trust Services Criteria categories.

**Structure:**

```yaml
framework:
  id: soc2
  name: "SOC 2 Type II — Trust Services Criteria"
  version: "2017-revised-2022"
  jurisdiction: united_states
  body: "AICPA"
  themes:
    - id: security
      name: "Common Criteria (Security)"
      controls:
        - id: "CC1.1"
          name: "COSO Principle 1"
          objective: "The entity demonstrates a commitment to integrity and ethical values."
          attributes:
            control_type: [preventive]
            security_concepts: [governance]
            points_of_focus:
              - "Sets the Tone at the Top"
              - "Establishes Standards of Conduct"
          dsl_evidence:
            - construct: persona
              description: "persona definitions encode organisational roles and responsibilities"
        # ... CC1.1 through CC9.2
    - id: availability
      name: "Availability"
      controls: [...]  # A1.1–A1.3
    - id: confidentiality
      name: "Confidentiality"
      controls: [...]  # C1.1–C1.2
    - id: processing_integrity
      name: "Processing Integrity"
      controls: [...]  # PI1.1–PI1.5
    - id: privacy
      name: "Privacy"
      controls: [...]  # P1.1–P8.1
```

**Control counts by theme (normative):**

| Theme | Controls | Approx. evidenced | Approx. excluded |
|-------|----------|-------------------|------------------|
| Security (CC1–CC9) | 33 | ~15 | ~18 |
| Availability (A1) | 3 | 1 | 2 |
| Confidentiality (C1) | 2 | 2 | 0 |
| Processing Integrity (PI1) | 5 | 2 | 3 |
| Privacy (P1–P8) | 18 | ~8 | ~10 |
| **Total** | **61** | **~28** | **~33** |

Controls that cannot be evidenced by DSL constructs (physical security, HR screening, vendor management, disaster recovery infrastructure, etc.) get `dsl_evidence: []` and compile to `excluded` status.

### 2. Evidence Mapping

Which DSL constructs evidence which SOC 2 criteria. In the YAML, always use the taxonomy-side name (left column):

| Taxonomy Construct | Security (CC) | Availability | Confidentiality | Processing Integrity | Privacy |
|--------------------|:---:|:---:|:---:|:---:|:---:|
| `permit` | CC5, CC6 | | C1 | | P6, P7 |
| `scope` | CC6 | | C1 | | P6 |
| `classify` | CC1, CC6 | | C1 | | P1, P2 |
| `transitions` | CC8 | | | PI1 | |
| `processes` | CC3, CC7, CC8 | A1 | | PI1 | |
| `personas` | CC1, CC2 | | | | P1 |
| `stories` | CC2, CC3 | | | | |
| `visible` | CC6 | | C1 | | P6 |

Note: `grant_schema` maps to `permit` via `CONSTRUCT_TO_KEY`, so grant evidence appears under `permit`. Similarly `workspace` → `personas`, `scenarios` → `stories`. Use the taxonomy-side names above in the YAML.

### 3. Test Fixture — `tests/unit/fixtures/compliance/mini_soc2_taxonomy.yaml`

A separate fixture (not merged into `mini_taxonomy.yaml`) because it needs to exercise `points_of_focus` attributes which the ISO fixture doesn't cover. Contains ~5 controls across 2 themes:

- 1 control with `dsl_evidence: [{construct: permit, ...}]` → compiles to `evidenced` when permit evidence present
- 1 control with `dsl_evidence: []` → compiles to `excluded`
- 1 control with `attributes.points_of_focus: [...]` → preserved through load/compile
- 2 controls from a second theme (e.g. `privacy`)

### 4. Test Cases

Add to `tests/unit/test_compliance_taxonomy.py`:

- `test_load_soc2_taxonomy` — loads the full `soc2.yaml`, validates structure (themes present, controls non-empty)
- `test_soc2_control_count` — asserts total control count equals the exact normative count (61)
- `test_soc2_compile_pipeline` — loads mini fixture, creates `EvidenceMap` with a `permit` item, calls `compile_auditspec()`. Asserts: the `permit`-evidenced control has `status="evidenced"`, the empty-evidence control has `status="excluded"`, `summary.evidenced >= 1`, `summary.excluded >= 1`
- `test_soc2_points_of_focus` — loads mini fixture, verifies `control.attributes["points_of_focus"]` is a non-empty list of strings

### 5. CLI/MCP Help Text Updates

- `src/dazzle/cli/compliance.py` — update **both** `--framework` option definitions (lines ~21 and ~71) to: `"Framework ID (iso27001 or soc2, default: iso27001)"`
- `src/dazzle/mcp/server/tools_consolidated.py` — update the `framework` field description in the `compliance` tool definition (line ~1373) to: `"Framework ID: iso27001 or soc2 (default: iso27001)"`

## What Is NOT In Scope

- No Python logic changes to loader, compiler, coordinator, or evidence extractor
- No cross-framework comparison (deferred to #667)
- No new DSL constructs for availability/processing integrity (deferred to #666)
- No `partial` status implementation (existing limitation, orthogonal to this work)
- No renderer/PDF changes
