# Documentation Infrastructure Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a TOML-driven doc generator that renders the knowledge base into human-readable reference docs, then use it for a systematic documentation overhaul.

**Architecture:** A `docs_gen.py` module reads all TOML files from `src/dazzle/mcp/semantics_kb/`, groups concepts by their `doc_page` field, and renders structured markdown pages to `docs/reference/`. CLI commands `dazzle docs generate` and `dazzle docs check` expose this. The README gets slimmed down with an auto-injected feature table.

**Tech Stack:** Python 3.12, tomllib (stdlib), typer (existing CLI), Jinja2-free string formatting, pytest

---

## Task 1: Create `doc_pages.toml` — Page Metadata

**Files:**
- Create: `src/dazzle/mcp/semantics_kb/doc_pages.toml`

**Step 1: Create the page metadata file**

```toml
# Documentation page definitions.
# Each [pages.X] entry defines a reference doc page that concepts map to via doc_page field.

[meta]
version = "0.37.0"

[pages.entities]
title = "Entities"
slug = "entities"
order = 1
intro = """
Entities are the core data models in DAZZLE. They define structure, relationships,
constraints, state machines, computed fields, and access rules. An entity maps to a
database table at runtime but is defined at the semantic level — types, invariants,
and transitions are all declarative.
"""

[pages.access-control]
title = "Access Control"
slug = "access-control"
order = 2
intro = """
DAZZLE uses Cedar-style access rules with three layers: entity-level permit/forbid
blocks, surface-level access restrictions, and workspace-level persona allow/deny
lists. The evaluation order is FORBID > PERMIT > default-deny, aligned with NIST
SP 800-162.
"""

[pages.surfaces]
title = "Surfaces"
slug = "surfaces"
order = 3
intro = """
Surfaces define the UI screens of your application. Each surface binds to an entity
and declares which fields to display, in what layout, and with what UX affordances.
Surfaces support list, detail, form, grid, timeline, and calendar modes.
"""

[pages.workspaces]
title = "Workspaces"
slug = "workspaces"
order = 4
intro = """
Workspaces are role-specific dashboards that combine multiple data sources with
filters, aggregates, and navigation groups. Each workspace declares its purpose
and the persona it serves.
"""

[pages.ux]
title = "UX Semantic Layer"
slug = "ux"
order = 5
intro = """
The UX semantic layer lets you declare user experience intent — sort order, empty
states, attention signals, persona-scoped visibility, and purpose directives —
without writing UI code.
"""

[pages.experiences]
title = "Experiences"
slug = "experiences"
order = 6
intro = """
Experiences define multi-step user flows like onboarding wizards, checkout processes,
or guided setup sequences. Each experience has stages with completion conditions.
"""

[pages.services]
title = "Services"
slug = "services"
order = 7
intro = """
Services define custom business logic that lives outside the DSL. The DSL declares
the service interface (operations, inputs, outputs) and the runtime calls your
Python stub implementation.
"""

[pages.integrations]
title = "Integrations"
slug = "integrations"
order = 8
intro = """
Integrations connect your application to external APIs and data sources. They
declare mapping rules, sync schedules, and error handling without writing
integration code.
"""

[pages.processes]
title = "Processes"
slug = "processes"
order = 9
intro = """
Processes define multi-step workflows with triggers, conditions, and step types
including service calls, LLM intents, human tasks, and subprocesses. Execution
is checkpointed for resilience.
"""

[pages.stories]
title = "Stories"
slug = "stories"
order = 10
intro = """
Stories describe user journeys as structured narratives with personas, goals, and
acceptance criteria. They drive test generation and fidelity scoring.
"""

[pages.ledgers]
title = "Ledgers & Transactions"
slug = "ledgers"
order = 11
intro = """
DAZZLE integrates with TigerBeetle for double-entry accounting. Ledgers define
account structures and transactions define transfers between them, with
idempotency keys and linked transfer support.
"""

[pages.llm]
title = "LLM Models & Intents"
slug = "llm"
order = 12
intro = """
LLM features let you define AI-powered operations declaratively. Models configure
provider and tier, intents define prompts with structured output, and triggers
fire intents automatically on entity events.
"""

[pages.testing]
title = "Testing"
slug = "testing"
order = 13
intro = """
DAZZLE supports three tiers of testing: DSL contract tests (generated from entity
specs), E2E browser tests (agent-driven), and capability discovery (automated
gap analysis).
"""

[pages.frontend]
title = "Frontend & Templates"
slug = "frontend"
order = 14
intro = """
The frontend runtime uses HTMX for interactivity and Jinja2 for server-rendered
templates. Features include fragment contracts, OOB swaps, site specs for public
pages, and island architecture for client-side components.
"""

[pages.messaging]
title = "Messaging & Events"
slug = "messaging"
order = 15
intro = """
Messaging channels define real-time communication between the application and
external systems. Events declare domain occurrences that trigger workflows.
"""

[pages.governance]
title = "Governance"
slug = "governance"
order = 16
intro = """
Governance constructs define approval workflows and SLA constraints. Approvals
require sign-off from specified roles before state transitions. SLAs define
time-bound expectations with escalation paths.
"""

[pages.patterns]
title = "Patterns"
slug = "patterns"
order = 17
intro = """
Reusable design patterns and architectural conventions used across DAZZLE
applications. These are runtime and integration patterns, not DSL syntax.
"""
```

