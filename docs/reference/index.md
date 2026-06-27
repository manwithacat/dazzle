# DSL Reference

> **Auto-generated** by `docs_gen.py`. Run `dazzle docs generate` to regenerate.

| Section | Description |
|---------|-------------|
| [Entities](entities.md) | Entities are the core data models in DAZZLE. |
| [Access Control](access-control.md) | DAZZLE uses Cedar-style access rules with three layers: entity-level permit/forbid blocks, surface-level access restrictions, and workspace-level persona allow/deny lists. |
| [Surfaces](surfaces.md) | Surfaces define the UI and API interfaces for interacting with entities. |
| [Workspaces](workspaces.md) | Workspaces compose multiple data views into cohesive dashboards or information hubs. |
| [UX Semantic Layer](ux.md) | The UX semantic layer expresses WHY interfaces exist and WHAT matters to users, without prescribing HOW to implement it. |
| [UX Catalogue](ux-catalogue.md) | A live gallery of Dazzle display modes — each component rendered from real DSL through the real render pipeline, with its DSL snippet. |
| [Experiences](experiences.md) | Experiences define multi-step user flows such as onboarding wizards, checkout processes, and approval workflows. |
| [Services](services.md) | Services declare custom business logic in DSL with implementation in Python or TypeScript stubs. |
| [Integrations](integrations.md) | Integrations connect DAZZLE apps to external systems via declarative API bindings with triggers, field mappings, and error handling. |
| [Processes](processes.md) | Processes orchestrate durable, multi-step workflows across entities and services. |
| [Stories](stories.md) | Stories capture expected user-visible outcomes in a structured format tied to personas and entities. |
| [Rhythms](rhythms.md) | Rhythms capture longitudinal persona journeys through the app, organized into temporal phases containing scenes — evaluable actions on specific surfaces. |
| [Ledgers & Transactions](ledgers.md) | Ledgers and transactions provide TigerBeetle-backed double-entry accounting. |
| [LLM Models & Intents](llm.md) | DAZZLE supports declarative LLM job definitions for AI-powered tasks such as classification, extraction, and generation. |
| [Testing](testing.md) | DAZZLE provides a comprehensive testing toolkit including E2E testing with Playwright, FlowSpec test generation, semantic DOM conventions, capability discovery, CRUD completeness analysis, workflow coherence checks, and RBAC validation. |
| [MCP Tool Inventory](mcp-tools.md) | Live inventory of the MCP tools exposed by `dazzle mcp run`. |
| [Frontend & Templates](frontend.md) | The Dazzle frontend uses the **typed Fragment substrate** (frozen-dataclass HTML primitives) with HTMX for declarative server interactions. |
| [Messaging & Events](messaging.md) | Messaging and events enable asynchronous communication between components and users. |
| [Graph Features](graphs.md) | Dazzle has first-class support for property graphs — data models where entities form nodes and their relationships form edges. |
| [Compliance Framework](compliance.md) | Dazzle can automatically assess how well your DSL specification maps to recognised compliance frameworks. |
| [Governance](governance.md) | Governance constructs enforce organisational policies, approval workflows, and service-level agreements. |
| [Patterns](patterns.md) | Patterns are reusable DSL recipes that combine multiple constructs into proven solutions. |

## Guides & Operations

