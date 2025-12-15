# DAZZLE Development Roadmap

**Last Updated**: 2025-12-15
**Current Version**: v0.15.0
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

### v0.16.0 - Messaging Channels

**Issue**: [#20](https://github.com/manwithacat/dazzle/issues/20)
**Status**: Planned

Unified messaging abstraction for email, queues, and event streams.

- `message` construct for typed, reusable message schemas
- `channel` construct with `kind: email | queue | stream`
- Provider auto-detection (Mailpit locally, SendGrid/SQS/Kafka in prod)
- Transactional outbox pattern
- DSL-native template language

---

### v0.17.0 - API Knowledgebase & Integration Assistant

**Issue**: [#21](https://github.com/manwithacat/dazzle/issues/21)
**Status**: Planned

Curated API definitions and LLM-assisted integration setup.

- Pre-baked API packs for common services (Stripe, HMRC, Xero)
- `.env.example` generation from service requirements
- MCP tools: `lookup_api_pack`, `suggest_integration`
- Zero hallucinated endpoints - all from curated packs

---

### v0.18.0 - SiteSpec: Public Site Shell

**Issue**: [#24](https://github.com/manwithacat/dazzle/issues/24)
**Status**: Planned

Public-facing site shell pages without polluting the App DSL.

- YAML-based `sitespec.yaml` for home, about, pricing, terms, privacy pages
- Section-based landing pages (hero, features, cta, faq, testimonials)
- Markdown content with template variables
- Zero-config default generation
- MCP tools: `site_spec`, `site_content`

---

### v0.20.0 - Event-First Architecture

**Issue**: [#25](https://github.com/manwithacat/dazzle/issues/25)
**Status**: Planned

Events as the invisible substrate - correctness by construction.

- EventBus interface (Kafka-shaped) with DevBrokerSQLite (zero-Docker)
- Transactional outbox + idempotent inbox (at-least-once, dedupe)
- DSL: `topic`, `event`, `publish when`, `subscribe`, `project`
- Replay capability for projection rebuild
- CLI: `dazzle bus info/tail/replay`, `dazzle outbox drain`
- AsyncAPI generation (Swagger for events)
- Optional data product boundaries with classification policies

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

### v1.1.0 - Multi-Platform Support

**Issue**: [#23](https://github.com/manwithacat/dazzle/issues/23)
**Status**: Planned

Beyond web applications.

- React Native runtime (mobile)
- Desktop app packaging (Electron/Tauri)
- Offline-first patterns
- Cross-platform sync

---

## Contributing

**Current Opportunities**:

1. **DNR Testing**: Run your projects with DNR, report issues
2. **Example Projects**: Create domain-specific examples
3. **Documentation**: Improve guides and tutorials
4. **API Packs**: Contribute curated API pack definitions

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## Resources

- **Repository**: https://github.com/manwithacat/dazzle
- **Documentation**: `docs/` directory
- **Examples**: `examples/` directory
- **Issues**: [GitHub Issues](https://github.com/manwithacat/dazzle/issues)
