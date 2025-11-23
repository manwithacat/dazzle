# DAZZLE App-Local Vocabulary - Evaluation & Implementation Plan

**Date**: 2025-11-23
**Spec Version**: v1
**Status**: 🔍 Analysis Complete
**Complexity**: ⚠️ HIGH - Multi-stage implementation required

---

## Executive Summary

The App-Local Vocabulary specification proposes a **metaprogramming layer** on top of the core DAZZLE DSL that enables:
1. Apps to define reusable patterns (macros/aliases) that expand to core DSL
2. Pattern detection and automatic vocabulary generation
3. Mining app-local vocabularies across projects to create extension packs
4. A stable core DSL with app-specific syntactic sugar

**Assessment**: This is an **ambitious and valuable feature** that addresses real needs but requires careful phased implementation to avoid complexity explosion.

**Recommendation**: **PROCEED** with a **4-phase implementation** starting with foundational tooling and gradually adding higher-level features.

---

## Strategic Analysis

### ✅ Strengths

1. **Preserves Core DSL Stability**
   - App-local vocab is purely additive
   - Core DSL remains the ground truth
   - Deterministic expansion ensures reversibility

2. **Addresses Real Pain Points**
   - Repeated patterns in generated apps (e.g., user profile panels)
   - Boilerplate reduction
   - Cross-project learning (extension packs)

3. **Well-Designed Architecture**
   - Clear separation of concerns
   - Machine-readable metadata
   - Usage tracking for data-driven decisions

4. **Composability**
   - Extension packs can be mixed
   - Namespacing prevents collisions
   - Versioning supports evolution

5. **Aligns with DAZZLE Philosophy**
   - Token efficiency (macros reduce DSL size)
   - LLM-friendly (agents can generate and use vocab)
   - Framework-agnostic (vocab is DSL-level)

### ⚠️ Risks & Concerns

1. **Implementation Complexity**
   - Requires new parser/expander layer
   - Metadata management and mining infrastructure
   - Testing complexity (vocab + expansion + core DSL)

2. **Potential for Overuse**
   - Risk of "vocabulary explosion" with hundreds of tiny entries
   - Could create app-specific dialects that hinder portability
   - Debugging becomes harder (which layer has the bug?)

3. **Discovery & Discoverability**
   - How do users find useful vocabularies?
   - How do they know what's available in a project?
   - IDE/tooling support needed for autocomplete

4. **Versioning Challenges**
   - Vocabulary versions vs core DSL versions
   - Breaking changes in vocab definitions
   - Migration paths when vocab changes

5. **Performance Overhead**
   - Expansion step adds compilation time
   - Usage tracking adds I/O overhead
   - Mining process could be expensive

6. **Scope Creep Risk**
   - Could evolve into a full macro system (like Rust or Lisp)
   - Need clear boundaries on what vocab can/can't do
   - Temptation to add control flow, variables, etc.

### 🎯 Strategic Fit

**Fits well with DAZZLE's vision** of:
- LLM-driven development (agents can learn patterns)
- Token efficiency (reduce repetition)
- Rapid iteration (reuse patterns)

**Potential conflicts**:
- Simplicity vs. power (adds conceptual overhead)
- Explicit vs. implicit (hides DSL behind abstractions)

---

## Technical Evaluation

### Architecture Components

**Proposed System**:
```
┌─────────────────────────────────────────────┐
│  App DSL with Local Vocab References       │
│  (e.g., "use user_profile_summary_panel")  │
└───────────────┬─────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────┐
│  Vocabulary Expander                        │
│  - Load manifest.yml                        │
│  - Substitute parameters                    │
│  - Expand to core DSL                       │
└───────────────┬─────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────┐
│  Core DSL (pure, no vocab references)      │
└───────────────┬─────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────┐
│  Existing DAZZLE Parser/Linker/Generator   │
└─────────────────────────────────────────────┘
```

**Required New Components**:

1. **Vocabulary Manifest Schema** (`manifest.yml`)
   - Pydantic models for validation
   - YAML serialization/deserialization
   - Version compatibility checking

