# Version-Aware Knowledge Responses Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the MCP `knowledge` tool with version annotations on concepts and a `changelog` operation that surfaces agent guidance from recent releases.

**Architecture:** Three layers of change: (1) TOML schema gains `since_version` and `changed_in` fields, seeded into KG metadata, (2) concept lookup handler builds a `version_info` block from those fields, (3) new `parse_changelog_guidance()` parser reads `### Agent Guidance` from CHANGELOG.md, seeded into KG as `changelog:vX.Y.Z` entities, served by a new `changelog` handler operation.

**Tech Stack:** Python 3.12, TOML (semantics KB), `packaging.version.Version` (semver comparison), pytest

---

### Task 1: Changelog Parser — Tests

**Files:**
- Create: `tests/unit/test_changelog_parser.py`

- [ ] **Step 1: Write the test file with all changelog parser tests**

```python
"""Tests for parse_changelog_guidance()."""

import textwrap
from unittest.mock import patch

from dazzle.mcp.semantics_kb.changelog import parse_changelog_guidance


SAMPLE_CHANGELOG = textwrap.dedent("""\
    # Changelog

    ## [0.50.0] - 2026-04-01

    ### Added
    - Some new feature

    ### Agent Guidance
    - **New rule**: Do the new thing
    - **Another rule**: Also do this

    ## [0.49.0] - 2026-03-30

    ### Fixed
    - Bug fix

    ## [0.48.12] - 2026-03-26

    ### Added
    - Admin workspace

    ### Agent Guidance
    - **Admin entities**: Filter by domain="platform"
    - **Schema migrations**: Use Alembic for all changes

    ## [0.48.8] - 2026-03-25

    ### Agent Guidance
    - **CSS**: Local-first delivery

    ## [0.48.2] - 2026-03-24

    ### Agent Guidance
    - **PostgreSQL only**: No SQLite

    ## [0.48.0] - 2026-03-24

    ### Agent Guidance
    - **Grant RBAC**: Use has_grant() in guards
    - **Templates**: Use dz:// prefix for extends

    ## [0.47.0] - 2026-03-20

    ### Agent Guidance
    - **Old guidance**: Something from before
""")


class TestParseChangelogGuidance:
    """Tests for the changelog parser."""

    def test_returns_entries_with_guidance(self) -> None:
        """Versions without Agent Guidance sections are excluded."""
        entries = parse_changelog_guidance(changelog_text=SAMPLE_CHANGELOG)
        versions = [e["version"] for e in entries]
        # 0.49.0 has no Agent Guidance — should be excluded
        assert "0.49.0" not in versions
        # 0.50.0 has Agent Guidance — should be included
        assert "0.50.0" in versions

    def test_default_limit_is_5(self) -> None:
        """Default returns at most 5 entries."""
        entries = parse_changelog_guidance(changelog_text=SAMPLE_CHANGELOG)
        assert len(entries) <= 5

    def test_ordered_newest_first(self) -> None:
        """Entries are ordered newest version first."""
        entries = parse_changelog_guidance(changelog_text=SAMPLE_CHANGELOG, limit=10)
        versions = [e["version"] for e in entries]
        assert versions[0] == "0.50.0"
        assert versions[-1] == "0.47.0"

    def test_extracts_bullet_points(self) -> None:
        """Each entry has a guidance list of bullet point strings."""
        entries = parse_changelog_guidance(changelog_text=SAMPLE_CHANGELOG, limit=10)
        entry_050 = next(e for e in entries if e["version"] == "0.50.0")
        assert len(entry_050["guidance"]) == 2
        assert "New rule" in entry_050["guidance"][0]

    def test_since_filter(self) -> None:
        """since parameter filters to versions >= the given version."""
        entries = parse_changelog_guidance(
            changelog_text=SAMPLE_CHANGELOG, since="0.48.8", limit=10
        )
        versions = [e["version"] for e in entries]
        assert "0.47.0" not in versions
        assert "0.48.2" not in versions
        assert "0.48.8" in versions
        assert "0.50.0" in versions

    def test_since_filter_with_limit(self) -> None:
        """since + limit work together."""
        entries = parse_changelog_guidance(
            changelog_text=SAMPLE_CHANGELOG, since="0.48.0", limit=2
        )
        assert len(entries) == 2
        assert entries[0]["version"] == "0.50.0"

    def test_empty_changelog(self) -> None:
        """Empty changelog returns empty list."""
        entries = parse_changelog_guidance(changelog_text="# Changelog\n")
        assert entries == []

    def test_strips_leading_dash_from_bullets(self) -> None:
        """Bullet text has the leading '- ' stripped."""
        entries = parse_changelog_guidance(changelog_text=SAMPLE_CHANGELOG, limit=10)
        entry = next(e for e in entries if e["version"] == "0.48.2")
        assert entry["guidance"] == ["**PostgreSQL only**: No SQLite"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_changelog_parser.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'dazzle.mcp.semantics_kb.changelog'`

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_changelog_parser.py
git commit -m "test: add changelog parser tests (#716)"
```

---

### Task 2: Changelog Parser — Implementation

**Files:**
- Create: `src/dazzle/mcp/semantics_kb/changelog.py`

- [ ] **Step 1: Implement the changelog parser**

```python
"""
Changelog parser — extracts Agent Guidance sections from CHANGELOG.md.

Parses Keep-a-Changelog format, finds ``### Agent Guidance`` subsections,
and returns structured entries with version + bullet points.
"""

