# DAZZLE Development Roadmap

**Last Updated**: 2026-03-18
**Current Version**: v0.46.5

For past releases, see [CHANGELOG.md](CHANGELOG.md).

---

## How Dazzle Evolves

Dazzle does not follow a traditional sprint roadmap. Development is **issue-driven** — we build real applications with the framework, encounter gaps, file issues, and fix them. Each complex domain (healthcare, education, finance, logistics) stresses a different combination of DSL constructs and exposes different classes of problems.

This means the roadmap is less "what we plan to build next quarter" and more "what kinds of problems we're looking for." If you bring a domain that exposes a new class of gap, that's a contribution.

---

## Active Focus Areas

### Provable RBAC

The RBAC verification framework (`dazzle rbac matrix`, `dazzle rbac verify`) is new in v0.43.0. The static matrix and audit trail are complete. The dynamic verifier (Layer 2) — which spins up the app, seeds golden-master data, and probes every endpoint as every role — is stubbed and needs implementation. This is the most impactful piece of work available: completing it means every Dazzle app can prove its security model holds.

See [RBAC Verification Reference](docs/reference/rbac-verification.md) for the full architecture.

### Domain Stress-Testing

Dazzle's DSL grows by encountering domains it can't yet express cleanly. The most productive contributions are **example applications from complex, real-world domains** that push the boundaries of what the DSL can describe. Current examples cover task management, contact management, ops dashboards, and medical prescribing. We're particularly interested in:

- **Multi-tenant SaaS** — domains where tenancy isolation, delegated admin, and cross-tenant reporting intersect
- **Regulated industries** — healthcare, finance, education — where audit trails, approval workflows, and separation of duty are non-negotiable
- **Complex state machines** — domains with many entity lifecycle states, conditional transitions, and escalation paths
- **High-cardinality relationships** — domains where entities have dozens of related entities and the UI must navigate them efficiently

Each new domain that doesn't fit cleanly generates issues. Those issues drive the DSL forward.

### Runtime Hardening

The v0.43.0 release fixed critical RBAC enforcement bugs (#520) and 14 code smells (#504-#518). Ongoing focus areas:

- **Subsystem decomposition** — `DazzleBackendApp` (2182 lines) has subsystem plugin infrastructure but more `_init_*` methods to extract (#517)
- **Cedar evaluation completeness** — the `_is_field_condition` gate logic is correct but the row-filter path needs comprehensive testing for complex OR/AND condition trees
- **Audit trail integration** — the `evaluate_permission()` audit sink is wired; the `dazzle rbac verify` dynamic verifier needs its server lifecycle + probe implementation

---

## Interesting Problems We'd Like to Solve

These are not scheduled. They're problems that would make Dazzle meaningfully better if someone brought the right domain or approach.

**Grant-based delegation** — the `grant_schema` DSL construct exists (v0.42.0) but the runtime grant resolution is minimal. A domain that needs "school admin delegates marking authority to a specific teacher for a specific class" would drive this to completion.

**Process orchestration at scale** — the process engine handles state machines and human tasks but hasn't been stressed with long-running, multi-step workflows (insurance claims, immigration applications, clinical trials). Bringing a domain with 20+ step processes would expose gaps in timeout handling, compensation, and parallel execution.

**Derived views and aggregation** — workspaces support `aggregate:` blocks but the DSL can't yet express "show me a dashboard of KPIs computed from multiple entities with time-series rollup." This is a common SaaS pattern that would benefit from DSL-level support.

**Multi-language / i18n** — the DSL has `label` strings everywhere but no localization framework. A domain requiring multiple languages would define the requirements.

---

## Contributing

The best way to contribute to Dazzle is to **build something with it** and tell us where it breaks.

1. Pick a domain you know well
2. Write the DSL (start with entities + surfaces)
3. Run `dazzle serve --local` and `dazzle rbac matrix`
4. File issues for anything that doesn't work or can't be expressed
5. Submit your example as a PR to `examples/`

Each example app that exercises a new combination of DSL constructs is a permanent regression test. See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup.

**Specific opportunities right now:**

- **Complete `dazzle rbac verify`** — implement the server lifecycle + HTTP probe loop (types and comparison logic exist in `src/dazzle/rbac/verifier.py`)
- **API Packs** — contribute integration packs for third-party APIs (Stripe, Xero, HMRC exist; many more needed)
- **Example apps** — complex domains that stress the DSL
- **Documentation** — guides, tutorials, and reference improvements

---

## Resources

- **Repository**: https://github.com/manwithacat/dazzle
- **Documentation**: https://manwithacat.github.io/dazzle/
- **Examples**: `examples/` directory
- **Issues**: [GitHub Issues](https://github.com/manwithacat/dazzle/issues)
