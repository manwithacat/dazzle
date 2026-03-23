# Compliance Compiler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a pipeline that generates ISO 27001:2022 compliance documentation from AegisMark's Dazzle DSL, producing a customer-facing statement and a formal audit pack as branded PDFs.

**Architecture:** Framework taxonomy (YAML) defines ISO 27001 controls with DSL evidence mappings. A Python compiler walks the DSL (via MCP tools) and produces an AuditSpec IR (JSON). Per-document AI agents expand the IR into markdown. WeasyPrint renders branded PDFs via CSS driven by brandspec.yaml.

**Tech Stack:** Python 3.12, PyYAML, WeasyPrint, Dazzle MCP tools (dsl/policy/conformance), Claude Code Agent tool for AI expansion.

**Spec:** `docs/superpowers/specs/2026-03-23-compliance-compiler-design.md`

---

## File Structure

### New files

```
pipeline/compliance/
├── __init__.py                    # Package init, version
├── taxonomy.py                    # Load & validate framework taxonomy YAML
├── evidence.py                    # Extract DSL evidence via MCP tools
├── compiler.py                    # AuditSpec compiler (taxonomy + evidence → IR)
├── slicer.py                      # Slice AuditSpec/DSL by document/section
├── citation.py                    # Deterministic citation validation
├── renderer.py                    # Markdown → branded PDF via WeasyPrint
├── css/
│   └── compliance.css             # Print stylesheet for compliance documents
└── templates/
    └── document.html              # Jinja2 HTML wrapper for WeasyPrint

.dazzle/compliance/
├── frameworks/
│   └── iso27001.yaml              # ISO 27001:2022 Annex A taxonomy (93 controls)
├── documents/
│   ├── iso27001-audit-pack.yaml   # Formal audit document spec
│   └── iso27001-customer-statement.yaml  # Customer-facing document spec
└── templates/
    ├── risk_assessment_methodology.md
    ├── security_commitment.md
    └── access_control_principles.md

brandspec.yaml                     # Brand identity pack (root level)
```

### Modified files

```
.gitignore                         # Add .dazzle/compliance/output/*/pdf/
requirements.txt                   # Add pyyaml (if not present), jinja2
```

---

## Task 1: Framework Taxonomy Loader

**Files:**
- Create: `pipeline/compliance/__init__.py`
- Create: `pipeline/compliance/taxonomy.py`
- Create: `.dazzle/compliance/frameworks/iso27001.yaml`
- Test: `tests/compliance/test_taxonomy.py`

This task builds the data layer: the YAML schema for compliance frameworks and a loader that validates and returns structured data.

- [ ] **Step 1: Create package init**

```python
# pipeline/compliance/__init__.py
"""AegisMark Compliance Compiler — generates audit documentation from DSL."""
```

- [ ] **Step 2: Write failing test for taxonomy loader**

```python
# tests/compliance/test_taxonomy.py
import pytest
from pathlib import Path

from pipeline.compliance.taxonomy import load_taxonomy, TaxonomyError


FIXTURES = Path(__file__).parent / "fixtures"


def test_load_valid_taxonomy():
    taxonomy = load_taxonomy(FIXTURES / "mini_taxonomy.yaml")
    assert taxonomy.id == "iso27001"
    assert taxonomy.name == "ISO/IEC 27001:2022"
    assert len(taxonomy.themes) == 1
    assert len(taxonomy.themes[0].controls) == 2


def test_control_has_dsl_evidence():
    taxonomy = load_taxonomy(FIXTURES / "mini_taxonomy.yaml")
    ctrl = taxonomy.themes[0].controls[0]
    assert ctrl.id == "A.5.1"
    assert len(ctrl.dsl_evidence) == 2
    assert ctrl.dsl_evidence[0].construct == "classify"


def test_control_with_no_evidence():
    taxonomy = load_taxonomy(FIXTURES / "mini_taxonomy.yaml")
    ctrl = taxonomy.themes[0].controls[1]
    assert ctrl.id == "A.7.4"
    assert ctrl.dsl_evidence == []


def test_all_controls_flat():
    taxonomy = load_taxonomy(FIXTURES / "mini_taxonomy.yaml")
    all_ctrls = taxonomy.all_controls()
    assert len(all_ctrls) == 2
    assert all_ctrls[0].id == "A.5.1"


def test_missing_file_raises():
    with pytest.raises(TaxonomyError):
        load_taxonomy(Path("/nonexistent.yaml"))


def test_invalid_yaml_raises():
    with pytest.raises(TaxonomyError):
        load_taxonomy(FIXTURES / "bad_taxonomy.yaml")
```

- [ ] **Step 3: Create test fixtures**

```yaml
# tests/compliance/fixtures/mini_taxonomy.yaml
framework:
  id: iso27001
  name: "ISO/IEC 27001:2022"
  jurisdiction: international
  body: "International Organization for Standardization"
  version: "2022"
  themes:
    - id: organisational
      name: "Organisational Controls"
      controls:
        - id: "A.5.1"
          name: "Policies for information security"
          objective: "Provide management direction"
          attributes:
            control_type: [preventive]
            security_concepts: [identify]
            operational_capabilities: [governance]
          dsl_evidence:
            - construct: classify
              description: "Data classification directives"
            - construct: permit
              description: "Role-based access rules"
        - id: "A.7.4"
          name: "Physical security monitoring"
          objective: "Monitor physical access"
          dsl_evidence: []
```

```yaml
# tests/compliance/fixtures/bad_taxonomy.yaml
not_a_framework: true
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `python3 -m pytest tests/compliance/test_taxonomy.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.compliance.taxonomy'`

- [ ] **Step 5: Implement taxonomy loader**

```python
# pipeline/compliance/taxonomy.py
"""Load and validate compliance framework taxonomy YAML files."""
from __future__ import annotations

import yaml
from dataclasses import dataclass, field
from pathlib import Path


class TaxonomyError(Exception):
    """Raised when a taxonomy file is missing, malformed, or invalid."""


@dataclass
class DslEvidence:
    construct: str
    description: str


@dataclass
class Control:
    id: str
    name: str
    objective: str
    attributes: dict = field(default_factory=dict)
    dsl_evidence: list[DslEvidence] = field(default_factory=list)


@dataclass
class Theme:
    id: str
    name: str
    controls: list[Control] = field(default_factory=list)


@dataclass
class Taxonomy:
    id: str
    name: str
    jurisdiction: str
    body: str
    version: str
    themes: list[Theme] = field(default_factory=list)

    def all_controls(self) -> list[Control]:
        """Return flat list of all controls across all themes."""
        return [c for t in self.themes for c in t.controls]

    def controls_by_id(self) -> dict[str, Control]:
        """Return dict mapping control ID to Control."""
        return {c.id: c for c in self.all_controls()}


def load_taxonomy(path: Path) -> Taxonomy:
    """Load a framework taxonomy from a YAML file.

    Args:
        path: Path to the taxonomy YAML file.

    Returns:
        Parsed Taxonomy dataclass.

    Raises:
        TaxonomyError: If the file is missing, malformed, or invalid.
    """
    if not path.exists():
        raise TaxonomyError(f"Taxonomy file not found: {path}")

    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        raise TaxonomyError(f"Invalid YAML in {path}: {e}") from e

    if not isinstance(raw, dict) or "framework" not in raw:
        raise TaxonomyError(f"Missing 'framework' key in {path}")

    fw = raw["framework"]
    themes = []
    for t in fw.get("themes", []):
        controls = []
        for c in t.get("controls", []):
            evidence = [
                DslEvidence(construct=e["construct"], description=e["description"])
                for e in c.get("dsl_evidence", [])
            ]
            controls.append(Control(
                id=c["id"],
                name=c["name"],
                objective=c.get("objective", ""),
                attributes=c.get("attributes", {}),
                dsl_evidence=evidence,
            ))
        themes.append(Theme(id=t["id"], name=t["name"], controls=controls))

    return Taxonomy(
        id=fw["id"],
        name=fw["name"],
        jurisdiction=fw.get("jurisdiction", ""),
        body=fw.get("body", ""),
        version=fw.get("version", ""),
        themes=themes,
    )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python3 -m pytest tests/compliance/test_taxonomy.py -v`
Expected: All 6 tests PASS

- [ ] **Step 7: Commit**

```bash
git add pipeline/compliance/__init__.py pipeline/compliance/taxonomy.py tests/compliance/
git commit -m "feat(compliance): add framework taxonomy loader with dataclasses and YAML validation"
```

---

## Task 2: ISO 27001:2022 Full Taxonomy

**Files:**
- Create: `.dazzle/compliance/frameworks/iso27001.yaml`

This is the reference data — all 93 Annex A controls from ISO 27001:2022, with DSL evidence mappings for each. This is a content-heavy task requiring ISO domain knowledge.

- [ ] **Step 1: Write failing test that validates the full taxonomy**