import logging
import re
from pathlib import Path
from typing import Any

from packaging.version import Version

logger = logging.getLogger(__name__)

# Matches: ## [0.48.12] - 2026-03-26
_VERSION_RE = re.compile(r"^## \[(\d+\.\d+\.\d+)\]")
# Matches: ### Agent Guidance
_GUIDANCE_RE = re.compile(r"^### Agent Guidance\s*$")
# Matches: ### <anything> (next section header)
_SECTION_RE = re.compile(r"^### ")
# Matches: - bullet point
_BULLET_RE = re.compile(r"^- (.+)$")


def _find_changelog_path() -> Path | None:
    """Walk up from this file to find CHANGELOG.md at the project root."""
    current = Path(__file__).resolve().parent
    for _ in range(10):
        candidate = current / "CHANGELOG.md"
        if candidate.exists():
            return candidate
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def parse_changelog_guidance(
    *,
    since: str | None = None,
    limit: int = 5,
    changelog_text: str | None = None,
) -> list[dict[str, Any]]:
    """
    Parse Agent Guidance sections from CHANGELOG.md.

    Args:
        since: If given, only return entries for versions >= this value.
        limit: Maximum number of entries to return (default 5).
        changelog_text: Raw changelog text. If None, reads from CHANGELOG.md.

    Returns:
        List of ``{"version": "X.Y.Z", "guidance": ["bullet1", ...]}`` dicts,
        ordered newest-first.
    """
    if changelog_text is None:
        path = _find_changelog_path()
        if path is None:
            logger.warning("CHANGELOG.md not found")
            return []
        changelog_text = path.read_text(encoding="utf-8")

    entries: list[dict[str, Any]] = []
    current_version: str | None = None
    in_guidance = False
    bullets: list[str] = []

    for line in changelog_text.splitlines():
        # Check for version header
        version_match = _VERSION_RE.match(line)
        if version_match:
            # Flush previous version's guidance
            if current_version and bullets:
                entries.append({"version": current_version, "guidance": list(bullets)})
            current_version = version_match.group(1)
            in_guidance = False
            bullets = []
            continue

        # Check for Agent Guidance section start
        if _GUIDANCE_RE.match(line):
            in_guidance = True
            continue

        # Check for next section (exits Agent Guidance)
        if in_guidance and _SECTION_RE.match(line):
            in_guidance = False
            continue

        # Collect bullets inside Agent Guidance
        if in_guidance:
            bullet_match = _BULLET_RE.match(line)
            if bullet_match:
                bullets.append(bullet_match.group(1))

    # Flush last version
    if current_version and bullets:
        entries.append({"version": current_version, "guidance": list(bullets)})

    # Filter by since
    if since:
        since_ver = Version(since)
        entries = [e for e in entries if Version(e["version"]) >= since_ver]

    # Already ordered newest-first (changelog convention)
    return entries[:limit]
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `pytest tests/unit/test_changelog_parser.py -v`
Expected: All 8 tests PASS

