# DAZZLE Development Roadmap

**Last Updated**: 2026-02-01
**Current Version**: v0.33.0

For past releases, see [CHANGELOG.md](CHANGELOG.md).

---

## Philosophy

DAZZLE is a **DSL-first toolkit** that bridges human specifications and production code.

```
Human Intent ──▶ LLM ──▶ Structured DSL ──▶ Runtime (live app)
                         (one-time cost)    (zero marginal cost)
```

1. **LLM translates intent to DSL** - High-value token spend, done once
2. **DSL is the compression boundary** - Validated, version-controlled spec
3. **Runtime executes directly** - No code generation step, your spec is the app

---

## Recently Completed

- **Fidelity scoring** - Spec-aware interaction checks, `source=` field validation
- **Fragment system** - `search_select` and `search_results` fragments with API pack bridge; all 9 HTMX fragments registered for MCP discovery
- **Codebase cleanup** - Split oversized modules, removed dead code, registered all fragments
- **Founder Console** - HTMX + DaisyUI control plane at `/_console/`

---

## In Progress

### WS1: Dazzle Bar HTMX Rebuild
Server-rendered Dazzle Bar using HTMX + Alpine.js + DaisyUI. Replaces previous JS-based bar with partial endpoints and composable templates.

### WS2: FragmentContext Standardization
Wire `source=` annotations from DSL surfaces through to fragment rendering. Standardize `FragmentContext` as the base model for all fragment rendering inputs.

### WS3: Integration Runtime
Execute `integration` actions against external APIs at form submit time. Maps DSL `IntegrationAction` call/response mappings to real HTTP calls via httpx.

### WS4: Workspace Layouts
Render `WorkspaceSpec` as HTMX pages with stage-driven grid layouts (focus metric, dual pane, scanner table, monitor wall, command center).

---

## Next Up

- **Experience flows** - Multi-step user journeys (parser/IR complete, needs runtime)
- **Sync scheduling** - Cron/event-driven `IntegrationSync` execution
- **Advanced display modes** - KANBAN, TIMELINE, MAP, chart modes for workspaces

---

## Deferred

These are real plans but not the current priority:

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