**Step 2: Commit**

```bash
git add src/dazzle/mcp/semantics_kb/doc_pages.toml
git commit -m "Add doc_pages.toml — page metadata for doc generator"
```

---

## Task 2: Add `doc_page` to All Existing TOML Concepts

**Files:**
- Modify: `src/dazzle/mcp/semantics_kb/core.toml`
- Modify: `src/dazzle/mcp/semantics_kb/cognition.toml`
- Modify: `src/dazzle/mcp/semantics_kb/expressions.toml`
- Modify: `src/dazzle/mcp/semantics_kb/extensibility.toml`
- Modify: `src/dazzle/mcp/semantics_kb/frontend.toml`
- Modify: `src/dazzle/mcp/semantics_kb/logic.toml`
- Modify: `src/dazzle/mcp/semantics_kb/misc.toml`
- Modify: `src/dazzle/mcp/semantics_kb/patterns.toml`
- Modify: `src/dazzle/mcp/semantics_kb/reference.toml`
- Modify: `src/dazzle/mcp/semantics_kb/testing.toml`
- Modify: `src/dazzle/mcp/semantics_kb/types.toml`
- Modify: `src/dazzle/mcp/semantics_kb/ux.toml`
- Modify: `src/dazzle/mcp/semantics_kb/workspace.toml`

**Step 1: Add `doc_page` and `doc_order` fields to every `[concepts.X]` entry**

Full mapping (75 concepts):

**core.toml:**
- `entity` → `doc_page = "entities"`, `doc_order = 1`
- `surface` → `doc_page = "surfaces"`, `doc_order = 1`
- `workspace` → `doc_page = "workspaces"`, `doc_order = 1`
- `stage` → `doc_page = "experiences"`, `doc_order = 2`
- `process` → `doc_page = "processes"`, `doc_order = 1`
- `experience` → `doc_page = "experiences"`, `doc_order = 1`

**cognition.toml:**
- `archetype` → `doc_page = "entities"`, `doc_order = 15`
- `domain_patterns` → `doc_page = "entities"`, `doc_order = 16`
- `examples` → `doc_page = "entities"`, `doc_order = 14`
- `intent` → `doc_page = "entities"`, `doc_order = 13`
- `invariant_message` → `doc_page = "entities"`, `doc_order = 12`

**expressions.toml:**
- `conditions` → `doc_page = "entities"`, `doc_order = 20`

**extensibility.toml:**
- `action_purity` → `doc_page = "services"`, `doc_order = 3`
- `component_role` → `doc_page = "services"`, `doc_order = 4`
- `domain_service` → `doc_page = "services"`, `doc_order = 1`
- `stub` → `doc_page = "services"`, `doc_order = 2`
- `three_layer_architecture` → `doc_page = "services"`, `doc_order = 5`
- `semantic_archetype` → `doc_page = "entities"`, `doc_order = 17`