2. **Expander/Macro Processor**
   - Template substitution engine
   - Parameter validation
   - Recursive expansion (vocab can use vocab)
   - Error handling with source location tracking

3. **Pattern Detection Engine**
   - AST analysis to find repeated structures
   - Similarity scoring
   - Parameterization heuristics
   - Threshold-based candidate generation

4. **Usage Tracking System**
   - Incremental logging
   - Aggregation and statistics
   - Metadata enrichment

5. **Mining & Clustering**
   - Cross-app vocabulary aggregation
   - Semantic similarity detection
   - Extension pack proposal generation
   - Packaging and distribution

6. **CLI Extensions**
   - `dazzle vocab list` - show available vocab
   - `dazzle vocab expand` - preview expansion
   - `dazzle vocab create` - define new entry
   - `dazzle vocab mine` - analyze for extension packs

### Implementation Challenges

**1. Parser Integration**
- Need to decide: expand before or during parsing?
- **Recommendation**: Expand BEFORE core parsing (preprocessing step)
- Allows vocab to be completely transparent to core DSL parser

**2. Error Messages**
- Errors can occur at two levels:
  - Vocabulary expansion (bad parameters, missing vocab)
  - Core DSL compilation (after expansion)
- Must provide clear source mapping back to original file

**3. Circular Dependencies**
- Vocab A uses Vocab B uses Vocab A = infinite loop
- **Solution**: Track expansion depth, detect cycles

**4. Testing Strategy**
- Need to test:
  - Each vocabulary entry expands correctly
  - Parameter substitution works
  - Core DSL result is valid
  - Round-trip (DSL → vocab → core DSL → vocab) preserves semantics
- Requires golden master tests for each vocab entry

**5. IDE/Tooling Support**
- Autocomplete for vocab entries
- Hover to see expansion
- Go-to-definition for vocab
- Validation in real-time
- **Challenge**: VS Code extension needs major upgrade

---

## Recommended Multi-Stage Implementation Plan

### Phase 1: Foundation (v0.2.0) - **4-6 weeks**

**Goal**: Establish core infrastructure for vocabulary without LLM/mining features.

**Deliverables**:
1. ✅ Vocabulary manifest schema (`dazzle/core/vocab.py`)
   - Pydantic models for `VocabEntry`, `VocabManifest`
   - Validation and version checking
   - YAML serialization

2. ✅ Simple expander (`dazzle/core/expander.py`)
   - Template substitution (Jinja2-based?)
   - Parameter validation
   - Cycle detection
   - Error messages with source mapping

3. ✅ Manual vocabulary creation
   - CLI command: `dazzle vocab create <name>`
   - Interactive prompts for parameters
   - Write to `dazzle/local_vocab/manifest.yml`

4. ✅ Expansion in build pipeline
   - Add preprocessing step before parsing
   - `dazzle build` expands vocab automatically
   - Optional flag: `--show-expanded` to see result

5. ✅ Basic CLI commands
   - `dazzle vocab list` - show all entries
   - `dazzle vocab show <name>` - show expansion
   - `dazzle vocab expand <file>` - expand file and print

6. ✅ Documentation
   - User guide for creating vocab
   - Developer guide for vocab schema
   - Examples of good vocab entries

**Testing**:
- Unit tests for expander
- Integration tests for build pipeline
- Example project with simple vocab

**Success Criteria**:
- Developers can manually create and use vocabulary
- Vocabulary expands correctly to core DSL
- Build pipeline handles vocab transparently

---

### Phase 2: Automation (v0.3.0) - **4-6 weeks**

**Goal**: Automatic pattern detection and vocabulary generation.

**Deliverables**:
1. ✅ Pattern detection engine
   - AST visitor for core DSL
   - Similarity scoring (edit distance, structural similarity)
   - Threshold-based detection (>= 3 occurrences)

2. ✅ Automatic vocab proposal
   - CLI command: `dazzle vocab detect`
   - Scans DSL for patterns
   - Proposes vocabulary entries
   - Interactive confirmation

3. ✅ Parameterization heuristics
   - Identify variable parts (field names, titles)
   - Generate parameter definitions
   - Suggest parameter types and defaults

