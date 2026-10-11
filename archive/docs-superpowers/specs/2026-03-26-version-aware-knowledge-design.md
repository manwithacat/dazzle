# Version-Aware Knowledge Responses

**Issue**: #716
**Status**: Approved
**Date**: 2026-03-26

## Summary

Extend the MCP `knowledge` tool with version annotations so agents naturally discover new capabilities during work. Three changes: structured version fields on TOML concepts, a `version_info` block in concept responses, and a new `changelog` operation that surfaces agent guidance from recent releases.

## Design

### 1. TOML Schema Extensions

Add two optional fields to concept/pattern entries in the semantics KB TOML files:

```toml
[concepts.template_overrides]
category = "Frontend"
definition = "..."
since_version = "0.48.0"
changed_in = [
  { version = "0.48.12", note = "Declaration headers and CLI scan commands" },
]
```

- **`since_version`**: string, optional. The version when this concept was introduced. Omit for concepts that predate version tracking.
- **`changed_in`**: array of `{version, note}` tables, optional. Ordered newest-first. Each entry describes a notable change to the concept in that release.
- Existing `v0_X_changes` fields remain untouched. Normalization into the new format is a separate future effort.
- No changes to `[meta]` sections.

**Initial annotations** on ~5 concepts with clear version provenance: `template_overrides`, `feedback_widget`, `grant_schema`, `scope_block`, `deploy_trigger`.

### 2. Concept Response Format

When `knowledge concept <term>` returns a concept that has version info, include a `version_info` block:

```json
{
  "term": "template_overrides",
  "found": true,
  "category": "Frontend",
  "definition": "Project templates in templates/ override framework templates...",
  "version_info": {
    "since": "0.48.0",
    "changes": [
      {"version": "0.48.12", "note": "Declaration headers and CLI scan commands"}
    ]
  }
}
```

- `version_info` key only present when `since_version` or `changed_in` exists — no empty objects.
- `changes` array ordered newest-first (matches TOML source order).
- Existing `v0_X_changes` keys continue as top-level response fields (backward compat). Not duplicated into `version_info`.

**Implementation**: `lookup_concept_handler()` in `knowledge.py` extracts the new fields. `lookup_concept()` in `semantics_kb/__init__.py` passes them through like `related`, `implemented_by`, etc.

### 3. `knowledge changelog` Operation

New operation on the `knowledge` tool. Parses `### Agent Guidance` sections from CHANGELOG.md.

**Input schema:**
```json
{
  "operation": "changelog",
  "since": "0.48.0"
}
```

- `since`: optional string. Return guidance from this version onward.
- Default (no `since`): return last 5 releases that have agent guidance sections.

**Response:**
```json
{
  "current_version": "0.48.16",
  "entries": [
    {
      "version": "0.48.12",
      "guidance": [
        "Admin workspace entities have domain=\"platform\" — filter these out in counts",
        "Schema migrations: Use dazzle db revision + dazzle db upgrade (ADR-0017)"
      ]
    }
  ],
  "total_entries": 6
}
```

**Implementation:**

- `parse_changelog_guidance(since: str | None = None, limit: int = 5) -> list[dict]` in `semantics_kb/__init__.py`.
- Parses CHANGELOG.md: regex matches `## [X.Y.Z]` version headers, finds `### Agent Guidance` subsections within each, extracts bullet points.
- Called during KG seeding — stores entries as `changelog:vX.Y.Z` entities in the knowledge graph.
- Handler reads from KG at query time; falls back to live parsing if KG unavailable.
- `since` parameter filters by semver comparison using `packaging.version.Version`.

**Tool registration:** Add `"changelog"` to the operation enum and `"since"` as optional string in `tools_consolidated.py`.

### 4. Testing

- **changelog parser**: Mock a small CHANGELOG.md, verify extraction and `since` filtering.
- **version_info in concept lookup**: Add `since_version`/`changed_in` to a test concept, verify response JSON.
- **changelog handler**: Mock parsed data, verify response shape and default limit of 5.
- **KG seed**: Extend existing seed test to verify `changelog:vX.Y.Z` entities are created.

### 5. What Does Not Change

- KG schema (entities are schemaless dicts).
- Alias system.
- Concept lookup fallback chain (KG first, TOML fallback).
- Non-MCP agent experience (CHANGELOG.md `### Agent Guidance` sections remain their interface).

## Files to Modify

| File | Change |
|------|--------|
| `src/dazzle/mcp/semantics_kb/*.toml` | Add `since_version`/`changed_in` to ~5 concepts |
| `src/dazzle/mcp/semantics_kb/__init__.py` | Pass through new fields in `lookup_concept()`; add `parse_changelog_guidance()` |
| `src/dazzle/mcp/knowledge_graph/seed.py` | Seed changelog entities during `seed_framework_knowledge()` |
| `src/dazzle/mcp/server/handlers/knowledge.py` | Build `version_info` block; add `changelog` handler |
| `src/dazzle/mcp/server/tools_consolidated.py` | Add `changelog` operation + `since` param |
| `tests/unit/test_knowledge_handler.py` | Tests for version_info and changelog operation |
| `tests/unit/test_changelog_parser.py` | Tests for `parse_changelog_guidance()` |
| `tests/unit/test_kg_seed.py` | Extend for changelog entities |
