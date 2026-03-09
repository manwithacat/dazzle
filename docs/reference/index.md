# DSL Reference

> **Auto-generated** by `docs_gen.py`. Run `dazzle docs generate` to regenerate.

| Section | Description |
|---------|-------------|
| [Entities](entities.md) | Entities are the core data models in DAZZLE. |
| [Access Control](access-control.md) | DAZZLE uses Cedar-style access rules with three layers: entity-level permit/forbid blocks, surface-level access restrictions, and workspace-level persona allow/deny lists. |
| [Surfaces](surfaces.md) | Surfaces define the UI and API interfaces for interacting with entities. |
| [Workspaces](workspaces.md) | Workspaces compose multiple data views into cohesive dashboards or information hubs. |
| [UX Semantic Layer](ux.md) | The UX semantic layer expresses WHY interfaces exist and WHAT matters to users, without prescribing HOW to implement it. |
| [Experiences](experiences.md) | Experiences define multi-step user flows such as onboarding wizards, checkout processes, and approval workflows. |
| [Services](services.md) | Services declare custom business logic in DSL with implementation in Python or TypeScript stubs. |
| [Integrations](integrations.md) | Integrations connect DAZZLE apps to external systems via declarative API bindings with triggers, field mappings, and error handling. |
| [Processes](processes.md) | Processes orchestrate durable, multi-step workflows across entities and services. |
| [Stories](stories.md) | Stories capture expected user-visible outcomes in a structured format tied to personas and entities. |
| [Ledgers & Transactions](ledgers.md) | Ledgers and transactions provide TigerBeetle-backed double-entry accounting. |
| [LLM Models & Intents](llm.md) | DAZZLE supports declarative LLM job definitions for AI-powered tasks such as classification, extraction, and generation. |
| [Testing](testing.md) | DAZZLE provides a comprehensive testing toolkit including E2E testing with Playwright, FlowSpec test generation, semantic DOM conventions, capability discovery, CRUD completeness analysis, workflow coherence checks, and RBAC validation. |
| [Frontend & Templates](frontend.md) | The Dazzle frontend uses server-rendered Jinja2 templates with HTMX for declarative HTTP interactions. |
| [Messaging & Events](messaging.md) | Messaging and events enable asynchronous communication between components and users. |
| [Governance](governance.md) | Governance constructs enforce organisational policies, approval workflows, and service-level agreements. |
| [Patterns](patterns.md) | Patterns are reusable DSL recipes that combine multiple constructs into proven solutions. |