```python
# tests/compliance/test_iso27001_taxonomy.py
import pytest
from pathlib import Path

from pipeline.compliance.taxonomy import load_taxonomy

ISO_PATH = Path(__file__).parents[2] / ".dazzle" / "compliance" / "frameworks" / "iso27001.yaml"


@pytest.fixture
def taxonomy():
    return load_taxonomy(ISO_PATH)


def test_file_exists():
    assert ISO_PATH.exists(), f"ISO 27001 taxonomy not found at {ISO_PATH}"


def test_total_controls(taxonomy):
    assert len(taxonomy.all_controls()) == 93


def test_four_themes(taxonomy):
    theme_ids = [t.id for t in taxonomy.themes]
    assert theme_ids == ["organisational", "people", "physical", "technological"]


def test_theme_control_counts(taxonomy):
    counts = {t.id: len(t.controls) for t in taxonomy.themes}
    assert counts == {
        "organisational": 37,
        "people": 8,
        "physical": 14,
        "technological": 34,
    }


def test_all_controls_have_ids(taxonomy):
    for ctrl in taxonomy.all_controls():
        assert ctrl.id.startswith("A."), f"Control {ctrl.id} missing A. prefix"
        assert ctrl.name, f"Control {ctrl.id} has no name"
        assert ctrl.objective, f"Control {ctrl.id} has no objective"


def test_evidence_constructs_are_valid(taxonomy):
    valid = {
        "classify", "permit", "scope", "visible", "transitions",
        "processes", "stories", "grant_schema", "persona", "workspace",
        "llm_config", "archetype", "scenarios",
    }
    for ctrl in taxonomy.all_controls():
        for ev in ctrl.dsl_evidence:
            assert ev.construct in valid, (
                f"Control {ctrl.id} has unknown construct '{ev.construct}'"
            )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/compliance/test_iso27001_taxonomy.py -v`
Expected: FAIL — file not found or wrong control count

- [ ] **Step 3: Author the full ISO 27001:2022 taxonomy**

Create `.dazzle/compliance/frameworks/iso27001.yaml` with all 93 Annex A controls across 4 themes. Use an AI agent for this — dispatch with ISO 27001:2022 domain knowledge and the DSL construct vocabulary from the spec (Section 3). The agent should:
- Include every Annex A control from A.5.1 through A.8.34
- Map each control to relevant DSL constructs where applicable
- Leave `dsl_evidence: []` for controls with no DSL representation (physical security, HR screening, etc.)
- Include `attributes` with control_type, security_concepts, operational_capabilities

This is best done by dispatching an AI agent with web search access to retrieve the full ISO 27001:2022 Annex A control list and cross-referencing against AegisMark's DSL constructs.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/compliance/test_iso27001_taxonomy.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add .dazzle/compliance/frameworks/iso27001.yaml tests/compliance/test_iso27001_taxonomy.py
git commit -m "feat(compliance): add complete ISO 27001:2022 Annex A taxonomy (93 controls, 4 themes)"
```

---

## Task 3: DSL Evidence Extractor

**Files:**
- Create: `pipeline/compliance/evidence.py`
- Test: `tests/compliance/test_evidence.py`

This module extracts evidence from the DSL using two strategies:
1. **Dazzle MCP/CLI** for permit evidence (uses `python3 -m dazzle` which has a proper parser)
2. **Targeted regex** only for simple, unambiguous patterns (classify directives in the policies block, visible directives)
3. **JSON file parsing** for processes and stories (structured data, no regex needed)
4. **DSL persona/scope blocks** via Dazzle's `inspect_entity` output

The key principle: **never regex-parse entity blocks** — the DSL has entity, persona, workspace, scenario, rhythm, archetype, surface, and policies blocks at the top level, and a naive `entity.*?(?=entity|\Z)` regex will consume non-entity blocks. Use Dazzle's own parser via CLI for anything inside entity blocks.

- [ ] **Step 1: Write failing test for evidence extraction**

```python
# tests/compliance/test_evidence.py
import json
import pytest
from pathlib import Path

from pipeline.compliance.evidence import (
    extract_classify_evidence,
    extract_permit_evidence,
    extract_scope_evidence,
    extract_process_evidence,
    extract_story_evidence,
    extract_transition_evidence,
    extract_visible_evidence,
    extract_persona_evidence,
    extract_all_evidence,
)

PROJECT_PATH = Path("/Volumes/SSD/AegisMark")


def test_classify_evidence_structure():
    """Test that classify evidence returns structured data."""
    evidence = extract_classify_evidence(PROJECT_PATH)
    assert isinstance(evidence, list)
    assert len(evidence) > 100  # We know there are 112
    first = evidence[0]
    assert "entity" in first
    assert "field" in first
    assert "classification" in first


def test_classify_evidence_categories():
    """Known categories from the DSL."""
    evidence = extract_classify_evidence(PROJECT_PATH)
    categories = {e["classification"] for e in evidence}
    assert "PII_DIRECT" in categories
    assert "HEALTH_DATA" in categories


def test_permit_evidence_structure():
    """Test that permit evidence returns per-entity operation breakdown."""
    evidence = extract_permit_evidence(PROJECT_PATH)
    assert isinstance(evidence, dict)
    assert "MarkingResult" in evidence
    mr = evidence["MarkingResult"]
    assert "operations" in mr
    assert "read" in mr["operations"]
    assert isinstance(mr["operations"]["read"], list)


def test_permit_evidence_count():
    """Should have entries for most entities (53 have permit blocks)."""
    evidence = extract_permit_evidence(PROJECT_PATH)
    assert len(evidence) >= 40  # At least 40 entities with permit blocks


def test_scope_evidence_structure():
    """Test that scope evidence returns entity-level scope rules."""
    evidence = extract_scope_evidence(PROJECT_PATH)
    assert isinstance(evidence, list)
    assert len(evidence) >= 40  # 53 entities have scope blocks


def test_process_evidence_structure():
    """Test that process evidence returns process metadata."""
    evidence = extract_process_evidence(PROJECT_PATH)
    assert isinstance(evidence, list)
    assert len(evidence) >= 40  # 49 processes
    first = evidence[0]
    assert "name" in first
    assert "file" in first
    assert "steps" in first


def test_story_evidence_structure():
    """Test that story evidence returns story metadata."""
    evidence = extract_story_evidence(PROJECT_PATH)
    assert isinstance(evidence, list)
    assert len(evidence) >= 40  # 62 stories
    first = evidence[0]
    assert "story_id" in first or "id" in first
    assert "title" in first


def test_transition_evidence_structure():
    """Test that transition evidence returns guard data."""
    evidence = extract_transition_evidence(PROJECT_PATH)
    assert isinstance(evidence, list)
    assert len(evidence) >= 50  # 88 transition guards
    first = evidence[0]
    assert "entity" in first
    assert "from_state" in first
    assert "to_state" in first
    assert "roles" in first


def test_visible_evidence_structure():
    """Test that visible evidence returns visibility restrictions."""
    evidence = extract_visible_evidence(PROJECT_PATH)
    assert isinstance(evidence, list)
    assert len(evidence) >= 15  # 20+ visible directives


def test_persona_evidence_structure():
    """Test that persona evidence returns persona metadata."""
    evidence = extract_persona_evidence(PROJECT_PATH)
    assert isinstance(evidence, list)
    assert len(evidence) >= 8  # 9 personas


def test_extract_all_returns_all_construct_types():
    """Test that extract_all returns all construct types."""
    evidence = extract_all_evidence(PROJECT_PATH)
    expected_keys = {
        "classify", "permit", "scope", "transitions",
        "visible", "processes", "stories", "personas",
    }
    assert expected_keys.issubset(set(evidence.keys()))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/compliance/test_evidence.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement evidence extractor**

