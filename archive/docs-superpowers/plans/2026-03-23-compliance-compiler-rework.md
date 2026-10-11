# Compliance Compiler Rework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rework AegisMark's compliance compiler branch to use AppSpec IR instead of regex parsing, add Pydantic models, fix MCP/CLI patterns, and wire in registration — making it ready for all Dazzle users.

**Architecture:** Evidence extraction walks the typed AppSpec IR (same foundation as every other Dazzle subsystem). All data shapes are Pydantic models in a single `models.py`. MCP handler returns read-only data; CLI handles file output. Coordinator orchestrates the full pipeline with proper type safety and cycle detection.

**Tech Stack:** Python 3.12, Pydantic v2, Dazzle IR (`AppSpec`), Typer CLI, Rich console

**Spec:** `docs/superpowers/specs/2026-03-23-compliance-compiler-rework-design.md`

**Branch:** `feat/compliance-compiler` (working from existing 5 commits)

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/dazzle/compliance/models.py` | Create | ALL Pydantic models (taxonomy + evidence + AuditSpec) |
| `src/dazzle/compliance/taxonomy.py` | Rewrite | Loader only — types move to models.py |
| `src/dazzle/compliance/evidence.py` | Rewrite | AppSpec IR walking (replaces 579-line regex version) |
| `src/dazzle/compliance/compiler.py` | Rewrite | Typed AuditSpec output, documented CONSTRUCT_TO_KEY |
| `src/dazzle/compliance/coordinator.py` | Rewrite | Type safety, cycle detection, multi-file hash |
| `src/dazzle/compliance/slicer.py` | Modify | Typed parameters, error guards |
| `src/dazzle/compliance/citation.py` | Modify | Type hints, documented citation format |
| `src/dazzle/compliance/review.py` | Modify | Rename function, type hints |
| `src/dazzle/compliance/renderer.py` | Modify | Fix base_url, file guards, brandspec path |
| `src/dazzle/mcp/server/handlers/compliance_handler.py` | Rewrite | Match handler patterns, no file I/O |
| `src/dazzle/cli/compliance.py` | Rewrite | Rich console, division guards, file output |
| `src/dazzle/mcp/server/handlers_consolidated.py` | Modify | Register compliance handler |
| `src/dazzle/mcp/server/tools_consolidated.py` | Modify | Add compliance tool definition |
| `src/dazzle/cli/__init__.py` | Modify | Register compliance_app |
| `pyproject.toml` | Modify | Add [compliance] extra, package-data |
| `tests/unit/test_compliance_*.py` | Rewrite | AppSpec fixtures, Pydantic models, new edge cases |

---

### Task 1: Create models.py with all Pydantic types

**Files:**
- Create: `src/dazzle/compliance/models.py`
- Create: `tests/unit/test_compliance_models.py`

- [ ] **Step 1: Write failing tests for taxonomy models**

Create `tests/unit/test_compliance_models.py`:

```python
"""Tests for compliance Pydantic models."""

from __future__ import annotations

from dazzle.compliance.models import (
    AuditSpec,
    AuditSummary,
    Control,
    ControlResult,
    DslEvidence,
    EvidenceItem,
    EvidenceMap,
    Taxonomy,
    Theme,
)


class TestTaxonomyModels:
    def test_control_with_evidence(self) -> None:
        ctrl = Control(
            id="A.5.1",
            name="Policies",
            objective="Management direction",
            dsl_evidence=[DslEvidence(construct="classify")],
        )
        assert ctrl.id == "A.5.1"
        assert len(ctrl.dsl_evidence) == 1

    def test_taxonomy_round_trip(self) -> None:
        tax = Taxonomy(
            id="iso27001",
            name="ISO 27001:2022",
            version="2022",
            body="ISO",
            themes=[
                Theme(
                    id="org",
                    name="Organisational",
                    controls=[Control(id="A.5.1", name="Policies")],
                )
            ],
        )
        data = tax.model_dump()
        assert data["body"] == "ISO"
        assert len(data["themes"][0]["controls"]) == 1


class TestEvidenceModels:
    def test_evidence_item(self) -> None:
        item = EvidenceItem(
            entity="Customer",
            construct="classify",
            detail="PII_DIRECT on email",
            dsl_ref="Customer.classify",
        )
        assert item.entity == "Customer"

    def test_evidence_map_keying(self) -> None:
        emap = EvidenceMap(
            items={"classify": [], "permit": []},
            dsl_hash="sha256:abc123",
        )
        assert "classify" in emap.items


class TestAuditSpecModels:
    def test_control_result_tier_mapping(self) -> None:
        cr = ControlResult(
            control_id="A.5.1",
            control_name="Policies",
            theme_id="org",
            status="evidenced",
            tier=1,
            evidence=[],
        )
        assert cr.tier == 1

    def test_excluded_tier_zero(self) -> None:
        cr = ControlResult(
            control_id="A.5.1",
            control_name="Policies",
            theme_id="org",
            status="excluded",
            tier=0,
            evidence=[],
        )
        assert cr.tier == 0

    def test_audit_spec_summary(self) -> None:
        spec = AuditSpec(
            framework_id="iso27001",
            framework_name="ISO 27001:2022",
            generated_at="2026-03-23T00:00:00Z",
            dsl_hash="sha256:abc",
            controls=[],
            summary=AuditSummary(
                total_controls=0,
                evidenced=0,
                partial=0,
                gaps=0,
                excluded=0,
            ),
        )
        assert spec.framework_id == "iso27001"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_compliance_models.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement models.py**

Create `src/dazzle/compliance/models.py`:

```python
"""All Pydantic models for the compliance compiler.

Single import point for agents consuming the module. Contains:
- Taxonomy types (framework structure)
- Evidence types (DSL evidence extracted from AppSpec)
- AuditSpec types (compiler output)
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# =============================================================================
# Taxonomy Types (loaded from framework YAML files)
# =============================================================================


class DslEvidence(BaseModel):
    """Maps a DSL construct to a compliance control."""

    construct: str  # classify, permit, scope, etc.
    description: str = ""


class Control(BaseModel):
    """A single compliance framework control (e.g. ISO 27001 A.5.1)."""

    id: str
    name: str
    objective: str = ""
    dsl_evidence: list[DslEvidence] = Field(default_factory=list)
    attributes: dict[str, list[str]] = Field(default_factory=dict)


class Theme(BaseModel):
    """A group of related controls (e.g. 'Organisational Controls')."""

    id: str
    name: str
    controls: list[Control]


class Taxonomy(BaseModel):
    """A complete compliance framework taxonomy."""

    id: str
    name: str
    version: str = ""
    jurisdiction: str = ""
    body: str = ""  # standards body (e.g. "ISO")
    themes: list[Theme]

    def all_controls(self) -> list[Control]:
        """Flat list of all controls across all themes."""
        return [c for t in self.themes for c in t.controls]

    def controls_by_id(self) -> dict[str, Control]:
        """Map control ID to Control for O(1) lookup."""
        return {c.id: c for t in self.themes for c in t.controls}


# =============================================================================
# Evidence Types (extracted from AppSpec IR)
# =============================================================================


class EvidenceItem(BaseModel):
    """A single piece of compliance evidence found in the DSL."""

    entity: str  # which entity/persona/process this was found on
    construct: str  # raw construct name: classify, permit, scope, etc.
    detail: str  # human-readable summary
    dsl_ref: str  # "EntityName.construct" for citation validation


class EvidenceMap(BaseModel):
    """All evidence extracted from an AppSpec.

    Keys in ``items`` use raw DSL construct names (classify, permit, scope,
    visible, transitions, process, persona, story, grant_schema, llm_intent).
    The CONSTRUCT_TO_KEY mapping in compiler.py maps these to taxonomy
    categories when matching against control dsl_evidence entries.
    """

    items: dict[str, list[EvidenceItem]] = Field(default_factory=dict)
    dsl_hash: str = ""


# =============================================================================
# AuditSpec Types (compiler output)
# =============================================================================


class AuditSummary(BaseModel):
    """Summary counts for an audit spec."""

    total_controls: int = 0
    evidenced: int = 0
    partial: int = 0
    gaps: int = 0
    excluded: int = 0


class ControlResult(BaseModel):
    """Assessment result for a single compliance control."""

    control_id: str
    control_name: str
    theme_id: str
    status: Literal["evidenced", "partial", "gap", "excluded"]
    tier: int  # evidenced=1, partial=2, gap=3, excluded=0
    evidence: list[EvidenceItem] = Field(default_factory=list)
    gap_description: str = ""
    action: str = ""  # recommended action for gaps


class AuditSpec(BaseModel):
    """Complete audit specification — the central IR of the compliance pipeline."""

    framework_id: str
    framework_name: str
    framework_version: str = ""
    generated_at: str
    dsl_hash: str
    dsl_source: str = ""  # project root path for provenance
    controls: list[ControlResult] = Field(default_factory=list)
    summary: AuditSummary = Field(default_factory=AuditSummary)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_compliance_models.py -v`
Expected: PASS

- [ ] **Step 5: Lint**

Run: `ruff check src/dazzle/compliance/models.py tests/unit/test_compliance_models.py --fix && ruff format src/dazzle/compliance/models.py tests/unit/test_compliance_models.py`

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/compliance/models.py tests/unit/test_compliance_models.py
git commit -m "feat(compliance): add Pydantic models for taxonomy, evidence, and AuditSpec"
```

---

### Task 2: Rewrite taxonomy.py to use models

**Files:**
- Modify: `src/dazzle/compliance/taxonomy.py`
- Modify: `tests/unit/test_compliance_taxonomy.py`

- [ ] **Step 1: Rewrite taxonomy.py as loader-only**

Replace the entire file with:

```python
"""Compliance framework taxonomy loader.

Loads and validates YAML taxonomy files (e.g. ISO 27001).
Types are defined in models.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from dazzle.compliance.models import Control, DslEvidence, Taxonomy, Theme


class TaxonomyError(Exception):
    """Error loading or validating a compliance taxonomy."""


def load_taxonomy(path: Path) -> Taxonomy:
    """Load a compliance framework taxonomy from a YAML file.

    Args:
        path: Path to the framework YAML file.

    Returns:
        Parsed and validated Taxonomy.

    Raises:
        TaxonomyError: If the file is missing, malformed, or invalid.
    """
    if not path.exists():
        raise TaxonomyError(f"Taxonomy file not found: {path}")

    try:
        with path.open() as f:
            raw = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise TaxonomyError(f"Invalid YAML in {path}: {e}") from e

    if not isinstance(raw, dict) or "framework" not in raw:
        raise TaxonomyError(f"Missing 'framework' key in {path}")

    fw = raw["framework"]

    try:
        themes = []
        for theme_data in fw.get("themes", []):
            controls = []
            for ctrl_data in theme_data.get("controls", []):
                evidence = [
                    DslEvidence(**e) for e in ctrl_data.get("dsl_evidence", [])
                ]
                controls.append(
                    Control(
                        id=ctrl_data["id"],
                        name=ctrl_data["name"],
                        objective=ctrl_data.get("objective", ""),
                        dsl_evidence=evidence,
                        attributes=ctrl_data.get("attributes", {}),
                    )
                )
            themes.append(
                Theme(
                    id=theme_data["id"],
                    name=theme_data["name"],
                    controls=controls,
                )
            )

        return Taxonomy(
            id=fw["id"],
            name=fw["name"],
            version=fw.get("version", ""),
            jurisdiction=fw.get("jurisdiction", ""),
            body=fw.get("body", ""),
            themes=themes,
        )
    except KeyError as e:
        raise TaxonomyError(f"Missing required field {e} in {path}") from e
```

- [ ] **Step 2: Update taxonomy tests**

Update `tests/unit/test_compliance_taxonomy.py` to import from models and test missing sub-keys:

```python
"""Tests for compliance taxonomy loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.compliance.models import Taxonomy
from dazzle.compliance.taxonomy import TaxonomyError, load_taxonomy