- [ ] **Step 3: Commit**

```bash
git add src/dazzle/mcp/semantics_kb/changelog.py
git commit -m "feat: changelog parser for Agent Guidance extraction (#716)"
```

---

### Task 3: Version Info in Concept Lookup — Tests

**Files:**
- Create: `tests/unit/test_version_info.py`

- [ ] **Step 1: Write tests for version_info in concept lookup responses**

```python
"""Tests for version_info in concept lookup responses."""

import importlib.util
import sys
from pathlib import Path


def _import_knowledge_graph_module(module_name: str):
    """Import knowledge graph modules directly to avoid MCP package init issues."""
    module_path = (
        Path(__file__).parent.parent.parent
        / "src"
        / "dazzle"
        / "mcp"
        / "knowledge_graph"
        / f"{module_name}.py"
    )
    spec = importlib.util.spec_from_file_location(
        f"dazzle.mcp.knowledge_graph.{module_name}",
        module_path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"dazzle.mcp.knowledge_graph.{module_name}"] = module
    spec.loader.exec_module(module)
    return module


_store_module = _import_knowledge_graph_module("store")
KnowledgeGraph = _store_module.KnowledgeGraph


class TestVersionInfoInConceptLookup:
    """Tests for version_info extraction from KG concept metadata."""

    def test_concept_with_since_version(self) -> None:
        """Concept with since_version gets version_info.since in response."""
        graph = KnowledgeGraph(":memory:")
        graph.create_entity(
            entity_id="concept:test_feature",
            name="test_feature",
            entity_type="concept",
            metadata={
                "source": "framework",
                "category": "Test",
                "definition": "A test feature",
                "since_version": "0.48.0",
            },
        )
        entity = graph.get_entity("concept:test_feature")
        meta = entity.metadata
        assert meta["since_version"] == "0.48.0"

    def test_concept_with_changed_in(self) -> None:
        """Concept with changed_in gets version_info.changes in response."""
        graph = KnowledgeGraph(":memory:")
        changed_in = [
            {"version": "0.48.12", "note": "Added declaration headers"},
            {"version": "0.48.5", "note": "Initial support"},
        ]
        graph.create_entity(
            entity_id="concept:test_feature",
            name="test_feature",
            entity_type="concept",
            metadata={
                "source": "framework",
                "category": "Test",
                "definition": "A test feature",
                "changed_in": changed_in,
            },
        )
        entity = graph.get_entity("concept:test_feature")
        meta = entity.metadata
        assert meta["changed_in"] == changed_in

    def test_concept_without_version_info(self) -> None:
        """Concept without version fields has no version info in metadata."""
        graph = KnowledgeGraph(":memory:")
        graph.create_entity(
            entity_id="concept:old_feature",
            name="old_feature",
            entity_type="concept",
            metadata={
                "source": "framework",
                "category": "Test",
                "definition": "An old feature",
            },
        )
        entity = graph.get_entity("concept:old_feature")
        meta = entity.metadata
        assert "since_version" not in meta
        assert "changed_in" not in meta
```

- [ ] **Step 2: Run tests to verify they pass**

These tests verify that the KG store correctly persists structured metadata. They should pass already since the KG store accepts arbitrary metadata.