```python
# pipeline/compliance/evidence.py
"""Extract compliance evidence from the Dazzle DSL.

Uses Dazzle CLI (python3 -m dazzle) for entity-level data (permit, scope,
transitions) to avoid fragile regex parsing of entity blocks. Uses targeted
regex only for simple top-level patterns (classify directives). Uses JSON
parsing for structured data (processes, stories).
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


def _run_dazzle_cli(project_path: Path, *args: str) -> dict | list | None:
    """Run a dazzle CLI command and return parsed JSON output."""
    cmd = ["python3", "-m", "dazzle", *args, "--format", "json"]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
            cwd=str(project_path),
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        pass
    return None


def _get_entity_names(project_path: Path) -> list[str]:
    """Get all entity names from the DSL via dazzle CLI or regex fallback."""
    dsl_path = project_path / "dsl" / "app.dsl"
    text = dsl_path.read_text()
    # Entity declarations are unambiguous: 'entity Name "Title"' at line start
    return re.findall(r'^entity\s+(\w+)\s+"', text, re.MULTILINE)


def extract_classify_evidence(project_path: Path) -> list[dict]:
    """Extract all classify directives from the DSL policies block.

    Safe to regex: classify directives are simple, unambiguous, and live in the
    policies: block (not inside entity blocks).

    Returns list of {entity, field, classification} dicts.
    """
    dsl_path = project_path / "dsl" / "app.dsl"
    text = dsl_path.read_text()

    return [
        {
            "entity": m.group(1),
            "field": m.group(2),
            "classification": m.group(3),
        }
        for m in re.finditer(r"classify\s+(\w+)\.(\w+)\s+as\s+(\w+)", text)
    ]


def extract_permit_evidence(project_path: Path) -> dict[str, dict]:
    """Extract permit blocks using Dazzle's policy coverage MCP/CLI.

    Uses `python3 -m dazzle policy coverage` which returns the full RBAC matrix
    parsed from Dazzle's own AST — no regex needed.

    Falls back to regex if CLI unavailable.

    Returns dict of {EntityName: {operations: {read: [roles], ...}}}.
    """
    # Try Dazzle CLI first (uses proper parser)
    cli_result = _run_dazzle_cli(project_path, "policy", "coverage")
    if cli_result and "matrix" in cli_result:
        results = {}
        for entity_name, persona_ops in cli_result["matrix"].items():
            operations: dict[str, list[str]] = {}
            for persona, ops in persona_ops.items():
                for op, status in ops.items():
                    if status == "allow":
                        operations.setdefault(op, []).append(persona)
            if operations:
                results[entity_name] = {"operations": operations}
        return results

    # Fallback: parse permit blocks from DSL using per-entity regex
    return _extract_permit_via_regex(project_path)


def _extract_permit_via_regex(project_path: Path) -> dict[str, dict]:
    """Fallback permit extraction using regex on the DSL.

    Uses per-entity `inspect_entity` blocks rather than greedy entity regex.
    """
    dsl_path = project_path / "dsl" / "app.dsl"
    text = dsl_path.read_text()

    results = {}
    role_pattern = re.compile(r"role\((\w+)\)")

    # Find each entity's permit block by looking for 'permit:' after entity declaration
    # Use entity names to anchor, not greedy entity blocks
    entity_names = _get_entity_names(project_path)

    for i, name in enumerate(entity_names):
        # Find this entity's start
        entity_start = text.find(f'entity {name} "')
        if entity_start == -1:
            continue

        # Find next entity's start (or end of file)
        if i + 1 < len(entity_names):
            next_start = text.find(f'entity {entity_names[i + 1]} "', entity_start + 1)
        else:
            # Last entity: stop at next top-level keyword
            next_start = len(text)
            for keyword in ["persona ", "workspace ", "scenario ", "rhythm ", "policies:", "archetype "]:
                pos = text.find(f"\n{keyword}", entity_start + 1)
                if pos != -1:
                    next_start = min(next_start, pos)

        entity_text = text[entity_start:next_start]

        permit_start = entity_text.find("permit:")
        if permit_start == -1:
            continue

        # Find the end of the permit block (next sibling block keyword)
        permit_text = entity_text[permit_start:]
        scope_pos = permit_text.find("\n  scope:")
        if scope_pos != -1:
            permit_text = permit_text[:scope_pos]

        operations = {}
        for m in re.finditer(r"(read|write|list|create|delete):\s*(.+)", permit_text):
            roles = role_pattern.findall(m.group(2))
            if roles:
                operations[m.group(1)] = roles

        if operations:
            results[name] = {"operations": operations}

    return results


def extract_scope_evidence(project_path: Path) -> list[dict]:
    """Extract scope blocks from the DSL.

    Scope blocks define row-level filtering rules (separate from permit).
    Uses anchored entity search, not greedy regex.

    Returns list of {entity, rules} dicts.
    """
    dsl_path = project_path / "dsl" / "app.dsl"
    text = dsl_path.read_text()

    results = []
    entity_names = _get_entity_names(project_path)

    for i, name in enumerate(entity_names):
        entity_start = text.find(f'entity {name} "')
        if entity_start == -1:
            continue

        # Find entity boundary
        if i + 1 < len(entity_names):
            next_start = text.find(f'entity {entity_names[i + 1]} "', entity_start + 1)
        else:
            next_start = len(text)
            for keyword in ["persona ", "workspace ", "scenario ", "rhythm ", "policies:", "archetype "]:
                pos = text.find(f"\n{keyword}", entity_start + 1)
                if pos != -1:
                    next_start = min(next_start, pos)

        entity_text = text[entity_start:next_start]

        scope_start = entity_text.find("scope:")
        if scope_start == -1:
            continue

        # Extract scope rules (lines after scope: that are indented)
        scope_text = entity_text[scope_start:]
        rules = []
        for line in scope_text.split("\n")[1:]:  # Skip "scope:" line
            stripped = line.strip()
            if not stripped or not line.startswith("    "):
                break
            rules.append(stripped)

        if rules:
            results.append({"entity": name, "rules": rules})

    return results


def extract_transition_evidence(project_path: Path) -> list[dict]:
    """Extract state machine transition guards from the DSL.

    Uses anchored entity search for correct block boundaries.

    Returns list of {entity, from_state, to_state, roles} dicts.
    """
    dsl_path = project_path / "dsl" / "app.dsl"
    text = dsl_path.read_text()

    results = []
    role_pattern = re.compile(r"role\((\w+)\)")
    transition_pattern = re.compile(r"(\w+)\s*->\s*(\w+):\s*(.+)")
    entity_names = _get_entity_names(project_path)

    for i, name in enumerate(entity_names):
        entity_start = text.find(f'entity {name} "')
        if entity_start == -1:
            continue

        if i + 1 < len(entity_names):
            next_start = text.find(f'entity {entity_names[i + 1]} "', entity_start + 1)
        else:
            next_start = len(text)
            for keyword in ["persona ", "workspace ", "scenario ", "rhythm ", "policies:", "archetype "]:
                pos = text.find(f"\n{keyword}", entity_start + 1)
                if pos != -1:
                    next_start = min(next_start, pos)

        entity_text = text[entity_start:next_start]

        transitions_start = entity_text.find("transitions:")
        if transitions_start == -1:
            continue

        # Only search within the transitions block
        trans_text = entity_text[transitions_start:]
        # Stop at next sibling keyword
        for keyword in ["\n  permit:", "\n  scope:", "\n  access:"]:
            pos = trans_text.find(keyword)
            if pos != -1:
                trans_text = trans_text[:pos]

        for t_match in transition_pattern.finditer(trans_text):
            roles = role_pattern.findall(t_match.group(3))
            if roles:
                results.append({
                    "entity": name,
                    "from_state": t_match.group(1),
                    "to_state": t_match.group(2),
                    "roles": roles,
                })

    return results


def extract_visible_evidence(project_path: Path) -> list[dict]:
    """Extract visible: directives from the DSL.

    Captures surrounding context (surface or field name) for richer evidence.

    Returns list of {context, condition, roles} dicts.
    """
    dsl_path = project_path / "dsl" / "app.dsl"
    lines = dsl_path.read_text().split("\n")

    results = []
    role_pattern = re.compile(r"role\((\w+)\)")

    for i, line in enumerate(lines):
        if "visible:" not in line:
            continue

        condition = line.split("visible:")[1].strip()
        roles = role_pattern.findall(condition)
        if not roles:
            continue

        # Look backwards for context (field name or section/surface)
        context = ""
        for j in range(i - 1, max(i - 5, 0), -1):
            prev = lines[j].strip()
            if prev.startswith("field ") or prev.startswith("section ") or prev.startswith("surface "):
                context = prev.split('"')[0].strip() if '"' in prev else prev
                break

        results.append({
            "context": context,
            "condition": condition,
            "roles": roles,
            "line": i + 1,
        })

    return results


def extract_persona_evidence(project_path: Path) -> list[dict]:
    """Extract persona definitions from the DSL.

    Personas are top-level blocks, safe to regex with proper boundaries.

    Returns list of persona metadata dicts.
    """
    dsl_path = project_path / "dsl" / "app.dsl"
    text = dsl_path.read_text()

    results = []
    # Personas are top-level: 'persona id "Name":'
    persona_pattern = re.compile(
        r'^persona\s+(\w+)\s+"([^"]*)".*?(?=\npersona\s|\nscenario\s|\nworkspace\s|\Z)',
        re.DOTALL | re.MULTILINE,
    )

    for match in persona_pattern.finditer(text):
        block = match.group(0)
        ws_match = re.search(r"default_workspace:\s*(\w+)", block)
        prof_match = re.search(r"proficiency:\s*(\w+)", block)

        results.append({
            "id": match.group(1),
            "name": match.group(2),
            "default_workspace": ws_match.group(1) if ws_match else None,
            "proficiency": prof_match.group(1) if prof_match else None,
        })

    return results


def extract_process_evidence(project_path: Path) -> list[dict]:
    """Extract process definitions from .dazzle/processes/ JSON files.

    Returns list of process metadata dicts.
    """
    processes_dir = project_path / ".dazzle" / "processes"
    results = []

    if not processes_dir.exists():
        return results

    for json_file in sorted(processes_dir.glob("*.json")):
        data = json.loads(json_file.read_text())
        if isinstance(data, list):
            processes = data
        elif isinstance(data, dict) and "processes" in data:
            processes = data["processes"]
        else:
            continue

        for proc in processes:
            results.append({
                "name": proc.get("name", ""),
                "title": proc.get("title", ""),
                "file": str(json_file.relative_to(project_path)),
                "steps": len(proc.get("steps", [])),
                "timeout_seconds": proc.get("timeout_seconds"),
                "has_approval_gate": any(
                    s.get("type") == "human_task"
                    for s in proc.get("steps", [])
                ),
            })

    return results


def extract_story_evidence(project_path: Path) -> list[dict]:
    """Extract user stories from .dazzle/stories/stories.json.

    Returns list of story metadata dicts.
    """
    stories_path = project_path / ".dazzle" / "stories" / "stories.json"
    if not stories_path.exists():
        return []

    data = json.loads(stories_path.read_text())
    stories = data if isinstance(data, list) else data.get("stories", [])

    return [
        {
            "story_id": s.get("story_id", s.get("id", "")),
            "title": s.get("title", s.get("description", "")),
            "persona": s.get("persona", ""),
            "criteria_count": len(s.get("acceptance_criteria", s.get("criteria", []))),
        }
        for s in stories
    ]


def extract_all_evidence(project_path: Path) -> dict[str, list | dict]:
    """Extract all DSL evidence types.

    Returns dict keyed by construct type.
    """
    return {
        "classify": extract_classify_evidence(project_path),
        "permit": extract_permit_evidence(project_path),
        "scope": extract_scope_evidence(project_path),
        "transitions": extract_transition_evidence(project_path),
        "visible": extract_visible_evidence(project_path),
        "processes": extract_process_evidence(project_path),
        "stories": extract_story_evidence(project_path),
        "personas": extract_persona_evidence(project_path),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/compliance/test_evidence.py -v`
