# DAZZLE 0.1 - Staged Implementation Plan

This document outlines a phased approach to implementing the missing core components of DAZZLE 0.1.

## Current State

### ✅ Completed
- Project structure and file organization
- CLI skeleton with Typer (validate, lint, build commands)
- Project manifest loading (`manifest.py`)
- DSL file discovery (`fileset.py`)
- Basic module parsing (extracts `module` and `use` declarations only)
- Documentation (README, DSL reference, grammar, examples)

### ⏳ In Progress / Missing
- Full DSL parser implementation
- IR type definitions (`ir.py`)
- Module linker (merge and resolve)
- Comprehensive validation rules
- Error types and reporting
- Backend plugin system
- All backend implementations

---

## Stage 1: Foundation - IR and Error Types

**Goal**: Define the complete IR type system and error handling framework.

**Why First**: The IR is the source of truth. All other components (parser, linker, validators, backends) depend on having well-defined IR types.

### Tasks

1. **Create `src/dazzle/core/errors.py`**
   - `DazzleError` base exception
   - `ParseError` for DSL syntax errors (with line/column info)
   - `LinkError` for module resolution failures
   - `ValidationError` for semantic errors
   - Error context helpers (file, line, column, snippet)

2. **Create `src/dazzle/core/ir.py`**

   Define Pydantic models for:

   - **Core types**:
     - `FieldType` (str, text, int, decimal, bool, date, datetime, uuid, enum, ref, email)
     - `FieldModifier` (required, optional, pk, unique, auto_add, auto_update, default)
     - `FieldSpec` (name, type, modifiers)

   - **Domain**:
     - `EntitySpec` (name, title, fields, constraints, indexes)
     - `DomainSpec` (entities list)

   - **Surfaces**:
     - `SurfaceMode` (view, create, edit, list, custom)
     - `SurfaceElement` (field references with labels/options)
     - `SurfaceSection` (name, title, elements)
     - `SurfaceAction` (name, label, trigger, outcome)
     - `SurfaceSpec` (name, title, entity_ref, mode, sections, actions)

   - **Experiences**:
     - `StepKind` (surface, process, integration)
     - `StepTransition` (on_success, on_failure)
     - `ExperienceStep` (name, kind, target, transitions)
     - `ExperienceSpec` (name, title, start_step, steps)

   - **Services**:
     - `AuthProfile` (kind, options)
     - `ServiceSpec` (name, title, spec_url, auth_profile, owner)

   - **Foreign Models**:
     - `ForeignConstraint` (read_only, event_driven, batch_import)
     - `ForeignModelSpec` (name, title, service_ref, key_fields, constraints, fields)

   - **Integrations**:
     - `IntegrationAction` (name, when_surface, call_spec, mapping)
     - `IntegrationSync` (name, mode, schedule, from_spec, into_entity, match_rules)
     - `IntegrationSpec` (name, title, service_refs, foreign_model_refs, actions, syncs)

   - **Top-level**:
     - `AppSpec` (name, title, version, domain, surfaces, experiences, services, foreign_models, integrations, metadata)
     - `ModuleIR` (update existing in parser.py to include parsed fragments)

3. **Update `parser.py`**
   - Extend `ModuleIR` to store parsed IR fragments (entities, surfaces, etc.)
   - Keep parsing lightweight for now (just store raw text, parse in Stage 2)

### Acceptance Criteria
- All IR types defined with proper Pydantic validation
- Error types support rich context (file, line, message)
- IR types have docstrings explaining their purpose
- Can instantiate sample `AppSpec` programmatically

### Estimated Complexity
**Medium** - Well-defined structure from docs, mainly translation work

---

## Stage 2: Parser - DSL to IR

**Goal**: Implement full DSL parsing to convert `.dsl` files into IR fragments.

**Dependencies**: Stage 1 (IR types must exist)

### Tasks

1. **Design Parser Architecture**
   - Choose approach: hand-written recursive descent vs. parser combinator library
   - Recommendation: Start with hand-written for simplicity and control
   - Handle indentation-based blocks (Python-style)
   - Track source locations for error reporting

2. **Implement Lexer/Tokenizer** (if using hand-written parser)
   - Tokenize identifiers, strings, numbers, keywords, operators
   - Handle indentation (INDENT/DEDENT tokens)
   - Strip comments
   - Track line/column positions

3. **Implement Parser for Each Construct**

   Build parsers in this order (simplest to most complex):

   - **App declaration**: `app <name> "<title>"`
   - **Entity declarations**: fields, constraints, indexes
   - **Surface declarations**: sections, fields, actions
   - **Service declarations**: spec, auth_profile, owner
   - **Foreign model declarations**: keys, constraints, fields
   - **Experience declarations**: steps, transitions
   - **Integration declarations**: actions, syncs, mappings
   - **Module/use declarations**: Already partially done