Run: `pytest tests/unit/test_version_info.py -v`
Expected: All 3 tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_version_info.py
git commit -m "test: add version_info concept lookup tests (#716)"
```

---

### Task 4: Seed Version Fields into KG

**Files:**
- Modify: `src/dazzle/mcp/knowledge_graph/seed.py:148-162`

- [ ] **Step 1: Write a test for version fields in seeded concepts**

Add to `tests/unit/test_version_info.py`:

```python
class TestVersionFieldsInSeed:
    """Tests that seed pipeline passes through since_version and changed_in."""

    def test_seed_passes_through_since_version(self) -> None:
        """Concepts with since_version in TOML have it in KG metadata after seeding."""
        _seed_module = _import_knowledge_graph_module("seed")
        graph = KnowledgeGraph(":memory:")
        _seed_module.seed_framework_knowledge(graph)

        # feedback_widget should have since_version after we annotate the TOML
        entity = graph.get_entity("concept:feedback_widget")
        assert entity is not None
        meta = entity.metadata
        assert meta.get("since_version") == "0.48.0"

    def test_seed_passes_through_changed_in(self) -> None:
        """Concepts with changed_in in TOML have it in KG metadata after seeding."""
        _seed_module = _import_knowledge_graph_module("seed")
        graph = KnowledgeGraph(":memory:")
        _seed_module.seed_framework_knowledge(graph)

        entity = graph.get_entity("concept:feedback_widget")
        assert entity is not None
        meta = entity.metadata
        changed_in = meta.get("changed_in")
        assert isinstance(changed_in, list)
        assert len(changed_in) >= 1
        assert changed_in[0]["version"]
        assert changed_in[0]["note"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_version_info.py::TestVersionFieldsInSeed -v`
Expected: FAIL — `since_version` not in metadata (seed doesn't pass it through yet)

- [ ] **Step 3: Update seed.py to pass through version fields**

In `src/dazzle/mcp/knowledge_graph/seed.py`, update the concept seeding block (lines 148-162). Change the metadata dict construction to include `since_version` and `changed_in`:

```python
    # Seed concepts as entities
    for name, concept_data in concepts.items():
        entity_id = f"concept:{name}"
        metadata: dict[str, Any] = {
            "source": "framework",
            "category": concept_data.get("category", ""),
            "definition": concept_data.get("definition", ""),
            "syntax": concept_data.get("syntax", ""),
            "example": concept_data.get("example", ""),
        }
        # Version tracking fields (optional)
        if "since_version" in concept_data:
            metadata["since_version"] = concept_data["since_version"]
        if "changed_in" in concept_data:
            metadata["changed_in"] = concept_data["changed_in"]

        graph.create_entity(
            entity_id=entity_id,
            name=name,
            entity_type="concept",
            metadata=metadata,
        )
        stats["concepts"] += 1
```

- [ ] **Step 4: Add version annotations to feedback.toml**

In `src/dazzle/mcp/semantics_kb/feedback.toml`, add version fields to `feedback_widget`:

```toml
[concepts.feedback_widget]
category = "Framework Feature"
since_version = "0.48.0"
changed_in = [
  { version = "0.48.15", note = "Resolved-report notification toast on page load" },
  { version = "0.48.13", note = "Mobile Safari fixes: button type, focus removal, dvh viewport" },
  { version = "0.48.12", note = "Retry toast suppressed on background retries" },
]
definition = """
In-app feedback collection. When `feedback_widget: enabled` is declared in the DSL,
the framework auto-generates a FeedbackReport entity, three synthetic surfaces
(CREATE, LIST, EDIT), and corresponding CRUD routes. A floating button appears on
every authenticated page, letting users report bugs, UX issues, and suggestions.
"""
```

- [ ] **Step 5: Bump SEED_SCHEMA_VERSION**

In `src/dazzle/mcp/knowledge_graph/seed.py`, bump the version:

```python
SEED_SCHEMA_VERSION = 7  # v7: version-aware concept metadata (#716)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/unit/test_version_info.py -v`
Expected: All 5 tests PASS

- [ ] **Step 7: Commit**

```bash
git add src/dazzle/mcp/knowledge_graph/seed.py src/dazzle/mcp/semantics_kb/feedback.toml tests/unit/test_version_info.py
git commit -m "feat: seed version fields into KG from TOML (#716)"
```

---

### Task 5: Annotate Remaining TOML Concepts

**Files:**
- Modify: `src/dazzle/mcp/semantics_kb/ux.toml` (scope concept)
- Modify: `src/dazzle/mcp/semantics_kb/frontend.toml` (static_assets concept)
- Modify: `src/dazzle/mcp/semantics_kb/runtime.toml` (predicate_compilation concept)
- Modify: `src/dazzle/mcp/semantics_kb/logic.toml` (surface_access concept)

- [ ] **Step 1: Add since_version to scope concept in ux.toml**

After the `category` line of `[concepts.scope]` in `src/dazzle/mcp/semantics_kb/ux.toml`:

```toml
since_version = "0.2.0"
changed_in = [
  { version = "0.48.0", note = "Scope rules now compile to formal predicate algebra with FK graph validation" },
]
```

- [ ] **Step 2: Add since_version to static_assets in frontend.toml**

Find `[concepts.static_assets]` in `src/dazzle/mcp/semantics_kb/frontend.toml` and add after `category`:

```toml
since_version = "0.48.8"
changed_in = [
  { version = "0.48.12", note = "Content-hash cache busting via static_url Jinja2 filter" },
]
```

- [ ] **Step 3: Add since_version to predicate_compilation in runtime.toml**

Find `[concepts.predicate_compilation]` in `src/dazzle/mcp/semantics_kb/runtime.toml` and add after `category`:

```toml
since_version = "0.48.0"
```

- [ ] **Step 4: Add since_version to surface_access in logic.toml**

Find `[concepts.surface_access]` in `src/dazzle/mcp/semantics_kb/logic.toml` and add after `category`:

```toml
since_version = "0.45.0"
changed_in = [
  { version = "0.48.0", note = "permit: now role-only; field conditions moved to scope: blocks" },
]
```

- [ ] **Step 5: Run seed test to verify all annotations are picked up**

Run: `pytest tests/unit/test_kg_seed.py -v`
Expected: All existing tests PASS (annotations are additive)

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/mcp/semantics_kb/ux.toml src/dazzle/mcp/semantics_kb/frontend.toml src/dazzle/mcp/semantics_kb/runtime.toml src/dazzle/mcp/semantics_kb/logic.toml
git commit -m "feat: annotate 4 TOML concepts with version provenance (#716)"
```

---

### Task 6: version_info Block in Concept Handler

**Files:**
- Modify: `src/dazzle/mcp/semantics_kb/__init__.py:366-406` (lookup_concept)
- Modify: `src/dazzle/mcp/server/handlers/knowledge.py:20-29` (lookup_concept_handler)

- [ ] **Step 1: Write a test for version_info in handler response**

Add to `tests/unit/test_version_info.py`:

```python
import json


class TestVersionInfoInHandler:
    """Tests for version_info block in knowledge handler concept response."""

    def test_handler_includes_version_info_when_present(self) -> None:
        """lookup_concept_handler returns version_info for annotated concepts."""
        from unittest.mock import patch, MagicMock

        mock_entity = MagicMock()
        mock_entity.entity_type = "concept"
        mock_entity.metadata = {
            "source": "framework",
            "category": "Framework Feature",
            "definition": "A feature",
            "since_version": "0.48.0",
            "changed_in": [{"version": "0.48.12", "note": "Added stuff"}],
        }

        mock_graph = MagicMock()
        mock_graph.lookup_concept.return_value = mock_entity

        with patch("dazzle.mcp.semantics_kb._get_kg", return_value=mock_graph):
            from dazzle.mcp.semantics_kb import lookup_concept

            result = lookup_concept("test_feature")

        assert result["found"] is True
        assert "version_info" in result
        assert result["version_info"]["since"] == "0.48.0"
        assert len(result["version_info"]["changes"]) == 1
        assert result["version_info"]["changes"][0]["version"] == "0.48.12"

    def test_handler_omits_version_info_when_absent(self) -> None:
        """lookup_concept_handler omits version_info for unannotated concepts."""
        from unittest.mock import patch, MagicMock

        mock_entity = MagicMock()
        mock_entity.entity_type = "concept"
        mock_entity.metadata = {
            "source": "framework",
            "category": "Core",
            "definition": "Old concept",
        }

        mock_graph = MagicMock()
        mock_graph.lookup_concept.return_value = mock_entity

        with patch("dazzle.mcp.semantics_kb._get_kg", return_value=mock_graph):
            from dazzle.mcp.semantics_kb import lookup_concept

            result = lookup_concept("old_concept")

        assert result["found"] is True
        assert "version_info" not in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_version_info.py::TestVersionInfoInHandler -v`
Expected: FAIL — `version_info` not in result (not yet built by lookup_concept)

- [ ] **Step 3: Update lookup_concept in semantics_kb/__init__.py**

In `src/dazzle/mcp/semantics_kb/__init__.py`, update the `lookup_concept` function. After the existing metadata extraction loop (lines 391-405), add version_info construction:

```python
        for key in (
            "category",
            "definition",
            "syntax",
            "example",
            "description",
            "runtime_behaviour",
            "limitations",
            "implemented_by",
            "known_issues",
            "important_notes",
            "related",
        ):
            if key in meta and meta[key]:
                result[key] = meta[key]

        # Build version_info block from structured version fields
        version_info: dict[str, Any] = {}
        if meta.get("since_version"):
            version_info["since"] = meta["since_version"]
        if meta.get("changed_in"):
            version_info["changes"] = meta["changed_in"]
        if version_info:
            result["version_info"] = version_info

        return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_version_info.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/mcp/semantics_kb/__init__.py tests/unit/test_version_info.py
git commit -m "feat: build version_info block in concept lookup (#716)"
```

---

### Task 7: Seed Changelog into KG

**Files:**
- Modify: `src/dazzle/mcp/knowledge_graph/seed.py`

- [ ] **Step 1: Write test for changelog seeding**

Add to `tests/unit/test_kg_seed.py`:

```python
class TestSeedChangelogGuidance:
    """Tests for changelog guidance seeding into KG."""

    def test_seed_creates_changelog_entities(self) -> None:
        """Seeding creates changelog entities from CHANGELOG.md."""
        graph = KnowledgeGraph(":memory:")
        _seed_module.seed_framework_knowledge(graph)

        # There should be at least one changelog entity
        changelog_entities = graph.list_entities(entity_type="changelog", limit=50)
        assert len(changelog_entities) >= 1

    def test_changelog_entity_has_guidance(self) -> None:
        """Changelog entities store guidance bullets in metadata."""
        graph = KnowledgeGraph(":memory:")
        _seed_module.seed_framework_knowledge(graph)

        changelog_entities = graph.list_entities(entity_type="changelog", limit=50)
        # At least one should have non-empty guidance
        has_guidance = any(
            e.metadata.get("guidance") for e in changelog_entities
        )
        assert has_guidance

    def test_changelog_entity_id_format(self) -> None:
        """Changelog entity IDs follow changelog:vX.Y.Z format."""
        graph = KnowledgeGraph(":memory:")
        _seed_module.seed_framework_knowledge(graph)

        changelog_entities = graph.list_entities(entity_type="changelog", limit=50)
        for e in changelog_entities:
            assert e.entity_id.startswith("changelog:v")

    def test_seed_stats_include_changelog(self) -> None:
        """Seed stats dict includes changelog_entries count."""
        graph = KnowledgeGraph(":memory:")
        stats = _seed_module.seed_framework_knowledge(graph)

        assert "changelog_entries" in stats
        assert stats["changelog_entries"] >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_kg_seed.py::TestSeedChangelogGuidance -v`
Expected: FAIL — no `changelog` entity type, no `changelog_entries` in stats

- [ ] **Step 3: Implement changelog seeding in seed.py**

In `src/dazzle/mcp/knowledge_graph/seed.py`, add the following.

First, add `"changelog_entries": 0` to the stats dict in `seed_framework_knowledge()`:

```python
    stats: dict[str, int] = {
        "concepts": 0,
        "patterns": 0,
        "inference_entries": 0,
        "changelog_entries": 0,
        "aliases": 0,
        "relations": 0,
    }
```

Then add a call to `_seed_changelog(graph, stats)` after `_seed_inference_kb(graph, stats)`:

```python
        # Load and seed changelog guidance
        _seed_changelog(graph, stats)
```

Add the new function at the end of the file:

```python
def _seed_changelog(graph: KnowledgeGraph, stats: dict[str, int]) -> None:
    """Seed Agent Guidance entries from CHANGELOG.md into the KG."""
    from dazzle.mcp.semantics_kb.changelog import parse_changelog_guidance

    entries = parse_changelog_guidance(limit=50)

    for entry in entries:
        version = entry["version"]
        entity_id = f"changelog:v{version}"
        graph.create_entity(
            entity_id=entity_id,
            name=f"v{version}",
            entity_type="changelog",
            metadata={
                "source": "framework",
                "version": version,
                "guidance": entry["guidance"],
            },
        )
        stats["changelog_entries"] += 1
```

Update the log message to include changelog_entries:

```python
        logger.info(
            "Seeded framework knowledge: %d concepts, %d patterns, "
            "%d inference entries, %d changelog entries, %d aliases, %d relations",
            stats["concepts"],
            stats["patterns"],
            stats["inference_entries"],
            stats["changelog_entries"],
            stats["aliases"],
            stats["relations"],
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_kg_seed.py -v`
Expected: All tests PASS (existing + new)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/mcp/knowledge_graph/seed.py tests/unit/test_kg_seed.py
git commit -m "feat: seed changelog guidance entries into KG (#716)"
```

---

### Task 8: Changelog Handler Operation

**Files:**
- Modify: `src/dazzle/mcp/server/handlers/knowledge.py`
- Modify: `src/dazzle/mcp/server/handlers_consolidated.py`
- Modify: `src/dazzle/mcp/server/tools_consolidated.py`

- [ ] **Step 1: Write test for changelog handler**

Add to `tests/unit/test_version_info.py`:

```python
class TestChangelogHandler:
    """Tests for the knowledge changelog handler operation."""

    def test_changelog_handler_returns_entries(self) -> None:
        """changelog handler returns structured entries."""
        from unittest.mock import patch, MagicMock

        mock_entities = []
        for version, guidance in [
            ("0.48.12", ["Rule A", "Rule B"]),
            ("0.48.8", ["Rule C"]),
        ]:
            entity = MagicMock()
            entity.entity_id = f"changelog:v{version}"
            entity.name = f"v{version}"
            entity.entity_type = "changelog"
            entity.metadata = {
                "source": "framework",
                "version": version,
                "guidance": guidance,
            }
            mock_entities.append(entity)

        mock_graph = MagicMock()
        mock_graph.list_entities.return_value = mock_entities

        with patch("dazzle.mcp.server.handlers.knowledge._get_kg", return_value=mock_graph):
            from dazzle.mcp.server.handlers.knowledge import get_changelog_handler

            result_str = get_changelog_handler({"_progress": MagicMock()})
            result = json.loads(result_str)

        assert "current_version" in result
        assert "entries" in result
        assert len(result["entries"]) == 2
        assert result["entries"][0]["version"] == "0.48.12"
        assert result["total_entries"] == 2

    def test_changelog_handler_respects_since(self) -> None:
        """changelog handler filters by since parameter."""
        from unittest.mock import patch, MagicMock

        mock_entities = []
        for version, guidance in [
            ("0.48.12", ["Rule A"]),
            ("0.48.8", ["Rule B"]),
            ("0.48.0", ["Rule C"]),
        ]:
            entity = MagicMock()
            entity.entity_id = f"changelog:v{version}"
            entity.name = f"v{version}"
            entity.entity_type = "changelog"
            entity.metadata = {
                "source": "framework",
                "version": version,
                "guidance": guidance,
            }
            mock_entities.append(entity)

        mock_graph = MagicMock()
        mock_graph.list_entities.return_value = mock_entities

        with patch("dazzle.mcp.server.handlers.knowledge._get_kg", return_value=mock_graph):
            from dazzle.mcp.server.handlers.knowledge import get_changelog_handler

            result_str = get_changelog_handler({
                "since": "0.48.8",
                "_progress": MagicMock(),
            })
            result = json.loads(result_str)

        versions = [e["version"] for e in result["entries"]]
        assert "0.48.0" not in versions
        assert "0.48.8" in versions
        assert "0.48.12" in versions
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_version_info.py::TestChangelogHandler -v`
Expected: FAIL — `get_changelog_handler` does not exist

- [ ] **Step 3: Implement the changelog handler**

In `src/dazzle/mcp/server/handlers/knowledge.py`, add the import and handler function:

Add to imports at top:

```python
from dazzle.mcp._graph_access import get_kg as _get_kg
from dazzle.mcp.semantics_kb import MCP_SEMANTICS_VERSION
```

Add the handler function:

```python
@wrap_handler_errors
def get_changelog_handler(args: dict[str, Any]) -> str:
    """Get Agent Guidance entries from recent releases."""
    progress = extract_progress(args)
    progress.log_sync("Loading changelog guidance...")

    since = args.get("since")
    limit = 5

    graph = _get_kg()
    if graph is not None:
        # Read from KG
        from packaging.version import Version

        entities = graph.list_entities(entity_type="changelog", limit=50)
        entries = []
        for e in entities:
            version = e.metadata.get("version", "")
            guidance = e.metadata.get("guidance", [])
            if guidance:
                entries.append({"version": version, "guidance": guidance})

        # Sort newest first
        entries.sort(key=lambda e: Version(e["version"]), reverse=True)

        # Filter by since
        if since:
            since_ver = Version(since)
            entries = [e for e in entries if Version(e["version"]) >= since_ver]

        entries = entries[:limit]
    else:
        # Fallback: parse CHANGELOG.md directly
        from dazzle.mcp.semantics_kb.changelog import parse_changelog_guidance

        entries = parse_changelog_guidance(since=since, limit=limit)

    return json.dumps(
        {
            "current_version": MCP_SEMANTICS_VERSION,
            "entries": entries,
            "total_entries": len(entries),
        },
        indent=2,
    )
```

- [ ] **Step 4: Wire the handler in handlers_consolidated.py**

In `src/dazzle/mcp/server/handlers_consolidated.py`, add `"changelog"` to the `_knowledge_standalone` operations dict (around line 481):

```python
_knowledge_standalone: Callable[[dict[str, Any]], str] = _make_standalone_handler(
    "knowledge",
    {
        "concept": f"{_MOD_KNOW}:lookup_concept_handler",
        "examples": f"{_MOD_KNOW_TOOL}:find_examples_handler",
        "cli_help": f"{_MOD_KNOW}:get_cli_help_handler",
        "workflow": f"{_MOD_KNOW}:get_workflow_guide_handler",
        "inference": f"{_MOD_KNOW}:lookup_inference_handler",
        "changelog": f"{_MOD_KNOW}:get_changelog_handler",
    },
)
```

- [ ] **Step 5: Add changelog to tool schema in tools_consolidated.py**

In `src/dazzle/mcp/server/tools_consolidated.py`, update the knowledge tool definition.

Add `"changelog"` to the operation enum:

```python
"enum": [
    "concept",
    "examples",
    "cli_help",
    "workflow",
    "inference",
    "get_spec",
    "search_commands",
    "changelog",
],
```

Add the `since` parameter to the properties dict:

```python
"since": {
    "type": "string",
    "description": "Version filter (for changelog, e.g. '0.48.0')",
},
```

Update the tool description:

```python
description="Knowledge lookup: concept, examples, cli_help, workflow, inference, changelog, get_spec, search_commands. Note: Static content also available via MCP Resources.",
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/unit/test_version_info.py -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add src/dazzle/mcp/server/handlers/knowledge.py src/dazzle/mcp/server/handlers_consolidated.py src/dazzle/mcp/server/tools_consolidated.py tests/unit/test_version_info.py
git commit -m "feat: knowledge changelog operation with KG-backed lookup (#716)"
```

---

### Task 9: Full Integration Test

**Files:**
- No new files — run existing test suites

- [ ] **Step 1: Run all unit tests**

Run: `pytest tests/ -m "not e2e" -x -q`
Expected: All tests PASS

- [ ] **Step 2: Run lint**

Run: `ruff check src/dazzle/mcp/semantics_kb/changelog.py src/dazzle/mcp/server/handlers/knowledge.py src/dazzle/mcp/knowledge_graph/seed.py src/dazzle/mcp/semantics_kb/__init__.py --fix && ruff format src/dazzle/mcp/semantics_kb/changelog.py src/dazzle/mcp/server/handlers/knowledge.py src/dazzle/mcp/knowledge_graph/seed.py src/dazzle/mcp/semantics_kb/__init__.py`
Expected: Clean

- [ ] **Step 3: Run mypy on changed modules**

Run: `mypy src/dazzle/mcp/semantics_kb/changelog.py src/dazzle/mcp/server/handlers/knowledge.py src/dazzle/mcp/knowledge_graph/seed.py`
Expected: No errors

- [ ] **Step 4: Fix any issues and commit**

```bash
git add -u
git commit -m "fix: lint and type fixes for version-aware knowledge (#716)"
```

(Skip this commit if no fixes needed.)