**frontend.toml:**
- `htmx` → `doc_page = "frontend"`, `doc_order = 1`
- `templates` → `doc_page = "frontend"`, `doc_order = 2`
- `fragment_contract` → `doc_page = "frontend"`, `doc_order = 3`
- `oob_swap` → `doc_page = "frontend"`, `doc_order = 4`
- `sitespec` → `doc_page = "frontend"`, `doc_order = 5`
- `copy_md` → `doc_page = "frontend"`, `doc_order = 6`
- `section_types` → `doc_page = "frontend"`, `doc_order = 7`
- `directive_syntax` → `doc_page = "frontend"`, `doc_order = 8`
- `hybrid_pages` → `doc_page = "frontend"`, `doc_order = 9`
- `static_assets` → `doc_page = "frontend"`, `doc_order = 10`

**logic.toml:**
- `access_rules` → `doc_page = "access-control"`, `doc_order = 1`
- `computed_field` → `doc_page = "entities"`, `doc_order = 8`
- `invariant` → `doc_page = "entities"`, `doc_order = 9`
- `state_machine` → `doc_page = "entities"`, `doc_order = 10`

**misc.toml:**
- `authentication` → `doc_page = "access-control"`, `doc_order = 10`
- `index` → `doc_page = "entities"`, `doc_order = 6`
- `section` → `doc_page = "surfaces"`, `doc_order = 3`
- `surface_modes` → `doc_page = "surfaces"`, `doc_order = 2`
- `surface_actions` → `doc_page = "surfaces"`, `doc_order = 4`
- `scenario` → `doc_page = "testing"`, `doc_order = 10`
- `demo_data` → `doc_page = "testing"`, `doc_order = 11`
- `pagination` → `doc_page = "surfaces"`, `doc_order = 6`
- `aggregate` → `doc_page = "workspaces"`, `doc_order = 3`
- `foreign_model` → `doc_page = "integrations"`, `doc_order = 2`
- `ledger` → `doc_page = "ledgers"`, `doc_order = 1`
- `transaction` → `doc_page = "ledgers"`, `doc_order = 2`
- `llm_intent` → `doc_page = "llm"`, `doc_order = 3`
- `llm_model` → `doc_page = "llm"`, `doc_order = 1`
- `llm_config` → `doc_page = "llm"`, `doc_order = 2`
- `integration` → `doc_page = "integrations"`, `doc_order = 1`
- `unique_constraint` → `doc_page = "entities"`, `doc_order = 7`

**reference.toml:**
- `reserved_keywords` → `doc_page = "entities"`, `doc_order = 25`

**testing.toml:**
- `e2e_testing` → `doc_page = "testing"`, `doc_order = 1`
- `flowspec` → `doc_page = "testing"`, `doc_order = 2`
- `semantic_dom` → `doc_page = "testing"`, `doc_order = 3`
- `capability_discovery` → `doc_page = "testing"`, `doc_order = 4`
- `entity_completeness` → `doc_page = "testing"`, `doc_order = 5`
- `workflow_coherence` → `doc_page = "testing"`, `doc_order = 6`
- `rbac_validation` → `doc_page = "testing"`, `doc_order = 7`

**types.toml:**
- `enum` → `doc_page = "entities"`, `doc_order = 2`
- `field_types` → `doc_page = "entities"`, `doc_order = 3`
- `json` → `doc_page = "entities"`, `doc_order = 4`
- `ref` → `doc_page = "entities"`, `doc_order = 5`
- `relationships` → `doc_page = "entities"`, `doc_order = 5` (merged with ref section)
- `money` → `doc_page = "entities"`, `doc_order = 4`
- `timezone` → `doc_page = "entities"`, `doc_order = 4`

