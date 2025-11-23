# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**DAZZLE v0.1.0** - Complete DSL-to-Code Generation System

DAZZLE (Domain-Aware, Token-Efficient DSL for LLM-Enabled Apps) is a production-ready toolkit where:
- Humans describe business intent in natural language or directly in DSL
- LLMs can translate requirements into compact DSL (optional)
- Tooling parses DSL into an internal representation (IR)
- Stacks generate concrete artifacts (APIs, UIs, infrastructure, databases)

**Status**: Released November 2025, actively maintained, production-ready
**Stacks**: 6 implemented (Django Micro, Django API, Express Micro, OpenAPI, Docker, Terraform)
**Distribution**: Homebrew, PyPI-ready, multiple installation methods

---

## Current Implementation Status (v0.1.0)

### ✅ Fully Complete

**Core Engine**:
- **DSL Parser**: 800+ lines, handles all DSL constructs (entities, surfaces, experiences, services, foreign models, integrations, tests)
- **Internal Representation (IR)**: 900+ lines, complete Pydantic models with full type safety
- **Module System**: Dependency resolution, cycle detection, topological sorting, reference validation
- **Linker**: Merges modules, resolves dependencies, validates cross-references
- **Validation**: Comprehensive lint rules, type checking, reference validation, use-declaration enforcement
- **Pattern Detection**: CRUD patterns, integration patterns, experience flow analysis
- **Error Handling**: Rich error types with file/line/column context

**Stack Generation** (6 Production Stacks):
- **django_micro_modular**: Complete Django apps with admin, forms, views, templates, tests
- **django_api**: Django REST Framework APIs with serializers, viewsets, OpenAPI integration
- **express_micro**: Node.js/Express equivalent with Sequelize ORM, EJS templates, AdminJS
- **openapi**: OpenAPI 3.0 spec generation with schemas, paths, components
- **docker**: Docker Compose setups with multi-service orchestration
- **terraform**: AWS infrastructure as code (ECS, RDS, VPC, ALB)

**LLM Integration**:
- Spec analysis (natural language → structured requirements)
- DSL generation (requirements → .dsl files)
- Interactive Q&A for clarifications
- Cost estimation and safety checks
- Supports Anthropic Claude and OpenAI GPT

**IDE & Tooling**:
- **LSP Server**: Real-time diagnostics, hover info, completions, go-to-definition
- **VS Code Extension**: Full IDE integration with syntax highlighting and validation
- **CLI**: init, validate, lint, build, inspect, analyze-spec, clone, demo
- **Test Suite**: 59+ tests (unit, integration, LLM), pytest-based, CI/CD with GitHub Actions
- **Distribution**: Homebrew formula, PyPI packaging, multiple install methods

**Documentation**:
- Complete DSL reference and EBNF grammar
- IR documentation with examples
- Stack development guides
- VS Code extension user guide
- LLM integration documentation

### 🚧 Partially Complete

- **Integration actions/syncs parsing**: Uses functional stubs (can parse blocks but creates placeholder data)
- **OpenAPI security schemes**: Placeholder implementation (users can add manually)

### 📋 Planned for Future Versions

- **Export declarations** (v2.0): `export entity Foo` for module encapsulation
- **Port-based composition** (v2.0): Graph-theoretic module composition
- **Formal verification** (v2.0): Mathematical guarantees about composed systems
- **Additional stacks**: Community-driven (Next.js, Vue, FastAPI, etc.)

---

## Architecture

### Three-Layer Model (FULLY IMPLEMENTED)

1. **DSL Layer** → `.dsl` files
   - Token-efficient, human-readable specifications
   - Defines entities, surfaces, experiences, services, foreign models, integrations, tests
   - Located in `dsl/` directory (or paths specified in `dazzle.toml`)
   - **Implementation**: `src/dazzle/core/dsl_parser.py` (800+ lines)

2. **IR Layer** → Internal Representation
   - Structured, typed model built from DSL using Pydantic
   - Immutable (frozen=True) for thread safety and predictability
   - Source of truth for all code generation
   - **Implementation**: `src/dazzle/core/ir.py` (900+ lines, complete type system)

3. **Stack Layer** → Code Generation
   - Plugins that consume IR to produce artifacts
   - Each stack is self-contained and independent
   - Extensible plugin architecture with base classes
   - **Implementation**: `src/dazzle/stacks/` (6 production stacks)

### Module System

- DSL files declare `module <name>` at the top (e.g., `module vat_tools.core`)
- Modules declare dependencies via `use <module_name>` directives
- Project manifest (`dazzle.toml`) defines root module and DSL paths
- Linker performs topological sort, detects cycles, validates references
- **Strict enforcement**: Modules must declare `use` for cross-module references (as of v0.1.0)

