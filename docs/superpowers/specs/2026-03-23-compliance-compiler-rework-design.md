# Compliance Compiler Rework — Design Spec

**Date:** 2026-03-23
**Status:** Approved
**Scope:** Rework AegisMark's compliance compiler branch for Dazzle core integration
**Branch:** `feat/compliance-compiler` (5 commits, 27 files, 6,936 lines, 72 tests)

## Problem

AegisMark prototyped a compliance documentation compiler that maps DSL metadata to framework controls (ISO 27001). The prototype works but was built outside the framework — it regex-parses raw DSL text instead of walking the parsed IR, uses untyped dicts for all data shapes, and doesn't follow Dazzle's MCP/CLI patterns. A rework is needed before merging to main.

## Decisions

1. **AppSpec-first evidence extraction** — walk the parsed IR, not raw DSL text
2. **All models in one `models.py`** — single import point for agents consuming the module
3. **Two-layer evidence API** — pure `extract_evidence(appspec)` + convenience `extract_evidence_from_project(path)`
4. **MCP reads, CLI writes** — MCP handler returns data only; CLI handles file output
5. **Ship ISO 27001 only** — defer NIST CSF 2.0, SOC 2 until needed
6. **Brandspec stays separate from sitespec** — different mediums (print vs web)

## Module Structure

```
compliance/
  models.py              # ALL Pydantic models (taxonomy + evidence + AuditSpec)
  taxonomy.py            # load_taxonomy() — loader only, types from models.py
  evidence.py            # extract_evidence(appspec) + extract_evidence_from_project(path)
  compiler.py            # compile_auditspec(taxonomy, evidence) → AuditSpec
  slicer.py              # slice_auditspec(auditspec, filters) → filtered AuditSpec
  citation.py            # validate_citations(text, evidence) → list[CitationError]
  review.py              # generate_review_data(auditspec) → ReviewData
  coordinator.py         # compile_full_pipeline(project_root, framework) → PipelineResult
  renderer.py            # render_pdf(auditspec, brandspec) — optional deps
  frameworks/iso27001.yaml
  css/compliance.css
  templates/document.html
```

## Data Models (`models.py`)

All Pydantic `BaseModel` subclasses. Single file, single import path.

### Taxonomy Types

```python
class DslEvidence(BaseModel):
    construct: str           # classify, permit, scope, etc.
    description: str = ""

class Control(BaseModel):
    id: str                  # "A.5.1"
    name: str
    objective: str = ""
    dsl_evidence: list[DslEvidence] = []
    attributes: dict[str, list[str]] = {}

class Theme(BaseModel):
    id: str
    name: str
    controls: list[Control]

class Taxonomy(BaseModel):
    id: str
    name: str
    version: str = ""
    jurisdiction: str = ""
    body: str = ""           # standards body (e.g. "ISO")
    themes: list[Theme]
```

### Evidence Types

```python
class EvidenceItem(BaseModel):
    entity: str              # which entity/persona/process this was found on
    construct: str           # raw construct name: classify, permit, scope, etc.
    detail: str              # human-readable summary
    dsl_ref: str             # "EntityName.construct" for citation validation

class EvidenceMap(BaseModel):
    """All evidence extracted from an AppSpec."""
    items: dict[str, list[EvidenceItem]]  # keyed by RAW construct name (not mapped)
    dsl_hash: str            # sha256 of concatenated DSL content

    # Keys use raw construct names: "classify", "permit", "scope", "visible",
    # "transitions", "process", "persona", "story", "grant_schema", "llm_intent".
    # The CONSTRUCT_TO_KEY mapping in compiler.py maps these to compliance
    # categories when matching against taxonomy dsl_evidence entries.
```

### AuditSpec Types (Compiler Output)

