# Proposal: Compliance Compiler for Dazzle DSL

**Author**: AegisMark team (proof-of-concept)
**Date**: 2026-03-23
**Branch**: `feat/compliance-compiler`

## Summary

Dazzle projects already declare data classification, access controls, processes, workflows, state machines, and role structures. This metadata — when mapped against a compliance framework — constitutes the bulk of the evidence required for certification.

The Compliance Compiler extracts this evidence, identifies gaps, and produces a structured AuditSpec IR that drives AI-powered document generation.

**Proven at AegisMark**: 21-document ISO 27001 ISMS pack generated from DSL, ~166 pages, covering all 93 Annex A controls. 37 controls (40%) fully evidenced from DSL alone.

## What This Branch Adds

### New Module: `dazzle.compliance`

| File | Purpose |
|------|---------|
| `taxonomy.py` | Load/validate compliance framework taxonomies from YAML |
| `evidence.py` | Extract DSL evidence (8 construct types, MCP-first) |
| `compiler.py` | Combine taxonomy + evidence → AuditSpec IR |
| `slicer.py` | Slice AuditSpec per-document for agent context |
| `citation.py` | Validate DSL ref citations in generated text |
| `review.py` | Generate review tracking for human-in-the-loop |
| `coordinator.py` | Orchestrate full pipeline |

### New MCP Tool: `compliance`

5 operations: `compile`, `evidence`, `gaps`, `review`, `summary`

### New CLI: `dazzle compliance`

3 commands: `compile`, `evidence`, `gaps`

### Tests

72 unit tests covering taxonomy, compiler, slicer, citation, review.

## Architecture

```
Framework Taxonomy (YAML)  +  DSL Evidence (parsed)
         │                           │
         └───────────┬───────────────┘
                     ▼
            AuditSpec Compiler
                     │
                     ▼
              AuditSpec IR (JSON)
                     │
         ┌───────────┼───────────┐
         ▼           ▼           ▼
    Per-document  Document    review.yaml
    AI agents     specs       (human-in-loop)
         │
         ▼
    Markdown documents → PDF (project-level renderer)
```

**Deterministic**: taxonomy loading, DSL walking, evidence matching, AuditSpec generation
**Creative**: prose authoring via AI agents (project-level, not in Dazzle core)
**Mechanical**: PDF rendering (project-level, WeasyPrint)

## DSL Evidence Constructs

The compiler recognises these DSL constructs as compliance evidence:

| Construct | What it evidences |
|-----------|-------------------|
| `classify` | Data classification, asset identification |
| `permit` | Role-based access control |
| `scope` | Row-level filtering, least-privilege |
| `visible` | Data minimisation |
| `transitions` | Workflow control, approval gates |
| `processes` | Operational procedures, SLAs |
| `grant_schema` | Privilege delegation |
| `persona` | Role definitions |
| `workspace` | Role-specific interfaces |
| `llm_config` | AI governance, logging |
| `archetype` | Audit trail fields |
| `scenarios` | Control flow validation |
| `stories` | Acceptance criteria |

## Framework Taxonomy Format

Any compliance standard is encoded as YAML:

```yaml
framework:
  id: iso27001
  name: "ISO/IEC 27001:2022"
  jurisdiction: international
  version: "2022"
  themes:
    - id: organisational
      controls:
        - id: "A.5.1"
          name: "Policies for information security"
          objective: "..."
          dsl_evidence:
            - construct: classify
            - construct: permit
```

Adding a new framework = adding a new YAML file. No code changes.

## What's NOT in This Branch (Project-Level)

- ISO 27001 taxonomy YAML (93 controls) — project content, not framework code
- Document specification YAMLs — project-specific document structure
- Human templates — project-specific boilerplate
- WeasyPrint PDF renderer — requires system deps, stays project-level
- Brand identity spec — project-specific styling
- `/audit` command — project-specific AI agent orchestration

## Suggested Next Steps for Dazzle

1. **Review & merge** this compliance module
2. **Register** the MCP tool in `tools_consolidated.py` and CLI in `cli/__init__.py`
3. **Add `compliance` to optional deps** in pyproject.toml (just PyYAML, already a dep)
4. **Consider DSL grammar extensions**:
   - `compliance_framework` block for declaring which frameworks apply
   - `retention:` directive on entities/fields
   - `brandspec` as a first-class concept
5. **Ship framework taxonomy files** as bundled data (ISO 27001, NIST CSF 2.0, SOC 2)
6. **Add compliance workspace** concept for browsable compliance surface in the UI

## AegisMark Results

From the proof-of-concept:

- **93 ISO 27001 controls** assessed
- **37 controls (40%)** fully evidenced from DSL
- **21 documents** generated (~166 pages)
- **110 human review markers** for items needing manual input
- **0 citation validation errors**
- **1.9 MB** zip archive with branded PDFs
- **Full pipeline**: taxonomy → evidence → AuditSpec → AI agents → markdown → PDF

The compliance compiler turns "define your business in DSL" into "get your compliance documentation for free."
