# DAZZLE Development Roadmap

**Last Updated**: 2026-02-01
**Current Version**: v0.19.0

For past releases, see [CHANGELOG.md](CHANGELOG.md).

---

## Philosophy

DAZZLE is a **DSL-first toolkit** that bridges human specifications and production code.

```
Human Intent ──▶ LLM ──▶ Structured DSL ──▶ DNR Runtime (live app)
                         (one-time cost)    (zero marginal cost)
```

1. **LLM translates intent to DSL** - High-value token spend, done once
2. **DSL is the compression boundary** - Validated, version-controlled spec
3. **DNR executes directly** - No code generation step, your spec is the app

---

## Current Focus: Consolidation

With one active user building on DAZZLE, the priority is hardening what works
over adding new capabilities.

### In Progress

- **Fidelity scoring** - Spec-aware interaction checks, `source=` field validation
- **Fragment system** - `search_select` and `search_results` fragments with API pack bridge
- **Codebase cleanup** - Splitting oversized modules, removing dead code

### Next Up

- **Fragment composition** - Register and document all 9 HTMX fragments for MCP discovery
- **`FragmentContext` base model** - Standardize fragment rendering inputs
- **Richer workspace layouts** - Dual-pane, monitor wall patterns
- **Integration runtime** - Execute `integration` actions against external APIs (parser/IR already complete)

### Deferred

These are real plans but not the current priority:

- **Experience flows** - Multi-step user journeys (parser/IR complete, needs runtime)
- **Multi-platform support** ([#23](https://github.com/manwithacat/dazzle/issues/23)) - React Native, desktop packaging
- **Orchestrator control plane** ([#22](https://github.com/manwithacat/dazzle/issues/22)) - Spec versioning, migrations, blue/green deploys

---

## Contributing

**Current Opportunities**:

1. **API Packs** - Contribute curated API pack definitions
2. **Queue/Stream Adapters** - Add RabbitMQ, Redis Streams send adapters
3. **Documentation** - Improve guides and tutorials
4. **Example Projects** - Create domain-specific examples

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## Resources

- **Repository**: https://github.com/manwithacat/dazzle
- **Documentation**: https://manwithacat.github.io/dazzle/
- **Examples**: `examples/` directory
- **Issues**: [GitHub Issues](https://github.com/manwithacat/dazzle/issues)