**ux.toml:**
- `attention_signals` → `doc_page = "ux"`, `doc_order = 3`
- `defaults` → `doc_page = "ux"`, `doc_order = 6`
- `information_needs` → `doc_page = "ux"`, `doc_order = 5`
- `persona` → `doc_page = "ux"`, `doc_order = 1`
- `purpose` → `doc_page = "ux"`, `doc_order = 2`
- `scope` → `doc_page = "ux"`, `doc_order = 4`
- `ux_block` → `doc_page = "ux"`, `doc_order = 7`
- `datatable` → `doc_page = "surfaces"`, `doc_order = 5`

**workspace.toml:**
- `aggregates` → `doc_page = "workspaces"`, `doc_order = 4`
- `display_modes` → `doc_page = "workspaces"`, `doc_order = 5`
- `regions` → `doc_page = "workspaces"`, `doc_order = 2`

**patterns.toml** — all `[patterns.X]` entries:
- All patterns → `doc_page = "patterns"`
- `doc_order` = alphabetical default (no explicit ordering needed)

**Step 2: Commit**

```bash
git add src/dazzle/mcp/semantics_kb/*.toml
git commit -m "Add doc_page field to all 75 TOML knowledge base concepts"
```

---

## Task 3: Write New TOML Concept Entries

**Files:**
- Modify: `src/dazzle/mcp/semantics_kb/logic.toml` (add visibility_rules, surface_access, workspace_access)
- Modify: `src/dazzle/mcp/semantics_kb/core.toml` (add story)
- Modify: `src/dazzle/mcp/semantics_kb/misc.toml` (add schedule, nav_group, process_steps, channel, approval, sla, webhook, llm_trigger, llm_concurrency)

**Step 1: Write 13 new concept entries**

For each new concept, read the IR source to get the definitive syntax. Reference files:

- `src/dazzle/core/ir/domain.py:53` — `VisibilityRule`
- `src/dazzle/core/ir/surfaces.py:130` — `SurfaceAccessSpec`
- `src/dazzle/core/ir/workspaces.py:27` — `WorkspaceAccessSpec`
- `src/dazzle/core/ir/workspaces.py:123` — `NavGroupSpec`
- `src/dazzle/core/ir/stories.py:107` — `StorySpec`
- `src/dazzle/core/ir/process.py:423` — `ScheduleSpec`
- `src/dazzle/core/ir/approvals.py:50` — `ApprovalSpec`
- `src/dazzle/core/ir/sla.py:71` — `SLASpec`
- `src/dazzle/core/ir/webhooks.py:69` — `WebhookSpec`
- `src/dazzle/core/ir/messaging.py:451` — `ChannelSpec`
- `src/dazzle/core/ir/llm.py` — `LLMTriggerSpec`, `LLMConfigSpec.concurrency`
- `src/dazzle/core/ir/process.py` — `ProcessStepSpec` step kinds

Each entry must have: `category`, `doc_page`, `doc_order`, `definition`, `syntax`, `example`, `related`. Optionally `best_practices`.

Use existing TOML entries as style reference — e.g. `[concepts.access_rules]` in `logic.toml` for tone and depth.

Also reference the DSL examples:
- `examples/rbac_validation/dsl/app.dsl` — access control patterns
- `examples/llm_ticket_classifier/dsl/app.dsl` — LLM intent with trigger/concurrency
- `examples/pra/dsl/` — processes, stories, experiences

**Step 2: Commit**

```bash
git add src/dazzle/mcp/semantics_kb/*.toml
git commit -m "Add 13 new TOML concepts for undocumented DSL features"
```

---

## Task 4: Fill Content Gaps in Existing Concepts

**Files:**
- Modify: `src/dazzle/mcp/semantics_kb/misc.toml` (surface_modes, pagination, llm_model, llm_config, llm_intent)
- Modify: `src/dazzle/mcp/semantics_kb/expressions.toml` (conditions)
- Modify: `src/dazzle/mcp/semantics_kb/types.toml` (field_types)
- Modify: `src/dazzle/mcp/semantics_kb/workspace.toml` (regions)

**Step 1: Fill empty definitions and examples**

Concepts with empty or stub content (identified by the audit):
- `surface_modes` — needs definition explaining list/detail/form/grid/timeline/calendar
- `pagination` — needs definition and syntax
- `regions` — needs definition, syntax, example
- `conditions` — needs syntax and example (condition expressions)
- `field_types` — needs a comprehensive type table
- `llm_model` — needs example (use llm_ticket_classifier as reference)
- `llm_config` — needs example
- `llm_intent` — needs example