4. **Update `parse_modules()` in `parser.py`**
   - Parse full DSL into IR fragments
   - Populate `ModuleIR` with parsed entities, surfaces, etc.
   - Return rich syntax errors with line/column info

5. **Add Parser Tests**
   - Unit tests for each construct type
   - Test error cases (syntax errors, malformed input)
   - Test multi-file scenarios
   - Use examples from `docs/DAZZLE_EXAMPLES_0_1.dsl` and `examples/`

### Acceptance Criteria
- Can parse all examples in `examples/` directory
- Parse errors include helpful messages with line/column
- All DSL constructs from grammar are supported
- Parser tests have >90% coverage of happy paths

### Estimated Complexity
**High** - Most complex stage, requires careful attention to grammar details

---

## Stage 3: Linker - Module Resolution

**Goal**: Merge parsed modules into a unified `AppSpec`, resolving cross-module references.

**Dependencies**: Stage 2 (parser must produce IR fragments)

### Tasks

1. **Implement Dependency Resolution**
   - Build module dependency graph from `use` declarations
   - Detect cycles in module dependencies
   - Topologically sort modules for processing order
   - Error on missing/unresolved modules

2. **Implement Symbol Table**
   - Track all entities, surfaces, services, foreign_models across modules
   - Support qualified names (module.Entity vs Entity)
   - Detect duplicate definitions
   - Build lookup index for reference resolution

3. **Implement Fragment Merging**
   - Merge entities from all modules into single domain
   - Collect surfaces, experiences, services, foreign_models, integrations
   - Preserve source module info for error reporting

4. **Implement Reference Resolution**
   - Resolve entity references in fields (`ref Client`)
   - Resolve surface references in experiences and actions
   - Resolve service references in integrations
   - Resolve foreign model references in integrations
   - Track unresolved references for error reporting

5. **Update `build_appspec()` in `linker.py`**
   - Replace stub with full implementation
   - Return complete, linked `AppSpec`
   - Raise `LinkError` for unresolvable references

6. **Add Linker Tests**
   - Test single-module specs
   - Test multi-module specs with dependencies
   - Test cycle detection
   - Test missing module errors
   - Test duplicate definition errors

### Acceptance Criteria
- Can link multi-module projects successfully
- Detects and reports all types of link errors
- Preserves source location info through linking
- All references are resolved or errors reported

### Estimated Complexity
**Medium-High** - Complex graph algorithms but well-defined requirements

---

## Stage 4: Validator - Semantic Checks

**Goal**: Implement comprehensive validation rules for `AppSpec`.

**Dependencies**: Stage 3 (linker must produce complete AppSpec)

### Tasks

1. **Implement Entity Validation**
   - All entities have primary key
   - Field types are valid
   - Enum values are valid identifiers
   - References point to existing entities
   - Unique/index constraints reference existing fields
   - No duplicate field names

2. **Implement Surface Validation**
   - Referenced entities exist
   - Surface fields match entity fields (or are valid for the mode)
   - Actions reference valid outcomes (surfaces, experiences, integrations)
   - Modes are appropriate for sections/actions

3. **Implement Experience Validation**
   - Start step exists
   - All steps are reachable from start
   - Step kinds match their targets (surface steps → surfaces)
   - Transitions reference existing steps
   - No orphaned steps
   - No infinite loops without exit

4. **Implement Service Validation**
   - Spec URLs are valid
   - Auth profiles use supported kinds
   - Required fields are present

5. **Implement Foreign Model Validation**
   - Service references exist
   - Key fields exist in field list
   - Field types are valid
   - Constraints are valid

6. **Implement Integration Validation**
   - Service references exist
   - Foreign model references exist
   - Entity references exist
   - Surface references (in `when` clauses) exist
   - Mapping expressions reference valid paths
   - Sync schedules are valid cron expressions (if scheduled mode)

7. **Implement Extended Lint Rules** (for `--strict` mode)
   - Naming conventions (snake_case, PascalCase)
   - Unused surfaces/entities
   - Dead code detection
   - Unused `use` declarations
   - Missing descriptions/titles

8. **Update `lint_appspec()` in `lint.py`**
   - Replace stub with full validation
   - Return separate lists of errors and warnings
   - Support extended mode for stricter checks

9. **Add Validator Tests**
   - Test each validation rule individually
   - Test valid specs pass validation
   - Test invalid specs produce expected errors
   - Test warning-level issues