FIXTURES = Path(__file__).parent / "fixtures" / "compliance"


class TestLoadTaxonomy:
    def test_load_valid_taxonomy(self) -> None:
        tax = load_taxonomy(FIXTURES / "mini_taxonomy.yaml")
        assert isinstance(tax, Taxonomy)
        assert tax.id == "test_framework"
        assert len(tax.themes) >= 1

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(TaxonomyError, match="not found"):
            load_taxonomy(tmp_path / "nonexistent.yaml")

    def test_missing_framework_key_raises(self) -> None:
        with pytest.raises(TaxonomyError, match="framework"):
            load_taxonomy(FIXTURES / "bad_taxonomy.yaml")

    def test_controls_by_id(self) -> None:
        tax = load_taxonomy(FIXTURES / "mini_taxonomy.yaml")
        by_id = tax.controls_by_id()
        assert isinstance(by_id, dict)
        assert all(isinstance(k, str) for k in by_id)

    def test_all_controls_flat(self) -> None:
        tax = load_taxonomy(FIXTURES / "mini_taxonomy.yaml")
        controls = tax.all_controls()
        assert len(controls) > 0

    def test_missing_control_id_raises(self, tmp_path: Path) -> None:
        """Taxonomy with control missing 'id' field should raise TaxonomyError."""
        bad = tmp_path / "bad.yaml"
        bad.write_text(
            "framework:\n"
            "  id: test\n"
            "  name: Test\n"
            "  themes:\n"
            "    - id: t1\n"
            "      name: Theme 1\n"
            "      controls:\n"
            "        - name: Missing ID\n"
        )
        with pytest.raises(TaxonomyError, match="Missing required field"):
            load_taxonomy(bad)

    def test_missing_themes_returns_empty(self, tmp_path: Path) -> None:
        """Taxonomy with no themes is valid (just empty)."""
        minimal = tmp_path / "minimal.yaml"
        minimal.write_text(
            "framework:\n  id: test\n  name: Test\n"
        )
        tax = load_taxonomy(minimal)
        assert tax.themes == []
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/unit/test_compliance_taxonomy.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/dazzle/compliance/taxonomy.py tests/unit/test_compliance_taxonomy.py
git commit -m "refactor(compliance): rewrite taxonomy.py as loader-only, types in models.py"
```

---

### Task 3: Rewrite evidence.py to walk AppSpec IR

**Files:**
- Rewrite: `src/dazzle/compliance/evidence.py`
- Rewrite: `tests/unit/test_compliance_evidence.py` (new file, replaces inline evidence tests in compiler tests)

This is the biggest change — 579 lines of regex → ~120 lines of IR walking.

- [ ] **Step 1: Write failing tests for evidence extraction**

Create `tests/unit/test_compliance_evidence.py`:

```python
"""Tests for AppSpec-based evidence extraction."""

from __future__ import annotations

from unittest.mock import MagicMock

from dazzle.compliance.evidence import extract_evidence
from dazzle.compliance.models import EvidenceMap


def _make_appspec(
    *,
    entities: list | None = None,
    personas: list | None = None,
    processes: list | None = None,
    stories: list | None = None,
    policies: object | None = None,
    grant_schemas: list | None = None,
    llm_intents: list | None = None,
) -> MagicMock:
    """Build a minimal mock AppSpec for testing."""
    appspec = MagicMock()
    appspec.domain.entities = entities or []
    appspec.personas = personas or []
    appspec.processes = processes or []
    appspec.stories = stories or []
    appspec.policies = policies
    appspec.grant_schemas = grant_schemas or []
    appspec.llm_intents = llm_intents or []
    return appspec


class TestExtractEvidence:
    def test_empty_appspec_returns_empty_evidence(self) -> None:
        appspec = _make_appspec()
        result = extract_evidence(appspec)
        assert isinstance(result, EvidenceMap)
        assert all(len(v) == 0 for v in result.items.values())

    def test_classify_evidence_from_policies(self) -> None:
        policy = MagicMock()
        policy.classifications = [
            MagicMock(entity="Customer", field="email", classification="PII_DIRECT"),
        ]
        appspec = _make_appspec(policies=policy)
        result = extract_evidence(appspec)
        assert len(result.items.get("classify", [])) == 1
        assert result.items["classify"][0].entity == "Customer"

    def test_permit_evidence_from_entity_access(self) -> None:
        entity = MagicMock()
        entity.name = "Task"
        entity.access = MagicMock()
        entity.access.permissions = [
            MagicMock(operation="create", condition=MagicMock(__str__=lambda s: "authenticated")),
        ]
        entity.access.scopes = []
        entity.access.visibility = []
        entity.state_machine = None
        appspec = _make_appspec(entities=[entity])
        result = extract_evidence(appspec)
        assert len(result.items.get("permit", [])) >= 1

    def test_persona_evidence(self) -> None:
        persona = MagicMock()
        persona.id = "teacher"
        persona.name = "Teacher"
        persona.goals = ["manage classes"]
        appspec = _make_appspec(personas=[persona])
        result = extract_evidence(appspec)
        assert len(result.items.get("persona", [])) == 1
        assert result.items["persona"][0].entity == "teacher"

    def test_process_evidence(self) -> None:
        process = MagicMock()
        process.name = "onboarding"
        process.title = "Onboarding"
        process.steps = [MagicMock(), MagicMock()]
        appspec = _make_appspec(processes=[process])
        result = extract_evidence(appspec)
        assert len(result.items.get("process", [])) == 1

    def test_story_evidence(self) -> None:
        story = MagicMock()
        story.story_id = "create_task"
        story.title = "Create Task"
        story.actor = "teacher"
        appspec = _make_appspec(stories=[story])
        result = extract_evidence(appspec)
        assert len(result.items.get("story", [])) == 1

    def test_transition_evidence(self) -> None:
        sm = MagicMock()
        sm.transitions = [
            MagicMock(from_state="draft", to_state="published"),
        ]
        entity = MagicMock()
        entity.name = "Article"
        entity.access = None
        entity.state_machine = sm
        appspec = _make_appspec(entities=[entity])
        result = extract_evidence(appspec)
        assert len(result.items.get("transitions", [])) >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_compliance_evidence.py -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement evidence.py**

