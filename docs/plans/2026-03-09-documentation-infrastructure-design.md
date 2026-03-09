# Documentation Infrastructure Design

**Date:** 2026-03-09
**Status:** Approved
**Goal:** Build a doc generator that renders TOML knowledge base into human-readable reference docs, then use it for a systematic documentation overhaul.

## Problem

Dazzle has extensive documentation optimised for LLM cognition (`.claude/CLAUDE.md`, 75 TOML knowledge base concepts, 32 MCP tools) but leaves human developers behind. Nine reference docs are frozen since Feb 2. Major features — LLM intents, Cedar-style access control, nav_groups, approvals, SLAs, webhooks — have zero human-readable documentation. The knowledge base TOMLs contain excellent definitions, syntax, and examples that are only accessible via MCP.

## Decisions

- **TOML is the single source of truth.** All reference doc content lives in TOML. Editing docs means editing TOML. Generated markdown files carry an auto-generated header and are not hand-edited.
- **Explicit `doc_page` field** on each TOML concept controls which reference page it appears on.
- **Slim README + link out.** README keeps editorial voice (philosophy, quickstart, architecture) but links to generated reference docs for detail. Feature highlights table auto-injected between markers.
- **CLI command `dazzle docs`** with `generate` and `check` subcommands, consistent with existing `dazzle grammar`.

## Architecture

```
semantics_kb/*.toml  ──→  docs_gen.py  ──→  docs/reference/*.md
doc_pages.toml       ──┘                ──→  docs/reference/index.md
                                        ──→  README.md (feature table injection)
```

Separate from `grammar_gen.py` which produces formal EBNF from parser source. The two generators serve different purposes: grammar.md is syntax, reference docs are human guides with examples and best practices.

## 1. TOML Schema Extensions

### 1a. New fields on concept entries

Every `[concepts.X]` and `[patterns.X]` entry gains two optional fields:

```toml
[concepts.entity]
category = "Core Construct"
doc_page = "entities"       # Which reference page this concept appears on
doc_order = 1               # Sort order within page (default 50)
definition = "..."
syntax = "..."
example = "..."
best_practices = [...]
related = [...]
```

### 1b. New file: `src/dazzle/mcp/semantics_kb/doc_pages.toml`

Defines page metadata — titles, slugs, ordering, introductory text:

```toml
[meta]
version = "0.37.0"

[pages.entities]
title = "Entities"
slug = "entities"
order = 1
intro = """
Entities are the core data models in DAZZLE. They define structure,
relationships, constraints, state machines, and access rules.
"""

[pages.access-control]
title = "Access Control"
slug = "access-control"
order = 2
intro = """
DAZZLE uses Cedar-style access rules with three layers: entity-level
permit/forbid blocks, surface-level access restrictions, and workspace-level
persona allow/deny lists. Default policy is deny.
"""
```

Full page list (17 pages):

| Order | Slug | Title | Concept count |
|-------|------|-------|---------------|
| 1 | `entities` | Entities | ~16 |
| 2 | `access-control` | Access Control | ~6 |
| 3 | `surfaces` | Surfaces | ~6 |
| 4 | `workspaces` | Workspaces | ~5 |
| 5 | `ux` | UX Semantic Layer | ~7 |
| 6 | `experiences` | Experiences | ~2 |
| 7 | `services` | Services | ~5 |
| 8 | `integrations` | Integrations | ~3 |
| 9 | `processes` | Processes | ~4 |
| 10 | `stories` | Stories | ~2 |
| 11 | `ledgers` | Ledgers & Transactions | ~2 |
| 12 | `llm` | LLM Models & Intents | ~8 |
| 13 | `testing` | Testing | ~7 |
| 14 | `frontend` | Frontend & Templates | ~10 |
| 15 | `messaging` | Messaging & Events | ~2 |
| 16 | `governance` | Governance | ~3 |
| 17 | `patterns` | Patterns | ~25 |

## 2. Doc Generator (`src/dazzle/core/docs_gen.py`)

Single module, three public functions:

```python
def generate_reference_docs() -> dict[str, str]:
    """Return {slug: markdown_content} for all pages."""

def write_reference_docs(output_dir: Path | None = None) -> list[Path]:
    """Write all reference pages to docs/reference/. Returns paths written."""

def check_docs_coverage() -> list[str]:
    """Return list of issues (missing doc_page, orphan pages, etc.)."""
```