```python
class AuditSummary(BaseModel):
    total_controls: int
    evidenced: int
    partial: int
    gaps: int
    excluded: int

class ControlResult(BaseModel):
    control_id: str
    control_name: str
    theme_id: str
    status: Literal["evidenced", "partial", "gap", "excluded"]
    # tier derives from status: evidenced=1, partial=2, gap=3, excluded=0
    # Kept as explicit field for easy filtering/sorting in agent contexts.
    tier: int
    evidence: list[EvidenceItem]
    gap_description: str = ""
    action: str = ""         # recommended action for gaps

class AuditSpec(BaseModel):
    framework_id: str
    framework_name: str
    framework_version: str = ""
    generated_at: str
    dsl_hash: str
    dsl_source: str = ""     # project root path for provenance
    controls: list[ControlResult]
    summary: AuditSummary
```

## Evidence Extraction (Rewrite)

### Why

The current `evidence.py` (579 lines) regex-parses raw `.dsl` files and shells out to `python3 -m dazzle policy coverage` via subprocess. Every piece of evidence it extracts is already available as typed IR in `AppSpec`:

| DSL Construct | IR Location |
|---|---|
| `classify` | `appspec.policies.classifications` → `ClassificationSpec` |
| `permit` | `entity.access.permissions` → `PermissionRule` |
| `scope` | `entity.access.scopes` → `ScopeRule` |
| `visible` | `entity.access.visibility` → `VisibilityRule` |
| `transitions` | `entity.state_machine.transitions` |
| `process` | `appspec.processes` → `ProcessSpec` |
| `persona` | `appspec.personas` → `PersonaSpec` |
| `story` | `appspec.stories` → `StorySpec` |
| `grant_schema` | `appspec.grant_schemas` |
| `llm_intent` | `appspec.llm_intents` → `LLMIntentSpec` (AI governance, logging config) |

### Interface

```python
def extract_evidence(appspec: AppSpec) -> EvidenceMap:
    """Walk AppSpec IR and extract compliance evidence.

    One inner function per construct type (~10 lines each).
    Returns typed EvidenceMap with items keyed by construct.
    """

def extract_evidence_from_project(project_root: Path) -> EvidenceMap:
    """Convenience wrapper: parse DSL → AppSpec → extract evidence."""
    appspec = load_project_appspec(project_root)
    return extract_evidence(appspec)
```

### DSL Hash

Computed over concatenated content of all DSL files (not just the first):

```python
from dazzle.core.fileset import discover_dsl_files
dsl_files = discover_dsl_files(project_root, manifest)
content = "".join(f.read_text() for f in sorted(dsl_files))
dsl_hash = f"sha256:{hashlib.sha256(content.encode()).hexdigest()[:16]}"
```

### CONSTRUCT_TO_KEY Documentation

The compiler maps DSL constructs to compliance evidence categories. Each mapping is documented:

```python
# Why these mappings exist (raw construct → taxonomy category):
# grant_schema → "permit": delegation rules evidence access control policies
# workspace → "personas": workspace assignments evidence role-based interfaces
# llm_intent → "classify": AI intent config evidences data handling governance
# archetype → "classify": audit trail fields evidence data lifecycle tracking
# scenarios → "stories": test scenarios evidence control validation
```

## MCP Handler

Rewritten to match existing patterns. Five read-only operations, no file I/O.

```python
# Signature: (project_path: Path, args: dict[str, Any]) → str (JSON)
# Decorator: @wrap_handler_errors
# Registration: _make_project_handler() in handlers_consolidated.py

# Operations:
# "compile"  → taxonomy + evidence + compile → AuditSpec JSON
# "evidence" → extract evidence only → EvidenceMap JSON
# "gaps"     → compile + filter gaps/partial → filtered ControlResult list
# "summary"  → compile → AuditSummary JSON
# "review"   → compile + generate review data → review items JSON
```

All operations load AppSpec via the standard MCP project state, not by re-parsing DSL.

## CLI

Three commands following `db.py` patterns:

