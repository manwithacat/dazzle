# Example /audit Command

> **Note:** This is provided as a reference implementation. Dazzle projects can adapt this as a Claude Code command (`.claude/commands/audit.md`) or integrate it into their CI/CD pipeline.

This document describes a 9-step compliance audit pipeline that orchestrates the Dazzle compliance compiler to produce branded PDF documents from DSL evidence. The example targets ISO 27001 but the structure applies to any framework supported by `dazzle.compliance.taxonomy`.

## Arguments

The command accepts a mode argument:

- `/audit` — Full pipeline: compile AuditSpec, generate all documents, render PDFs
- `/audit dry-run` — Compile AuditSpec only, report summary statistics
- `/audit customer` — Generate customer-facing compliance statement only
- `/audit audit-pack` — Generate formal audit pack only
- `/audit render` — Re-render existing markdown to PDF (skip generation)

## Pipeline Overview

```
Framework Taxonomy (YAML) + DSL Evidence -> AuditSpec IR (JSON)
    -> Per-document AI agents -> Markdown documents
    -> Citation validation -> Cross-reference check
    -> WeasyPrint PDF rendering
```

## Execution

### Step 1: Compile AuditSpec

Run the deterministic compiler pipeline:

```python
from dazzle.compliance.coordinator import compile_full_pipeline, write_outputs
from pathlib import Path

PROJECT = Path("{project_path}")
auditspec = compile_full_pipeline(PROJECT, framework="iso27001")
output_dir = write_outputs(PROJECT, auditspec, framework="iso27001")
```

Report summary: `"{total} controls: {evidenced} evidenced, {partial} partial, {gaps} gaps"`

If mode is `dry-run`, stop here.

### Step 2: Load Document Specifications

```python
from dazzle.compliance.slicer import load_document_spec

docs_dir = PROJECT / ".dazzle" / "compliance" / "documents"

if mode in ("customer", None):
    customer_spec = load_document_spec(docs_dir / "iso27001-customer-statement.yaml")
if mode in ("audit-pack", None):
    audit_spec = load_document_spec(docs_dir / "iso27001-audit-pack.yaml")
```

Document specification files define the structure, sections, and formality level for each output document. These YAML files live in the project's `.dazzle/compliance/documents/` directory.

### Step 3: Topological Sort Documents

```python
from dazzle.compliance.coordinator import topological_sort_documents

# For whichever pack(s) are being generated
documents = topological_sort_documents(spec["documents"])
```

Documents without `depends_on` are generated first. For example, a Statement of Applicability typically depends on the risk assessment, access control policy, and data classification policy being generated first.

### Step 4: Generate Documents via AI Agents

For each document in sorted order, build the agent context and dispatch:

```python
from dazzle.compliance.coordinator import build_agent_context

ctx = build_agent_context(document, auditspec, formality=spec["formality"])
```

**Dispatch an AI agent** with this prompt template (fill in the variables):

```
You are an ISO 27001 compliance specialist generating a formal document
for {organisation_name}.

## Document
Title: {ctx.document_title}
Formality: {ctx.formality}
Target pages: {ctx.target_pages or "appropriate length"}

## Sections to Write

{For each section in ctx.section_instructions:}
### {section.title}
Source: {section.source}
{section.ai_instruction if present}

## AuditSpec Evidence (filtered to relevant controls)

{JSON of ctx.sliced_auditspec}

## DSL Context

{Read relevant portions of the project DSL for entities/policies referenced
 in evidence}

## Templates (if source is "template")

{Read the template file from .dazzle/compliance/templates/{section_slug}.md}

## Instructions

1. Write each section in order as markdown
2. Use evidence from the AuditSpec to support every claim
3. Cite DSL constructs as: (DSL ref: EntityName.construct)
4. For tier 2/3 gaps, mark sections with <!-- HUMAN_INPUT_REQUIRED -->
   where human review is needed
5. Match the formality level: formal ISO language or accessible non-technical
6. Do NOT invent evidence -- only reference what exists in the AuditSpec
7. Write the complete document to: {output_dir}/markdown/{document_id}.md
```