Replace the entire file:

```python
"""Extract compliance evidence from AppSpec IR.

Walks the typed AppSpec to find DSL constructs that evidence compliance
controls. Each construct type has a dedicated extractor function (~10 lines).

Usage:
    evidence = extract_evidence(appspec)          # from parsed IR
    evidence = extract_evidence_from_project(path) # convenience wrapper
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dazzle.compliance.models import EvidenceItem, EvidenceMap

if TYPE_CHECKING:
    from dazzle.core.ir import AppSpec


def extract_evidence(appspec: AppSpec) -> EvidenceMap:
    """Walk AppSpec IR and extract compliance evidence.

    Returns an EvidenceMap with items keyed by raw construct name.
    """
    items: dict[str, list[EvidenceItem]] = {
        "classify": _extract_classify(appspec),
        "permit": _extract_permit(appspec),
        "scope": _extract_scope(appspec),
        "visible": _extract_visible(appspec),
        "transitions": _extract_transitions(appspec),
        "process": _extract_processes(appspec),
        "persona": _extract_personas(appspec),
        "story": _extract_stories(appspec),
        "grant_schema": _extract_grant_schemas(appspec),
        "llm_intent": _extract_llm_intents(appspec),
    }
    return EvidenceMap(items=items)


def extract_evidence_from_project(project_root: Path) -> EvidenceMap:
    """Convenience wrapper: parse DSL → AppSpec → extract evidence."""
    from dazzle.cli.utils import load_project_appspec

    appspec = load_project_appspec(project_root)
    evidence = extract_evidence(appspec)

    # Compute DSL hash over all files
    from dazzle.core.fileset import discover_dsl_files
    from dazzle.core.manifest import load_manifest

    manifest_path = project_root / "dazzle.toml"
    if manifest_path.exists():
        manifest = load_manifest(manifest_path)
        dsl_files = discover_dsl_files(project_root, manifest)
        content = "".join(f.read_text() for f in sorted(dsl_files))
        evidence.dsl_hash = f"sha256:{hashlib.sha256(content.encode()).hexdigest()[:16]}"

    return evidence


# ---------------------------------------------------------------------------
# Per-construct extractors
# ---------------------------------------------------------------------------


def _extract_classify(appspec: AppSpec) -> list[EvidenceItem]:
    if not appspec.policies:
        return []
    return [
        EvidenceItem(
            entity=c.entity,
            construct="classify",
            detail=f"{c.classification} on {c.entity}.{c.field}",
            dsl_ref=f"{c.entity}.classify",
        )
        for c in appspec.policies.classifications
    ]


def _extract_permit(appspec: AppSpec) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    for entity in appspec.domain.entities:
        if not entity.access:
            continue
        for perm in entity.access.permissions:
            items.append(
                EvidenceItem(
                    entity=entity.name,
                    construct="permit",
                    detail=f"{perm.operation}: {perm.condition}",
                    dsl_ref=f"{entity.name}.permit",
                )
            )
    return items


def _extract_scope(appspec: AppSpec) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    for entity in appspec.domain.entities:
        if not entity.access:
            continue
        for scope in entity.access.scopes:
            items.append(
                EvidenceItem(
                    entity=entity.name,
                    construct="scope",
                    detail=f"{scope.operation}: {scope.condition}",
                    dsl_ref=f"{entity.name}.scope",
                )
            )
    return items


def _extract_visible(appspec: AppSpec) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    for entity in appspec.domain.entities:
        if not entity.access:
            continue
        for vis in entity.access.visibility:
            items.append(
                EvidenceItem(
                    entity=entity.name,
                    construct="visible",
                    detail=f"{vis.context}: {vis.condition}",
                    dsl_ref=f"{entity.name}.visible",
                )
            )
    return items


def _extract_transitions(appspec: AppSpec) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    for entity in appspec.domain.entities:
        if not entity.state_machine:
            continue
        for t in entity.state_machine.transitions:
            items.append(
                EvidenceItem(
                    entity=entity.name,
                    construct="transitions",
                    detail=f"{t.from_state} → {t.to_state}",
                    dsl_ref=f"{entity.name}.transitions",
                )
            )
    return items


def _extract_processes(appspec: AppSpec) -> list[EvidenceItem]:
    return [
        EvidenceItem(
            entity=p.name,
            construct="process",
            detail=f"{p.title or p.name} ({len(p.steps)} steps)",
            dsl_ref=f"{p.name}.process",
        )
        for p in appspec.processes
    ]


def _extract_personas(appspec: AppSpec) -> list[EvidenceItem]:
    return [
        EvidenceItem(
            entity=p.id,
            construct="persona",
            detail=getattr(p, "name", None) or p.id,
            dsl_ref=f"{p.id}.persona",
        )
        for p in appspec.personas
    ]


def _extract_stories(appspec: AppSpec) -> list[EvidenceItem]:
    return [
        EvidenceItem(
            entity=s.story_id,
            construct="story",
            detail=f"{s.title or s.story_id} (actor: {s.actor})",
            dsl_ref=f"{s.story_id}.story",
        )
        for s in appspec.stories
    ]


def _extract_grant_schemas(appspec: AppSpec) -> list[EvidenceItem]:
    return [
        EvidenceItem(
            entity=g.scope if hasattr(g, "scope") else g.name,
            construct="grant_schema",
            detail=f"grant_schema on {g.scope if hasattr(g, 'scope') else g.name}",
            dsl_ref=f"{g.scope if hasattr(g, 'scope') else g.name}.grant_schema",
        )
        for g in appspec.grant_schemas
    ]


def _extract_llm_intents(appspec: AppSpec) -> list[EvidenceItem]:
    return [
        EvidenceItem(
            entity=intent.name,
            construct="llm_intent",
            detail=f"{intent.title or intent.name}",
            dsl_ref=f"{intent.name}.llm_intent",
        )
        for intent in appspec.llm_intents
    ]
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_compliance_evidence.py -v`
Expected: PASS