### Acceptance Criteria
- All validation rules from requirements are implemented
- Validation errors are clear and actionable
- Extended lint mode catches style issues
- Examples pass validation without errors

### Estimated Complexity
**Medium** - Many rules but each is straightforward

---

## Stage 5: Backend Plugin System

**Goal**: Define backend plugin interface and registry.

**Dependencies**: Stage 1 (IR types), Stage 4 (need validated AppSpec)

### Tasks

1. **Create `src/dazzle/backends/__init__.py`**
   - Define `Backend` abstract base class
   - Required method: `generate(appspec: AppSpec, output_dir: Path) -> None`
   - Optional methods: `validate_config()`, `get_capabilities()`

2. **Create Backend Registry**
   - `register_backend(name: str, backend_class: Type[Backend])`
   - `get_backend(name: str) -> Backend`
   - Auto-discover backends in `backends/` directory

3. **Update CLI `build` Command**
   - Use backend registry to load requested backend
   - Pass validated AppSpec to backend
   - Handle backend errors gracefully

4. **Add Plugin Tests**
   - Test backend registration
   - Test backend discovery
   - Test error handling for missing backends

### Acceptance Criteria
- Backend interface is clean and minimal
- Registry supports multiple backends
- Easy to add new backends without modifying core

### Estimated Complexity
**Low** - Simple abstraction layer

---

## Stage 6: First Backend - OpenAPI

**Goal**: Implement OpenAPI spec generation as proof of concept.

**Dependencies**: Stage 5 (backend plugin system)

### Tasks

1. **Create `src/dazzle/backends/openapi.py`**
   - Implement `Backend` interface
   - Generate OpenAPI 3.0 spec from `AppSpec`

2. **Map DAZZLE Concepts to OpenAPI**
   - Entities → Schemas (components/schemas)
   - Surfaces (list/view) → GET endpoints
   - Surfaces (create) → POST endpoints
   - Surfaces (edit) → PUT/PATCH endpoints
   - Experiences → Multi-step operation flows (operationId links)
   - Services → External API references (not directly generated)

3. **Generate OpenAPI Structure**
   - Info section (from app name/title/version)
   - Paths (from surfaces)
   - Schemas (from entities)
   - Tags (group by entity)
   - Security schemes (placeholder for auth)

4. **Output OpenAPI Document**
   - Write to `{output_dir}/openapi.yaml` or `openapi.json`
   - Validate output against OpenAPI 3.0 schema

5. **Add Backend Tests**
   - Test generation for each entity type
   - Test path generation for each surface mode
   - Test output is valid OpenAPI 3.0
   - Test with example specs

### Acceptance Criteria
- Generated OpenAPI specs validate successfully
- All DAZZLE examples produce valid OpenAPI output
- Output can be imported into tools like Swagger UI or Postman

### Estimated Complexity
**Medium** - Requires understanding OpenAPI spec structure

---

## Stage 7: Testing and Integration

**Goal**: End-to-end testing and polish.

**Dependencies**: All previous stages

### Tasks

1. **Create Integration Tests**
   - Full pipeline tests: DSL → IR → AppSpec → Generated Output
   - Test with all example DSL files
   - Test multi-file projects
   - Test error paths end-to-end

2. **Add CLI Tests**
   - Test all CLI commands (validate, lint, build)
   - Test flag combinations
   - Test error output format
   - Test manifest loading with various configs

3. **Create Additional Examples**
   - E-commerce platform example
   - CRM system example
   - Document management example
   - Demonstrate all DSL features

4. **Documentation Updates**
   - Add implementation notes to README
   - Create backend authoring guide
   - Add troubleshooting section
   - Document error messages

5. **Polish Error Messages**
   - Ensure all errors have clear, actionable messages
   - Add "did you mean?" suggestions where applicable
   - Include relevant code snippets in error output

6. **Performance Testing**
   - Test with large DSL files (1000+ entities)
   - Optimize parsing/linking if needed
   - Profile memory usage

### Acceptance Criteria
- All tests pass
- All examples work end-to-end
- Error messages are helpful
- Performance is acceptable for medium-sized projects

### Estimated Complexity
**Medium** - Time-consuming but straightforward

---

## Stage 8: Optional Enhancements

**Goal**: Nice-to-have features for v0.1.

**Dependencies**: Stage 7 (core complete)

### Tasks (pick based on priorities)

1. **IDE Support**
   - Language server protocol (LSP) for DSL
   - Syntax highlighting definitions (VS Code, Sublime, etc.)
   - Auto-completion for DSL keywords