### Generation pipeline

1. Load all `*.toml` from `semantics_kb/`
2. Load `doc_pages.toml` for page metadata
3. Collect all entries (`concepts.*` and `patterns.*`) that have a `doc_page` field
4. Group by `doc_page`, sort by `doc_order` (default 50)
5. For each page, render markdown

### Page template

```markdown
# {page.title}

> **Auto-generated** from knowledge base TOML files by `docs_gen.py`.
> Do not edit manually; run `dazzle docs generate` to regenerate.

{page.intro}

---

## {concept_name title-cased}

{concept.definition}

### Syntax

```dsl
{concept.syntax}
```

### Example

```dsl
{concept.example}
```

### Best Practices

- {each best practice}

**Related:** [name](page.md#name), ...

---
```

### Rendering rules

- Sections with empty content (no syntax, no example, no best_practices) are omitted
- Related concepts that have a `doc_page` become markdown links: `[name](page.md#anchor)`
- Related concepts without `doc_page` render as plain text
- Concept anchors use kebab-case of the concept name
- Code blocks use `dsl` language tag for DSL syntax, no tag for Python examples

### Index page generation

`docs/reference/index.md` is also generated — a table of contents linking to all pages in order:

```markdown
# DSL Reference

| Section | Description |
|---------|-------------|
| [Entities](entities.md) | Core data models with types, constraints... |
| [Access Control](access-control.md) | Cedar-style permit/forbid rules... |
| ... | ... |
```

### Coverage checker

`check_docs_coverage()` returns issues:

- Concepts without `doc_page` field (warning)
- `doc_page` values that don't exist in `doc_pages.toml` (error)
- Pages in `doc_pages.toml` with no matching concepts (error)
- Concepts with empty `definition` (warning)

## 3. CLI Integration

New `dazzle docs` subcommand group in `src/dazzle/cli/__init__.py`:

```python
docs_app = typer.Typer(help="Documentation generation and validation.")

@docs_app.command(name="generate")
def docs_generate(
    output_dir: Path | None = Option(None, "--output-dir", "-o"),
    stdout: bool = Option(False, "--stdout"),
) -> None:
    """Regenerate reference docs from knowledge base TOML files."""

@docs_app.command(name="check")
def docs_check() -> None:
    """Validate TOML coverage. Exits non-zero if issues found."""

app.add_typer(docs_app, name="docs")
```

No new dependencies — uses `tomllib` (stdlib 3.11+) and string formatting.

## 4. TOML Content Enrichment

### Existing concepts needing `doc_page` assignment

All 75 existing concepts get a `doc_page` field added. No content changes needed for concepts that already have definition + syntax + example.

### New concepts to create (~13)

These features exist in the DSL but have no TOML knowledge base entry:

| Concept | `doc_page` | Source of truth |
|---------|-----------|-----------------|
| `surface_access` | `access-control` | `ir/surfaces.py` SurfaceAccessSpec |
| `workspace_access` | `access-control` | `ir/workspaces.py` WorkspaceAccessSpec |
| `visibility_rules` | `access-control` | `ir/domain.py` VisibilityRule |
| `story` | `stories` | `ir/stories.py` StorySpec |
| `schedule` | `processes` | `ir/process.py` ScheduleSpec |
| `approval` | `governance` | `ir/governance.py` ApprovalSpec |
| `sla` | `governance` | `ir/governance.py` SLASpec |
| `webhook` | `integrations` | `ir/eventing.py` WebhookSpec |
| `nav_group` | `workspaces` | `ir/workspaces.py` NavGroupSpec |
| `process_steps` | `processes` | `ir/process.py` ProcessStepSpec |
| `channel` | `messaging` | `ir/messaging.py` ChannelSpec |
| `llm_trigger` | `llm` | `ir/llm.py` LLMTriggerSpec |
| `llm_concurrency` | `llm` | `ir/llm.py` LLMConfigSpec.concurrency |

Each new entry follows existing TOML structure: `definition`, `syntax`, `example`, `related`, optionally `best_practices`.

### Content gaps in existing concepts