- [ ] **Step 5: Delete old evidence tests that use DSL text fixtures**

The old tests in `test_compliance_compiler.py` that tested evidence extraction via raw DSL will be replaced in Task 4. For now, verify no imports break:

Run: `pytest tests/unit/test_compliance_*.py -v`

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/compliance/evidence.py tests/unit/test_compliance_evidence.py
git commit -m "feat(compliance): rewrite evidence.py to walk AppSpec IR instead of regex"
```

---

### Task 4: Rewrite compiler.py with typed output

**Files:**
- Rewrite: `src/dazzle/compliance/compiler.py`
- Rewrite: `tests/unit/test_compliance_compiler.py`

- [ ] **Step 1: Write failing tests**

Rewrite `tests/unit/test_compliance_compiler.py` to use Pydantic models:

```python
"""Tests for compliance AuditSpec compiler."""

from __future__ import annotations

from dazzle.compliance.compiler import compile_auditspec
from dazzle.compliance.models import (
    AuditSpec,
    Control,
    DslEvidence,
    EvidenceItem,
    EvidenceMap,
    Taxonomy,
    Theme,
)


def _mini_taxonomy() -> Taxonomy:
    return Taxonomy(
        id="test",
        name="Test Framework",
        themes=[
            Theme(
                id="org",
                name="Organisational",
                controls=[
                    Control(
                        id="C-1",
                        name="Access Control",
                        dsl_evidence=[DslEvidence(construct="permit")],
                    ),
                    Control(
                        id="C-2",
                        name="Data Classification",
                        dsl_evidence=[DslEvidence(construct="classify")],
                    ),
                    Control(
                        id="C-3",
                        name="Workflow Control",
                        dsl_evidence=[DslEvidence(construct="transitions")],
                    ),
                ],
            )
        ],
    )


def _evidence_with_permit() -> EvidenceMap:
    return EvidenceMap(
        items={
            "permit": [
                EvidenceItem(
                    entity="Task",
                    construct="permit",
                    detail="create: authenticated",
                    dsl_ref="Task.permit",
                )
            ],
            "classify": [],
        },
        dsl_hash="sha256:abc123",
    )


class TestCompileAuditspec:
    def test_returns_audit_spec(self) -> None:
        result = compile_auditspec(_mini_taxonomy(), _evidence_with_permit())
        assert isinstance(result, AuditSpec)

    def test_evidenced_control(self) -> None:
        result = compile_auditspec(_mini_taxonomy(), _evidence_with_permit())
        c1 = next(c for c in result.controls if c.control_id == "C-1")
        assert c1.status == "evidenced"
        assert c1.tier == 1

    def test_gap_control(self) -> None:
        result = compile_auditspec(_mini_taxonomy(), _evidence_with_permit())
        c3 = next(c for c in result.controls if c.control_id == "C-3")
        assert c3.status == "gap"
        assert c3.tier == 3

    def test_summary_counts(self) -> None:
        result = compile_auditspec(_mini_taxonomy(), _evidence_with_permit())
        assert result.summary.total_controls == 3
        assert result.summary.evidenced == 1
        assert result.summary.gaps == 2

    def test_empty_evidence_all_gaps(self) -> None:
        empty = EvidenceMap(items={}, dsl_hash="sha256:empty")
        result = compile_auditspec(_mini_taxonomy(), empty)
        assert result.summary.gaps == 3
        assert result.summary.evidenced == 0

    def test_construct_to_key_mapping(self) -> None:
        """grant_schema evidence should match 'permit' controls."""
        evidence = EvidenceMap(
            items={
                "grant_schema": [
                    EvidenceItem(
                        entity="School",
                        construct="grant_schema",
                        detail="delegation",
                        dsl_ref="School.grant_schema",
                    )
                ],
            },
            dsl_hash="sha256:test",
        )
        result = compile_auditspec(_mini_taxonomy(), evidence)
        c1 = next(c for c in result.controls if c.control_id == "C-1")
        assert c1.status == "evidenced"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_compliance_compiler.py -v`

- [ ] **Step 3: Implement compiler.py**

Replace the entire file:

```python
"""Compile taxonomy + evidence into a typed AuditSpec.

Maps DSL evidence to compliance framework controls and produces
a per-control assessment (evidenced / partial / gap / excluded).
"""

from __future__ import annotations

from datetime import UTC, datetime

from dazzle.compliance.models import (
    AuditSpec,
    AuditSummary,
    ControlResult,
    EvidenceItem,
    EvidenceMap,
    Taxonomy,
)

# Maps raw DSL construct names to taxonomy evidence categories.
# When a taxonomy control lists dsl_evidence with construct="permit",
# evidence items from both "permit" AND "grant_schema" match.
#
# Why these mappings exist:
# grant_schema → permit: delegation rules evidence access control policies
# workspace → personas: workspace assignments evidence role-based interfaces
# llm_intent → classify: AI intent config evidences data handling governance
# archetype → classify: audit trail fields evidence data lifecycle tracking
# scenarios → stories: test scenarios evidence control validation
CONSTRUCT_TO_KEY: dict[str, str] = {
    "grant_schema": "permit",
    "workspace": "personas",
    "llm_intent": "classify",
    "archetype": "classify",
    "scenarios": "stories",
}


