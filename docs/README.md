# DAZZLE Documentation

**Current Version**: v0.8.0

DAZZLE is a DSL-first toolkit for building applications. Write your domain model once, run it instantly with the Native Runtime, then eject to standalone code when ready for production.

## Quick Start

```bash
# Install
brew install manwithacat/tap/dazzle

# Create a new project
dazzle new my_app

# Run the app
cd my_app && dazzle dev
```

## Documentation

### Getting Started
- **[Installation](INSTALLATION.md)** - Install via Homebrew, pip, or pipx
- **[Examples](EXAMPLES.md)** - Working example projects
- **[Philosophy](PHILOSOPHY.md)** - Design principles

### DSL Reference
- **[Quick Reference](DAZZLE_DSL_QUICK_REFERENCE.md)** - Syntax in 5 minutes
- **[Reserved Keywords](DSL_RESERVED_KEYWORDS.md)** - Language keywords
- **[Grammar (v0.7)](v0.7/DAZZLE_DSL_GRAMMAR.ebnf)** - Formal EBNF specification

### Runtime & Tooling
- **[CLI Reference](CLI_REFERENCE.md)** - Command-line interface
- **[DNR Architecture](dnr/ARCHITECTURE.md)** - Native Runtime internals
- **[Tooling](TOOLING.md)** - MCP server and IDE integration
- **[VS Code Extension](VSCODE_EXTENSION.md)** - Editor support

### Features
- **[Authentication](AUTHENTICATION.md)** - Built-in auth system
- **[E2E Testing](E2E_TESTING.md)** - Flow-based testing
- **[Extensibility](EXTENSIBILITY.md)** - Service stubs and extensions
- **[Troubleshooting](TROUBLESHOOTING.md)** - Common issues

### Reference
- **[Capabilities](CAPABILITIES.md)** - Feature support matrix
- **[Deprecation Policy](DEPRECATION_POLICY.md)** - Version lifecycle
- **[Semantic DOM Contract](SEMANTIC_DOM_CONTRACT.md)** - UI attribute spec

## Version History

| Version | Key Changes |
|---------|-------------|
| v0.8.0 | New Bun CLI (50x faster), JSON-first output |
| v0.7.x | State machines, LLM cognition layer, invariants |
| v0.2.x-v0.6.x | UX semantic layer, workspaces, GraphQL BFF |

See [CHANGELOG](../CHANGELOG.md) for full history.

## Getting Help

- **Syntax questions**: [Quick Reference](DAZZLE_DSL_QUICK_REFERENCE.md)
- **CLI commands**: [CLI Reference](CLI_REFERENCE.md)
- **Issues**: [GitHub Issues](https://github.com/manwithacat/dazzle/issues)