4. ✅ Refactoring support
   - After creating vocab, offer to refactor DSL
   - Replace pattern occurrences with vocab references
   - Update manifest with usage counts

5. ✅ Usage tracking
   - Increment `usage_count` on expansion
   - Log to `dazzle/local_vocab/usage_logs/`
   - Aggregate statistics

**Testing**:
- Pattern detection accuracy tests
- Parameterization tests
- Refactoring correctness tests

**Success Criteria**:
- Agent can detect repeated patterns
- Vocabulary entries are generated automatically
- DSL is refactored to use vocab

---

### Phase 3: Mining & Extension Packs (v0.4.0) - **6-8 weeks**

**Goal**: Cross-app mining and extension pack creation.

**Deliverables**:
1. ✅ Mining infrastructure
   - CLI command: `dazzle mine <directory>`
   - Scans multiple apps for vocabularies
   - Clusters similar entries
   - Generates extension pack proposals

2. ✅ Clustering algorithm
   - Semantic similarity (embeddings? or structural?)
   - Frequency-based ranking
   - Metadata-based grouping (tags, scope)

3. ✅ Extension pack format
   - Package structure (similar to npm/pypi)
   - `pack.yml` manifest
   - Versioning and dependencies
   - Installation mechanism

4. ✅ Pack installation
   - CLI command: `dazzle pack install <name>`
   - Downloads/copies to `dazzle/local_vocab/packs/`
   - Registers in app's manifest
   - Namespace management

5. ✅ Pack registry (optional)
   - Central repository (GitHub repo? or simple JSON index?)
   - Search and browse
   - Version resolution

**Testing**:
- Mining with synthetic app corpus
- Pack installation and usage
- Version compatibility tests

**Success Criteria**:
- Vocabulary can be extracted from multiple apps
- Extension packs are created and installable
- Packs work across different apps

---

### Phase 4: LLM Integration & Polish (v0.5.0) - **4-6 weeks**

**Goal**: LLM-driven vocabulary management and developer experience improvements.

**Deliverables**:
1. ✅ LLM-guided vocabulary creation
   - Analyze DSL and suggest vocab names/descriptions
   - Generate parameter definitions from examples
   - Write human-readable documentation

2. ✅ Intelligent pattern detection
   - Use LLM to identify semantic patterns (not just syntactic)
   - Cluster by intent, not just structure
   - Better naming and categorization

3. ✅ VS Code extension updates
   - Autocomplete for vocab entries
   - Hover to show expansion preview
   - Inline expansion view
   - Quick actions: "Create vocab from selection"

4. ✅ Quality metrics
   - Measure vocab usage across apps
   - Identify low-value entries (mark for deprecation)
   - Suggest refactorings

5. ✅ Migration tooling
   - Update vocab when core DSL changes
   - Deprecation warnings
   - Automated migration scripts

**Testing**:
- LLM integration tests (mock or real)
- VS Code extension tests
- User acceptance testing

**Success Criteria**:
- LLMs can generate high-quality vocabularies
- Developer experience is seamless
- Vocabulary ecosystem is healthy and well-maintained

---

## Phase 1 Detailed Implementation Plan

### Week 1-2: Schema & Foundation

**Tasks**:
1. Create `src/dazzle/core/vocab.py`
   - `VocabEntry` Pydantic model
   - `VocabManifest` Pydantic model
   - `VocabParameter` Pydantic model
   - YAML serialization helpers

2. Create `src/dazzle/core/expander.py`
   - `VocabExpander` class
   - Template substitution engine
   - Parameter validation
   - Cycle detection

3. Add unit tests
   - `tests/unit/test_vocab_schema.py`
   - `tests/unit/test_expander.py`