Expected: All 12 tests PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/compliance/evidence.py tests/compliance/test_evidence.py
git commit -m "feat(compliance): add DSL evidence extractor (MCP-first with anchored regex fallback)"
```

---

## Task 4: AuditSpec Compiler

**Files:**
- Create: `pipeline/compliance/compiler.py`
- Test: `tests/compliance/test_compiler.py`

The compiler combines the taxonomy and DSL evidence to produce the AuditSpec IR.

- [ ] **Step 1: Write failing test for compiler**

```python
# tests/compliance/test_compiler.py
import json
import pytest
from pathlib import Path
from unittest.mock import patch

from pipeline.compliance.taxonomy import load_taxonomy
from pipeline.compliance.compiler import compile_auditspec


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def mini_taxonomy():
    return load_taxonomy(FIXTURES / "mini_taxonomy.yaml")


@pytest.fixture
def mock_evidence():
    return {
        "classify": [
            {"entity": "User", "field": "email", "classification": "PII_DIRECT"},
            {"entity": "StudentProfile", "field": "dob", "classification": "PII_DIRECT"},
        ],
        "permit": {
            "MarkingResult": {
                "operations": {
                    "read": ["teacher", "school_admin"],
                    "write": ["teacher"],
                }
            }
        },
        "transitions": [],
        "visible": [],
        "processes": [],
        "stories": [],
        "personas": [],
    }


def test_compile_produces_valid_structure(mini_taxonomy, mock_evidence):
    spec = compile_auditspec(mini_taxonomy, mock_evidence, "dsl/app.dsl")
    assert spec["auditspec_version"] == "1.0"
    assert spec["framework"] == "iso27001"
    assert "summary" in spec
    assert "controls" in spec


def test_evidenced_control(mini_taxonomy, mock_evidence):
    spec = compile_auditspec(mini_taxonomy, mock_evidence, "dsl/app.dsl")
    ctrl = next(c for c in spec["controls"] if c["id"] == "A.5.1")
    assert ctrl["status"] == "evidenced"
    assert len(ctrl["evidence"]) > 0
    assert ctrl["gaps"] == []


def test_gap_control(mini_taxonomy, mock_evidence):
    spec = compile_auditspec(mini_taxonomy, mock_evidence, "dsl/app.dsl")
    ctrl = next(c for c in spec["controls"] if c["id"] == "A.7.4")
    assert ctrl["status"] == "gap"
    assert ctrl["evidence"] == []
    assert len(ctrl["gaps"]) > 0
    assert ctrl["gaps"][0]["tier"] == 3


def test_summary_counts(mini_taxonomy, mock_evidence):
    spec = compile_auditspec(mini_taxonomy, mock_evidence, "dsl/app.dsl")
    s = spec["summary"]
    assert s["total_controls"] == 2
    assert s["evidenced"] + s["partial"] + s["gaps"] == 2


def test_dsl_hash_present(mini_taxonomy, mock_evidence):
    spec = compile_auditspec(mini_taxonomy, mock_evidence, "dsl/app.dsl")
    assert "dsl_hash" in spec
    assert spec["dsl_hash"].startswith("sha256:")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/compliance/test_compiler.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement compiler**

```python
# pipeline/compliance/compiler.py
"""AuditSpec compiler — combines taxonomy + DSL evidence into the IR."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from pipeline.compliance.taxonomy import Taxonomy, Control


# Map taxonomy construct names to evidence dict keys
CONSTRUCT_TO_KEY = {
    "classify": "classify",
    "permit": "permit",
    "scope": "scope",
    "visible": "visible",
    "transitions": "transitions",
    "processes": "processes",
    "stories": "stories",
    "grant_schema": "permit",  # grant_schema is part of access control evidence
    "persona": "personas",
    "workspace": "personas",  # workspace info is bundled with personas
    "llm_config": "classify",  # llm logging is part of data handling evidence
    "archetype": "classify",  # audit trails are part of data classification evidence
    "scenarios": "stories",  # scenarios are bundled with stories evidence
}


def _build_evidence_for_control(
    control: Control, all_evidence: dict
) -> tuple[list[dict], list[dict]]:
    """Build evidence and gap entries for a single control."""
    evidence = []
    gaps = []

    if not control.dsl_evidence:
        gaps.append({
            "description": f"No DSL construct addresses '{control.name}' — requires organisational policy",
            "tier": 3,
            "action": f"Document policy for: {control.name}",
        })
        return evidence, gaps

    for mapping in control.dsl_evidence:
        key = CONSTRUCT_TO_KEY.get(mapping.construct, mapping.construct)
        data = all_evidence.get(key)

        if data and (isinstance(data, list) and len(data) > 0 or isinstance(data, dict) and len(data) > 0):
            entry = {
                "construct": mapping.construct,
                "type": mapping.description,
                "summary": f"DSL {mapping.construct} evidence found",
            }

            if isinstance(data, list):
                entry["count"] = len(data)
                entry["refs"] = data[:5]  # First 5 as sample
            elif isinstance(data, dict):
                entry["count"] = len(data)
                entry["refs"] = [
                    {"entity": k, **v} for k, v in list(data.items())[:5]
                ]

            evidence.append(entry)
        else:
            gaps.append({
                "description": f"No {mapping.construct} evidence found: {mapping.description}",
                "tier": 2,
                "action": f"Add {mapping.construct} constructs or document manually",
            })

    return evidence, gaps


def _compute_status(evidence: list[dict], gaps: list[dict]) -> str:
    """Compute control status from evidence and gaps."""
    if not evidence and gaps:
        return "gap"
    if evidence and not gaps:
        return "evidenced"
    return "partial"


def compile_auditspec(
    taxonomy: Taxonomy,
    evidence: dict,
    dsl_source: str,
    dsl_content: str | None = None,
) -> dict:
    """Compile an AuditSpec from taxonomy and evidence.

    Args:
        taxonomy: Parsed framework taxonomy.
        evidence: Dict of all DSL evidence keyed by construct type.
        dsl_source: Path to the DSL source file (for metadata).
        dsl_content: Optional DSL file content for hashing. If None, reads from dsl_source.

    Returns:
        AuditSpec dict ready for JSON serialisation.
    """
    if dsl_content is None:
        dsl_path = Path(dsl_source)
        dsl_content = dsl_path.read_text() if dsl_path.exists() else ""

    dsl_hash = f"sha256:{hashlib.sha256(dsl_content.encode()).hexdigest()[:16]}"

    controls = []
    counts = {"evidenced": 0, "partial": 0, "gaps": 0}

    for control in taxonomy.all_controls():
        ev, gaps = _build_evidence_for_control(control, evidence)
        status = _compute_status(ev, gaps)
        counts[status if status != "gap" else "gaps"] += 1

        controls.append({
            "id": control.id,
            "name": control.name,
            "theme": _find_theme(taxonomy, control.id),
            "status": status,
            "evidence": ev,
            "gaps": gaps,
            "recommendations": [],
        })

    return {
        "auditspec_version": "1.0",
        "framework": taxonomy.id,
        "framework_version": taxonomy.version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dsl_source": dsl_source,
        "dsl_hash": dsl_hash,
        "summary": {
            "total_controls": len(controls),
            **counts,
        },
        "controls": controls,
    }


def _find_theme(taxonomy: Taxonomy, control_id: str) -> str:
    """Find which theme a control belongs to."""
    for theme in taxonomy.themes:
        for ctrl in theme.controls:
            if ctrl.id == control_id:
                return theme.id
    return "unknown"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/compliance/test_compiler.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/compliance/compiler.py tests/compliance/test_compiler.py
git commit -m "feat(compliance): add AuditSpec compiler (taxonomy + evidence → IR)"
```

---

## Task 5: End-to-End Compiler Integration Test

**Files:**
- Test: `tests/compliance/test_integration.py`

Run the full compiler against the real AegisMark DSL and the full ISO 27001 taxonomy.

- [ ] **Step 1: Write integration test**

