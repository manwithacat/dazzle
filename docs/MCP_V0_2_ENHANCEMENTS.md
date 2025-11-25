# DAZZLE MCP Server v0.2 Enhancements

**Date**: 2025-11-25
**Version**: 0.2.0

## Overview

The DAZZLE MCP server has been significantly enhanced to provide LLMs with immediate, contextual access to DAZZLE DSL v0.2 semantics and grammar. These enhancements enable natural use of Dazzle-specific terminology with automatic context retrieval.

## What's New

### 1. Semantic Concept Lookup Tool

**Tool**: `lookup_concept`

Provides immediate access to DSL concept definitions, syntax, examples, and relationships.

**Usage:**
```
Use the lookup_concept tool with term="persona"
```

**Returns:**
```json
{
  "term": "persona",
  "found": true,
  "category": "UX Semantic Layer (v0.2)",
  "definition": "A role-based variant that adapts surfaces...",
  "syntax": "for <persona_name>:\n  scope: ...",
  "example": "for admin:\n  scope: all\n  ...",
  "related": ["ux_block", "scope", "workspace"],
  "v0_2_changes": "NEW in v0.2",
  "best_practices": [...]
}
```

**Supported Concepts:**
- **Core**: entity, surface, workspace, module
- **UX Semantic Layer**: ux_block, purpose, information_needs, attention_signals, persona, scope
- **Workspace Components**: regions, display_modes, aggregates
- **Expression System**: conditions
- **Type System**: field_types, surface_modes, relationships

### 2. Example Project Search Tool

**Tool**: `find_examples`

Searches example projects by features or complexity level.

**Usage:**
```
Use find_examples with features=["persona", "workspace"]
```

**Returns:**
```json
{
  "query": {
    "features": ["persona", "workspace"],
    "complexity": null
  },
  "count": 3,
  "examples": [
    {
      "name": "simple_task",
      "title": "Simple Task Manager",
      "demonstrates": ["entities", "workspace", "persona", ...],
      "v0_2_features": ["ux_block", "workspace", "persona"],
      "complexity": "beginner",
      "uri": "dazzle://examples/simple_task"
    },
    ...
  ]
}
```

**Parameters:**
- `features` (array): Features to search for (e.g., ['persona', 'attention_signals'])
- `complexity` (string): Filter by complexity ('beginner', 'intermediate', 'advanced')

### 3. Enhanced Resources

#### Semantic Concept Index
**URI**: `dazzle://semantics/index`

Complete structured index of all DSL v0.2 concepts with:
- Definitions
- Syntax specifications
- Examples
- Related concepts
- v0.2 change notes
- Best practices

**Format**: JSON

#### Example Projects Catalog
**URI**: `dazzle://examples/catalog`

Metadata about all example projects including:
- What features they demonstrate
- Complexity level
- Entities, surfaces, workspaces
- Use cases

**Format**: JSON

#### Migration Guide
**URI**: `dazzle://docs/migration-guide`

Complete guide for migrating from v0.1 to v0.2.

**Format**: Markdown

### 4. Updated Documentation Resources

All documentation resources now reference **v0.2**:

- `dazzle://docs/glossary` - Updated with v0.2 concepts
- `dazzle://docs/dsl-reference` - Now points to v0.2 reference
- `dazzle://docs/quick-reference` - Syntax quick reference

## How It Works

### Natural Context Injection

When you mention Dazzle-specific terminology in prompts, the MCP server can automatically provide context:

**Before:**
```
User: "How do I use personas in workspaces?"
LLM: *Searches files manually, assembles answer*
```

**After:**
```
User: "How do I use personas in workspaces?"
LLM: *Uses lookup_concept('persona') and lookup_concept('workspace')*
     *Receives structured definitions, syntax, and examples*
     *Answers immediately with precise, contextual information*
```

### Example Search Integration

Find relevant examples automatically:

```
User: "Show me an example of attention signals"
LLM: *Uses find_examples(features=['attention_signals'])*
     *Gets: support_tickets example*
     *Provides path and context*
```

## Usage Examples

### Example 1: Learning a Concept

**Query**: "What is a persona in DAZZLE?"

**LLM Action**:
```
lookup_concept(term="persona")
```

**Result**: Full definition, syntax, example code, related concepts, and best practices.

### Example 2: Finding Implementation Examples

**Query**: "Show me examples using workspaces and aggregates"

**LLM Action**:
```
find_examples(features=["workspace", "aggregates"])
```

**Result**: List of examples demonstrating both features with URIs to access them.

### Example 3: Understanding Relationships

**Query**: "How do personas relate to workspaces?"