**Example Code**:
```python
# src/dazzle/core/vocab.py
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

class VocabParameter(BaseModel):
    name: str
    type: str  # model_ref, string, boolean, number
    required: bool = True
    default: Optional[Any] = None
    description: Optional[str] = None

class VocabEntry(BaseModel):
    id: str = Field(..., pattern=r'^[a-z0-9_]+$')
    kind: str = Field(..., pattern=r'^(macro|alias|pattern)$')
    scope: str = Field(..., pattern=r'^(ui|data|workflow|auth|misc)$')
    dsl_core_version: str
    description: str
    parameters: List[VocabParameter] = []
    expansion: Dict[str, str]  # language, body
    metadata: Dict[str, Any] = {}

    class Config:
        frozen = True

class VocabManifest(BaseModel):
    version: str = "1.0.0"
    app_id: str
    dsl_core_version: str
    entries: List[VocabEntry] = []

    def add_entry(self, entry: VocabEntry):
        """Add new vocabulary entry."""
        # Check for ID collision
        if any(e.id == entry.id for e in self.entries):
            raise ValueError(f"Entry '{entry.id}' already exists")
        self.entries.append(entry)

    def get_entry(self, entry_id: str) -> Optional[VocabEntry]:
        """Get entry by ID."""
        for entry in self.entries:
            if entry.id == entry_id:
                return entry
        return None
```

### Week 3-4: Expander Implementation

**Tasks**:
1. Implement template expansion
2. Add parameter substitution
3. Implement cycle detection
4. Add error handling with source tracking

**Example Code**:
```python
# src/dazzle/core/expander.py
from jinja2 import Environment, BaseLoader, TemplateError
from typing import Dict, Any, Set
from .vocab import VocabManifest, VocabEntry

class ExpansionError(Exception):
    """Raised when vocabulary expansion fails."""
    pass

class VocabExpander:
    """Expands vocabulary references to core DSL."""

    def __init__(self, manifest: VocabManifest):
        self.manifest = manifest
        self.jinja_env = Environment(loader=BaseLoader())

    def expand_entry(
        self,
        entry_id: str,
        params: Dict[str, Any],
        visited: Optional[Set[str]] = None
    ) -> str:
        """
        Expand a vocabulary entry with given parameters.

        Args:
            entry_id: ID of vocabulary entry
            params: Parameters to substitute
            visited: Set of visited entry IDs (for cycle detection)

        Returns:
            Expanded core DSL string

        Raises:
            ExpansionError: If expansion fails
        """
        if visited is None:
            visited = set()

        # Cycle detection
        if entry_id in visited:
            raise ExpansionError(f"Circular dependency detected: {' -> '.join(visited)} -> {entry_id}")

        visited.add(entry_id)

        # Get entry
        entry = self.manifest.get_entry(entry_id)
        if not entry:
            raise ExpansionError(f"Vocabulary entry '{entry_id}' not found")

        # Validate parameters
        self._validate_parameters(entry, params)

        # Expand template
        try:
            template = self.jinja_env.from_string(entry.expansion['body'])
            expanded = template.render(**params)
        except TemplateError as e:
            raise ExpansionError(f"Template expansion failed for '{entry_id}': {e}")

        # TODO: Recursively expand any nested vocab references in the result

        visited.remove(entry_id)
        return expanded

    def _validate_parameters(self, entry: VocabEntry, params: Dict[str, Any]):
        """Validate parameters against entry definition."""
        # Check required parameters
        for param_def in entry.parameters:
            if param_def.required and param_def.name not in params:
                raise ExpansionError(
                    f"Missing required parameter '{param_def.name}' for '{entry.id}'"
                )

        # Check for unknown parameters
        known_params = {p.name for p in entry.parameters}
        unknown = set(params.keys()) - known_params
        if unknown:
            raise ExpansionError(
                f"Unknown parameters for '{entry.id}': {', '.join(unknown)}"
            )
```

### Week 5-6: CLI Integration

**Tasks**:
1. Add `dazzle vocab` subcommands to CLI
2. Integrate expander into build pipeline
3. Add tests for CLI commands