```python
# compliance_app = typer.Typer(help="Compliance documentation tools")
# Uses rich.Console for output (not typer.echo)

# dazzle compliance compile [--framework iso27001] [--output path]
#   Extract + compile + write to .dazzle/compliance/output/<framework>/
#   Display summary with coverage percentage (division-by-zero guarded)

# dazzle compliance evidence [--framework iso27001]
#   Extract evidence only, display construct counts

# dazzle compliance gaps [--framework iso27001] [--tier 2,3]
#   Compile + display gap/partial controls with severity tiers
```

**Registration:** Import `compliance_app` in `cli/__init__.py`, register as `compliance` subcommand.

## Coordinator Bug Fixes

### Type Mutation

Replace:
```python
all_control_ids = set()
if controls == "all":
    all_control_ids = "all"  # BUG: set → str
```

With:
```python
use_all_controls: bool = False
control_ids: set[str] = set()
if controls == "all":
    use_all_controls = True
elif isinstance(controls, list):
    control_ids.update(controls)
```

### Cycle Detection

Add three-colour visited set to `topological_sort_documents`:

```python
def topological_sort_documents(doc_specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    visited: set[str] = set()
    in_progress: set[str] = set()
    order: list[dict[str, Any]] = []
    specs_by_id = {s["id"]: s for s in doc_specs}

    def visit(doc_id: str) -> None:
        if doc_id in in_progress:
            raise ValueError(f"Circular dependency detected: {doc_id}")
        if doc_id in visited:
            return
        in_progress.add(doc_id)
        for dep in deps.get(doc_id, []):
            visit(dep)
        in_progress.discard(doc_id)
        visited.add(doc_id)
        if doc_id in specs_by_id:
            order.append(specs_by_id[doc_id])
```

### Multi-File Hash

Hash all DSL files, not just the first. Pass concatenated content to `compile_auditspec` instead of a single file path.

## Renderer

Mostly unchanged. Four fixes:

1. **`base_url`** — use `str(PACKAGE_DIR)` not `str(Path.cwd())`
2. **File existence** — check `CSS_PATH.exists()` and `TEMPLATE_PATH.exists()` before use
3. **Brandspec location** — look in `.dazzle/compliance/brandspec.yaml` (not project root)
4. **Package data** — ensure `css/` and `templates/` are in `pyproject.toml` `[tool.setuptools.package-data]`

## Registration Checklist

| File | Change |
|---|---|
| `src/dazzle/mcp/server/tools_consolidated.py` | Add `compliance` tool definition with 5 operations |
| `src/dazzle/mcp/server/handlers_consolidated.py` | Register handler via `_make_project_handler()` |
| `src/dazzle/cli/__init__.py` | Import and register `compliance_app` |
| `pyproject.toml` | Add `compliance` optional extra (`weasyprint`, `markdown`) |
| `pyproject.toml` | Add `compliance` package-data for `css/`, `templates/`, `frameworks/` |

## What Stays Unchanged

- `frameworks/iso27001.yaml` — 93 controls, well-structured, good as-is
- `css/compliance.css` + `templates/document.html` — fine for rendering
- `slicer.py` — logic is correct, just needs typed parameters and error guards
- `citation.py` — logic is correct, just needs documented citation format
- `review.py` — logic is correct, rename to `generate_review_data`

## Testing

Existing 72 tests provide a baseline. Changes needed:

- **Evidence tests**: rewrite to pass `AppSpec` fixtures instead of raw DSL text
- **Compiler tests**: use Pydantic models instead of raw dicts
- **New tests**: taxonomy with missing sub-keys, duplicate control IDs, combined slicer filters, file-based DSL reading path, `dsl_content=None` branch
- **MCP handler tests**: standard handler test pattern with `@wrap_handler_errors`

## Deferred

- Additional framework taxonomies (NIST CSF 2.0, SOC 2, Cyber Essentials Plus)
- DSL grammar extensions (`compliance_framework` blocks, `retention:` directives)
- Compliance workspace UI surface
- Canary/tenant-specific compliance runs