**LLM Action**:
```
lookup_concept(term="persona")  # Related: ["ux_block", "scope", "workspace"]
lookup_concept(term="workspace")  # Shows persona usage in workspaces
```

**Result**: Clear explanation of how personas adapt workspaces for different user roles.

## Implementation Details

### New Modules

#### `/src/dazzle/mcp/semantics.py`
- `get_semantic_index()` - Returns complete semantic concept index
- `lookup_concept(term)` - Looks up individual concepts

**Data Structure:**
```python
{
  "version": "0.2.0",
  "concepts": {
    "persona": {
      "category": "UX Semantic Layer (v0.2)",
      "definition": "...",
      "syntax": "...",
      "example": "...",
      "related": [...],
      "v0_2_changes": "...",
      "best_practices": [...]
    },
    ...
  },
  "patterns": {...},
  "best_practices": {...}
}
```

#### `/src/dazzle/mcp/examples.py`
- `get_example_metadata()` - Returns all example metadata
- `search_examples(features, complexity)` - Searches examples
- `get_v0_2_examples()` - Gets all v0.2 feature examples
- `get_feature_examples_map()` - Maps features to examples

**Example Metadata Structure:**
```python
{
  "simple_task": {
    "name": "simple_task",
    "title": "Simple Task Manager",
    "demonstrates": ["entities", "workspace", "persona", ...],
    "v0_2_features": ["ux_block", "workspace", "persona"],
    "complexity": "beginner",
    "entities": ["Task"],
    "surfaces": ["task_list", ...],
    "workspaces": ["task_dashboard", ...]
  },
  ...
}
```

### Updated Server Implementation

**New Tools** (`/src/dazzle/mcp/server.py`):
- `lookup_concept` - Semantic concept lookup
- `find_examples` - Example project search

**New Resources**:
- `dazzle://semantics/index` - Complete concept index
- `dazzle://examples/catalog` - Example metadata
- `dazzle://docs/migration-guide` - v0.1 to v0.2 migration

**Updated Glossary**: Now includes v0.2 concepts with version annotations.

## Benefits

### For LLMs

1. **Immediate Context** - No need to search files for definitions
2. **Structured Information** - JSON format for easy parsing
3. **Relationship Mapping** - Understand how concepts relate
4. **Example Discovery** - Find relevant code examples quickly
5. **Version Awareness** - Know what's new in v0.2

### For Users

1. **Natural Language** - Use Dazzle terminology naturally in prompts
2. **Faster Responses** - LLM has context immediately available
3. **Accurate Answers** - Definitions come from canonical source
4. **Learning Path** - Examples guide from beginner to advanced
5. **Migration Support** - Clear v0.1 to v0.2 upgrade path

## Testing

### Test Semantic Lookup
```bash
python -c "
from dazzle.mcp.semantics import lookup_concept
import json
print(json.dumps(lookup_concept('workspace'), indent=2))
"
```

### Test Example Search
```bash
python -c "
from dazzle.mcp.examples import search_examples
import json
print(json.dumps(search_examples(features=['persona']), indent=2))
"
```

### Verify MCP Server
```bash
python -m dazzle.mcp.server
# Should start without errors
```

## Future Enhancements

### Planned for Next Release

1. **Auto-Context Injection** - Automatically inject relevant context when DSL terms are mentioned
2. **Syntax Validation** - Real-time syntax checking for DSL snippets
3. **Pattern Recommendations** - Suggest patterns based on entities
4. **Interactive Examples** - Live preview of example DSL
5. **Concept Graph** - Visual representation of concept relationships

### Under Consideration

1. **Custom Concept Extensions** - Allow projects to define custom concepts
2. **Example Code Extraction** - Pull specific code snippets from examples
3. **Version Comparison** - Show v0.1 vs v0.2 syntax differences
4. **Best Practice Linting** - Check DSL against best practices

## Migration from Previous MCP

If you have an existing DAZZLE MCP configuration, no changes are needed. The new tools and resources are backwards compatible:

- All existing tools continue to work
- All existing resources continue to work
- New tools are available immediately
- New resources are available immediately

Simply restart your MCP server to enable the new features.

## Summary

The v0.2 MCP enhancements provide:

✅ **Semantic concept lookup** - Instant access to DSL definitions and syntax
✅ **Example search** - Find relevant examples by features
✅ **Structured semantic index** - Complete v0.2 concept catalog
✅ **Example metadata** - Searchable example project information
✅ **Migration guide** - v0.1 to v0.2 upgrade documentation
✅ **v0.2 documentation** - All docs updated to latest version

These enhancements enable natural, contextual conversations about DAZZLE DSL with immediate access to relevant information.
