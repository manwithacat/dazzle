# DAZZLE Development Roadmap

**Last Updated**: 2025-12-16
**Current Version**: v0.16.0
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

### v0.17.0 - Messaging Channels

**Issue**: [#20](https://github.com/manwithacat/dazzle/issues/20)
**Status**: In Progress (Next Sprint)

Unified messaging built on the event substrate.

**Completed:**
- DSL parser for `message`, `channel`, `asset`, `document`, `template`
- IR types: `MessageSpec`, `ChannelSpec`, `SendOperationSpec`, `ReceiveOperationSpec`, `ThrottleSpec`
- Provider detection framework with Mailpit, SendGrid, SQS detectors
- Outbox table structure with status tracking
- MCP tools: `list_channels`, `get_channel_status`, `list_messages`, `get_outbox_status`

**Remaining:**
- [ ] Background outbox dispatcher worker
- [ ] Actual email sending via detected provider
- [ ] In-memory queue/stream providers
- [ ] RabbitMQ and Redis Streams providers
- [ ] Dazzle Bar Mailpit panel

---

### v0.18.0 - API Knowledgebase & Integration Assistant

**Issue**: [#21](https://github.com/manwithacat/dazzle/issues/21)
**Status**: Planned

Curated API definitions and LLM-assisted integration setup.

- Pre-baked API packs for common services (Stripe, HMRC, Xero)
- `.env.example` generation from service requirements
- MCP tools: `lookup_api_pack`, `suggest_integration`
- Zero hallucinated endpoints - all from curated packs

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

## Completed Milestones

### v0.16.0 - Documentation, Event-First, SiteSpec ✅

Released 2025-12-16. See [CHANGELOG.md](CHANGELOG.md#0160---2025-12-16).

- MkDocs Material documentation site at [manwithacat.github.io/dazzle](https://manwithacat.github.io/dazzle)
- Event-First Architecture (Issue #25) - events as invisible substrate
- SiteSpec: Public Site Shell (Issue #24) - YAML-based public pages
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

1. **Messaging Channels**: Help complete the dispatcher and providers
2. **API Packs**: Contribute curated API pack definitions
3. **Documentation**: Improve guides and tutorials
4. **Example Projects**: Create domain-specific examples

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## Resources

- **Repository**: https://github.com/manwithacat/dazzle
- **Documentation**: https://manwithacat.github.io/dazzle/
- **Examples**: `examples/` directory
- **Issues**: [GitHub Issues](https://github.com/manwithacat/dazzle/issues)