def compile_auditspec(taxonomy: Taxonomy, evidence: EvidenceMap) -> AuditSpec:
    """Compile a taxonomy and evidence map into a typed AuditSpec.

    For each control in the taxonomy, checks whether the DSL evidence
    contains items matching the control's expected constructs. Produces
    a ControlResult with status and tier for each control.
    """
    # Build reverse mapping: taxonomy category → list of evidence items
    evidence_by_category: dict[str, list[EvidenceItem]] = {}
    for construct_name, items in evidence.items.items():
        # Map to taxonomy category (or use raw name if no mapping)
        category = CONSTRUCT_TO_KEY.get(construct_name, construct_name)
        evidence_by_category.setdefault(category, []).extend(items)

    # Pre-compute theme lookup
    control_to_theme: dict[str, str] = {}
    for theme in taxonomy.themes:
        for ctrl in theme.controls:
            control_to_theme[ctrl.id] = theme.id

    # Assess each control
    results: list[ControlResult] = []
    for control in taxonomy.all_controls():
        expected = {e.construct for e in control.dsl_evidence}
        matched: list[EvidenceItem] = []
        for category in expected:
            matched.extend(evidence_by_category.get(category, []))

        if matched:
            status = "evidenced"
            tier = 1
        elif not expected:
            # Control has no DSL evidence mapping — excluded
            status = "excluded"
            tier = 0
        else:
            status = "gap"
            tier = 3

        results.append(
            ControlResult(
                control_id=control.id,
                control_name=control.name,
                theme_id=control_to_theme.get(control.id, ""),
                status=status,
                tier=tier,
                evidence=matched,
            )
        )

    # Summary
    summary = AuditSummary(
        total_controls=len(results),
        evidenced=sum(1 for r in results if r.status == "evidenced"),
        partial=sum(1 for r in results if r.status == "partial"),
        gaps=sum(1 for r in results if r.status == "gap"),
        excluded=sum(1 for r in results if r.status == "excluded"),
    )

    return AuditSpec(
        framework_id=taxonomy.id,
        framework_name=taxonomy.name,
        framework_version=taxonomy.version,
        generated_at=datetime.now(UTC).isoformat(),
        dsl_hash=evidence.dsl_hash,
        controls=results,
        summary=summary,
    )
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_compliance_compiler.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/compliance/compiler.py tests/unit/test_compliance_compiler.py
git commit -m "feat(compliance): rewrite compiler.py with typed AuditSpec output"
```

---

### Task 5: Fix coordinator.py bugs

**Files:**
- Rewrite: `src/dazzle/compliance/coordinator.py`

- [ ] **Step 1: Rewrite coordinator.py**

Replace the entire file with a version that:
- Uses typed models from `models.py`
- Has proper cycle detection in topological sort
- Uses `bool` flag instead of set→str mutation
- Hashes all DSL files
- Does NOT import private `_find_dsl_files`
- Does NOT call `write_outputs()` (that moves to CLI)

```python
"""Orchestrate the full compliance compilation pipeline.

Coordinates: taxonomy loading → evidence extraction → AuditSpec compilation.
File output is handled by the CLI, not this module.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dazzle.compliance.compiler import compile_auditspec
from dazzle.compliance.evidence import extract_evidence_from_project
from dazzle.compliance.models import AuditSpec, EvidenceMap, Taxonomy
from dazzle.compliance.taxonomy import TaxonomyError, load_taxonomy

# Default framework taxonomy bundled with Dazzle
_BUNDLED_FRAMEWORKS = Path(__file__).parent / "frameworks"


def compile_full_pipeline(
    project_root: Path,
    framework: str = "iso27001",
    taxonomy_path: Path | None = None,
) -> AuditSpec:
    """Run the full compliance pipeline: taxonomy + evidence → AuditSpec.

    Args:
        project_root: Path to the Dazzle project root.
        framework: Framework ID (used to find bundled taxonomy YAML).
        taxonomy_path: Override path to taxonomy YAML file.

    Returns:
        Compiled AuditSpec with per-control assessments.
    """
    # Load taxonomy
    if taxonomy_path is None:
        taxonomy_path = _BUNDLED_FRAMEWORKS / f"{framework}.yaml"
    taxonomy = load_taxonomy(taxonomy_path)

    # Extract evidence from AppSpec
    evidence = extract_evidence_from_project(project_root)

    # Compile
    auditspec = compile_auditspec(taxonomy, evidence)
    auditspec.dsl_source = str(project_root)

    return auditspec


def topological_sort_documents(
    doc_specs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Sort document specs by dependency order with cycle detection.

    Args:
        doc_specs: List of document spec dicts with 'id' and 'depends_on' keys.

    Returns:
        Sorted list of document spec dicts.

    Raises:
        ValueError: If a circular dependency is detected.
    """
    specs_by_id: dict[str, dict[str, Any]] = {s["id"]: s for s in doc_specs}
    deps: dict[str, list[str]] = {
        s["id"]: s.get("depends_on", []) for s in doc_specs
    }

    visited: set[str] = set()
    in_progress: set[str] = set()
    order: list[dict[str, Any]] = []

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

    for doc_id in specs_by_id:
        visit(doc_id)

    return order