```python
# tests/compliance/test_integration.py
"""Integration test: compile AuditSpec from real AegisMark DSL + ISO 27001 taxonomy."""
import json
import pytest
from pathlib import Path

from pipeline.compliance.taxonomy import load_taxonomy
from pipeline.compliance.evidence import extract_all_evidence
from pipeline.compliance.compiler import compile_auditspec

PROJECT = Path("/Volumes/SSD/AegisMark")
ISO_PATH = PROJECT / ".dazzle" / "compliance" / "frameworks" / "iso27001.yaml"
OUTPUT = PROJECT / ".dazzle" / "compliance" / "output" / "iso27001"


@pytest.fixture(scope="module")
def auditspec():
    taxonomy = load_taxonomy(ISO_PATH)
    evidence = extract_all_evidence(PROJECT)
    return compile_auditspec(taxonomy, evidence, "dsl/app.dsl")


def test_93_controls(auditspec):
    assert auditspec["summary"]["total_controls"] == 93


def test_majority_evidenced(auditspec):
    """At least 50% of controls should have some evidence."""
    s = auditspec["summary"]
    assert (s["evidenced"] + s["partial"]) / s["total_controls"] >= 0.5


def test_no_unknown_themes(auditspec):
    themes = {c["theme"] for c in auditspec["controls"]}
    assert "unknown" not in themes


def test_classify_evidence_present(auditspec):
    """At least one control should have classify evidence."""
    has_classify = any(
        any(e["construct"] == "classify" for e in c["evidence"])
        for c in auditspec["controls"]
    )
    assert has_classify


def test_write_auditspec_json(auditspec):
    """Write the AuditSpec to disk for manual inspection."""
    OUTPUT.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT / "auditspec.json"
    out_path.write_text(json.dumps(auditspec, indent=2))
    assert out_path.exists()
```

- [ ] **Step 2: Run integration test**

Run: `python3 -m pytest tests/compliance/test_integration.py -v`
Expected: All 5 tests PASS. `auditspec.json` written to `.dazzle/compliance/output/iso27001/`

- [ ] **Step 3: Inspect the generated auditspec.json**

Review the output manually. Check:
- Are the status counts reasonable? (~60+ evidenced, ~15 partial, ~15 gap)
- Do gap controls make sense? (physical security, HR, etc.)
- Are evidence refs populated with real data?

- [ ] **Step 4: Commit**

```bash
git add tests/compliance/test_integration.py .dazzle/compliance/output/iso27001/auditspec.json
git commit -m "feat(compliance): integration test — compile full AuditSpec from AegisMark DSL"
```

---

## Task 6: Brand Identity Pack

**Files:**
- Create: `brandspec.yaml`

- [ ] **Step 1: Check existing theme assets**

Review `themespec.yaml` and `static/images/` for existing brand assets (logo, colours, fonts).

- [ ] **Step 2: Create brandspec.yaml**

Create `brandspec.yaml` at project root following the spec (Section 8). Use actual AegisMark brand values from `themespec.yaml` where they exist.

- [ ] **Step 3: Commit**

```bash
git add brandspec.yaml
git commit -m "feat(compliance): add brand identity pack (brandspec.yaml)"
```

---

## Task 7: WeasyPrint Renderer

**Files:**
- Create: `pipeline/compliance/renderer.py`
- Create: `pipeline/compliance/css/compliance.css`
- Create: `pipeline/compliance/templates/document.html`
- Test: `tests/compliance/test_renderer.py`

Renders markdown documents into branded PDFs using WeasyPrint with CSS styling from brandspec.yaml.

- [ ] **Step 1: Write failing test for renderer**

```python
# tests/compliance/test_renderer.py
import pytest
from pathlib import Path

from pipeline.compliance.renderer import render_document, load_brandspec


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_markdown(tmp_path):
    md = tmp_path / "test_doc.md"
    md.write_text(
        "# Test Document\n\n"
        "## Section 1\n\n"
        "This is a test paragraph with **bold** and *italic*.\n\n"
        "| Column A | Column B |\n"
        "|----------|----------|\n"
        "| Cell 1   | Cell 2   |\n"
    )
    return md


@pytest.fixture
def brandspec():
    return load_brandspec(Path("/Volumes/SSD/AegisMark/brandspec.yaml"))


def test_load_brandspec(brandspec):
    assert brandspec["brand"]["identity"]["name"] == "AegisMark"
    assert "colours" in brandspec["brand"]
    assert "print" in brandspec["brand"]


def test_render_produces_pdf(sample_markdown, brandspec, tmp_path):
    output = tmp_path / "output.pdf"
    render_document(
        markdown_path=sample_markdown,
        output_path=output,
        brandspec=brandspec,
        document_title="Test Document",
        document_id="TEST-001",
        version="1.0",
    )
    assert output.exists()
    assert output.stat().st_size > 0
    # PDF magic bytes
    assert output.read_bytes()[:4] == b"%PDF"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/compliance/test_renderer.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Create CSS stylesheet**

```css
/* pipeline/compliance/css/compliance.css */
/* Brand-aware compliance document stylesheet.
   Variables are injected from brandspec.yaml at render time. */