| Page | Description |
|------|-------------|
| [Project Layout](project-layout.md) | The recommended directory layout for a Dazzle project — where DSL, app code, and one-shot scripts live. |
| [DSL Grammar Specification](grammar.md) | The formal EBNF grammar for the DAZZLE DSL, regenerated from parser source by `dazzle grammar`. |
| [Personas and Scenarios](scenarios.md) | Personas define user types; scenarios define test-data states for development and demonstration. |
| [UI Islands](islands.md) | Self-contained interactive JavaScript components that mount into server-rendered pages. |
| [Reports & Charts](reports.md) | How chart and report regions (bar_chart, pivot_table, heatmap, funnel, metrics) compile to scope-aware aggregate queries. |
| [Runtime UI Capabilities](runtime-capabilities.md) | What the Dazzle runtime actually renders for each DSL construct — the map from DSL to live UI. |
| [Framework UX-Maturity Rubric](ux-maturity.md) | Scores the framework, not a screen: does Dazzle make the data-right UI the DEFAULT? The 0-4 capability ladder, 13 criteria, evidence/attribution, and the `dazzle ux maturity` scan + `/ux-maturity` command. |
| [HTMX Template Specification](htmx-templates.md) | The HTMX interaction patterns the runtime emits; SSR + HTMX with no SPA framework. |
| [Card-Safety Invariants](card-safety-invariants.md) | The canonical spec for what a card means in Dazzle templates and the eight invariants its scanners enforce. |
| [RBAC Scope Rules](rbac-scope.md) | Operation-by-operation reference for `scope:` row-level authorization rules and their predicate algebra. |
| [RBAC Verification Framework](rbac-verification.md) | The three-layer access-control verification system that proves DSL-declared security policies hold. |
| [Security Profiles](security-profiles.md) | The security profile every app declares in its `app` block, and what each profile enforces. |
| [Enterprise SSO & Provisioning](enterprise-sso.md) | Native per-org enterprise connections (OIDC, SAML, SCIM) behind the opt-in capability registry. |
| [Verified-Domain Join](verified-domain-join.md) | The non-SSO self-service join: a tenant proves its email domain (DNS-TXT), then verified-email users self-join under a per-tenant policy (#1424). |
| [PII & Privacy Primitives](pii-privacy.md) | Analytics, consent, and privacy primitives for marking and handling personally identifiable data. |
| [Document Signing](document-signing.md) | Native PAdES B-T document signing as a first-class DSL primitive via `signable: true`. |
| [Multi-Tenant Hosts](tenant-hosts.md) | The `tenant_host:` sub-block that auto-mounts Host-header-based tenant routing (#1289). |
| [Database Configuration](databases.md) | PostgreSQL configuration for development and production — Dazzle is Postgres-only (ADR-0008). |
| [Schema Migrations](migrations.md) | How Dazzle uses Alembic for all schema changes, including framework entities (ADR-0017). |
| [AWS Deployment](deployment.md) | Generating and managing AWS CDK infrastructure from your DSL specifications. |
| [CLI Reference](cli.md) | Complete reference for the `dazzle` command-line interface and its command groups. |
| [E2E Environment (Mode A)](e2e-environment.md) | The Mode A developer one-shot harness that launches a live example app for end-to-end testing. |
| [QA Trial Patterns](qa-trial-patterns.md) | Patterns surfaced by `dazzle qa trial` — qualitative business-user evaluation of a Dazzle app. |
| [Fitness Methodology](fitness-methodology.md) | The optional Agent-Led Fitness Methodology V&V loop that checks app fitness against declared intent. |
| [Fitness Investigator](fitness-investigator.md) | Agent-led investigation of ranked fitness clusters that produces actionable improvement proposals. |
| [Fitness Triage](fitness-triage.md) | Turning a flat fitness backlog into ranked, actionable clusters for investigation. |
| [Performance Envelope](performance-envelope.md) | Where the Dazzle runtime is fast, where it degrades, and by how much — measured. |
| [Performance Observability](perf-observability.md) | Local on-demand OpenTelemetry tracing for any Dazzle project via `dazzle perf`. |
| [Perf Findings Schema](perf-findings-schema.md) | The JSON schema emitted by `dazzle perf report --format json` (FindingsReport). |
| [Implicitness Audit](implicitness-audit.md) | A working doc on identifying implicit behaviour in Dazzle, written after a runtime post-mortem. |
| [Onboarding Guides](guides.md) | The `guide` construct: terse, in-fiction, per-persona onboarding overlays — authored by the agent, validated by a fast quality-bar gate plus an e2e guide-walk oracle. |
| [LLM Drivers](llm-drivers.md) | Subscription-billed (`claude-cli`) vs metered (`anthropic-api`) cognition: resolution order, the dev → deploy path, and the production guard. |
