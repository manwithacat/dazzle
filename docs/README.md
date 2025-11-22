# DAZZLE Core Reference Documentation

This directory contains the core language reference specifications for DAZZLE.

For user guides, tutorials, and examples, see the [main README](../README.md).

## Language Specifications

### [DSL Reference](DAZZLE_DSL_REFERENCE_0_1.md)
Complete syntax reference for the DAZZLE Domain-Specific Language (v0.1).

Covers:
- Entity definitions and field types
- Surface declarations (UI entry points)
- Experience flows (multi-step workflows)
- Service integrations
- Module system and dependencies

### [DSL Grammar](DAZZLE_DSL_GRAMMAR_0_1.ebnf)
Formal EBNF grammar specification for the DAZZLE DSL (v0.1).

Use this for:
- Parser implementation
- Syntax validation
- Language tooling development
- Grammar-based code generation

### [DSL Examples](DAZZLE_EXAMPLES_0_1.dsl)
Annotated DSL examples demonstrating language features (v0.1).

Includes:
- Entity relationships
- Surface modes
- Field constraints
- Integration patterns

### [IR Specification](DAZZLE_IR_0_1.md)
Internal Representation (IR) schema documentation (v0.1).

Covers:
- AppSpec structure
- Entity and field models
- Surface and experience types
- Service integration models
- Linker and validation rules

## Working Examples

Complete working example projects are available in [`../examples/`](../examples/):

- **[simple_task](../examples/simple_task/)** - Basic task manager with CRUD operations
- **[support_tickets](../examples/support_tickets/)** - Multi-module support ticket system

## Development Documentation

For architecture, development guides, and implementation notes, see [`../dev_docs/`](../dev_docs/).

## Version

All specifications in this directory are for **DAZZLE v0.1**.

Updated specifications for newer versions will use version-specific filenames (e.g., `DAZZLE_DSL_REFERENCE_0_2.md`).
