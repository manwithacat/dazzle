# DAZZLE Development Roadmap

**Last Updated**: 2025-12-16
**Current Version**: v0.17.0
**Status**: DSL-first toolkit with DNR runtime + Ejection toolchain

For past releases, see [CHANGELOG.md](CHANGELOG.md).

---

## Philosophy

DAZZLE is a **DSL-first toolkit** that bridges human specifications and production code.

```
Human Intent ──▶ LLM ──▶ Structured DSL ──▶ Deterministic Code
                         (one-time cost)    (zero marginal cost)
```

1. **LLM translates intent to DSL** - High-value token spend, done once
2. **DSL is the compression boundary** - Validated, version-controlled spec
3. **All downstream is deterministic** - Parser, IR, code gen are mechanical

### Two Paths from DSL

| Path | Use Case | Cost |
|------|----------|------|
| **DNR Runtime** | Rapid iteration, prototyping | Zero - runs directly |
| **Ejection** | Production deployment | One-time generation |

---

## Roadmap

### v0.18.0 - Multi-Platform Support

**Issue**: [#23](https://github.com/manwithacat/dazzle/issues/23)
**Status**: Planned

Beyond web applications.

- React Native runtime (mobile)
- Desktop app packaging (Electron/Tauri)
- Offline-first patterns
- Cross-platform sync

---

### v1.0.0 - Dazzle Orchestrator Control Plane

**Issue**: [#22](https://github.com/manwithacat/dazzle/issues/22)
**Status**: Planned

Hosted control plane for production app management.

- SpecVersion snapshots and semantic diffing
- Migration planning with risk assessment
- Blue/green deployments with rollback
- Founder Web UI with LLM-assisted changes

---

## Completed Milestones

### v0.17.0 - API Knowledgebase & Integration Assistant ✅

Completed 2025-12-16. Issue [#21](https://github.com/manwithacat/dazzle/issues/21).

- 12 curated API packs (Stripe, HMRC×6, Companies House, Xero, Ordnance Survey, SumSub, DocuSeal)
- MCP tools: `list_api_packs`, `search_api_packs`, `get_api_pack`, `generate_service_dsl`
- DSL generation from packs (service blocks, foreign_models, .env.example)
- Zero hallucinated endpoints - all from curated TOML packs

### v0.16.0 - Documentation, Event-First, SiteSpec, Messaging ✅

Released 2025-12-16. See [CHANGELOG.md](CHANGELOG.md#0160---2025-12-16).

- MkDocs Material documentation site at [manwithacat.github.io/dazzle](https://manwithacat.github.io/dazzle)
- Event-First Architecture (Issue #25) - events as invisible substrate
- SiteSpec: Public Site Shell (Issue #24) - YAML-based public pages
- Messaging Channels (Issue #20) - outbox pattern, email adapters, provider detection
- Performance & Reliability Analysis (PRA) framework
- HLESS (High-Level Event Semantics Specification)
- Playwright E2E tests

### v0.15.0 - Interactive CLI ✅

Released 2025-12-15.

- `dazzle init`: Interactive project wizard
- `dazzle doctor`: Environment diagnostics
- `dazzle explore`: Interactive DSL explorer
- `dazzle kb`: Knowledgebase browser

### v0.14.0 - MCP Commands Restored ✅

Released 2025-12-14.

- Full MCP server functionality in Bun CLI
- Deterministic port allocation for DNR serve
- Semantic E2E attributes for testability

---

## Contributing

**Current Opportunities**:

1. **API Packs**: Contribute curated API pack definitions (Stripe, HMRC, Xero, etc.)
2. **Queue/Stream Adapters**: Add RabbitMQ, Redis Streams send adapters
3. **Documentation**: Improve guides and tutorials
4. **Example Projects**: Create domain-specific examples

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## Resources

- **Repository**: https://github.com/manwithacat/dazzle
- **Documentation**: https://manwithacat.github.io/dazzle/
- **Examples**: `examples/` directory
- **Issues**: [GitHub Issues](https://github.com/manwithacat/dazzle/issues)