Reference the IR types and parser source for accurate syntax:
- `src/dazzle/core/ir/surfaces.py` — SurfaceMode enum
- `src/dazzle/core/ir/workspaces.py` — WorkspaceRegionSpec
- `src/dazzle/core/ir/fields.py` — FieldTypeKind
- `src/dazzle/core/ir/llm.py` — LLMModelSpec, LLMConfigSpec, LLMIntentSpec

**Step 2: Commit**

```bash
git add src/dazzle/mcp/semantics_kb/*.toml
git commit -m "Fill content gaps in existing TOML knowledge base concepts"
```

---

## Task 5: Build `docs_gen.py` — Write Failing Tests

**Files:**
- Create: `tests/unit/test_docs_gen.py`

**Step 1: Write test file with all tests**

```python
"""Tests for documentation generator."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

# The module under test — doesn't exist yet, tests should fail on import
from dazzle.core.docs_gen import (
    check_docs_coverage,
    generate_reference_docs,
    load_concepts,
    load_page_metadata,
)


KB_DIR = Path("src/dazzle/mcp/semantics_kb")


class TestLoadConcepts:
    def test_loads_all_concepts(self):
        concepts = load_concepts(KB_DIR)
        # After enrichment, should have 75+ concepts
        assert len(concepts) >= 75

    def test_concepts_have_required_fields(self):
        concepts = load_concepts(KB_DIR)
        for name, info in concepts.items():
            assert "definition" in info, f"{name} missing definition"
            assert "doc_page" in info, f"{name} missing doc_page"

    def test_loads_patterns_too(self):
        concepts = load_concepts(KB_DIR)
        # patterns.toml uses [patterns.X] not [concepts.X]
        pattern_names = [n for n, i in concepts.items() if i.get("source") == "patterns"]
        assert len(pattern_names) > 0


class TestLoadPageMetadata:
    def test_loads_pages(self):
        pages = load_page_metadata(KB_DIR / "doc_pages.toml")
        assert len(pages) >= 15

    def test_pages_have_required_fields(self):
        pages = load_page_metadata(KB_DIR / "doc_pages.toml")
        for slug, page in pages.items():
            assert "title" in page, f"{slug} missing title"
            assert "order" in page, f"{slug} missing order"
            assert "intro" in page, f"{slug} missing intro"


class TestGenerateReferenceDocs:
    def test_returns_dict_of_slug_to_markdown(self):
        docs = generate_reference_docs()
        assert isinstance(docs, dict)
        assert "entities" in docs
        assert "access-control" in docs

    def test_pages_have_auto_generated_header(self):
        docs = generate_reference_docs()
        for slug, content in docs.items():
            assert "Auto-generated" in content, f"{slug} missing auto-generated header"

    def test_pages_have_title(self):
        docs = generate_reference_docs()
        for slug, content in docs.items():
            assert content.startswith("# "), f"{slug} missing title"

    def test_entities_page_has_entity_concept(self):
        docs = generate_reference_docs()
        assert "## Entity" in docs["entities"]

    def test_skips_empty_syntax_sections(self):
        docs = generate_reference_docs()
        # Should not have empty code blocks
        for slug, content in docs.items():
            assert "```dsl\n\n```" not in content, f"{slug} has empty code block"

    def test_related_links_are_markdown(self):
        docs = generate_reference_docs()
        # access_rules has related = ["entity", ...] — should link
        ac = docs["access-control"]
        assert "[" in ac  # Should contain at least one markdown link

    def test_index_page_generated(self):
        docs = generate_reference_docs()
        assert "index" in docs
        assert "| Section |" in docs["index"]


class TestCheckDocsCoverage:
    def test_no_errors_after_enrichment(self):
        issues = check_docs_coverage()
        errors = [i for i in issues if i.startswith("ERROR")]
        assert errors == [], f"Coverage errors: {errors}"
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_docs_gen.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'dazzle.core.docs_gen'`