**Parallel dispatch:** Documents without dependency relationships can be dispatched in parallel. Documents with `depends_on` must wait for their dependencies.

**Model selection:** Use a high-capability model (e.g. Opus) for complex documents like risk assessments and statements of applicability. Use a faster model (e.g. Sonnet) for simpler documents like scope statements and data classification policies.

### Step 5: Citation Validation

After each document is generated, validate that all citations reference real evidence:

```python
from dazzle.compliance.citation import validate_citations

md_path = output_dir / "markdown" / f"{document_id}.md"
text = md_path.read_text()
issues = validate_citations(text, auditspec)

if issues:
    print(f"Citation issues in {document_id}: {issues}")
    # Re-dispatch agent with correction instructions
```

### Step 6: Cross-Reference Consistency Check

After ALL documents are generated, run a consistency check across the full set:

```
You are a compliance document reviewer. Read all generated documents and check:

1. Consistent terminology (same role names, entity counts, statistics
   across all docs)
2. No contradictions between documents
3. Cross-references resolve (if doc A references "see Access Control
   Policy section 3.2", that section exists)

Documents to review:
{list all generated .md files with their content}

Report any inconsistencies found. For each, state which documents conflict
and what the correct value should be (based on the AuditSpec as ground truth).
```

If inconsistencies are found, regenerate only the affected sections (max 2 attempts). If still inconsistent, flag for human review.

### Step 7: Generate review.yaml

The `write_outputs` call in Step 1 generates `review.yaml`. After document generation, update it to reflect which tier 2/3 sections were actually marked with `<!-- HUMAN_INPUT_REQUIRED -->`.

### Step 8: Render PDFs

```python
from dazzle.compliance.renderer import render_document, load_brandspec

brandspec = load_brandspec(project_path=PROJECT)
md_dir = output_dir / "markdown"
pdf_dir = output_dir / "pdf"

for md_file in sorted(md_dir.glob("*.md")):
    doc_id = md_file.stem.upper().replace("_", "-")
    render_document(
        markdown_path=md_file,
        output_path=pdf_dir / f"{md_file.stem.replace('_', '-').title()}-v1.0.pdf",
        brandspec=brandspec,
        document_title=md_file.stem.replace("_", " ").title(),
        document_id=doc_id,
        version="1.0",
    )
```

The renderer reads `brandspec.yaml` from the project root. If no brandspec is found, it uses a minimal default with a neutral colour palette. See the [brandspec reference](brandspec-reference.md) for the full schema.

### Step 9: Report

Summarise the pipeline run:

- AuditSpec: {evidenced}/{total} controls evidenced ({percentage}%)
- Documents generated: {count} markdown files
- PDFs rendered: {count} files in {output_dir}/pdf/
- Citation issues: {count} (0 = clean)
- Cross-reference issues: {count}
- Human review items: {count} (from review.yaml)
- Output directory: {output_dir}

## Output Location

All outputs go to `.dazzle/compliance/output/{framework}/`:

```
.dazzle/compliance/output/iso27001/
  auditspec.json        # Compiled AuditSpec IR
  review.yaml           # Human review tracker
  markdown/             # Generated document markdown
  pdf/                  # Rendered branded PDFs
```

## Integration Patterns

### Git Workflow

- The AuditSpec JSON is committed to git (changes to compliance posture are visible in diffs)
- PDFs are gitignored (generated artefacts, reproducible from markdown)
- Run `/audit dry-run` to check compliance posture without generating documents

### CI/CD

The pipeline can be integrated into CI by running the compiler step only:

```bash
python3 -c "
from dazzle.compliance.coordinator import compile_full_pipeline
from pathlib import Path
spec = compile_full_pipeline(Path('.'), framework='iso27001')
gaps = [c for c in spec.controls if c.tier == 'gap']
if gaps:
    print(f'WARN: {len(gaps)} compliance gaps detected')
"
```

### Selective Regeneration

To regenerate only one document pack (e.g. after updating a policy):

```
/audit customer    # Regenerate customer-facing statement only
/audit render      # Re-render all markdown to PDF without regenerating content
```
