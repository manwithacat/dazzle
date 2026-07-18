# MCP Tool Inventory

> **Auto-generated** from knowledge base TOML files by `docs_gen.py`.
> Do not edit manually; run `dazzle docs generate` to regenerate.

Live inventory of the MCP tools exposed by `dazzle mcp run`. Generated from the tool registry — every operation, parameter, and description below comes straight from `dazzle.mcp.server.tools_consolidated.get_all_consolidated_tools()` at build time. Run `dazzle docs generate` to refresh after adding, renaming, or removing tools or operations. The drift gate at `tests/unit/test_api_surface_drift.py` (mcp_tools baseline) catches surface changes that didn't update the docs.

**Live count:** 37 tools, 168 operations. Regenerated from the registry every time `dazzle docs generate` runs.

Each tool is a single MCP entry point that dispatches on the `operation` argument. The Bootstrap tool (`bootstrap`) is the exception — it takes free-form spec text, not an operation enum, and is the canonical entry point for "build me an app" requests.

## Tool index

| Tool | Operations | Summary |
|------|------------|---------|
| [`agent`](#agent) | 3 | Agent closed-loop control plane (#1605): context (brownfield map + runtime |
| [`agent_commands`](#agent_commands) | 3 | Agent development commands: list (available commands with maturity status), get (rendered skill content for a command), check_updates (version comparison for sync) |
| [`api_pack`](#api_pack) | 3 | API pack operations: list, search, get |
| [`bootstrap`](#bootstrap) | — | Entry point for 'build me an app' requests |
| [`compliance`](#compliance) | 5 | Compliance documentation operations |
| [`composition`](#composition) | 6 | Composition analysis: audit (DOM-level visual hierarchy audit), capture (Playwright section-level screenshots), analyze (LLM visual evaluation of captured screenshots), report (combined audit+capture+analyze with merged scoring), bootstrap (generate synthetic reference library for few-shot evaluation) |
| [`conformance`](#conformance) | 4 | DSL conformance testing operations |
| [`db`](#db) | 2 | Database operations: status (row counts per entity, database size), verify (FK integrity check, orphan detection) |
| [`demo_data`](#demo_data) | 1 | Demo data operations: get |
| [`discovery`](#discovery) | 1 | Capability discovery operations: coherence (persona-by-persona authenticated UX coherence score) |
| [`dsl`](#dsl) | 11 | DSL operations: validate, list_modules, inspect_entity, inspect_surface, analyze, lint, get_spec, fidelity, list_fragments, export_frontend_spec, brief |
| [`e2e`](#e2e) | 4 | E2E environment operations (read-only) |
| [`feedback`](#feedback) | 4 | Feedback operations: list, get, triage, resolve |
| [`fitness`](#fitness) | 1 | Agent-Led Fitness Methodology queries (read-only) |
| [`graph`](#graph) | 14 | Knowledge graph operations for codebase understanding |
| [`guide`](#guide) | 4 | Inspect declared onboarding guides |
| [`knowledge`](#knowledge) | 9 | Knowledge lookup: concept, examples, cli_help, workflow, inference, changelog, counter_prior, get_spec, search_commands |
| [`llm`](#llm) | 4 | LLM operations: list_intents (declared intents), list_models (declared models), inspect_intent (detailed intent view with resolved model), get_config (module-level LLM configuration) |
| [`mock`](#mock) | 2 | Vendor mock server management: status, request_log |
| [`param`](#param) | 2 | Query runtime parameter declarations |
| [`perf`](#perf) | 3 | Local OpenTelemetry trace findings for the current project (read-only) |
| [`pitch`](#pitch) | 1 | Pitch deck operations: get |
| [`policy`](#policy) | 6 | Policy analysis operations for RBAC access control |
| [`process`](#process) | 5 | Process operations: list, inspect, list_runs, get_run, coverage |
| [`product_quality`](#product_quality) | 1 | Felt product/demo quality for commercial showcase apps (#1626) |
| [`representation`](#representation) | 4 | Data-representation organisational judgement (#1617): named hatch patterns (rel |
| [`rhythm`](#rhythm) | 3 | Rhythm operations: get, list, coverage |
| [`semantics`](#semantics) | 6 | Semantic analysis: extract, validate_events, tenancy, compliance, analytics, extract_guards |
| [`sentinel`](#sentinel) | 4 | Sentinel operations: findings (get findings from latest/specific scan), status (available agents and last scan), history (list recent scans), fuzz_summary (run a small mutation fuzz campaign and return the markdown report) |
| [`sitespec`](#sitespec) | 14 | SiteSpec operations: get, validate, scaffold, coherence, review, advise |
| [`spec_analyze`](#spec_analyze) | 6 | Analyze narrative specs before DSL generation |
| [`status`](#status) | 7 | Status operations: mcp, logs, active_project, telemetry, activity, demo_world (alias: runtime) |
| [`story`](#story) | 4 | Story operations: get, composition, coverage, scope_fidelity |
| [`test_design`](#test_design) | 2 | Test design operations: get, gaps |
| [`test_intelligence`](#test_intelligence) | 6 | Query persisted test result history |
| [`user_management`](#user_management) | 9 | User management operations: list, create, get, update, reset_password, deactivate, list_sessions, revoke_session, config |
| [`user_profile`](#user_profile) | 4 | User profile for adaptive persona inference |

## Per-tool detail

### `agent`

Agent closed-loop control plane (#1605): context (brownfield map + runtime.truth + next_steps), prove (static binding evidence), playbook (domain_logic map→bind→scaffold→prove). Does NOT write files — use CLI `dazzle scaffold` / `dazzle prove`. For data-shape judgement (exclusive FKs / poly_ref / JSONB) use the `representation` tool (#1617).

**Operations (3):** `context`, `prove`, `playbook`

**Parameters:**

- `story_id` *(string)* — Story id for prove (optional; default all accepted)
- `name` *(string)* — Playbook name (default: domain_logic)
- `project_path` *(string)* — Optional: Absolute path to project directory. If omitted, uses active project.

---

### `agent_commands`

Agent development commands: list (available commands with maturity status), get (rendered skill content for a command), check_updates (version comparison for sync).

**Operations (3):** `list`, `get`, `check_updates`

**Parameters:**

- `project_path` *(string)* — Optional: Absolute path to project directory. If omitted, uses active project.
- `command` *(string)* — Command name (for 'get' operation)
- `commands_version` *(string)* — Local commands_version from .manifest.json (for 'check_updates')

---

### `api_pack`

API pack operations: list, search, get. Project-local packs in .dazzle/api_packs/ override built-in packs.

**Operations (3):** `list`, `search`, `get`

**Parameters:**

- `pack_name` *(string)* — Pack name (for get)
- `query` *(string)* — Search query (for search)
- `category` *(string)* — Filter by category (for search)
- `provider` *(string)* — Filter by provider (for search)
- `project_path` *(string)* — Optional: Absolute path to project directory. If omitted, uses active project.

---

### `bootstrap`

Entry point for 'build me an app' requests. Scans for spec files, runs cognition pass, and returns a mission briefing with agent instructions. Call this first when a user wants to build an app. Returns structured guidance for the next steps: either questions to ask the user, or instructions for DSL generation. The workflow includes mandatory RBAC: every entity must have permit:/forbid: access rules, verified via policy(operation='access_matrix') before the app is considered complete.

**Parameters:**

- `spec_text` *(string)* — Optional: spec text if provided directly by user
- `spec_path` *(string)* — Optional: path to spec file
- `project_path` *(string)* — Optional: project directory to scan for specs

---

### `compliance`

Compliance documentation operations. compile: compile taxonomy + evidence into AuditSpec. evidence: extract DSL evidence summary. gaps: list controls with gaps or partial evidence. summary: quick compliance posture summary. review: generate review data for gap remediation.

**Operations (5):** `compile`, `evidence`, `gaps`, `summary`, `review`

**Parameters:**

- `framework` *(string)* — Framework ID: iso27001 or soc2 (default: iso27001)
- `project_path` *(string)* — Optional: Absolute path to project directory. If omitted, uses active project.

---

### `composition`

Composition analysis: audit (DOM-level visual hierarchy audit), capture (Playwright section-level screenshots), analyze (LLM visual evaluation of captured screenshots), report (combined audit+capture+analyze with merged scoring), bootstrap (generate synthetic reference library for few-shot evaluation). Audit computes attention weights using a 5-factor model and evaluates composition rules. Capture takes section-level screenshots from a running app. Analyze uses Claude vision to evaluate screenshots for rendering fidelity, icon/media issues, color consistency, layout overflow, visual hierarchy, and responsive fidelity. Report runs audit (always) + visual pipeline (when base_url given) and merges into a combined score. Bootstrap generates synthetic reference images for few-shot visual evaluation prompts. Inspect_styles extracts computed CSS styles via Playwright getComputedStyle() for agent-driven layout diagnosis (zero LLM tokens).

**Operations (6):** `audit`, `capture`, `analyze`, `report`, `bootstrap`, `inspect_styles`

**Parameters:**

- `base_url` *(string)* — Server URL (required for capture, e.g. http://localhost:3000)
- `pages` *(array)* — Filter to specific page routes (e.g. ["/", "/about"])
- `viewports` *(array)* — Viewport names for capture (default: ["desktop"]). Options: desktop, mobile
- `focus` *(array)* — Visual eval dimensions to focus on (for analyze). Options: content_rendering, icon_media, color_consistency, layout_overflow, visual_hierarchy, responsive_fidelity
- `token_budget` *(integer)* — Max tokens for visual analysis (default: 50000)
- `route` *(string)* — Page route to inspect (for inspect_styles, default: "/")
- `selectors` *(object)* — Label-to-CSS-selector mapping (for inspect_styles). E.g. {"hero": ".dz-hero-with-media", "media": ".dz-hero-media"}
- `properties` *(array)* — CSS properties to inspect (for inspect_styles). Defaults to layout properties: display, flex-direction, position, width, height, overflow, gap, etc.
- `overwrite` *(boolean)* — Overwrite existing reference library (for bootstrap, default: false)
- `project_path` *(string)* — Optional: Absolute path to project directory. If omitted, uses active project.

---

### `conformance`

DSL conformance testing operations. summary: run derivation pipeline and return coverage metrics (total cases, per-entity counts, scope types). cases: return all conformance cases for a specific entity (requires entity_name). gaps: find entities that have permit rules but no scope blocks (authorization without row filtering). monitor_status: return current runtime conformance monitor state (observations collected).

**Operations (4):** `summary`, `cases`, `gaps`, `monitor_status`

**Parameters:**

- `entity_name` *(string)* — Entity name (required for cases)
- `auth_enabled` *(boolean)* — Include unauthenticated (401) cases (default: true)
- `project_path` *(string)* — Optional: Absolute path to project directory. If omitted, uses active project.

---

### `db`

Database operations: status (row counts per entity, database size), verify (FK integrity check, orphan detection).

**Operations (2):** `status`, `verify`

**Parameters:**

- `project_path` *(string)* — Optional: Absolute path to project directory. If omitted, uses active project.

---

### `demo_data`

Demo data operations: get. Retrieve the current demo data blueprint.

**Operations (1):** `get`

**Parameters:**

- `project_path` *(string)* — Optional: Absolute path to project directory. If omitted, uses active project.

---

### `discovery`

Capability discovery operations: coherence (persona-by-persona authenticated UX coherence score).

**Operations (1):** `coherence`

**Parameters:**

- `project_path` *(string)* — Optional: Absolute path to project directory. If omitted, uses active project.

---

### `dsl`

DSL operations: validate, list_modules, inspect_entity, inspect_surface, analyze, lint, get_spec, fidelity, list_fragments, export_frontend_spec, brief. 'brief' returns the deterministic stakeholder spec-brief (fact-only app facts + activated framework value-claims) consumed by the /spec-narrate skill. NOTE: export_frontend_spec produces a LARGE output intended for human developers migrating away from Dazzle — always use 'sections' and/or 'entities' filters to avoid flooding context. Prefer inspect_entity/inspect_surface for LLM queries.

**Operations (11):** `validate`, `list_modules`, `inspect_entity`, `inspect_surface`, `analyze`, `lint`, `get_spec`, `fidelity`, `list_fragments`, `export_frontend_spec`, `brief`

**Parameters:**

- `name` *(string)* — Entity or surface name (for inspect_entity/inspect_surface)
- `extended` *(boolean)* — Run extended checks (for lint)
- `entity_names` *(array)* — Entity names to fetch full details for (for get_spec). Omit for summary.
- `surface_names` *(array)* — Surface names to fetch full details for (for get_spec). Omit for summary.
- `surface_filter` *(string)* — Filter to a specific surface name (for fidelity)
- `gaps_only` *(boolean)* — Omit surfaces with fidelity=1.0 (for fidelity)
- `format` *(string)* — Output format (for export_frontend_spec, default: markdown)
- `sections` *(array)* — Filter to specific sections (for export_frontend_spec). Options: typescript_interfaces, route_map, component_inventory, state_machines, api_contract, workspace_layouts, test_criteria
- `entities` *(array)* — Filter to specific entity names (for export_frontend_spec)
- `project_path` *(string)* — Optional: Absolute path to project directory. If omitted, uses active project.

---

### `e2e`

E2E environment operations (read-only). Operations: list_modes (available runner modes), describe_mode (single mode details), status (lock + runtime + log-tail for an example app), list_baselines (hash-tagged db snapshot files for an example). Process operations (start/stop) live in the CLI only.

**Operations (4):** `list_modes`, `describe_mode`, `status`, `list_baselines`

**Parameters:**

- `name` *(string)* — Mode name (for describe_mode)
- `project_root` *(string)* — Path to an example app (for status/list_baselines)
- `project_path` *(string)* — Optional: Absolute path to project directory. If omitted, uses active project.

---

### `feedback`

Feedback operations: list, get, triage, resolve. Query and manage user-submitted feedback reports. Use 'list' to see open feedback, 'get' for detail, 'triage' to mark as triaged, 'resolve' to close.

**Operations (4):** `list`, `get`, `triage`, `resolve`

**Parameters:**

- `id` *(string)* — Feedback report ID (required for get/triage/resolve)
- `status` *(string)* — Filter by status (list only)
- `category` *(string)* — Filter by category (list only)
- `severity` *(string)* — Filter by severity (list only)
- `limit` *(integer)* — Max results (list only, default 20)
- `agent_notes` *(string)* — Agent notes (triage/resolve)
- `agent_classification` *(string)* — Classification (triage only)
- `assigned_to` *(string)* — Assign to (triage only)
- `resolved_by` *(string)* — Who resolved (resolve only)
- `project_path` *(string)* — Optional: Absolute path to project directory. If omitted, uses active project.

---

### `fitness`

Agent-Led Fitness Methodology queries (read-only). Operations: queue (ranked deduped finding clusters for a project). To regenerate the queue, use CLI: dazzle fitness triage.

**Operations (1):** `queue`

**Parameters:**

- `project_root` *(string)* *(required)* — Path to an example app project
- `top` *(integer)* — Max clusters to return (default 10)
- `project_path` *(string)* — Optional: Absolute path to project directory. If omitted, uses active project.

---

### `graph`

Knowledge graph operations for codebase understanding. Operations: query (search entities by text), dependencies (what does X depend on?), dependents (what depends on X?), neighbourhood (entities within N hops), paths (find paths between entities), stats (graph statistics), populate (refresh graph from source), concept (look up a framework concept by name), inference (find inference patterns matching a query), related (get related concepts for an entity), export (export project KG data to JSON), import (import KG data from JSON), triggers (show what fires when an entity event occurs), topology (derive project structure from DSL: entity relationships, surface/workspace mapping, dead constructs; optionally filter by entity name)

**Operations (14):** `query`, `dependencies`, `dependents`, `neighbourhood`, `paths`, `stats`, `populate`, `concept`, `inference`, `related`, `export`, `import`, `triggers`, `topology`

**Parameters:**

- `text` *(string)* — Search text (for query)
- `entity_id` *(string)* — Entity ID with prefix like file:, module:, class: (for dependencies, dependents, neighbourhood)
- `source_id` *(string)* — Source entity ID (for paths)
- `target_id` *(string)* — Target entity ID (for paths)
- `depth` *(integer)* — Traversal depth (for neighbourhood, default: 1)
- `transitive` *(boolean)* — Include transitive deps (for dependencies, dependents)
- `relation_types` *(array)* — Filter by relation types: imports, contains, inherits, depends_on
- `entity_types` *(array)* — Filter by entity types: file, module, class, function
- `limit` *(integer)* — Max results (default: 20)
- `root_path` *(string)* — Path to populate from (for populate)
- `name` *(string)* — Entity or concept name (for concept, related, triggers)
- `entity` *(string)* — Entity name (for triggers, e.g. 'Ticket')
- `event` *(string)* — Event type (for triggers, default: created)
- `data` *(object)* — JSON export data to import (for import)
- `file_path` *(string)* — Path to JSON file to import (for import, alternative to data)
- `mode` *(string)* — Import mode: merge (additive upsert) or replace (wipe and load). Default: merge

---

### `guide`

Inspect declared onboarding guides. Stateless reads only; writes (mark step complete/dismissed) stay on the HTTP routes. Operations: list (every guide with audience + step count), get (full IR for one guide by name), concordance (run the linker's concordance check in isolation — verifies target / completion / cta refs resolve against the DSL), narrate (linear ordered narrative of one guide's steps — agent-readable equivalent of the rendered overlay sequence).

**Operations (4):** `list`, `get`, `concordance`, `narrate`

**Parameters:**

- `name` *(string)* — Guide name (for 'get' / 'narrate')
- `project_path` *(string)* — Optional: Absolute path to project directory. If omitted, uses active project.

---

### `knowledge`

Knowledge lookup: concept, examples, cli_help, workflow, inference, changelog, counter_prior, get_spec, search_commands. counter_prior surfaces entries from docs/counter-priors/ — corpus pathologies Dazzle inoculates against. Call before emitting non-trivial user-app Python, raw SQL, or shell scripts. Note: Static content also available via MCP Resources.

**Operations (9):** `concept`, `examples`, `cli_help`, `workflow`, `inference`, `changelog`, `counter_prior`, `get_spec`, `search_commands`

**Parameters:**

- `term` *(string)* — Concept/pattern name (for concept)
- `features` *(array)* — Features to search (for examples)
- `complexity` *(string)* — Complexity level (for examples)
- `command` *(string)* — CLI command (for cli_help)
- `workflow` *(string)* — Workflow name (for workflow)
- `query` *(string)* — Search query (for inference or counter_prior text-trigger match)
- `detail` *(string)* — Detail level (for inference)
- `list_all` *(boolean)* — List all triggers (for inference / counter_prior)
- `since` *(string)* — Version filter (for changelog, e.g. '0.48.0')
- `id` *(string)* — Counter-prior id (for counter_prior direct fetch — returns full body)
- `code_shape` *(string)* — Description of code about to be written, or a code fragment — matched against triggers_code regexes with triggers_text fallback (for counter_prior)
- `layer` *(string)* — Substrate layer filter for list_all (for counter_prior)

---

### `llm`

LLM operations: list_intents (declared intents), list_models (declared models), inspect_intent (detailed intent view with resolved model), get_config (module-level LLM configuration).

**Operations (4):** `list_intents`, `list_models`, `inspect_intent`, `get_config`

**Parameters:**

- `name` *(string)* — Intent name (for inspect_intent)
- `project_path` *(string)* — Optional: Absolute path to project directory. If omitted, uses active project.

---

### `mock`

Vendor mock server management: status, request_log. Operates on auto-started mock servers during 'dazzle serve'.

**Operations (2):** `status`, `request_log`

**Parameters:**

- `vendor` *(string)* — API pack name (e.g. 'sumsub_kyc')
- `method` *(string)* — Filter by HTTP method (for request_log)
- `path` *(string)* — Filter by path substring (for request_log)
- `limit` *(integer)* — Max results (for request_log, default: 20)
- `project_path` *(string)* — Optional: Absolute path to project directory. If omitted, uses active project.

---

### `param`

Query runtime parameter declarations. Operations: list (all declared params with defaults), get (specific param by key with type, constraints, scope).

**Operations (2):** `list`, `get`

**Parameters:**

- `key` *(string)* — Parameter key (for 'get' operation)
- `project_path` *(string)* — Optional: Absolute path to project directory. If omitted, uses active project.

---

### `perf`

Local OpenTelemetry trace findings for the current project (read-only). list: enumerate past runs in .dazzle/perf/. report: return heuristic findings (slow endpoints, N+1, etc.) as JSON. show: return the raw span tree for a run.

**Operations (3):** `list`, `report`, `show`

**Parameters:**

- `run` *(string)* — Run id (default: latest).

---

### `pitch`

Pitch deck operations: get. Retrieve the current pitchspec.

**Operations (1):** `get`

**Parameters:**

- `project_path` *(string)* — Optional: Absolute path to project directory. If omitted, uses active project.

---

### `policy`

Policy analysis operations for RBAC access control. Operations: analyze (find entities without access rules), conflicts (detect contradictory permit/forbid rules), coverage (permission matrix: persona x entity x operation), simulate (trace which rules fire for a given persona + entity + operation), access_matrix (full RBAC access matrix from rbac module), verify_status (summary of last `dazzle rbac verify` run)

**Operations (6):** `analyze`, `conflicts`, `coverage`, `simulate`, `access_matrix`, `verify_status`

**Parameters:**

- `entity_names` *(array)* — Filter to specific entity names (optional)
- `persona` *(string)* — Persona ID (required for simulate)
- `operation_kind` *(string)* — CRUD operation to simulate (required for simulate)
- `project_path` *(string)* — Optional: Absolute path to project directory. If omitted, uses active project.

---

### `process`

Process operations: list, inspect, list_runs, get_run, coverage

**Operations (5):** `list`, `inspect`, `list_runs`, `get_run`, `coverage`

**Parameters:**

- `process_name` *(string)* — Process name (for inspect)
- `run_id` *(string)* — Run ID (for get_run)
- `status` *(string)* — Filter by status (for list_runs)
- `status_filter` *(string)* — Filter by coverage status (for coverage, default: all)
- `limit` *(integer)* — Max results (for list_runs, coverage; default: 50)
- `offset` *(integer)* — Skip N results for pagination (for coverage, default: 0)
- `project_path` *(string)* — Optional: Absolute path to project directory. If omitted, uses active project.

---

### `product_quality`

Felt product/demo quality for commercial showcase apps (#1626). Operations: score — aggregates structural product maturity, demo fleet floors, journey maturity, assignment-aware persona-home seed residual (current_user filters vs STABLE_PERSONA_USER_IDS), and empty-hero still byte floors into one residual_total + next force path. Prefer this over running probe scripts alone when judging whether a sales demo is empty-desk theater. CLI: dazzle demo quality.

**Operations (1):** `score`

**Parameters:**

- `project_root` *(string)* — Path to one example app (with dazzle.toml) or to examples/ for the showcase fleet. Defaults to the active MCP project.
- `app` *(string)* — When project_root is examples/, limit persona-home and still scoring to this showcase app name.
- `min_home_hits` *(integer)* — Minimum seed rows matching a current_user region filter (default 1).
- `project_path` *(string)* — Optional: Absolute path to project directory. If omitted, uses active project.

---

### `representation`

Data-representation organisational judgement (#1617): named hatch patterns (rel.explicit_ref, rel.exclusive_fks, rel.poly_ref, rel.tpt_subtype, rel.json_extension, …). Operations: patterns (catalogue), decide (ladder → pattern_id + DSL sketch + reject list), classify (project AppSpec evidence), prove (static integrity gate). Prefer before inventing host poly or dual-lock open-via. Complements agent/story prove (behaviour) with shape prove.

**Operations (4):** `patterns`, `decide`, `classify`, `prove`

**Parameters:**

- `text` *(string)* — Free-text domain pressure for decide
- `signals` *(object)* — Structured decide signals: shared_child_of_many_parents, exclusive_parents, parent_count, true_isa, needs_mixed_kind_list, tenant_variable_fields, four_questions_failed, host_extension, journey_open_via
- `project_path` *(string)* — Optional: Absolute path to project directory. If omitted, uses active project.

---

### `rhythm`

Rhythm operations: get, list, coverage. Rhythms are longitudinal persona journey maps through the app, organized into temporal phases containing scenes (actions on surfaces).

**Operations (3):** `get`, `list`, `coverage`

**Parameters:**

- `name` *(string)* — Rhythm name (for get)
- `project_path` *(string)* — Optional: Absolute path to project directory. If omitted, uses active project.

---

### `semantics`

Semantic analysis: extract, validate_events, tenancy, compliance, analytics, extract_guards

**Operations (6):** `extract`, `validate_events`, `tenancy`, `compliance`, `analytics`, `extract_guards`

**Parameters:**

- `project_path` *(string)* — Optional: Absolute path to project directory. If omitted, uses active project.

---

### `sentinel`

Sentinel operations: findings (get findings from latest/specific scan), status (available agents and last scan), history (list recent scans), fuzz_summary (run a small mutation fuzz campaign and return the markdown report). Deterministic static analysis of the IR — no source code scanning.

**Operations (4):** `findings`, `status`, `history`, `fuzz_summary`

**Parameters:**

- `severity_threshold` *(string)* — Minimum severity to include (for findings). Default: info.
- `agent` *(string)* — Filter findings by agent ID (for findings).
- `severity` *(string)* — Filter findings by severity (for findings).
- `scan_id` *(string)* — Specific scan ID (for findings).
- `limit` *(integer)* — Max scans to return (for history). Default: 10.
- `samples` *(integer)* — Samples per layer for fuzz_summary. Default: 10.
- `project_path` *(string)* — Optional: Absolute path to project directory. If omitted, uses active project.

---

### `sitespec`

SiteSpec operations: get, validate, scaffold, coherence, review, advise. Copy operations: get_copy, scaffold_copy, review_copy. Use 'coherence' to check if the site feels like a real website (navigation, CTAs, content completeness). Use 'review' for page-by-page comparison of spec vs rendering status. Use 'advise' to get proactive layout improvement suggestions. Theme operations: get_theme, scaffold_theme, validate_theme, generate_tokens, generate_imagery_prompts.

**Operations (14):** `get`, `validate`, `scaffold`, `get_copy`, `scaffold_copy`, `review_copy`, `coherence`, `review`, `get_theme`, `scaffold_theme`, `validate_theme`, `generate_tokens`, `generate_imagery_prompts`, `advise`

**Parameters:**

- `use_defaults` *(boolean)* — Use defaults when missing (for get, get_theme)
- `check_content_files` *(boolean)* — Check content files (for validate)
- `product_name` *(string)* — Product name (for scaffold, scaffold_copy)
- `overwrite` *(boolean)* — Overwrite existing (for scaffold, scaffold_copy, scaffold_theme)
- `business_context` *(string)* — Business type hint for coherence check (saas, marketplace, agency, ecommerce)
- `brand_hue` *(number)* — Brand hue 0-360 on OKLCH wheel (for scaffold_theme)
- `brand_chroma` *(number)* — Brand chroma 0-0.4 (for scaffold_theme)
- `project_path` *(string)* — Optional: Absolute path to project directory. If omitted, uses active project.

---

### `spec_analyze`

Analyze narrative specs before DSL generation. Operations: discover_entities (extract nouns/relationships), identify_lifecycles (find state transitions), extract_personas (identify user roles), surface_rules (extract business rules), generate_questions (surface ambiguities), refine_spec (produce structured spec from all analyses)

**Operations (6):** `discover_entities`, `identify_lifecycles`, `extract_personas`, `surface_rules`, `generate_questions`, `refine_spec`

**Parameters:**

- `spec_text` *(string)* — The narrative spec text to analyze
- `entities` *(array)* — Entity names (for identify_lifecycles, generate_questions)
- `answers` *(object)* — Answers to generated questions (for refine_spec)

---

### `status`

Status operations: mcp, logs, active_project, telemetry, activity, demo_world (alias: runtime). demo_world = agent-readable serve ports, test_secret present?, masked DB URL, STABLE persona ids, persona-home seed residual (#1629). activity = real-time MCP tool invocations (cursor polling).

**Operations (7):** `mcp`, `logs`, `active_project`, `telemetry`, `activity`, `demo_world`, `runtime`

**Parameters:**

- `reload` *(boolean)* — Reload modules (for mcp)
- `include_changelog` *(boolean)* — For mcp: include full new_since_last_check CHANGELOG text (default false — compact count only; #1629 G6)
- `count` *(integer)* — Number of entries (for logs, telemetry, activity)
- `level` *(string)* — Filter by level (for logs)
- `errors_only` *(boolean)* — Show only errors (for logs)
- `tool_name` *(string)* — Filter by tool name (for telemetry)
- `since_minutes` *(integer)* — Only show invocations from the last N minutes (for telemetry)
- `stats_only` *(boolean)* — Only return aggregate stats, no individual invocations (for telemetry)
- `cursor_seq` *(integer)* — Sequence number to read after (for activity, 0 = from start)
- `cursor_epoch` *(integer)* — Epoch counter for staleness detection (for activity, 0 = initial)
- `format` *(string)* — Response format (for activity): 'structured' (JSON, default) or 'formatted' (human-readable text)
- `project_path` *(string)* — Optional: Absolute path to project directory. If omitted, uses active project.

---

### `story`

Story operations: get, composition, coverage, scope_fidelity. Use get with view='wall' for a founder-friendly board grouped by implementation status (working/needs polish/not started). composition maps the story⇄rhythm graph — which phase composes a story (and whether it is active), and which stories are declared but composed into no journey. scope_fidelity checks that implementing processes exercise all entities in story scope.

**Operations (4):** `get`, `composition`, `coverage`, `scope_fidelity`

**Parameters:**

- `status_filter` *(string)* — Filter by status (for get)
- `story_ids` *(array)* — Story IDs (for get: fetch full details; for composition: focus on these stories)
- `view` *(string)* — View mode for get operation. 'wall' groups stories by implementation status (working/needs polish/not started)
- `persona` *(string)* — Filter stories by persona/actor name (for get with view=wall)
- `project_path` *(string)* — Optional: Absolute path to project directory. If omitted, uses active project.

---

### `test_design`

Test design operations: get, gaps. Query test designs and identify coverage gaps.

**Operations (2):** `get`, `gaps`

**Parameters:**

- `status_filter` *(string)* — Filter by status (for get)
- `test_ids` *(array)* — Test design IDs to fetch full details (for get)
- `project_path` *(string)* — Optional: Absolute path to project directory. If omitted, uses active project.

---

### `test_intelligence`

Query persisted test result history. Operations: summary (recent runs overview), failures (failure patterns, flaky tests, persistent failures), regression (tests that went pass→fail between last two runs), coverage (success rate trend across recent runs), context (single-call AI-ready snapshot combining all above), journey (most recent E2E journey analysis). Results are automatically persisted by dsl_test run_all.

**Operations (6):** `summary`, `failures`, `regression`, `coverage`, `context`, `journey`

**Parameters:**

- `limit` *(integer)* — Number of recent runs to analyze (default: 10)
- `run_id` *(string)* — Specific run ID to query test cases for
- `failure_type` *(string)* — Filter by failure type (for failures)
- `category` *(string)* — Filter by test category (for failures)
- `project_path` *(string)* — Optional: Absolute path to project directory. If omitted, uses active project.

---

### `user_management`

User management operations: list, create, get, update, reset_password, deactivate, list_sessions, revoke_session, config. Manage auth users and sessions in PostgreSQL.

**Operations (9):** `list`, `create`, `get`, `update`, `reset_password`, `deactivate`, `list_sessions`, `revoke_session`, `config`

**Parameters:**

- `email` *(string)* — User email (for create, get)
- `user_id` *(string)* — User UUID (for get, update, reset_password, deactivate, list_sessions)
- `name` *(string)* — Display name (for create)
- `username` *(string)* — New display name (for update)
- `roles` *(array)* — Role names (for create, update)
- `role` *(string)* — Filter by role (for list)
- `is_superuser` *(boolean)* — Superuser flag (for create, update)
- `is_active` *(boolean)* — Active status (for update)
- `active_only` *(boolean)* — Only active users/sessions (for list, list_sessions; default: true)
- `password` *(string)* — Explicit password (for create, reset_password). If omitted, a random password is generated.
- `session_id` *(string)* — Session ID (for revoke_session)
- `limit` *(integer)* — Max results (for list, list_sessions; default: 50)
- `offset` *(integer)* — Pagination offset (for list; default: 0)
- `project_path` *(string)* — Optional: Absolute path to project directory. If omitted, uses active project.

---

### `user_profile`

User profile for adaptive persona inference. Operations: observe (analyze recent tool invocations), observe_message (analyze user message vocabulary), get (return current profile context), reset (delete and return fresh default).

**Operations (4):** `observe`, `observe_message`, `get`, `reset`

**Parameters:**

- `message_text` *(string)* — User message text (for observe_message)
- `limit` *(integer)* — Max invocations to analyze (for observe; default: 50)
- `since_minutes` *(integer)* — Only analyze invocations from last N minutes (for observe; default: 30)

---