2. **Additional Backends**
   - `django_drf` backend (Django models + DRF serializers)
   - `fastapi` backend (FastAPI routers + Pydantic models)
   - `react_ui` backend (UI schema for code generation)
   - `infra` backend (Infrastructure templates)

3. **DSL Formatter**
   - Canonical formatting for DSL files
   - `dazzle fmt` command

4. **DSL Linter Auto-fixes**
   - `dazzle lint --fix` to auto-correct style issues

5. **Watch Mode**
   - `dazzle watch` to auto-rebuild on file changes

6. **Diff Tool**
   - Compare two AppSpec versions
   - Show semantic differences between DSL revisions

7. **Interactive Mode**
   - REPL for exploring IR
   - Query entities, surfaces, etc. interactively

### Estimated Complexity
**Variable** - Each enhancement is independent

---

## Implementation Strategy

### Order of Execution
Follow stages 1-7 in sequence. Each stage builds on the previous.

### Incremental Validation
After each stage, ensure:
- All existing tests still pass
- New tests are added for new functionality
- Examples still work (or work better)
- CLI commands remain functional

### Testing Philosophy
- Write tests alongside implementation, not after
- Test error cases as thoroughly as happy paths
- Use example DSL files as integration test fixtures
- Keep unit tests fast (<100ms each)

### Code Style
- Follow PEP 8 for Python code
- Use type hints throughout
- Use Pydantic for all IR types (validation + serialization)
- Keep functions small and focused
- Document complex algorithms

### Git Workflow (if using version control)
- One branch per stage
- Merge to main after stage completion
- Tag releases (v0.1.0-stage1, v0.1.0-stage2, etc.)

---

## Risk Management

### High-Risk Areas

1. **Parser Complexity**
   - Risk: Custom parser becomes unmaintainable
   - Mitigation: Keep grammar simple; consider parser generator if hand-written gets too complex
   - Fallback: Use existing Python parsing library (Lark, pyparsing)

2. **Performance with Large Specs**
   - Risk: Linking/validation is too slow for real projects
   - Mitigation: Profile early, optimize hot paths
   - Fallback: Add caching/incremental compilation

3. **Backend Interface Stability**
   - Risk: Interface changes break all backends
   - Mitigation: Version backend API; keep it minimal
   - Fallback: Support multiple backend API versions

### Medium-Risk Areas

1. **Error Message Quality**
   - Risk: Users get cryptic errors
   - Mitigation: Test all error paths; get user feedback
   - Fallback: Add verbose mode with full stack traces

2. **Module System Complexity**
   - Risk: Dependency resolution is buggy
   - Mitigation: Extensive testing with various module graphs
   - Fallback: Start with single-file projects first

---

## Success Metrics

### Stage 1-4 Complete
- Can parse, link, and validate all example DSL files
- Error messages are clear and helpful
- Test coverage >80%

### Stage 5-6 Complete
- Can generate valid OpenAPI specs from examples
- Backend plugin system works smoothly
- Easy to add new backends

### Stage 7 Complete
- All CLI commands work end-to-end
- Documentation is complete
- Ready for early adopter feedback

### Stage 8 Complete (Optional)
- Additional backends available
- IDE support makes DSL authoring pleasant
- Community contributors can extend DAZZLE

---

## Timeline Estimates

Assuming one developer working full-time:

| Stage | Duration | Cumulative |
|-------|----------|------------|
| Stage 1: IR & Errors | 3-5 days | 5 days |
| Stage 2: Parser | 7-10 days | 15 days |
| Stage 3: Linker | 5-7 days | 22 days |
| Stage 4: Validator | 4-6 days | 28 days |
| Stage 5: Backend System | 2-3 days | 31 days |
| Stage 6: OpenAPI Backend | 4-5 days | 36 days |
| Stage 7: Testing & Polish | 5-7 days | 43 days |
| **Total (Stages 1-7)** | **~6-9 weeks** | |
| Stage 8: Enhancements | 2-4 weeks (varies) | Optional |

These are estimates for a single developer familiar with parsing and compiler concepts. Adjust based on team size and experience.

---

## Next Steps

To begin implementation:

1. Review this plan with stakeholders
2. Set up testing infrastructure (pytest, CI/CD)
3. Start with Stage 1 (IR definitions)
4. Commit after each stage completion
5. Update this plan if requirements change

For questions or clarifications, refer to:
- `README.md` - High-level philosophy
- `docs/DAZZLE_DSL_REFERENCE_0_1.md` - DSL syntax
- `docs/DAZZLE_DSL_GRAMMAR_0_1.ebnf` - Formal grammar
- `CLAUDE.md` - Development guidance