Some existing concepts have empty fields. Fill during enrichment:

- `surface_modes` — empty definition and example
- `pagination` — empty definition
- `regions` — no content at all
- `expressions/conditions` — empty
- `field_types` — empty
- `llm_model`, `llm_config`, `llm_intent` — syntax exists, examples missing

## 5. README.md Overhaul

### New structure

```
# DAZZLE                          ← keep existing elevator pitch
## Quick Start                    ← keep existing 5-line quickstart
## What Can You Build?            ← 2-3 sentences + link to examples/
## DSL Feature Highlights         ← auto-generated table between markers
## Architecture                   ← keep existing diagram, link to docs/architecture/
## Commands                       ← keep existing command table
## MCP Server                     ← keep existing tool table
## Documentation                  ← new section linking to all doc areas
## Package                        ← keep existing PyPI section
```

### Feature table injection

The generator injects a markdown table between marker comments:

```markdown
<!-- BEGIN FEATURE TABLE -->
| Feature | Description |
|---------|-------------|
| [Entities](docs/reference/entities.md) | Core data models with types... |
| [Access Control](docs/reference/access-control.md) | Cedar-style permit/forbid... |
...
<!-- END FEATURE TABLE -->
```

`dazzle docs generate` updates both `docs/reference/*.md` and the README feature table in one pass.

## 6. Stale Doc Handling

### Generated pages replace hand-written ones

These existing files will be overwritten by the generator:

- `entities.md` (stale since Jan 4)
- `surfaces.md` (stale since Feb 2)
- `workspaces.md` (stale since Feb 2)
- `experiences.md` (stale since Feb 2)
- `services.md` (stale since Feb 2)
- `integrations.md` (stale since Feb 2)
- `ledgers.md` (stale since Feb 2)
- `modules.md` (stale since Feb 2)
- `ux.md` (stale since Feb 2)

Before overwriting, any unique content from the old docs is migrated into TOML entries.

### Files that stay hand-written

Not generated from TOML — these remain untouched:

- `cli.md`, `databases.md`, `deployment.md` (operational, not DSL reference)
- `htmx-templates.md`, `islands.md` (frontend implementation guides)
- `messaging.md` (will be generated once channel concepts are added)
- `runtime-capabilities.md`, `scenarios.md`, `testing.md`, `workshop.md`
- `grammar.md` (generated by `grammar_gen.py`, separate pipeline)

### Index page

`docs/reference/index.md` is generated — replaces the current minimal hand-written one.

## 7. Testing & CI

### Unit tests (`tests/unit/test_docs_gen.py`)

- `test_load_concepts_from_toml` — all concepts load, have required fields
- `test_group_by_doc_page` — concepts without `doc_page` excluded, grouping correct
- `test_render_page_markdown` — output has title, intro, concept sections, code blocks
- `test_render_skips_empty_sections` — no empty syntax/example/best_practices blocks
- `test_related_links_resolve` — related concepts with `doc_page` become markdown links
- `test_check_coverage_catches_missing_doc_page` — flagged as warning
- `test_check_coverage_catches_orphan_pages` — flagged as error
- `test_feature_table_generation` — README marker injection produces valid markdown

### CI integration

Add `dazzle docs check` to the quality gate. If a TOML concept is added without `doc_page`, CI fails. Prevents documentation drift.

## Implementation Order

1. Create `doc_pages.toml` with page metadata
2. Add `doc_page` + `doc_order` to all 75 existing TOML concepts
3. Write ~13 new TOML concept entries for undocumented features
4. Fill content gaps in existing concepts (empty definitions/examples)
5. Build `docs_gen.py` generator
6. Wire CLI commands (`dazzle docs generate`, `dazzle docs check`)
7. Run generator — produces all reference docs + index
8. Slim down README.md, add feature table markers, run generator
9. Write unit tests
10. Add `dazzle docs check` to CI
11. CHANGELOG entry

## Verification

```bash
dazzle docs check                          # zero issues
dazzle docs generate                       # writes docs/reference/*.md
ruff check src/ tests/ --fix && ruff format src/ tests/
mypy src/dazzle
pytest tests/unit/test_docs_gen.py -v
pytest tests/ -m "not e2e" -x
```