**Step 3: Commit test file**

```bash
git add tests/unit/test_docs_gen.py
git commit -m "Add failing tests for docs_gen module"
```

---

## Task 6: Build `docs_gen.py` — Implementation

**Files:**
- Create: `src/dazzle/core/docs_gen.py`

**Step 1: Implement the generator module**

The module needs these functions:

```python
"""
Documentation generator for DAZZLE DSL reference.

Reads TOML knowledge base files and generates human-readable markdown
reference pages grouped by doc_page field.

Usage:
    python -m dazzle.core.docs_gen           # print summary
    dazzle docs generate                     # write docs/reference/*.md
    dazzle docs check                        # validate coverage
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

_KB_DIR = Path(__file__).parent.parent / "mcp" / "semantics_kb"
_DOCS_DIR = Path(__file__).parent.parent.parent.parent / "docs" / "reference"

def load_concepts(kb_dir: Path | None = None) -> dict[str, dict[str, Any]]: ...
def load_page_metadata(pages_path: Path | None = None) -> dict[str, dict[str, Any]]: ...
def _render_page(slug: str, page_meta: dict, concepts: list[tuple[str, dict]]) -> str: ...
def _render_concept(name: str, info: dict, all_concepts: dict) -> str: ...
def _render_index(pages: dict[str, dict[str, Any]]) -> str: ...
def _render_feature_table(pages: dict[str, dict[str, Any]]) -> str: ...
def generate_reference_docs(kb_dir: Path | None = None) -> dict[str, str]: ...
def write_reference_docs(output_dir: Path | None = None) -> list[Path]: ...
def check_docs_coverage(kb_dir: Path | None = None) -> list[str]: ...
def inject_readme_feature_table(readme_path: Path | None = None) -> bool: ...
```

Key implementation details:

- `load_concepts()`: Iterates `*.toml` in KB dir. For each file, reads both `concepts.*` and `patterns.*` sections. Patterns entries get `source = "patterns"` added. Returns flat dict of name→info.
- `load_page_metadata()`: Reads `doc_pages.toml`, returns dict of slug→page_meta.
- `_render_concept()`: Builds markdown for one concept. Title-cases the concept name (replacing `_` with space). Omits Syntax/Example/Best Practices sections if content is empty. For `related` entries, looks up their `doc_page` in `all_concepts` and creates `[Name](page.md#anchor)` links.
- `_render_page()`: Combines auto-generated header + intro + rendered concepts sorted by `doc_order`.
- `generate_reference_docs()`: Groups concepts by `doc_page`, renders each page + index page.
- `check_docs_coverage()`: Returns list of `"ERROR: ..."` and `"WARNING: ..."` strings.
- `inject_readme_feature_table()`: Reads README.md, finds `<!-- BEGIN FEATURE TABLE -->` / `<!-- END FEATURE TABLE -->` markers, replaces content between them with generated feature table.

**Step 2: Run tests**

```bash
pytest tests/unit/test_docs_gen.py -v
```

Expected: All pass

**Step 3: Commit**

```bash
git add src/dazzle/core/docs_gen.py
git commit -m "Add docs_gen module — TOML-driven reference doc generator"
```

---

## Task 7: Wire CLI Commands

**Files:**
- Modify: `src/dazzle/cli/docs.py` (add `generate` and `check` commands to existing `docs_app`)

**Step 1: Add the new commands**

Add two new commands to the existing `docs_app` Typer instance in `src/dazzle/cli/docs.py`. The existing `update` command stays unchanged.