@page {
    size: A4;
    margin: 25mm 25mm 25mm 30mm;
    @top-left { content: var(--header-left, ""); font-size: 8pt; color: #718096; }
    @top-right { content: var(--header-right, ""); font-size: 8pt; color: #718096; }
    @bottom-left { content: var(--footer-left, ""); font-size: 8pt; color: #718096; }
    @bottom-center { content: var(--footer-centre, ""); font-size: 8pt; color: #718096; }
    @bottom-right { content: "Page " counter(page) " of " counter(pages); font-size: 8pt; color: #718096; }
}

body {
    font-family: 'Inter', sans-serif;
    font-size: 11pt;
    color: #1a202c;
    line-height: 1.6;
}

h1 {
    font-size: 16pt;
    color: var(--colour-primary, #1a365d);
    font-weight: 600;
    margin-top: 18pt;
    page-break-before: always;
}

h1:first-of-type { page-break-before: avoid; }

h2 {
    font-size: 13pt;
    color: var(--colour-secondary, #2b6cb0);
    font-weight: 600;
    margin-top: 12pt;
}

h3 {
    font-size: 11pt;
    color: #1a202c;
    font-weight: 600;
}

table {
    width: 100%;
    border-collapse: collapse;
    margin: 12pt 0;
    font-size: 9pt;
}

th {
    background-color: var(--colour-primary, #1a365d);
    color: #ffffff;
    padding: 6pt 8pt;
    text-align: left;
    font-weight: 600;
}

td {
    padding: 5pt 8pt;
    border-bottom: 1px solid #e2e8f0;
}

tr:nth-child(even) td {
    background-color: #f7fafc;
}

.title-page {
    text-align: center;
    padding-top: 200pt;
    page-break-after: always;
}

.title-page h1 {
    font-size: 24pt;
    page-break-before: avoid;
}

.title-page .subtitle {
    font-size: 14pt;
    color: var(--colour-secondary, #2b6cb0);
    margin-top: 12pt;
}

.title-page .metadata {
    margin-top: 60pt;
    font-size: 10pt;
    color: #718096;
}

.doc-control {
    page-break-after: always;
}

.doc-control table {
    font-size: 10pt;
}

.classification-banner {
    text-align: center;
    font-size: 9pt;
    font-weight: 600;
    color: var(--colour-accent, #38a169);
    letter-spacing: 2pt;
    margin-bottom: 12pt;
}
```

- [ ] **Step 4: Create HTML template**

```html
<!-- pipeline/compliance/templates/document.html -->
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        :root {
            --colour-primary: {{ colours.primary }};
            --colour-secondary: {{ colours.secondary }};
            --colour-accent: {{ colours.accent }};
            --header-right: "{{ document_title }}";
            --footer-left: "{{ legal_name }} — {{ classification }}";
            --footer-centre: "{{ document_id }} v{{ version }}";
        }
    </style>
    <link rel="stylesheet" href="{{ css_path }}">
</head>
<body>
    <div class="classification-banner">{{ classification }}</div>

    <div class="title-page">
        {% if logo_path %}<img src="{{ logo_path }}" style="max-width: 200px;">{% endif %}
        <h1>{{ document_title }}</h1>
        <div class="subtitle">{{ organisation_name }}</div>
        <div class="metadata">
            <p>Document ID: {{ document_id }}</p>
            <p>Version: {{ version }}</p>
            <p>Date: {{ date }}</p>
            <p>Classification: {{ classification }}</p>
        </div>
    </div>

    <div class="doc-control">
        <h2>Document Control</h2>
        <table>
            <tr><th>Field</th><th>Value</th></tr>
            <tr><td>Author</td><td>{{ author }}</td></tr>
            <tr><td>Reviewer</td><td>{{ reviewer }}</td></tr>
            <tr><td>Approver</td><td>{{ approver }}</td></tr>
            <tr><td>Classification</td><td>{{ classification }}</td></tr>
        </table>
    </div>

    {{ content }}
</body>
</html>
```

- [ ] **Step 5: Implement renderer**

```python
# pipeline/compliance/renderer.py
"""Render compliance markdown documents to branded PDF via WeasyPrint."""
from __future__ import annotations

import yaml
import markdown
from datetime import date
from jinja2 import Template
from pathlib import Path
from weasyprint import HTML


PACKAGE_DIR = Path(__file__).parent
CSS_PATH = PACKAGE_DIR / "css" / "compliance.css"
TEMPLATE_PATH = PACKAGE_DIR / "templates" / "document.html"


def load_brandspec(path: Path) -> dict:
    """Load brandspec.yaml and return as dict."""
    return yaml.safe_load(path.read_text())


def render_document(
    markdown_path: Path,
    output_path: Path,
    brandspec: dict,
    document_title: str,
    document_id: str,
    version: str = "1.0",
    reviewer: str = "",
    approver: str = "",
) -> Path:
    """Render a markdown document to a branded PDF.

    Args:
        markdown_path: Path to the source markdown file.
        output_path: Path for the output PDF.
        brandspec: Parsed brandspec dict.
        document_title: Title for the title page and headers.
        document_id: Document identifier (e.g. ISMS-001).
        version: Document version string.
        reviewer: Reviewer name for doc control table.
        approver: Approver name for doc control table.

    Returns:
        Path to the generated PDF.
    """
    brand = brandspec["brand"]
    identity = brand["identity"]
    colours = brand["colours"]
    compliance = brand.get("compliance", {})
    doc_control = compliance.get("document_control", {})

    # Convert markdown to HTML
    md_text = markdown_path.read_text()
    content_html = markdown.markdown(
        md_text,
        extensions=["tables", "toc", "fenced_code"],
    )

    # Render Jinja2 template
    template = Template(TEMPLATE_PATH.read_text())
    html_str = template.render(
        content=content_html,
        document_title=document_title,
        document_id=document_id,
        version=version,
        date=date.today().isoformat(),
        organisation_name=identity["name"],
        legal_name=identity.get("legal_name", identity["name"]),
        classification=doc_control.get("classification", "Confidential"),
        author=doc_control.get("author", "Compliance Pipeline"),
        reviewer=reviewer or doc_control.get("reviewer", ""),
        approver=approver or doc_control.get("approver", ""),
        colours=colours,
        css_path=str(CSS_PATH),
        logo_path=str(Path(brand.get("assets", {}).get("logo_mono", "")))
            if "assets" in brand else None,
    )

    # Render PDF
    output_path.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html_str, base_url=str(Path.cwd())).write_pdf(str(output_path))

    return output_path
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python3 -m pytest tests/compliance/test_renderer.py -v`
Expected: All 2 tests PASS

- [ ] **Step 7: Commit**

```bash
git add pipeline/compliance/renderer.py pipeline/compliance/css/ pipeline/compliance/templates/ tests/compliance/test_renderer.py
git commit -m "feat(compliance): add WeasyPrint PDF renderer with branded CSS and title page"
```

---

## Task 8: Document Spec Loader & AuditSpec Slicer

**Files:**
- Create: `pipeline/compliance/slicer.py`
- Test: `tests/compliance/test_slicer.py`

Loads DocumentSpec YAML and slices the AuditSpec to produce per-document context for the AI agents.

- [ ] **Step 1: Write failing test**

```python
# tests/compliance/test_slicer.py
import pytest
from pathlib import Path

from pipeline.compliance.slicer import load_document_spec, slice_auditspec


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def doc_spec():
    return load_document_spec(FIXTURES / "mini_docspec.yaml")


@pytest.fixture
def auditspec():
    return {
        "controls": [
            {"id": "A.5.1", "status": "evidenced", "evidence": [{"construct": "classify"}], "gaps": []},
            {"id": "A.5.12", "status": "evidenced", "evidence": [{"construct": "classify"}], "gaps": []},
            {"id": "A.7.4", "status": "gap", "evidence": [], "gaps": [{"tier": 3}]},
        ],
        "summary": {"total_controls": 3, "evidenced": 2, "partial": 0, "gaps": 1},
    }


def test_load_docspec(doc_spec):
    assert doc_spec["id"] == "test_pack"
    assert len(doc_spec["documents"]) == 1


def test_slice_by_controls(auditspec):
    sliced = slice_auditspec(auditspec, controls=["A.5.1", "A.5.12"])
    assert len(sliced["controls"]) == 2
    assert all(c["id"] in ("A.5.1", "A.5.12") for c in sliced["controls"])


def test_slice_all_controls(auditspec):
    sliced = slice_auditspec(auditspec, controls="all")
    assert len(sliced["controls"]) == 3


def test_slice_by_status(auditspec):
    sliced = slice_auditspec(auditspec, status_filter=["gap"])
    assert len(sliced["controls"]) == 1
    assert sliced["controls"][0]["id"] == "A.7.4"


def test_slice_by_extract(auditspec):
    sliced = slice_auditspec(auditspec, extract=["classify"])
    assert len(sliced["controls"]) == 2
```

- [ ] **Step 2: Create fixture**

```yaml
# tests/compliance/fixtures/mini_docspec.yaml
document_pack:
  id: test_pack
  name: "Test Pack"
  framework: iso27001
  formality: formal
  documents:
    - id: test_doc
      name: "Test Document"
      sections:
        - title: "Test Section"
          source: auditspec
          controls: ["A.5.1"]
          extract: classify
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python3 -m pytest tests/compliance/test_slicer.py -v`
Expected: FAIL

- [ ] **Step 4: Implement slicer**

```python
# pipeline/compliance/slicer.py
"""Load DocumentSpec YAML and slice AuditSpec for per-document agent context."""
from __future__ import annotations

import yaml
from pathlib import Path


def load_document_spec(path: Path) -> dict:
    """Load a DocumentSpec YAML file.

    Returns the document_pack dict.
    """
    raw = yaml.safe_load(path.read_text())
    return raw["document_pack"]


def slice_auditspec(
    auditspec: dict,
    controls: list[str] | str = "all",
    status_filter: list[str] | None = None,
    extract: list[str] | None = None,
    tier_filter: list[int] | None = None,
) -> dict:
    """Slice an AuditSpec to a subset of controls.

    Args:
        auditspec: Full AuditSpec dict.
        controls: List of control IDs, or "all" for everything.
        status_filter: Only include controls with these statuses.
        extract: Only include controls that have evidence of these construct types.
        tier_filter: Only include gaps with these tiers.

    Returns:
        Sliced AuditSpec with filtered controls and recomputed summary.
    """
    filtered = auditspec["controls"]

    if controls != "all":
        filtered = [c for c in filtered if c["id"] in controls]

    if status_filter:
        filtered = [c for c in filtered if c["status"] in status_filter]

    if extract:
        filtered = [
            c for c in filtered
            if any(e["construct"] in extract for e in c.get("evidence", []))
        ]

    if tier_filter:
        filtered = [
            c for c in filtered
            if any(g.get("tier") in tier_filter for g in c.get("gaps", []))
        ]

    # Recompute summary
    summary = {
        "total_controls": len(filtered),
        "evidenced": sum(1 for c in filtered if c["status"] == "evidenced"),
        "partial": sum(1 for c in filtered if c["status"] == "partial"),
        "gaps": sum(1 for c in filtered if c["status"] == "gap"),
    }

    return {**auditspec, "controls": filtered, "summary": summary}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/compliance/test_slicer.py -v`
Expected: All 5 tests PASS

- [ ] **Step 6: Commit**

```bash
git add pipeline/compliance/slicer.py tests/compliance/test_slicer.py tests/compliance/fixtures/mini_docspec.yaml
git commit -m "feat(compliance): add DocumentSpec loader and AuditSpec slicer"
```

---

## Task 9: Citation Validator

**Files:**
- Create: `pipeline/compliance/citation.py`
- Test: `tests/compliance/test_citation.py`

Deterministic pass that validates `DSL ref:` citations in generated markdown against the AuditSpec IR.

- [ ] **Step 1: Write failing test**

```python
# tests/compliance/test_citation.py
import pytest
from pipeline.compliance.citation import validate_citations


@pytest.fixture
def auditspec():
    return {
        "controls": [
            {
                "id": "A.5.1",
                "evidence": [
                    {"construct": "permit", "refs": [{"entity": "MarkingResult"}]},
                    {"construct": "classify", "refs": [{"entity": "User", "field": "email"}]},
                ],
            }
        ]
    }


def test_valid_citation(auditspec):
    text = "Access is restricted (DSL ref: MarkingResult.permit)"
    issues = validate_citations(text, auditspec)
    assert len(issues) == 0


def test_invalid_citation(auditspec):
    text = "Access is restricted (DSL ref: FakeEntity.permit)"
    issues = validate_citations(text, auditspec)
    assert len(issues) == 1
    assert "FakeEntity" in issues[0]


def test_no_citations(auditspec):
    text = "This text has no citations."
    issues = validate_citations(text, auditspec)
    assert len(issues) == 0


def test_multiple_citations_mixed(auditspec):
    text = (
        "Data classified (DSL ref: User.classify). "
        "Access restricted (DSL ref: MarkingResult.permit). "
        "Also see (DSL ref: NonExistent.scope)."
    )
    issues = validate_citations(text, auditspec)
    assert len(issues) == 1
```

- [ ] **Step 2: Run tests, verify failure, implement, verify pass**

Run: `python3 -m pytest tests/compliance/test_citation.py -v`

```python
# pipeline/compliance/citation.py
"""Deterministic citation validation for generated compliance documents."""
from __future__ import annotations

import re


CITATION_PATTERN = re.compile(r"DSL ref:\s*(\w+)\.(\w+)")


def validate_citations(text: str, auditspec: dict) -> list[str]:
    """Validate all DSL ref: citations in text against the AuditSpec.

    Args:
        text: Generated markdown text to validate.
        auditspec: AuditSpec dict with controls and evidence.

    Returns:
        List of issue descriptions for invalid citations. Empty if all valid.
    """
    # Build set of valid (entity, construct) pairs from evidence
    valid_refs = set()
    for control in auditspec.get("controls", []):
        for ev in control.get("evidence", []):
            construct = ev.get("construct", "")
            for ref in ev.get("refs", []):
                entity = ref.get("entity", "")
                if entity:
                    valid_refs.add((entity, construct))

    issues = []
    for match in CITATION_PATTERN.finditer(text):
        entity = match.group(1)
        construct = match.group(2)
        if (entity, construct) not in valid_refs:
            issues.append(
                f"Invalid citation: DSL ref: {entity}.{construct} — "
                f"not found in AuditSpec evidence"
            )

    return issues
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `python3 -m pytest tests/compliance/test_citation.py -v`
Expected: All 4 tests PASS

- [ ] **Step 4: Commit**

```bash
git add pipeline/compliance/citation.py tests/compliance/test_citation.py
git commit -m "feat(compliance): add deterministic citation validator for generated docs"
```

---

## Task 10: Document Spec YAML Files

**Files:**
- Create: `.dazzle/compliance/documents/iso27001-audit-pack.yaml`
- Create: `.dazzle/compliance/documents/iso27001-customer-statement.yaml`

- [ ] **Step 1: Create the audit pack document spec**

Copy from spec Section 5 "Audit pack (formal)" — the full YAML as shown in the design spec. Add `depends_on` fields where documented.

- [ ] **Step 2: Create the customer statement document spec**

Copy from spec Section 5 "Customer statement (informal)" — the full YAML as shown in the design spec.

- [ ] **Step 3: Write a validation test**

```python
# tests/compliance/test_docspec_validation.py
import pytest
from pathlib import Path

from pipeline.compliance.slicer import load_document_spec

DOCS_DIR = Path("/Volumes/SSD/AegisMark/.dazzle/compliance/documents")


def test_audit_pack_loads():
    spec = load_document_spec(DOCS_DIR / "iso27001-audit-pack.yaml")
    assert spec["id"] == "iso27001_audit_pack"
    assert len(spec["documents"]) >= 6


def test_customer_statement_loads():
    spec = load_document_spec(DOCS_DIR / "iso27001-customer-statement.yaml")
    assert spec["id"] == "iso27001_customer_statement"
    assert len(spec["documents"]) >= 1


def test_all_sources_valid():
    valid_sources = {"auditspec", "personas", "gaps", "dsl_metadata", "template"}
    for yaml_file in DOCS_DIR.glob("*.yaml"):
        spec = load_document_spec(yaml_file)
        for doc in spec["documents"]:
            for section in doc.get("sections", []):
                source = section.get("source", "")
                assert source in valid_sources, (
                    f"Invalid source '{source}' in {yaml_file.name} "
                    f"doc={doc['id']} section='{section['title']}'"
                )
```

- [ ] **Step 4: Run tests, commit**

Run: `python3 -m pytest tests/compliance/test_docspec_validation.py -v`
Expected: All 3 PASS

```bash
git add .dazzle/compliance/documents/ tests/compliance/test_docspec_validation.py
git commit -m "feat(compliance): add ISO 27001 document specs (audit pack + customer statement)"
```

---

## Task 11: Human Templates

**Files:**
- Create: `.dazzle/compliance/templates/risk_assessment_methodology.md`
- Create: `.dazzle/compliance/templates/security_commitment.md`
- Create: `.dazzle/compliance/templates/access_control_principles.md`

- [ ] **Step 1: Author templates using AI agent**

Dispatch an AI agent with ISO 27001 domain knowledge to draft the three template files. These are starting points — the AI document generator will enrich them with DSL evidence. Each should be 1-2 pages of boilerplate appropriate for a UK SaaS company operating in the education sector.

- [ ] **Step 2: Review templates for accuracy**

Read each template. Verify ISO 27001 terminology is correct and content is appropriate for AegisMark's context (UK schools, AI-powered assessment marking, cloud-hosted SaaS).

- [ ] **Step 3: Commit**

```bash
git add .dazzle/compliance/templates/
git commit -m "feat(compliance): add human-authored ISO 27001 templates (risk methodology, security commitment, access control)"
```

---

## Task 12: Coordinator Module + Review YAML Generator

**Files:**
- Create: `pipeline/compliance/coordinator.py`
- Create: `pipeline/compliance/review.py`
- Test: `tests/compliance/test_coordinator.py`
- Test: `tests/compliance/test_review.py`

The coordinator is a Python module (not just a skill file) that orchestrates the pipeline. The `/audit` skill calls this module. Separating the logic into Python makes it testable and reusable.

- [ ] **Step 1: Write failing test for review.yaml generator**

```python
# tests/compliance/test_review.py
import pytest
import yaml
from pathlib import Path

from pipeline.compliance.review import generate_review_yaml


def test_generates_review_for_tier2_gaps():
    auditspec = {
        "controls": [
            {"id": "A.5.1", "status": "evidenced", "gaps": []},
            {"id": "A.8.3", "status": "partial", "gaps": [
                {"tier": 2, "description": "Missing network controls", "action": "Document"}
            ]},
            {"id": "A.7.4", "status": "gap", "gaps": [
                {"tier": 3, "description": "Physical security", "action": "Write policy"}
            ]},
        ]
    }
    review = generate_review_yaml(auditspec)
    assert len(review["pending_reviews"]) == 2
    assert review["pending_reviews"][0]["tier"] == 2
    assert review["pending_reviews"][1]["tier"] == 3


def test_no_reviews_for_fully_evidenced():
    auditspec = {
        "controls": [
            {"id": "A.5.1", "status": "evidenced", "gaps": []},
        ]
    }
    review = generate_review_yaml(auditspec)
    assert len(review["pending_reviews"]) == 0


def test_review_yaml_serialisable(tmp_path):
    auditspec = {
        "controls": [
            {"id": "A.7.4", "status": "gap", "gaps": [
                {"tier": 3, "description": "Physical security", "action": "Write policy"}
            ]},
        ]
    }
    review = generate_review_yaml(auditspec)
    out = tmp_path / "review.yaml"
    out.write_text(yaml.dump(review))
    reloaded = yaml.safe_load(out.read_text())
    assert reloaded["pending_reviews"][0]["control_id"] == "A.7.4"
```

- [ ] **Step 2: Implement review.yaml generator**

```python
# pipeline/compliance/review.py
"""Generate review.yaml for human-in-the-loop workflow."""
from __future__ import annotations


def generate_review_yaml(auditspec: dict) -> dict:
    """Generate review tracking structure for tier 2/3 gaps.

    Args:
        auditspec: Compiled AuditSpec dict.

    Returns:
        Dict with pending_reviews list, ready for YAML serialisation.
    """
    reviews = []
    for control in auditspec.get("controls", []):
        for gap in control.get("gaps", []):
            tier = gap.get("tier", 1)
            if tier >= 2:
                reviews.append({
                    "control_id": control["id"],
                    "control_name": control.get("name", ""),
                    "tier": tier,
                    "status": "draft" if tier == 2 else "stub",
                    "description": gap.get("description", ""),
                    "action": gap.get("action", ""),
                    "resolved": False,
                })

    return {"pending_reviews": reviews}
```

- [ ] **Step 3: Run review tests**

Run: `python3 -m pytest tests/compliance/test_review.py -v`
Expected: All 3 tests PASS

- [ ] **Step 4: Write failing test for coordinator**

```python
# tests/compliance/test_coordinator.py
import pytest
from pathlib import Path

from pipeline.compliance.coordinator import (
    topological_sort_documents,
    build_agent_context,
)


def test_topological_sort_no_deps():
    docs = [
        {"id": "a", "name": "A"},
        {"id": "b", "name": "B"},
    ]
    order = topological_sort_documents(docs)
    assert len(order) == 2


def test_topological_sort_with_deps():
    docs = [
        {"id": "soa", "depends_on": ["risk", "access"]},
        {"id": "risk"},
        {"id": "access"},
    ]
    order = topological_sort_documents(docs)
    ids = [d["id"] for d in order]
    assert ids.index("risk") < ids.index("soa")
    assert ids.index("access") < ids.index("soa")


def test_build_agent_context():
    doc = {
        "id": "access_control",
        "name": "Access Control Policy",
        "sections": [
            {
                "title": "Role Definitions",
                "source": "personas",
                "controls": ["A.5.2"],
                "ai_instruction": "Describe roles",
            }
        ],
    }
    auditspec = {
        "controls": [
            {"id": "A.5.2", "status": "evidenced", "evidence": [{"construct": "persona"}]},
            {"id": "A.7.4", "status": "gap", "evidence": []},
        ],
        "summary": {"total_controls": 2},
    }
    ctx = build_agent_context(doc, auditspec, formality="formal")
    assert "Access Control Policy" in ctx["document_title"]
    assert len(ctx["sliced_auditspec"]["controls"]) == 1
    assert ctx["formality"] == "formal"
    assert "Describe roles" in ctx["section_instructions"][0]["ai_instruction"]
```

- [ ] **Step 5: Implement coordinator module**

```python
# pipeline/compliance/coordinator.py
"""Compliance pipeline coordinator — orchestrates compilation, agent dispatch, and rendering."""
from __future__ import annotations

import json
import yaml
from pathlib import Path

from pipeline.compliance.taxonomy import load_taxonomy
from pipeline.compliance.evidence import extract_all_evidence
from pipeline.compliance.compiler import compile_auditspec
from pipeline.compliance.slicer import load_document_spec, slice_auditspec
from pipeline.compliance.review import generate_review_yaml


def topological_sort_documents(documents: list[dict]) -> list[dict]:
    """Sort documents by depends_on for correct generation order.

    Documents with no dependencies come first.
    """
    by_id = {d["id"]: d for d in documents}
    visited = set()
    order = []

    def visit(doc_id):
        if doc_id in visited:
            return
        visited.add(doc_id)
        doc = by_id.get(doc_id, {})
        for dep in doc.get("depends_on", []):
            if dep in by_id:
                visit(dep)
        order.append(by_id[doc_id])

    for doc in documents:
        visit(doc["id"])

    return order


def build_agent_context(
    document: dict,
    auditspec: dict,
    formality: str = "formal",
) -> dict:
    """Build the context dict that gets passed to a per-document AI agent.

    Returns a dict with everything the agent needs to generate one document.
    """
    # Collect all control IDs referenced by this document's sections
    all_control_ids = set()
    section_instructions = []

    for section in document.get("sections", []):
        controls = section.get("controls", [])
        if controls == "all":
            all_control_ids = "all"
        elif isinstance(all_control_ids, set) and isinstance(controls, list):
            all_control_ids.update(controls)

        section_instructions.append({
            "title": section["title"],
            "source": section.get("source", "auditspec"),
            "extract": section.get("extract"),
            "ai_instruction": section.get("ai_instruction", ""),
            "tone": section.get("tone", ""),
            "layout": section.get("layout"),
            "columns": section.get("columns"),
            "filter": section.get("filter"),
        })

    # Slice the auditspec
    if all_control_ids == "all":
        sliced = auditspec
    else:
        sliced = slice_auditspec(auditspec, controls=list(all_control_ids))

    return {
        "document_id": document["id"],
        "document_title": document["name"],
        "formality": formality,
        "target_pages": document.get("target_pages"),
        "sliced_auditspec": sliced,
        "section_instructions": section_instructions,
    }


def compile_full_pipeline(
    project_path: Path,
    framework: str = "iso27001",
) -> dict:
    """Run the full deterministic pipeline: taxonomy + evidence → AuditSpec.

    Returns the compiled AuditSpec dict.
    """
    taxonomy_path = (
        project_path / ".dazzle" / "compliance" / "frameworks" / f"{framework}.yaml"
    )
    taxonomy = load_taxonomy(taxonomy_path)
    evidence = extract_all_evidence(project_path)
    dsl_source = str(project_path / "dsl" / "app.dsl")

    return compile_auditspec(taxonomy, evidence, dsl_source)


def write_outputs(
    project_path: Path,
    auditspec: dict,
    framework: str = "iso27001",
) -> Path:
    """Write AuditSpec and review.yaml to output directory.

    Returns the output directory path.
    """
    output_dir = (
        project_path / ".dazzle" / "compliance" / "output" / framework
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    # Write auditspec.json
    auditspec_path = output_dir / "auditspec.json"
    auditspec_path.write_text(json.dumps(auditspec, indent=2))

    # Write review.yaml
    review = generate_review_yaml(auditspec)
    review_path = output_dir / "review.yaml"
    review_path.write_text(yaml.dump(review, default_flow_style=False))

    # Create markdown output dir
    (output_dir / "markdown").mkdir(exist_ok=True)

    return output_dir
```

- [ ] **Step 6: Run tests**

Run: `python3 -m pytest tests/compliance/test_coordinator.py tests/compliance/test_review.py -v`
Expected: All 6 tests PASS

- [ ] **Step 7: Commit**

```bash
git add pipeline/compliance/coordinator.py pipeline/compliance/review.py tests/compliance/test_coordinator.py tests/compliance/test_review.py
git commit -m "feat(compliance): add coordinator module and review.yaml generator"
```

---

## Task 13: /audit Claude Code Skill

**Files:**
- Create: `.claude/skills/audit.md`

The skill file is a markdown instruction file that tells Claude Code how to use the coordinator module. It delegates all deterministic work to Python and uses the Agent tool for AI document expansion.

- [ ] **Step 1: Write the skill file**

The skill should contain these instructions (write as markdown):

1. Parse args: `--pack audit|customer|both` (default: both), `--render`, `--dry-run`
2. Run `python3 -c "from pipeline.compliance.coordinator import compile_full_pipeline, write_outputs; ..."` to compile the AuditSpec and write outputs
3. If `--dry-run`, stop and report summary stats
4. Load the DocumentSpec YAML for the requested pack(s)
5. Use `topological_sort_documents` to determine generation order
6. For each document, use `build_agent_context` to prepare context, then dispatch an Agent tool subagent with:
   - A system prompt instructing it to act as an ISO 27001 compliance specialist
   - The sliced AuditSpec as JSON
   - The section instructions with ai_instruction fields
   - The DSL source file content (or relevant excerpts)
   - Instructions to write markdown output to the correct path
   - Instructions to use `DSL ref: Entity.construct` citation style
   - The formality level and target page count
7. After each agent writes its markdown, run citation validation via `python3 -c "from pipeline.compliance.citation import validate_citations; ..."`
8. After all documents are generated, dispatch one final Agent to read all markdown files and check for cross-reference consistency (terminology, statistics, role names)
9. If the consistency agent finds issues, regenerate the affected section(s) with a correction instruction (max 2 attempts)
10. If `--render`, run `python3 -c "from pipeline.compliance.renderer import render_document, load_brandspec; ..."` for each markdown file
11. Report summary: documents generated, citation issues found, review items pending

- [ ] **Step 2: Test dry-run**

Run: `/audit --dry-run`
Expected: AuditSpec compiled, summary printed (e.g., "93 controls: 61 evidenced, 18 partial, 14 gaps")

- [ ] **Step 3: Test customer statement generation**

Run: `/audit --pack customer`
Expected: `compliance_statement.md` written with coherent prose about AegisMark's security posture

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/audit.md
git commit -m "feat(compliance): add /audit coordinator skill with agent dispatch"
```

---

## Task 14: End-to-End Generation Test

**Files:**
- No new files — this is a validation task

- [ ] **Step 1: Generate the customer statement**

Run: `/audit --pack customer --render`

Expected outputs:
- `.dazzle/compliance/output/iso27001/auditspec.json`
- `.dazzle/compliance/output/iso27001/markdown/compliance_statement.md`
- `.dazzle/compliance/output/iso27001/pdf/AegisMark-Information-Security-Statement-v1.0.pdf`

- [ ] **Step 2: Review the generated PDF**

Open the PDF manually. Check:
- Title page has logo, document ID, version, date, classification
- Document control table is populated
- Content is coherent and references AegisMark's actual data (classify directives, role names, entity counts)
- No hallucinated citations (citation validator should have caught these)
- Tone is appropriate (customer-facing, non-technical)

- [ ] **Step 3: Generate the audit pack**

Run: `/audit --pack audit --render`

Expected: 6 markdown files + 6 PDFs in the output directory.

- [ ] **Step 4: Review audit pack for completeness**

Check each document:
- ISMS Scope: mentions AegisMark, 53 entities, 9 personas, 11 workspaces
- Risk Assessment: asset register from classify directives, risk register with likelihood/impact
- SoA: all 93 controls listed with status, justification, evidence summary
- Access Control Policy: role definitions from personas, RBAC matrix from permit/scope
- Data Classification Policy: maps DSL categories to ISO tiers
- Gap Analysis: lists partial/gap controls with remediation recommendations

- [ ] **Step 5: Commit generated outputs**

```bash
git add .dazzle/compliance/output/iso27001/auditspec.json .dazzle/compliance/output/iso27001/markdown/ .dazzle/compliance/output/iso27001/review.yaml
echo ".dazzle/compliance/output/*/pdf/" >> .gitignore
git add .gitignore
git commit -m "feat(compliance): first full ISO 27001 document generation for AegisMark"
```

---

## Task 15: Update .gitignore and requirements

**Files:**
- Modify: `.gitignore`
- Modify: `requirements.txt`

- [ ] **Step 1: Add PDF output to .gitignore**

```
# Compliance PDF outputs (generated artefacts)
.dazzle/compliance/output/*/pdf/
```

- [ ] **Step 2: Verify dependencies in requirements.txt**

Check that `pyyaml`, `jinja2`, `markdown`, and `weasyprint` are listed. Add any missing ones with pinned versions.

- [ ] **Step 3: Commit**

```bash
git add .gitignore requirements.txt
git commit -m "chore: add compliance PDF output to gitignore, verify dependencies"
```