**Example Code**:
```python
# src/dazzle/cli.py (additions)

@app.group()
def vocab():
    """Manage app-local vocabulary."""
    pass

@vocab.command("list")
def vocab_list(
    path: Optional[str] = typer.Option(None, "--path", "-p", help="Project directory")
):
    """List all vocabulary entries in the project."""
    from dazzle.core.vocab import VocabManifest
    from pathlib import Path
    import yaml

    project_path = Path(path or ".")
    manifest_path = project_path / "dazzle" / "local_vocab" / "manifest.yml"

    if not manifest_path.exists():
        typer.echo("No vocabulary manifest found.")
        return

    # Load manifest
    with open(manifest_path) as f:
        data = yaml.safe_load(f)
    manifest = VocabManifest(**data)

    # Display entries
    typer.echo(f"Vocabulary Entries ({len(manifest.entries)} total):\n")
    for entry in manifest.entries:
        typer.echo(f"  {entry.id:30s} [{entry.kind}] {entry.scope}")
        typer.echo(f"    {entry.description}")
        typer.echo()

@vocab.command("show")
def vocab_show(
    entry_id: str = typer.Argument(..., help="Entry ID to show"),
    path: Optional[str] = typer.Option(None, "--path", "-p", help="Project directory")
):
    """Show details and expansion of a vocabulary entry."""
    # ... implementation

@vocab.command("expand")
def vocab_expand(
    file_path: str = typer.Argument(..., help="DSL file to expand"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output file")
):
    """Expand vocabulary references in a DSL file."""
    # ... implementation
```

---

## Risks & Mitigation Strategies

### Risk 1: Feature Creep

**Risk**: Vocabulary system evolves into a full macro/metaprogramming system.

**Mitigation**:
- **Clear boundaries**: Vocabulary can only expand to core DSL (no computation, control flow, side effects)
- **Version 1.0 freeze**: Once Phase 1-3 complete, freeze vocabulary schema for 6 months
- **Review process**: Any new vocabulary features require RFC and community discussion

### Risk 2: Poor Vocabulary Quality

**Risk**: Generated vocabularies are poorly named, over-specific, or redundant.

**Mitigation**:
- **Quality metrics**: Track usage, staleness, redundancy
- **Curation**: Manual review of auto-generated entries
- **Best practices guide**: Document patterns for good vocabulary design
- **Deprecation policy**: Remove low-value entries regularly

### Risk 3: Debugging Complexity

**Risk**: Bugs could be in vocab layer or core DSL layer, making debugging hard.

**Mitigation**:
- **Clear error messages**: Always show both vocab source and expanded DSL
- **Debug mode**: `--debug-vocab` flag shows expansion steps
- **Source mapping**: Maintain line/column mapping from original to expanded DSL
- **Testing**: Require tests for both vocab and expanded DSL

### Risk 4: Version Hell

**Risk**: Incompatible versions of vocab, packs, and core DSL cause breakage.

**Mitigation**:
- **Semantic versioning**: Strict semver for all components
- **Compatibility matrix**: Document which versions work together
- **Migration tools**: Automated migration for breaking changes
- **Deprecation period**: 2 versions notice before removing features

---

## Success Metrics

### Phase 1 Success
- [ ] 5 example vocab entries created manually
- [ ] All examples expand correctly
- [ ] Build pipeline handles vocab transparently
- [ ] Developer documentation complete
- [ ] Zero regressions in existing functionality

### Phase 2 Success
- [ ] Pattern detection finds 80%+ of repeated patterns
- [ ] Auto-generated vocab saves 30%+ DSL tokens
- [ ] Refactoring preserves semantics (verified by tests)
- [ ] Usage tracking provides actionable insights

### Phase 3 Success
- [ ] Mining identifies 10+ reusable patterns across 5+ apps
- [ ] Extension pack installation works smoothly
- [ ] Packs reduce boilerplate by 50%+ in new apps
- [ ] Community creates and shares packs

### Phase 4 Success
- [ ] LLM generates high-quality vocab (80%+ accept rate)
- [ ] VS Code extension provides seamless experience
- [ ] Vocabulary ecosystem has 20+ quality extension packs
- [ ] Developers prefer using vocab over raw DSL for common patterns

---

## Resource Estimates

### Development Time