```python
@docs_app.command("generate")
def docs_generate(
    output_dir: Path | None = typer.Option(
        None,
        "--output-dir",
        "-o",
        help="Output directory (defaults to docs/reference/)",
    ),
    stdout: bool = typer.Option(
        False,
        "--stdout",
        help="Print all pages to stdout instead of writing files.",
    ),
    readme: bool = typer.Option(
        True,
        "--readme/--no-readme",
        help="Also update README.md feature table.",
    ),
) -> None:
    """Regenerate reference docs from knowledge base TOML files."""
    from dazzle.core.docs_gen import (
        generate_reference_docs,
        inject_readme_feature_table,
        write_reference_docs,
    )

    if stdout:
        docs = generate_reference_docs()
        for slug, content in docs.items():
            typer.echo(f"--- {slug}.md ---")
            typer.echo(content)
            typer.echo()
    else:
        paths = write_reference_docs(output_dir)
        for p in paths:
            typer.echo(f"  Written: {p}")
        if readme:
            updated = inject_readme_feature_table()
            if updated:
                typer.echo("  Updated: README.md (feature table)")
        typer.secho(f"\nDone — {len(paths)} reference doc(s) generated.", bold=True)


@docs_app.command("check")
def docs_check() -> None:
    """Validate TOML coverage. Exits non-zero if errors found."""
    from dazzle.core.docs_gen import check_docs_coverage

    issues = check_docs_coverage()
    if not issues:
        typer.secho("All concepts have doc_page assignments. No issues found.", fg=typer.colors.GREEN)
        raise typer.Exit(code=0)

    errors = []
    warnings = []
    for issue in issues:
        if issue.startswith("ERROR"):
            typer.secho(f"  {issue}", fg=typer.colors.RED)
            errors.append(issue)
        else:
            typer.secho(f"  {issue}", fg=typer.colors.YELLOW)
            warnings.append(issue)

    typer.echo(f"\n{len(errors)} error(s), {len(warnings)} warning(s)")
    if errors:
        raise typer.Exit(code=1)
```

**Step 2: Smoke test**

```bash
dazzle docs --help
dazzle docs check
dazzle docs generate --stdout | head -50
```

**Step 3: Commit**

```bash
git add src/dazzle/cli/docs.py
git commit -m "Add dazzle docs generate and check CLI commands"
```

---

## Task 8: Generate All Reference Docs

**Files:**
- Overwrite: `docs/reference/entities.md`, `surfaces.md`, `workspaces.md`, `experiences.md`, `services.md`, `integrations.md`, `ledgers.md`, `ux.md`
- Create: `docs/reference/access-control.md`, `docs/reference/processes.md`, `docs/reference/stories.md`, `docs/reference/llm.md`, `docs/reference/frontend.md`, `docs/reference/messaging.md`, `docs/reference/governance.md`, `docs/reference/patterns.md`
- Overwrite: `docs/reference/index.md`

**Step 1: Migrate unique content from stale docs**

Before generating, read each existing hand-written doc that will be overwritten. If it contains content not yet in TOML (e.g. `entities.md` has a "Reserved keywords in enums" note), add that content to the relevant TOML concept entry.

Check files:
- `docs/reference/entities.md`
- `docs/reference/surfaces.md`
- `docs/reference/workspaces.md`
- `docs/reference/experiences.md`
- `docs/reference/services.md`
- `docs/reference/integrations.md`
- `docs/reference/ledgers.md`
- `docs/reference/ux.md`
- `docs/reference/modules.md` (may have content worth moving)

**Step 2: Run the generator**

```bash
dazzle docs generate
```

Expected: ~18 files written (17 pages + index)

**Step 3: Verify output quality**

- Spot-check `entities.md` — should have entity definition, field types, enum, ref, computed fields, state machines, invariants, access rules, examples
- Spot-check `access-control.md` — should have Cedar-style rules, visibility, surface access, workspace access
- Spot-check `llm.md` — should have llm_model, llm_config, llm_intent, triggers, concurrency
- Verify `index.md` has links to all pages

**Step 4: Delete `docs/reference/modules.md`**

This page becomes orphaned — its content is distributed across entities, services, and integrations pages.

**Step 5: Commit**

```bash
git add docs/reference/
git rm docs/reference/modules.md  # if it existed and is now orphaned
git commit -m "Generate reference docs from TOML knowledge base

Replaces 9 stale hand-written reference docs with auto-generated pages.
Adds 8 new reference pages for previously undocumented features."
```

---

## Task 9: Slim Down README.md

**Files:**
- Modify: `README.md`

**Step 1: Read current README structure**