---

## Core Components (All Implemented)

### CLI (`src/dazzle/cli.py`)

**Project Creation**:
- `init`: Initialize new project (with optional `--from example`)
- `clone`: Clone example apps with stack selection
- `demo`: Create demo project with specific stack

**Validation & Analysis**:
- `validate`: Parse, link, and validate DSL (with use-declaration checking)
- `lint`: Extended validation rules (naming, dead modules, unused imports)
- `inspect`: **NEW** - Show module interfaces, patterns, type catalog

**Code Generation**:
- `build`: Generate artifacts from AppSpec using stacks
- `stacks`: List available stacks and presets

**LLM Integration**:
- `analyze-spec`: Parse natural language requirements with LLM
- Supports interactive Q&A and DSL generation

**Examples**:
- `example`: Build built-in examples in-situ

### Core Engine (`src/dazzle/core/`)

- **`manifest.py`**: Loads `dazzle.toml` project configuration
- **`fileset.py`**: Discovers DSL files based on manifest paths
- **`dsl_parser.py`**: Complete DSL parser (800+ lines)
  - Parses all DSL constructs into IR
  - Handles indentation-based blocks
  - Supports comments (#)
  - Extracts module dependencies
- **`ir.py`**: Full IR type system (900+ lines)
  - Complete Pydantic models for all DSL constructs
  - Immutable (frozen=True) for safety
  - Type-safe with validation
- **`linker.py` + `linker_impl.py`**: Module linking
  - Dependency resolution with topological sort
  - Cycle detection
  - Symbol table building
  - Reference validation
  - Module access validation (enforces `use` declarations)
  - Fragment merging
- **`lint.py`**: Comprehensive validation
  - Type checking
  - Reference validation
  - Constraint validation
  - Naming conventions (extended mode)
- **`errors.py`**: Rich error types
  - ParseError, LinkError, ValidationError
  - File/line/column context
  - Helpful error messages
- **`patterns.py`**: Pattern detection
  - CRUD pattern detection
  - Integration pattern analysis
  - Experience flow analysis (cycles, unreachable steps)

### Stacks (`src/dazzle/stacks/`)

Each stack is self-contained:

**Django Micro Modular** (`django_micro_modular/`):
- Complete Django project generator
- Models, admin, forms, views, templates
- SQLite database
- Professional styling
- Post-build hooks (migrations, admin creation)
- Tests with pytest-django

**Django API** (`django_api.py`):
- Django REST Framework setup
- Serializers, viewsets, routers
- OpenAPI integration
- CORS configuration
- Token authentication

**Express Micro** (`express_micro.py`):
- Node.js/Express application
- Sequelize ORM models
- EJS templates
- AdminJS interface
- SQLite database

**OpenAPI** (`openapi.py`):
- OpenAPI 3.0 specification generation
- Schemas from entities
- Paths from surfaces
- Components and references
- Validation with schemathesis

**Docker** (`docker.py`):
- Docker Compose configuration
- Multi-service orchestration
- Database services
- Environment configuration
- Health checks

**Terraform** (`terraform.py`):
- AWS infrastructure as code
- ECS, RDS, VPC, ALB resources
- Multi-environment support
- Modular structure
- State management

**Base System** (`base/`):
- Common utilities and hooks
- Shared templates
- Base backend class
- Hook system for post-generation tasks

### LLM Integration (`src/dazzle/llm/`)

- **`spec_analyzer.py`**: Parse natural language specs
  - Extracts state machines, CRUD operations, business rules
  - Generates clarifying questions
  - Supports Anthropic Claude and OpenAI GPT
- **`dsl_generator.py`**: Generate DSL from analysis
  - Converts structured requirements to .dsl files
  - Maintains DSL conventions
  - Validates generated output
- **`models.py`**: Pydantic models for LLM interactions
- **`client.py`**: LLM provider abstractions

### LSP Server (`src/dazzle/lsp/`)

- Real-time diagnostics as you type
- Hover information for DSL constructs
- Go-to-definition for entities, surfaces, etc.
- Auto-completion suggestions
- Signature help
- Works with VS Code extension and other LSP clients

---

## DSL Concepts

The DSL vocabulary is intentionally compact for token efficiency:

- **app**: Root declaration with name and title
- **module**: Module declaration for multi-file projects
- **use**: Import dependencies from other modules
- **entity**: Internal domain models (with fields, constraints, indexes)
- **surface**: User-facing screens/forms (with sections, fields, actions)
- **experience**: Orchestrated flows with steps and transitions
- **service**: External third-party systems (with auth profiles)
- **foreign_model**: External data shapes from services
- **integration**: Connections between entities, foreign models, and services
- **test**: Test specifications for generated code

**See**: `docs/DAZZLE_DSL_REFERENCE_0_1.md` for full syntax and `docs/DAZZLE_DSL_GRAMMAR_0_1.ebnf` for formal grammar.

---

## Common Development Commands

### Project Lifecycle

```bash
# Create new project
dazzle init                              # Blank project
dazzle init --from simple_task           # From example

# Or clone with stack selection
dazzle clone simple_task --stack micro

# Validate DSL
dazzle validate                          # Parse, link, validate
dazzle lint                              # Extended validation
dazzle lint --strict                     # Warnings as errors

# Generate code
dazzle build                             # Default stack (micro)
dazzle build --stack openapi             # Single stack
dazzle build --stack django_api,docker   # Multiple stacks
```

### New Commands in v0.1.0

```bash
# Inspect module structure and patterns
dazzle inspect                           # All information
dazzle inspect --patterns --types        # With type catalog
dazzle inspect --no-interfaces           # Just patterns

# Analyze natural language specifications
dazzle analyze-spec SPEC.md              # Interactive Q&A
dazzle analyze-spec SPEC.md --generate-dsl  # Auto-generate DSL

# Quick examples
dazzle example simple_task               # Build example in-place
dazzle demo                              # Create demo project
```

### Development Workflow

```bash
# Work in dev environment (auto-activated in project directory)
cd /Volumes/SSD/Dazzle                   # Auto-activates dazzle-dev virtualenv

# Make changes to code
vim src/dazzle/core/parser.py

# Test immediately (editable install - no reinstall needed!)
dazzle validate
pytest tests/unit/test_parser.py

# Commit changes
git add .
git commit -m "feat: add new feature"
```

---

## Development Guidelines

### Adding New Stacks

Each stack must:
1. Subclass `BaseBackend` from `src/dazzle/stacks/base/base.py`
2. Implement `generate(appspec, output_dir, artifacts=None)` method
3. Provide `get_capabilities()` returning `StackCapabilities`
4. Register in `src/dazzle/stacks/__init__.py`
5. Add tests in `tests/unit/test_backends.py`
6. Document in `docs/CAPABILITIES_MATRIX.md` (when created)

**Example Structure**:
```python
from dazzle.stacks.base import BaseBackend, StackCapabilities

class MyStack(BaseBackend):
    def get_capabilities(self) -> StackCapabilities:
        return StackCapabilities(
            name="my_stack",
            description="My custom stack",
            output_formats=["code", "config"],
            supports_incremental=False
        )

    def generate(self, spec: ir.AppSpec, output_dir: Path, artifacts=None):
        # Generate code from spec
        ...
```

### Extending the DSL

Changes require updates to:
1. **`docs/DAZZLE_DSL_REFERENCE_0_1.md`** - User documentation
2. **`docs/DAZZLE_DSL_GRAMMAR_0_1.ebnf`** - Formal grammar
3. **`src/dazzle/core/dsl_parser.py`** - Parser implementation
4. **`src/dazzle/core/ir.py`** - IR types (if new constructs)
5. **`tests/unit/test_parser.py`** - Parser tests
6. **All stacks** - Update to handle new construct

**Process**:
1. Design the DSL syntax (keep it token-efficient!)
2. Update grammar and reference docs
3. Add IR types with Pydantic models
4. Implement parser
5. Add tests
6. Update stacks to generate code for new construct

### Code Quality Standards

**Formatting & Linting**:
- Use `ruff` for linting and formatting
- Run `ruff format src/ tests/` before committing
- Run `ruff check src/ tests/ --fix` to auto-fix issues

**Type Checking**:
- All code uses type hints
- Enforced by `mypy`
- Run `mypy src/dazzle` to check

**Testing**:
- Tests required for new features
- Use pytest: `pytest tests/`
- Check coverage: `pytest tests/ --cov=dazzle`
- Tests must pass before merging

**Documentation**:
- Update docs with code changes
- Add docstrings to all public functions
- Include examples in docstrings
- Keep CLAUDE.md in sync with implementation

### Development Environment

**Setup** (first time):
```bash
# Clone repository
git clone https://github.com/manwithacat/dazzle.git
cd dazzle

# Create virtualenv (using pyenv)
pyenv virtualenv 3.12.11 dazzle-dev
echo "dazzle-dev" > .python-version

# Install in editable mode with all extras
pip install -e '.[llm,dev]'
pip install pygls  # For LSP support

# Verify
dazzle --version
pytest tests/
```

**Daily Development**:
```bash
# Navigate to project (auto-activates virtualenv)
cd /Volumes/SSD/Dazzle

# Verify dev environment
pyenv version  # Should show: dazzle-dev

# Make changes and test immediately (editable install!)
vim src/dazzle/cli.py
dazzle --version  # Runs your modified code immediately

# Run tests
pytest tests/unit/test_cli.py

# Format code
ruff format src/ tests/
ruff check src/ tests/ --fix

# Type check
mypy src/dazzle
```

**See**: `dev_docs/dual_version_workflow.md` for details on managing dev vs homebrew installations.

---

## Examples

DAZZLE includes complete example projects in `examples/`:

### simple_task (`examples/simple_task/`)
- **Purpose**: Starter project, learn DSL basics
- **Entities**: 1 (Task)
- **Surfaces**: 4 (list, detail, create, edit)
- **Complexity**: Minimal - perfect for learning
- **Generates**: Working Django or Express app in 5 minutes

```bash
dazzle clone simple_task
cd simple_task
dazzle validate && dazzle build
```

### support_tickets (`examples/support_tickets/`)
- **Purpose**: Production-like complexity
- **Entities**: 3 (User, Ticket, Comment)
- **Features**: Relationships, experiences, integrations
- **Complexity**: Moderate - real-world patterns
- **Generates**: Multi-entity system with workflows

```bash
dazzle clone support_tickets --stack django_next
cd support_tickets
dazzle validate && dazzle build
```

---

## Documentation

### Core Documentation (`docs/`)
- **`README.md`**: Project overview, quick start, installation
- **`DAZZLE_DSL_REFERENCE_0_1.md`**: Complete DSL syntax reference
- **`DAZZLE_DSL_GRAMMAR_0_1.ebnf`**: Formal EBNF grammar
- **`DAZZLE_IR_0_1.md`**: IR structure and examples
- **`DAZZLE_EXAMPLES_0_1.dsl`**: Additional DSL examples
- **`vscode_extension_user_guide.md`**: VS Code extension features
- **`vscode_extension_quick_reference.md`**: Quick reference card

### Development Documentation (`dev_docs/`)
- **`development/stages/`**: Stage 1-7 completion reports (all complete)
- **`releases/`**: Release summaries and announcements
- **`features/`**: Feature specifications and design docs
- **`llm/`**: LLM integration documentation
- **`gap_analysis_2025_11_23.md`**: Current gaps and improvements
- **`NEXT_STAGES_SPEC.md`**: Detailed specs for upcoming work
- **`dual_version_workflow.md`**: Dev environment management

### Testing Documentation (`tests/`)
- **`unit/`**: Component tests (IR, parser, linker, stacks, CLI)
- **`integration/`**: End-to-end pipeline tests, golden master tests
- **`llm/`**: LLM integration tests
- **`fixtures/`**: Test data and example DSL files
- **`conftest.py`**: Shared pytest fixtures

---

## Python Environment

- **Python**: 3.11+ required (3.12+ recommended)
- **Package Manager**: pip, pipx, or uv
- **Virtualenv**: pyenv-virtualenv recommended for development
- **Dependencies**:
  - Core: Typer, Pydantic, PyYAML, Jinja2
  - LLM (optional): anthropic, openai
  - LSP (optional): pygls
  - Dev (optional): pytest, mypy, ruff, coverage

**Installation Methods**:
```bash
# Homebrew (recommended for users)
brew tap manwithacat/tap
brew install dazzle

# pipx (fast alternative)
pipx install dazzle

# uv (fastest)
uv pip install dazzle

# pip (standard)
pip install dazzle

# Development (editable)
pip install -e '.[llm,dev]'
```

---

## Design Philosophy

### Core Principles

1. **Token Efficiency Over Verbosity**
   - DSL is compact to minimize LLM token costs
   - Every keyword earns its place
   - Implicit > Explicit when safe

2. **Machine-First, Human-Executive**
   - LLMs can generate and mutate specs
   - Humans guide intent and review output
   - Both can read and understand the DSL

3. **Framework-Agnostic Core**
   - IR and DSL not tied to any framework
   - Stacks handle framework specifics
   - Same DSL → Multiple targets

4. **Deterministic Generation**
   - Only DSL generation uses LLMs (optional)
   - Parsing, validation, and codegen are deterministic
   - Reproducible builds

5. **Intent-Based, Not Implementation-Based**
   - DSL expresses "what" and "why"
   - Implementation details in stacks
   - Same intent → Different implementations

### Recent Additions (v0.1.0)

**Quick Wins Features** (added Nov 23, 2025):
- **Type Catalog**: `appspec.type_catalog` extracts all field types
- **Stricter Use Validation**: Modules must declare dependencies
- **Pattern Detection**: Automatic CRUD, integration, experience analysis
- **Inspect Command**: `dazzle inspect` shows module interfaces and patterns

These features lay groundwork for v2.0's graph-theoretic normalization while providing immediate value.

---

## Testing with AI Assistants

DAZZLE is designed to be LLM-friendly. Try this prompt with a fresh AI assistant:

```
You're exploring a new codebase. This folder contains a DSL-based application project.

Your task:
  1. Investigate: Figure out what framework/tool this uses and what it does
  2. Validate: Ensure the configuration is correct
  3. Build: Generate the application artifacts
  4. Verify: Confirm the build was successful

Work step-by-step. Explain your reasoning as you go. If you encounter issues,
troubleshoot and document your fixes.

Success criteria:
  - You understand what the project does
  - All validation passes
  - Artifacts are generated
  - You can explain what was built
```

**Expected Behavior**:
- ✅ Discovers `dazzle.toml` manifest
- ✅ Identifies DAZZLE project
- ✅ Locates DSL files
- ✅ Runs `dazzle validate`
- ✅ Runs `dazzle build` with appropriate stack
- ✅ Explains generated artifacts

---

## Current Limitations

### Known Incomplete Features
1. **Integration Actions/Syncs**: Parser uses functional stubs (works but limited)
2. **OpenAPI Security**: Placeholder implementation (users add manually)
3. **Export Declarations**: Not yet implemented (planned v2.0)

### Not Supported (Yet)
- **Real-time sync**: Integrations are batch-oriented
- **Complex workflows**: Experiences support basic flows only
- **Custom validators**: No extension points for domain-specific validation
- **Multi-tenancy**: Not considered in core DSL

### Workarounds
- **Security**: Manually add security schemes to generated OpenAPI specs
- **Complex flows**: Use multiple experiences and chain them
- **Custom logic**: Modify generated code after build (stacks are starting points)

---

## Version History

### v0.1.0 (November 2025) - Initial Release
**Stages Completed**: 1-7
- ✅ Complete DSL parser and IR
- ✅ Module system with dependency resolution
- ✅ 6 production stacks
- ✅ LLM integration
- ✅ LSP server and VS Code extension
- ✅ Comprehensive test suite
- ✅ Homebrew distribution
- ✅ Pattern detection and quick wins

### v0.2.0 (Planned)
- Complete integration parsing (remove stubs)
- Enhanced pattern detection
- More stacks (Next.js, FastAPI, etc.)
- Improved error messages
- Performance optimizations

### v2.0.0 (Future)
- Graph-theoretic normalization
- Port-based composition
- Formal verification
- Export declarations
- Advanced pattern matching

---

## Quick Reference

### Project Structure
```
dazzle/
├── src/dazzle/           # Core implementation
│   ├── core/            # Parser, IR, linker, validation
│   ├── stacks/          # Stack generators (6 stacks)
│   ├── llm/             # LLM integration
│   ├── lsp/             # LSP server
│   └── cli.py           # CLI entry point
├── docs/                # User documentation
├── dev_docs/            # Development documentation
├── tests/               # Test suite (59+ tests)
├── examples/            # Example projects
└── extensions/          # VS Code extension

```

### Key Files
- **`.claude/CLAUDE.md`**: This file (AI assistant guidance)
- **`dazzle.toml`**: Project manifest
- **`src/dazzle/core/ir.py`**: Complete IR type system
- **`src/dazzle/core/dsl_parser.py`**: Full DSL parser
- **`src/dazzle/cli.py`**: All CLI commands

### Essential Commands
```bash
# Setup
dazzle init
dazzle validate

# Development
dazzle lint
dazzle inspect
pytest tests/

# Generation
dazzle build --stack micro
dazzle build --stack openapi,docker

# Help
dazzle --help
dazzle build --help
```

---

## Getting Help

- **Documentation**: `docs/` directory
- **Examples**: `examples/` directory
- **Issues**: https://github.com/manwithacat/dazzle/issues
- **Discussions**: GitHub Discussions
- **LLM Context**: Use this file for AI assistance

---

**Last Updated**: 2025-11-23
**DAZZLE Version**: 0.1.0
**Status**: Production Ready ✅