| Phase | Duration | FTE | Total Effort |
|-------|----------|-----|--------------|
| Phase 1 | 6 weeks | 1.0 | 6 person-weeks |
| Phase 2 | 6 weeks | 1.0 | 6 person-weeks |
| Phase 3 | 8 weeks | 1.0 | 8 person-weeks |
| Phase 4 | 6 weeks | 1.0 | 6 person-weeks |
| **Total** | **26 weeks** | | **26 person-weeks** (~6 months) |

### Dependencies

- **Phase 1**: No blockers (can start immediately)
- **Phase 2**: Requires Phase 1 complete
- **Phase 3**: Requires Phase 2 complete (but could run in parallel with some overlap)
- **Phase 4**: Requires Phase 1-3 (VS Code extension update is independent)

### Testing Effort

- Estimate **30% overhead** for testing (8 person-weeks)
- **Total**: ~34 person-weeks (~8 months with testing)

---

## Alternatives Considered

### Alternative 1: Don't Do This

**Pros**:
- Keeps DAZZLE simple
- No complexity overhead
- Faster to market with core features

**Cons**:
- Repeated boilerplate in apps
- Harder to share patterns across projects
- Less competitive vs. frameworks with component libraries

**Verdict**: ❌ Not recommended - vocabulary system addresses real pain points

### Alternative 2: Just Use Templates

**Pros**:
- Simpler to implement (Jinja2 templates)
- Already familiar to developers
- No need for mining/packs

**Cons**:
- No metadata or tracking
- No cross-app learning
- No automatic pattern detection
- Template versioning is hard

**Verdict**: ❌ Too limited - doesn't enable ecosystem growth

### Alternative 3: Full Macro System (Lisp-style)

**Pros**:
- Maximum flexibility
- Can implement complex abstractions
- Industry-proven (Rust, Lisp)

**Cons**:
- Enormous complexity
- Hard to debug
- Steeper learning curve
- Could diverge from core DSL philosophy

**Verdict**: ❌ Overkill - proposed spec is right level of power

---

## Recommendation

### ✅ PROCEED with Phased Implementation

**Start with Phase 1** (Foundation) immediately:
1. Implement vocabulary schema and expander
2. Add basic CLI commands
3. Integrate into build pipeline
4. Ship in **DAZZLE v0.2.0**

**Then assess**:
- Gather user feedback
- Measure adoption
- Validate technical approach
- Decide whether to continue to Phase 2

**Key Success Factors**:
1. **Keep it simple** - resist feature creep
2. **Focus on UX** - make it easy to create and use vocab
3. **Documentation first** - write guides before code
4. **Iterate based on data** - use metrics to guide decisions
5. **Community involvement** - gather feedback early and often

---

## Open Questions

1. **Vocabulary syntax in DSL**: How do users reference vocab?
   - Option A: Special syntax (e.g., `@use user_profile_panel(...)`)
   - Option B: Core DSL extension (e.g., `vocab: user_profile_panel`)
   - **Recommendation**: Option A - keeps core DSL unchanged

2. **Expansion timing**: When to expand vocab?
   - Option A: Preprocessing (before parsing)
   - Option B: During parsing
   - Option C: Post-parsing (IR manipulation)
   - **Recommendation**: Option A - simpler and cleaner

3. **Extension pack distribution**: Where to host packs?
   - Option A: GitHub repos (like Homebrew taps)
   - Option B: PyPI packages
   - Option C: DAZZLE registry service
   - **Recommendation**: Start with GitHub, consider registry later

4. **LLM integration**: Which model(s) to use?
   - Option A: Claude (best for code understanding)
   - Option B: GPT-4 (good balance)
   - Option C: Both (user choice)
   - **Recommendation**: Support both, default to Claude

---

## Conclusion

The App-Local Vocabulary specification is **well-designed and strategically important** for DAZZLE's evolution. It addresses real developer needs while preserving the simplicity of the core DSL.

**Recommended Action**: **Approve Phase 1 implementation** with the understanding that this is a long-term investment (6-8 months to completion) that will significantly enhance DAZZLE's value proposition.

**Priority**: **Medium-High** - important for competitive positioning but not blocking current releases.

**Timeline**: Start Phase 1 after completing current bug fixes and enhancements (v0.1.2 release).