The current README (~65KB) has these major sections:
- The Core Idea, Quick Start, First DSL File
- How Dazzle Works: The Eight Layers (detailed examples for each)
- The Pipeline, DSL Constructs Reference, MCP Tooling
- Agent Framework, Three-Tier Testing, API Packs, Fidelity Scoring
- Why HTMX Not React, Install, IDE Support, Examples
- Project Structure, Documentation, Contributing, License

**Step 2: Restructure**

Keep the editorial sections that work well (Core Idea, Quick Start, Architecture diagram, Why HTMX). Move detailed layer-by-layer examples into the reference docs (they duplicate TOML content). Add feature table markers and Documentation section with links.

Sections to keep as-is:
- Badges, headline, elevator pitch
- The Core Idea
- Quick Start (including First DSL File)
- Architecture diagram (the 4-line pipeline)
- Commands table
- MCP Server tool table
- Install
- IDE Support
- Examples (list with links)
- Contributing, License

Sections to slim down:
- "How Dazzle Works: The Eight Layers" — replace with feature table linking to reference docs
- "DSL Constructs Reference" table — replace with link to `docs/reference/index.md`
- "The Pipeline" — keep 1 paragraph, link to architecture docs
- "Agent Framework" — keep 1 paragraph, link to architecture docs
- "Three-Tier Testing" — keep 1 paragraph, link to testing reference
- "API Packs" — keep 1 paragraph, link to integrations reference
- "Fidelity Scoring" — keep 1 paragraph, link to reference
- "Project Structure" — keep, it's useful

**Step 3: Add feature table markers**

Insert between "Quick Start" and "Architecture":

```markdown
## DSL Feature Highlights

<!-- BEGIN FEATURE TABLE -->
<!-- END FEATURE TABLE -->
```

Then run:

```bash
dazzle docs generate
```

This injects the feature table.

**Step 4: Commit**

```bash
git add README.md
git commit -m "Slim README — link to generated reference docs for detail"
```

---

## Task 10: Quality Checks and Final Verification

**Files:**
- All modified files

**Step 1: Lint and format**

```bash
ruff check src/ tests/ --fix && ruff format src/ tests/
```

**Step 2: Type check**

```bash
mypy src/dazzle
```

**Step 3: Run all tests**

```bash
pytest tests/unit/test_docs_gen.py -v
pytest tests/ -m "not e2e" -x
```

**Step 4: Verify docs check passes**

```bash
dazzle docs check
```

Expected: `All concepts have doc_page assignments. No issues found.`

**Step 5: Verify generated docs look good**

```bash
dazzle docs generate
git diff docs/reference/ | head -100  # sanity check
```

---

## Task 11: Update CHANGELOG and Ship

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Add changelog entry**

Under `## [Unreleased]` → `### Added`:

```markdown
- Documentation infrastructure: `dazzle docs generate` renders TOML knowledge base into human-readable reference docs; `dazzle docs check` validates coverage
- 17 auto-generated reference pages covering all DSL constructs (entities, access control, surfaces, workspaces, LLM, processes, ledgers, governance, etc.)
- 13 new knowledge base concepts for previously undocumented features (nav_group, approval, SLA, webhook, LLM triggers, etc.)
- README.md overhauled — slimmed to editorial overview with auto-generated feature table linking to reference docs
```

**Step 2: Ship**

```bash
git add CHANGELOG.md
git commit -m "Add CHANGELOG entries for documentation infrastructure"
git push
```

---

## Summary

| Task | Description | Est. Files |
|------|-------------|-----------|
| 1 | Create `doc_pages.toml` | 1 new |
| 2 | Add `doc_page` to 75 existing concepts | 13 modified |
| 3 | Write 13 new TOML concepts | 3 modified |
| 4 | Fill content gaps | 4 modified |
| 5 | Write failing tests | 1 new |
| 6 | Build `docs_gen.py` | 1 new |
| 7 | Wire CLI commands | 1 modified |
| 8 | Generate all reference docs | ~18 new/overwritten |
| 9 | Slim README | 1 modified |
| 10 | Quality checks | 0 |
| 11 | CHANGELOG and ship | 1 modified |