def build_agent_context(
    auditspec: AuditSpec,
    doc_specs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build per-document agent context from an AuditSpec.

    Args:
        auditspec: Compiled AuditSpec.
        doc_specs: Sorted document specifications.

    Returns:
        List of context dicts, one per document, for AI agent dispatch.
    """
    use_all_controls = False
    control_ids: set[str] = set()

    for doc in doc_specs:
        controls = doc.get("controls", [])
        if controls == "all":
            use_all_controls = True
        elif isinstance(controls, list):
            control_ids.update(controls)

    # Filter controls for each document
    contexts: list[dict[str, Any]] = []
    for doc in doc_specs:
        doc_controls = doc.get("controls", [])
        if doc_controls == "all" or use_all_controls:
            relevant = auditspec.controls
        elif isinstance(doc_controls, list):
            relevant = [c for c in auditspec.controls if c.control_id in set(doc_controls)]
        else:
            relevant = []

        contexts.append({
            "document_id": doc["id"],
            "document_title": doc.get("title", doc["id"]),
            "controls": [c.model_dump() for c in relevant],
            "summary": auditspec.summary.model_dump(),
        })

    return contexts
```

- [ ] **Step 2: Run all compliance tests**

Run: `pytest tests/unit/test_compliance_*.py -v`

- [ ] **Step 3: Commit**

```bash
git add src/dazzle/compliance/coordinator.py
git commit -m "fix(compliance): rewrite coordinator with cycle detection and type safety"
```

---

### Task 6: Fix slicer, citation, review, renderer

**Files:**
- Modify: `src/dazzle/compliance/slicer.py`
- Modify: `src/dazzle/compliance/citation.py`
- Modify: `src/dazzle/compliance/review.py`
- Modify: `src/dazzle/compliance/renderer.py`
- Modify: `tests/unit/test_compliance_slicer.py`
- Modify: `tests/unit/test_compliance_citation.py`
- Modify: `tests/unit/test_compliance_review.py`

Minor fixes across supporting modules:

- [ ] **Step 1: Fix slicer.py** — add error guard for missing `document_pack` key, add type hints
- [ ] **Step 2: Fix citation.py** — add type hints, document citation format in docstring
- [ ] **Step 3: Fix review.py** — rename `generate_review_yaml` → `generate_review_data`, add type hints
- [ ] **Step 4: Fix renderer.py** — use `PACKAGE_DIR` for `base_url`, guard file existence, look for brandspec in `.dazzle/compliance/brandspec.yaml`
- [ ] **Step 5: Update `__init__.py`** — update public exports
- [ ] **Step 6: Update tests** — add combined slicer filter test, citation edge cases
- [ ] **Step 7: Run all tests**

Run: `pytest tests/unit/test_compliance_*.py -v`

- [ ] **Step 8: Lint and type check**

Run: `ruff check src/dazzle/compliance/ tests/unit/test_compliance_*.py --fix && ruff format src/dazzle/compliance/ tests/unit/test_compliance_*.py`
Run: `mypy src/dazzle/compliance/ --ignore-missing-imports`
Expected: 0 errors

- [ ] **Step 9: Commit**

```bash
git add src/dazzle/compliance/ tests/unit/test_compliance_*.py
git commit -m "fix(compliance): type hints, error guards, and style fixes across supporting modules"
```

---

### Task 7: Rewrite MCP handler and wire in registration

**Files:**
- Rewrite: `src/dazzle/mcp/server/handlers/compliance_handler.py`
- Modify: `src/dazzle/mcp/server/handlers_consolidated.py`
- Modify: `src/dazzle/mcp/server/tools_consolidated.py`

- [ ] **Step 1: Rewrite compliance_handler.py**

Follow the existing handler pattern exactly. All operations are read-only, return JSON strings:

```python
"""Compliance MCP handler — read-only compliance pipeline operations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def compile_compliance(project_path: Path, args: dict[str, Any]) -> str:
    """Compile taxonomy + evidence → AuditSpec JSON."""
    from dazzle.compliance.coordinator import compile_full_pipeline

    framework = args.get("framework", "iso27001")
    auditspec = compile_full_pipeline(project_path, framework=framework)
    return json.dumps(auditspec.model_dump(), indent=2)


def extract_evidence_op(project_path: Path, args: dict[str, Any]) -> str:
    """Extract evidence only → EvidenceMap JSON."""
    from dazzle.compliance.evidence import extract_evidence_from_project

    evidence = extract_evidence_from_project(project_path)
    return json.dumps(evidence.model_dump(), indent=2)


def compliance_gaps(project_path: Path, args: dict[str, Any]) -> str:
    """Compile + filter to gaps/partial → ControlResult list JSON."""
    from dazzle.compliance.coordinator import compile_full_pipeline

    framework = args.get("framework", "iso27001")
    auditspec = compile_full_pipeline(project_path, framework=framework)
    gaps = [c.model_dump() for c in auditspec.controls if c.status in ("gap", "partial")]
    return json.dumps({"gaps": gaps, "count": len(gaps)}, indent=2)


def compliance_summary(project_path: Path, args: dict[str, Any]) -> str:
    """Compile → AuditSummary JSON."""
    from dazzle.compliance.coordinator import compile_full_pipeline

    framework = args.get("framework", "iso27001")
    auditspec = compile_full_pipeline(project_path, framework=framework)
    return json.dumps(auditspec.summary.model_dump(), indent=2)


def compliance_review(project_path: Path, args: dict[str, Any]) -> str:
    """Compile + generate review data → review items JSON."""
    from dazzle.compliance.coordinator import compile_full_pipeline
    from dazzle.compliance.review import generate_review_data

    framework = args.get("framework", "iso27001")
    auditspec = compile_full_pipeline(project_path, framework=framework)
    review = generate_review_data(auditspec)
    return json.dumps(review, indent=2)
```

- [ ] **Step 2: Register in handlers_consolidated.py**

Add after the last handler registration:

```python
# =============================================================================
# Compliance Operations Handler
# =============================================================================

_MOD_COMPLIANCE = "dazzle.mcp.server.handlers.compliance_handler"

handle_compliance: Callable[[dict[str, Any]], str] = _make_project_handler(
    "Compliance",
    {
        "compile": f"{_MOD_COMPLIANCE}:compile_compliance",
        "evidence": f"{_MOD_COMPLIANCE}:extract_evidence_op",
        "gaps": f"{_MOD_COMPLIANCE}:compliance_gaps",
        "summary": f"{_MOD_COMPLIANCE}:compliance_summary",
        "review": f"{_MOD_COMPLIANCE}:compliance_review",
    },
)
```

- [ ] **Step 3: Register in tools_consolidated.py**

Add `compliance` tool definition following existing patterns. Check existing tool definitions for the exact format and add a matching entry with 5 operations.

- [ ] **Step 4: Verify MCP registration**

Run: `python -c "from dazzle.mcp.server.handlers_consolidated import handle_compliance; print('OK')"`

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/mcp/server/handlers/compliance_handler.py src/dazzle/mcp/server/handlers_consolidated.py src/dazzle/mcp/server/tools_consolidated.py
git commit -m "feat(compliance): rewrite MCP handler and register in consolidated dispatch"
```

---

### Task 8: Rewrite CLI and wire in registration

**Files:**
- Rewrite: `src/dazzle/cli/compliance.py`
- Modify: `src/dazzle/cli/__init__.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Rewrite compliance.py with Rich console**

```python
"""Dazzle compliance documentation CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console

compliance_app = typer.Typer(
    help="Compliance documentation tools",
    no_args_is_help=True,
)

console = Console()


@compliance_app.command(name="compile")
def compile_cmd(
    framework: str = typer.Option("iso27001", "--framework", "-f", help="Framework ID"),
    output: str = typer.Option("", "--output", "-o", help="Output path for auditspec JSON"),
) -> None:
    """Compile compliance audit spec from DSL evidence."""
    from dazzle.compliance.coordinator import compile_full_pipeline

    project_root = Path.cwd().resolve()
    auditspec = compile_full_pipeline(project_root, framework=framework)
    s = auditspec.summary

    # Write outputs
    out_dir = project_root / ".dazzle" / "compliance" / "output" / framework
    out_dir.mkdir(parents=True, exist_ok=True)
    auditspec_path = out_dir / "auditspec.json"
    auditspec_path.write_text(json.dumps(auditspec.model_dump(), indent=2))

    if output:
        Path(output).write_text(json.dumps(auditspec.model_dump(), indent=2))

    # Display summary
    console.print(f"\n[bold]Compliance: {auditspec.framework_name}[/bold]")
    console.print(f"  Controls: {s.total_controls}")
    console.print(f"  Evidenced: {s.evidenced}")
    console.print(f"  Partial: {s.partial}")
    console.print(f"  Gaps: {s.gaps}")
    console.print(f"  Excluded: {s.excluded}")
    if s.total_controls > 0:
        coverage = (s.evidenced + s.partial) / s.total_controls * 100
        console.print(f"  Coverage: {coverage:.1f}%")
    console.print(f"\n  Output: {auditspec_path}")


@compliance_app.command(name="evidence")
def evidence_cmd(
    framework: str = typer.Option("iso27001", "--framework", "-f", help="Framework ID"),
) -> None:
    """Show DSL evidence extracted from the current project."""
    from dazzle.compliance.evidence import extract_evidence_from_project

    project_root = Path.cwd().resolve()
    evidence = extract_evidence_from_project(project_root)

    console.print("\n[bold]DSL Evidence[/bold]")
    for construct, items in sorted(evidence.items.items()):
        if items:
            console.print(f"  [green]{construct}[/green]: {len(items)} items")
        else:
            console.print(f"  [dim]{construct}[/dim]: 0 items")


@compliance_app.command(name="gaps")
def gaps_cmd(
    framework: str = typer.Option("iso27001", "--framework", "-f", help="Framework ID"),
    tier: str = typer.Option("2,3", "--tier", help="Tiers to show (comma-separated)"),
) -> None:
    """Show compliance gaps and partial controls."""
    from dazzle.compliance.coordinator import compile_full_pipeline

    project_root = Path.cwd().resolve()
    auditspec = compile_full_pipeline(project_root, framework=framework)

    tiers = {int(t.strip()) for t in tier.split(",")}
    gaps = [c for c in auditspec.controls if c.tier in tiers]

    if not gaps:
        console.print("[green]No gaps found for selected tiers.[/green]")
        return

    console.print(f"\n[bold]Compliance Gaps ({len(gaps)} controls)[/bold]")
    for g in gaps:
        status_color = "yellow" if g.status == "partial" else "red"
        console.print(f"  [{status_color}]{g.control_id}[/{status_color}] {g.control_name} (tier {g.tier})")
        if g.gap_description:
            console.print(f"    {g.gap_description}")
```

- [ ] **Step 2: Register in cli/__init__.py**

Add import and registration:

```python
from dazzle.cli.compliance import compliance_app
# ... in the add_typer block:
app.add_typer(compliance_app, name="compliance")
```

- [ ] **Step 3: Add [compliance] extra to pyproject.toml**

Add optional extra and package-data for CSS/templates/frameworks.

- [ ] **Step 4: Verify CLI registration**

Run: `dazzle compliance --help`

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/cli/compliance.py src/dazzle/cli/__init__.py pyproject.toml
git commit -m "feat(compliance): rewrite CLI with Rich console, register in CLI and pyproject.toml"
```

---

### Task 9: Final verification and CHANGELOG

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Run full test suite**

Run: `pytest tests/ -m "not e2e" -x --timeout=120 -q`
Expected: All pass (count should be ~9,349 + new tests)

- [ ] **Step 2: Run lint**

Run: `ruff check src/dazzle/compliance/ tests/unit/test_compliance_*.py --fix && ruff format src/dazzle/compliance/ tests/unit/test_compliance_*.py`

- [ ] **Step 3: Run mypy**

Run: `mypy src/dazzle/compliance/ --ignore-missing-imports`
Expected: 0 errors

- [ ] **Step 4: Add CHANGELOG entry**

Add under `## [Unreleased]`:

```markdown
### Added
- Compliance documentation compiler: maps DSL metadata to framework controls
- `dazzle compliance compile` / `evidence` / `gaps` CLI commands
- MCP `compliance` tool with 5 operations (compile, evidence, gaps, summary, review)
- Safe cast registry for ISO 27001:2022 (93 controls, 4 themes)
- Pydantic models for Taxonomy, EvidenceMap, AuditSpec IR
- `[compliance]` optional extra in pyproject.toml
```

- [ ] **Step 5: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: CHANGELOG for compliance compiler"
```
